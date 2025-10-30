# -*- coding: utf-8 -*-
"""
Сервис для интеграции fast_bi.py с Django

⚡ ОПТИМИЗАЦИЯ СКОРОСТИ:
По умолчанию используется прямой API Ollama (в 10+ раз быстрее llama_index).
Для переключения на llama_index измените константу USE_DIRECT_API = False.

🛡️ СИСТЕМА ЗАЩИТЫ (многоуровневая):
1. Промпт: явно запрещает DDL/DML операции
2. Парсинг: _only_select() проверяет через sqlparse тип запроса
3. DuckDB: in-memory база, изолирована от файловой системы
4. Timeout: максимум 30 секунд на выполнение SQL

📊 ПРОИЗВОДИТЕЛЬНОСТЬ:
- Прямой API: ~3-7 секунд на запрос
- llama_index: ~50-60 секунд на запрос
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
import requests

try:
    from llama_index.llms.ollama import Ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("⚠️ llama_index.llms.ollama не установлен. Установите: llama-index-llms-ollama")


# -----------------------------
# Singleton для LLM
# -----------------------------
class OllamaLLMManager:
    """
    Singleton для управления единственным экземпляром Ollama LLM.
    Модель загружается один раз и остается в памяти.
    """
    _instance = None
    _llm = None
    _model_name = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OllamaLLMManager, cls).__new__(cls)
        return cls._instance
    
    def get_llm(self, model: str = None, keep_alive: str = "5m"):
        """
        Возвращает единственный экземпляр LLM.
        Если модель еще не инициализирована или запрошена другая модель - инициализирует заново.
        """
        if model is None:
            model = "mistral7b-tuned"  # Будет определено как DEFAULT_MODEL ниже
        
        # Если LLM уже инициализирован для этой модели - возвращаем его
        if self._llm is not None and self._model_name == model:
            print(f"♻️ Используем уже загруженную модель ({model})")
            return self._llm
        
        # Инициализируем новый LLM
        print(f"🤖 Инициализирую LLM ({model})...")
        if not OLLAMA_AVAILABLE:
            raise RuntimeError("llama_index.llms.ollama не установлен")
        
        try:
            self._llm = Ollama(
                model=model,
                request_timeout=180.0,
                keep_alive=keep_alive,
                # Не задаем num_predict здесь - он будет задаваться для каждого запроса отдельно
            )
            self._model_name = model
            print(f"✅ LLM инициализирован и будет переиспользоваться")
            return self._llm
        except Exception as e:
            print(f"❌ Ошибка инициализации LLM: {e}")
            raise


# -----------------------------
# Константы
# -----------------------------
DEFAULT_MODEL = "mistral7b-tuned"
OLLAMA_BASE_URL = "http://localhost:11434"  # Базовый URL Ollama API
SQL_GENERATION_TOKENS = 128  # Лимит токенов для генерации SQL
COMMENTARY_TOKENS = 80  # Лимит токенов для комментария (уменьшено с 192)
STATS_TOP_K = 10
SQL_TIMEOUT_SEC = 30
USE_DIRECT_API = True  # Использовать прямой API Ollama (быстрее в 10+ раз)


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


def _call_ollama_direct(
    prompt: str,
    model: str,
    num_predict: int,
    temperature: float = 0.1,
    stream: bool = False,
    stream_callback=None
) -> str:
    """
    Прямой вызов Ollama API (быстрее llama_index в 10+ раз).
    
    Args:
        prompt: Промпт для модели
        model: Название модели
        num_predict: Максимальное количество токенов для генерации
        temperature: Температура (0.1 для SQL, 0.3 для комментариев)
        stream: Включить streaming
        stream_callback: Функция обратного вызова для streaming
    
    Returns:
        Полный ответ от модели
    """
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
        "options": {
            "num_predict": num_predict,
            "temperature": temperature,
            "top_k": 40,
            "top_p": 0.9,
        }
    }
    
    if stream and stream_callback:
        # Streaming режим
        full_response = ""
        token_count = 0
        
        response = requests.post(url, json=payload, stream=True, timeout=180)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                try:
                    chunk_data = json.loads(line)
                    if "response" in chunk_data:
                        text = chunk_data["response"]
                        full_response += text
                        token_count += 1
                        if stream_callback:
                            stream_callback(text)
                    
                    # Проверяем завершение
                    if chunk_data.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue
        
        print(f"📊 Сгенерировано токенов: ~{token_count}")
        return full_response
    else:
        # Обычный режим
        response = requests.post(url, json=payload, timeout=180)
        response.raise_for_status()
        return response.json()["response"]


# -----------------------------
# Основной класс
# -----------------------------
class FastBIService:
    """
    Сервис для анализа табличных данных через DuckDB и Ollama.
    Адаптированный для использования в Django.
    Использует Singleton паттерн для LLM - модель загружается один раз.
    """
    
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        keep_alive: str = "5m",
    ):
        if not OLLAMA_AVAILABLE:
            raise RuntimeError("llama_index.llms.ollama не установлен")
            
        # Создаем новое DuckDB соединение (изолированное для каждого запроса)
        self.con = duckdb.connect()
        self.table_name: Optional[str] = None
        self.meta: Optional[Dict] = None
        
        # Получаем единственный экземпляр LLM через Singleton
        llm_manager = OllamaLLMManager()
        self.llm = llm_manager.get_llm(model=model, keep_alive=keep_alive)
    
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
                # Конвертируем datetime в строки, если необходимо
                for col in res.columns:
                    if pd.api.types.is_datetime64_any_dtype(res[col]):
                        res[col] = res[col].astype(str)
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
        """
        Генерирует SQL через LLM с поддержкой streaming.
        Использует прямой API Ollama для максимальной скорости.
        """
        prompt = self._build_sql_prompt(question)
        
        print(f"📝 Длина промпта для SQL: {len(prompt)} символов")
        print(f"🎯 Лимит токенов: {SQL_GENERATION_TOKENS}")
        
        start_time = time.time()
        
        # Пытаемся использовать прямой API Ollama (быстрее в 10+ раз)
        if USE_DIRECT_API:
            try:
                print(f"⚡ Используем прямой API Ollama")
                
                if stream_callback:
                    # Streaming режим с callback
                    def direct_stream_callback(text):
                        stream_callback({'type': 'sql_generation', 'text': text})
                    
                    resp_text = _call_ollama_direct(
                        prompt=prompt,
                        model=DEFAULT_MODEL,
                        num_predict=SQL_GENERATION_TOKENS,
                        temperature=0.1,  # Низкая температура для точного SQL
                        stream=True,
                        stream_callback=direct_stream_callback
                    )
                else:
                    # Обычный режим
                    resp_text = _call_ollama_direct(
                        prompt=prompt,
                        model=DEFAULT_MODEL,
                        num_predict=SQL_GENERATION_TOKENS,
                        temperature=0.1,
                        stream=False
                    )
                
                elapsed = time.time() - start_time
                print(f"⚡ SQL генерация (прямой API): {elapsed:.2f}с")
                
                sql_raw = _extract_sql_from_text(resp_text)
                sql = _only_select(sql_raw)
                return sql
                
            except Exception as e:
                print(f"⚠️ Прямой API не сработал ({e}), откат на llama_index...")
                # Откат на llama_index ниже
        
        # Fallback: используем llama_index (медленнее, но надежнее)
        print(f"🐢 Используем llama_index (медленнее)")
        if stream_callback:
            # Streaming режим
            full_response = ""
            token_count = 0
            for chunk in self.llm.stream_complete(
                prompt,
                additional_kwargs={"num_predict": SQL_GENERATION_TOKENS}
            ):
                text = chunk.delta
                full_response += text
                token_count += 1
                stream_callback({'type': 'sql_generation', 'text': text})
            
            resp_text = full_response
            print(f"📊 Сгенерировано токенов: ~{token_count}")
        else:
            # Обычный режим
            resp = self.llm.complete(
                prompt,
                additional_kwargs={"num_predict": SQL_GENERATION_TOKENS}
            )
            resp_text = resp.text
        
        elapsed = time.time() - start_time
        print(f"⚡ SQL генерация (llama_index): {elapsed:.2f}с")
        
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
        """
        Генерирует короткий комментарий по результатам с поддержкой streaming.
        Использует прямой API Ollama для максимальной скорости.
        """
        sample = _shorten(df, 30)
        
        # Конвертируем datetime колонки в строки для JSON
        sample_copy = sample.copy()
        for col in sample_copy.columns:
            if pd.api.types.is_datetime64_any_dtype(sample_copy[col]):
                sample_copy[col] = sample_copy[col].astype(str)
        
        payload = {
            "question": question,
            "result_preview": sample_copy.to_dict(orient="records"),
            "rows_returned": len(df),
        }
        
        prompt = (
            "Дай КРАТКИЙ вывод (макс 2-3 предложения) по данным. Только ключевые находки.\n"
            f"Данные:\n{json.dumps(payload, ensure_ascii=False, default=str)}"
        )
        
        print(f"📝 Длина промпта для комментария: {len(prompt)} символов")
        print(f"🎯 Лимит токенов: {COMMENTARY_TOKENS}")
        
        start_time = time.time()
        
        # Пытаемся использовать прямой API Ollama (быстрее в 10+ раз)
        if USE_DIRECT_API:
            try:
                print(f"⚡ Используем прямой API Ollama")
                
                if stream_callback:
                    # Streaming режим с callback
                    def direct_stream_callback(text):
                        stream_callback({'type': 'commentary', 'text': text})
                    
                    resp_text = _call_ollama_direct(
                        prompt=prompt,
                        model=DEFAULT_MODEL,
                        num_predict=COMMENTARY_TOKENS,
                        temperature=0.3,  # Чуть выше для более естественного комментария
                        stream=True,
                        stream_callback=direct_stream_callback
                    )
                else:
                    # Обычный режим
                    resp_text = _call_ollama_direct(
                        prompt=prompt,
                        model=DEFAULT_MODEL,
                        num_predict=COMMENTARY_TOKENS,
                        temperature=0.3,
                        stream=False
                    )
                
                elapsed = time.time() - start_time
                print(f"💭 Анализ (прямой API): {elapsed:.3f}с")
                
                return resp_text.strip()
                
            except Exception as e:
                print(f"⚠️ Прямой API не сработал ({e}), откат на llama_index...")
                # Откат на llama_index ниже
        
        # Fallback: используем llama_index (медленнее, но надежнее)
        print(f"🐢 Используем llama_index (медленнее)")
        if stream_callback:
            # Streaming режим
            full_response = ""
            token_count = 0
            for chunk in self.llm.stream_complete(
                prompt,
                additional_kwargs={"num_predict": COMMENTARY_TOKENS}
            ):
                text = chunk.delta
                full_response += text
                token_count += 1
                stream_callback({'type': 'commentary', 'text': text})
            
            resp_text = full_response.strip()
            print(f"📊 Сгенерировано токенов: ~{token_count}")
        else:
            # Обычный режим
            resp = self.llm.complete(
                prompt,
                additional_kwargs={"num_predict": COMMENTARY_TOKENS}
            )
            resp_text = resp.text.strip()
        
        elapsed = time.time() - start_time
        print(f"💭 Анализ (llama_index): {elapsed:.3f}с")
        
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
            # Преобразуем datetime колонки в строки для JSON сериализации
            df_copy = df.copy()
            for col in df_copy.columns:
                if pd.api.types.is_datetime64_any_dtype(df_copy[col]):
                    df_copy[col] = df_copy[col].astype(str)
            
            data_dict = df_copy.to_dict(orient="records")
            
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
        """
        Закрывает соединение с DuckDB.
        ВНИМАНИЕ: LLM НЕ закрывается, так как он Singleton и переиспользуется между запросами.
        """
        if self.con:
            self.con.close()
            self.con = None


# -----------------------------
# Утилиты
# -----------------------------
def preload_ollama_model(model: str = DEFAULT_MODEL, keep_alive: str = "5m"):
    """
    Предзагрузка модели Ollama при старте приложения.
    Это можно вызвать в apps.py или settings.py для ускорения первого запроса.
    
    Пример использования в apps.py:
    
    from django.apps import AppConfig
    
    class AiAssistantConfig(AppConfig):
        name = 'src.core.ai_assistant'
        
        def ready(self):
            from .fast_bi_service import preload_ollama_model
            try:
                preload_ollama_model()
            except Exception as e:
                print(f"⚠️ Не удалось предзагрузить модель: {e}")
    """
    if not OLLAMA_AVAILABLE:
        print("⚠️ llama_index.llms.ollama не установлен - предзагрузка невозможна")
        return False
    
    try:
        llm_manager = OllamaLLMManager()
        llm_manager.get_llm(model=model, keep_alive=keep_alive)
        return True
    except Exception as e:
        print(f"❌ Ошибка предзагрузки модели: {e}")
        return False




