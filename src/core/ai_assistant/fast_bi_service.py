# -*- coding: utf-8 -*-
"""
Сервис для интеграции fast_bi.py с Django
"""
import os
import re
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from django.conf import settings

import duckdb
import pandas as pd
import sqlparse

try:
    from llama_index.llms.ollama import Ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("⚠️ llama_index.llms.ollama не установлен. Установите: pip install llama-index-llms-ollama")


# -----------------------------
# Константы
# -----------------------------
DEFAULT_MODEL = "mistral7b-tuned"
MAX_OUTPUT_TOKENS = 256
STATS_TOP_K = 10
COMMENTARY_TOKENS = 192
SQL_TIMEOUT_SEC = 30


# -----------------------------
# Хелперы
# -----------------------------
def _only_select(sql: str) -> str:
    """Оставляем только первый SELECT; режем всё после ; и запрещаем DML/DDL."""
    sql_single = sql.split(";")[0].strip()
    parsed_list = sqlparse.parse(sql_single)
    if not parsed_list:
        raise ValueError("Пустой SQL.")
    parsed = parsed_list[0]
    if parsed.get_type().upper() != "SELECT":
        raise ValueError("Только SELECT-запросы разрешены.")
    return sql_single


def _extract_sql_from_text(text: str) -> str:
    """Пытаемся вытащить SQL из ответа LLM."""
    m = re.search(r"```sql\s*(.*?)```", text, flags=re.S | re.I)
    if m:
        return m.group(1).strip()
    idx = text.lower().find("select")
    if idx >= 0:
        return text[idx:].strip()
    return text.strip()


def _shorten(df: pd.DataFrame, max_rows: int = 50) -> pd.DataFrame:
    """Обрезаем DataFrame для предпросмотра."""
    return df.head(max_rows).copy()


# -----------------------------
# Основной класс
# -----------------------------
class FastBIService:
    """
    Сервис для анализа табличных данных через DuckDB и Ollama.
    Адаптированный для использования в Django.
    """
    
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        keep_alive: str = "5m",
        num_predict: int = MAX_OUTPUT_TOKENS,
    ):
        if not OLLAMA_AVAILABLE:
            raise RuntimeError("llama_index.llms.ollama не установлен")
            
        self.con = duckdb.connect()
        self.table_name: Optional[str] = None
        self.meta: Optional[Dict] = None
        
        # Инициализация LLM
        print(f"🤖 Инициализирую LLM ({model})...")
        try:
            self.llm = Ollama(
                model=model,
                request_timeout=180.0,
                keep_alive=keep_alive,
                additional_kwargs={"num_predict": num_predict},
            )
            print(f"✅ LLM инициализирован")
        except Exception as e:
            print(f"❌ Ошибка инициализации LLM: {e}")
            raise
    
    def load_file(self, file_path: str, table_name: str = "t") -> Dict[str, Any]:
        """
        Загружает файл в DuckDB.
        
        Args:
            file_path: Путь к файлу (CSV, XLSX, XLS)
            table_name: Имя таблицы в DuckDB
            
        Returns:
            Метаданные о загруженном файле
        """
        path = Path(file_path)
        self.table_name = table_name
        
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        
        try:
            if path.suffix.lower() in [".csv", ".tsv"]:
                # Быстрая загрузка CSV через DuckDB
                self.con.execute(f"""
                    CREATE OR REPLACE TABLE {table_name} AS
                    SELECT * FROM read_csv_auto('{path.as_posix()}', IGNORE_ERRORS=true);
                """)
            elif path.suffix.lower() in [".xlsx", ".xls"]:
                # Загрузка Excel через pandas
                df = pd.read_excel(path)
                self.con.register("tmp_df", df)
                self.con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM tmp_df;")
                self.con.unregister("tmp_df")
            else:
                raise ValueError(f"Неподдерживаемый формат файла: {path.suffix}")
            
            self._prepare_metadata()
            
            return {
                "success": True,
                "table_name": self.table_name,
                "rows": self.meta["rows"],
                "columns": len(self.meta["schema"]),
            }
            
        except Exception as e:
            raise RuntimeError(f"Ошибка загрузки файла: {e}")
    
    def _prepare_metadata(self) -> None:
        """Подготавливает метаданные о загруженной таблице."""
        assert self.table_name
        
        schema_df = self.con.execute(
            f"PRAGMA table_info({self.table_name})"
        ).fetchdf()
        
        n_rows = self.con.execute(
            f"SELECT COUNT(*) AS n FROM {self.table_name}"
        ).fetchone()[0]
        
        cols = schema_df["name"].tolist()
        numeric_cols, categorical_cols = [], []
        
        for _, row in schema_df.iterrows():
            col = row["name"]
            dtype = row["type"].lower()
            if any(x in dtype for x in ["int", "decimal", "double", "float"]):
                numeric_cols.append(col)
            else:
                categorical_cols.append(col)
        
        # Сводка по числовым колонкам
        num_summary = {}
        for c in numeric_cols:
            try:
                res = self.con.execute(
                    f"SELECT MIN({c}) AS min, MAX({c}) AS max, AVG({c}) AS avg FROM {self.table_name}"
                ).fetchone()
                num_summary[c] = {"min": res[0], "max": res[1], "avg": res[2]}
            except:
                num_summary[c] = {"min": None, "max": None, "avg": None}
        
        # Сводка по категориальным колонкам
        cat_summary = {}
        for c in categorical_cols:
            try:
                res = self.con.execute(
                    f"""
                    SELECT {c} AS value, COUNT(*) AS cnt
                    FROM {self.table_name}
                    GROUP BY 1
                    ORDER BY cnt DESC
                    LIMIT {STATS_TOP_K}
                    """
                ).fetchdf()
                cat_summary[c] = res.to_dict(orient="records")
            except:
                cat_summary[c] = []
        
        self.meta = {
            "table": self.table_name,
            "rows": int(n_rows),
            "schema": schema_df.to_dict(orient="records"),
            "numeric_summary": num_summary,
            "categorical_top": cat_summary,
        }
    
    def _build_sql_prompt(self, question: str) -> str:
        """Строит промпт для генерации SQL."""
        meta_min = {
            "table": self.meta["table"],
            "rows": self.meta["rows"],
            "columns": [
                {"name": c["name"], "type": c["type"]} for c in self.meta["schema"]
            ],
            "numeric_cols": list(self.meta["numeric_summary"].keys()),
            "categorical_cols": list(self.meta["categorical_top"].keys()),
        }
        
        df_schema = self.con.execute(f"SELECT * FROM {self.table_name} LIMIT 0").fetchdf()
        schema = ", ".join([f'{c}:{str(t)}' for c, t in zip(df_schema.columns, df_schema.dtypes)])
        extra = f"-- schema: {schema}\n-- table: {self.table_name}\n"
        
        prompt = extra + (
            f"Ты data-engineer. Напиши ОДИН DuckDB SQL-запрос (только SELECT) по таблице '{self.table_name}'. "
            "Учитывай типы столбцов. НЕЛЬЗЯ делать DDL/DML. НЕЛЬЗЯ читать внешние файлы. "
            f"СХЕМА И СВОДКИ (JSON):\n{json.dumps(meta_min, ensure_ascii=False)}\n\n"
            f"ВОПРОС ПОЛЬЗОВАТЕЛЯ:\n{question}\n\n"
            f"Верни ТОЛЬКО SQL, без пояснений. Обязательно используй только таблицу {self.table_name}."
        )
        return prompt
    
    def _gen_sql_via_llm(self, question: str, stream_callback=None) -> str:
        """Генерирует SQL через LLM с поддержкой streaming."""
        prompt = self._build_sql_prompt(question)
        
        start_time = time.time()
        
        if stream_callback:
            # Streaming режим
            full_response = ""
            for chunk in self.llm.stream_complete(prompt):
                text = chunk.delta
                full_response += text
                stream_callback({'type': 'sql_generation', 'text': text})
            
            resp_text = full_response
        else:
            # Обычный режим
            resp = self.llm.complete(prompt)
            resp_text = resp.text
        
        elapsed = time.time() - start_time
        print(f"⚡ SQL генерация: {elapsed:.2f}с")
        
        sql_raw = _extract_sql_from_text(resp_text)
        sql = _only_select(sql_raw)
        return sql
    
    def _run_sql(self, sql: str) -> pd.DataFrame:
        """Выполняет SQL запрос."""
        t0 = time.time()
        try:
            df = self.con.execute(sql).fetchdf()
        except Exception as e:
            raise RuntimeError(f"Ошибка выполнения SQL: {e}\nSQL:\n{sql}") from e
        
        elapsed = time.time() - t0
        if elapsed > SQL_TIMEOUT_SEC:
            raise TimeoutError(f"SQL выполнялся слишком долго: {elapsed:.1f}s")
        
        print(f"🗄️ SQL выполнение: {elapsed:.3f}с")
        return df
    
    def _commentary(self, question: str, df: pd.DataFrame, stream_callback=None) -> str:
        """Генерирует короткий комментарий по результатам с поддержкой streaming."""
        sample = _shorten(df, 30)
        payload = {
            "question": question,
            "result_preview": sample.to_dict(orient="records"),
            "rows_returned": len(df),
        }
        
        prompt = (
            "Ты аналитик BI. Дай КОРОТКИЙ вывод по результату (2-4 предложения): тренды, аномалии, рекомендации. "
            "Не повторяй таблицу. Учти, что это лишь превью.\n"
            f"ДАНО (JSON):\n{json.dumps(payload, ensure_ascii=False, default=str)}"
        )
        
        start_time = time.time()
        
        if stream_callback:
            # Streaming режим
            full_response = ""
            for chunk in self.llm.stream_complete(
                prompt,
                additional_kwargs={"num_predict": COMMENTARY_TOKENS}
            ):
                text = chunk.delta
                full_response += text
                stream_callback({'type': 'commentary', 'text': text})
            
            resp_text = full_response.strip()
        else:
            # Обычный режим
            resp = self.llm.complete(
                prompt,
                additional_kwargs={"num_predict": COMMENTARY_TOKENS}
            )
            resp_text = resp.text.strip()
        
        elapsed = time.time() - start_time
        print(f"💭 Анализ: {elapsed:.3f}с")
        
        return resp_text
    
    def ask(self, question: str, want_commentary: bool = True, stream_callback=None) -> Dict[str, Any]:
        """
        Основной метод: задать вопрос к данным.
        
        Args:
            question: Вопрос на естественном языке
            want_commentary: Нужен ли комментарий от LLM
            stream_callback: Функция для обработки streaming данных
            
        Returns:
            Словарь с результатами: sql, data (DataFrame as dict), comment
        """
        if not self.table_name or not self.meta:
            raise RuntimeError("Сначала загрузите файл через load_file()")
        
        total_start = time.time()
        
        try:
            # 1. Генерация SQL с streaming
            if stream_callback:
                stream_callback({'type': 'stage', 'text': '🔄 Генерирую SQL запрос...'})
            
            sql = self._gen_sql_via_llm(question, stream_callback)
            
            if stream_callback:
                stream_callback({'type': 'sql', 'text': sql})
                stream_callback({'type': 'stage', 'text': '⚡ Выполняю запрос к базе данных...'})
            
            # 2. Выполнение SQL
            df = self._run_sql(sql)
            
            if stream_callback:
                stream_callback({'type': 'stage', 'text': f'✅ Найдено строк: {len(df)}'})
            
            # 3. Комментарий (опционально) с streaming
            comment = ""
            if want_commentary and len(df) > 0:
                if stream_callback:
                    stream_callback({'type': 'stage', 'text': '💭 Анализирую результаты...'})
                
                comment = self._commentary(question, df, stream_callback)
            
            total_time = time.time() - total_start
            print(f"⏱️ Общее время: {total_time:.2f}с")
            
            # Конвертируем DataFrame в JSON-сериализуемый формат
            data_dict = df.to_dict(orient="records")
            
            return {
                "success": True,
                "sql": sql,
                "data": data_dict,
                "comment": comment,
                "rows": len(df),
                "columns": list(df.columns) if len(df) > 0 else [],
            }
            
        except Exception as e:
            if stream_callback:
                stream_callback({'type': 'error', 'text': str(e)})
            
            return {
                "success": False,
                "error": str(e),
                "sql": None,
                "data": [],
                "comment": "",
                "rows": 0,
                "columns": [],
            }
    
    def close(self):
        """Закрывает соединение с DuckDB."""
        if self.con:
            self.con.close()
            self.con = None




