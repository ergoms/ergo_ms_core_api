# -*- coding: utf-8 -*-
"""
Сервис анализа табличных данных через DuckDB и ускоренные LLM.

🔥 Возможности:
- Быстрый HTTP клиент Ollama с пулами соединений и поддержкой GPU/CPU
- Возможность переопределять модель и параметры через module-config

🛡️ Безопасность:
1. Промпт явно запрещает DDL/DML
2. `_only_select` проверяет тип запроса через sqlparse
3. DuckDB работает в памяти и не имеет доступа к файловой системе
4. Ограничение времени выполнения SQL
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

import duckdb
import pandas as pd
import sqlparse
from django.conf import settings

from .config import RuntimeLLMConfig, build_runtime_config
from .llm_clients import LLMClientError, build_llm_client

# -----------------------------
# Константы (из настроек Django)
# -----------------------------
DEFAULT_MODEL = getattr(settings, "OLLAMA_DEFAULT_MODEL", "mistral:7b")
OLLAMA_BASE_URL = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
STATS_TOP_K = 10
SQL_TIMEOUT_SEC = 30


# -----------------------------
# Хелперы
# -----------------------------
def _normalize_sql_for_duckdb(sql: str) -> str:
    """
    Нормализует SQL для DuckDB:
    - Заменяет обратные кавычки (`) на двойные кавычки (") для идентификаторов
    - DuckDB использует двойные кавычки для идентификаторов с пробелами или специальными символами
    """
    # Заменяем обратные кавычки на двойные для идентификаторов
    # Используем регулярное выражение для замены `identifier` на "identifier"
    import re
    # Паттерн для обратных кавычек вокруг идентификаторов
    # Заменяем `name` на "name", но не трогаем строки в одинарных кавычках
    def replace_backticks(match):
        identifier = match.group(1)
        return f'"{identifier}"'
    
    # Заменяем обратные кавычки на двойные
    normalized = re.sub(r'`([^`]+)`', replace_backticks, sql)
    return normalized


def _only_select(sql: str) -> str:
    """Оставляем только первый SELECT; режем всё после ; и запрещаем DML/DDL."""
    sql_single = sql.split(";")[0].strip()
    parsed_list = sqlparse.parse(sql_single)
    if not parsed_list:
        raise ValueError("Пустой SQL.")
    parsed = parsed_list[0]
    if parsed.get_type().upper() != "SELECT":
        raise ValueError("Только SELECT-запросы разрешены.")
    # Нормализуем SQL для DuckDB перед возвратом
    return _normalize_sql_for_duckdb(sql_single)


def _extract_sql_from_text(text: str) -> str:
    """Пытаемся вытащить SQL из ответа LLM."""
    match = re.search(r"```sql\s*(.*?)```", text, flags=re.S | re.I)
    if match:
        return match.group(1).strip()
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
    Сервис для анализа табличных данных через DuckDB и LLM.
    Адаптирован для использования в Django и поддерживает streaming выдачу.
    """

    def __init__(
        self,
        model: str = None,
        keep_alive: str = "5m",
        ollama_config: Dict[str, Any] = None,
    ):
        """
        Args:
            model: Название модели LLM (переопределяет конфиг)
            keep_alive: TTL модели в памяти (используется Ollama)
            ollama_config: Переопределения из module-config / frontend
        """
        overrides = dict(ollama_config or {})
        if model:
            overrides["model"] = model
        if keep_alive:
            overrides["keep_alive"] = keep_alive

        self._config: RuntimeLLMConfig = build_runtime_config(overrides)
        self.model = self._config.model
        self.keep_alive = self._config.keep_alive
        self.base_url = self._config.provider_config.get("base_url", self._config.base_url or OLLAMA_BASE_URL)
        self.sql_generation_tokens = self._config.sql_tokens
        self.commentary_tokens = self._config.commentary_tokens
        self.temperature_sql = self._config.temperature_sql
        self.temperature_commentary = self._config.temperature_commentary

        provider_name = self._config.provider.value if hasattr(self._config.provider, "value") else str(self._config.provider)

        self.llm_client = build_llm_client(
            provider=provider_name,
            model=self.model,
            base_url=self.base_url,
            request_timeout=self._config.request_timeout,
            stream_timeout=self._config.stream_timeout,
            concurrency_limit=self._config.concurrency_limit,
            max_retries=self._config.max_retries,
            keep_alive=self.keep_alive,
            provider_config=self._config.provider_config,
            device_config=self._config.device_config,
        )

        # Создаем новое DuckDB соединение (изолированное для каждого запроса)
        self.con = duckdb.connect()
        self.table_name: Optional[str] = None
        self.meta: Optional[Dict[str, Any]] = None

    def load_file(self, file_path: str, table_name: str = "t") -> Dict[str, Any]:
        """
        Загружает файл в DuckDB.

        Args:
            file_path: Путь к файлу (CSV, XLSX, XLS, BIN)
            table_name: Имя таблицы в DuckDB

        Returns:
            Метаданные о загруженном файле
        """
        path = Path(file_path)
        self.table_name = table_name

        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        try:
            # Проверяем, является ли файл бинарным (.bin)
            from src.core.bi_analysis.bi_datasets.binary_storage import is_binary_file, read_from_binary
            
            if is_binary_file(str(path)) or path.suffix.lower() == ".bin":
                # Читаем из бинарного файла через Polars IPC
                columns, rows = read_from_binary(str(path), row_limit=None)
                
                # Конвертируем в pandas DataFrame для загрузки в DuckDB
                if not rows:
                    raise ValueError("Бинарный файл не содержит данных")
                
                # Создаем DataFrame из списка строк
                df = pd.DataFrame(rows, columns=columns)
                
                # Регистрируем DataFrame в DuckDB
                self.con.register("tmp_df", df)
                self.con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM tmp_df;")
                self.con.unregister("tmp_df")
                
            elif path.suffix.lower() in [".csv", ".tsv"]:
                self.con.execute(
                    f"""
                    CREATE OR REPLACE TABLE {table_name} AS
                    SELECT * FROM read_csv_auto('{path.as_posix()}', IGNORE_ERRORS=true);
                    """
                )
            elif path.suffix.lower() in [".xlsx", ".xls"]:
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

        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Ошибка загрузки файла: {exc}") from exc

    def _prepare_metadata(self) -> None:
        """Подготавливает метаданные о загруженной таблице."""
        assert self.table_name

        schema_df = self.con.execute(f"PRAGMA table_info({self.table_name})").fetchdf()

        n_rows = self.con.execute(f"SELECT COUNT(*) AS n FROM {self.table_name}").fetchone()[0]

        numeric_cols, categorical_cols = [], []
        for _, row in schema_df.iterrows():
            col = row["name"]
            dtype = row["type"].lower()
            if any(x in dtype for x in ["int", "decimal", "double", "float"]):
                numeric_cols.append(col)
            else:
                categorical_cols.append(col)

        num_summary: Dict[str, Dict[str, Any]] = {}
        for column in numeric_cols:
            try:
                res = self.con.execute(
                    f"SELECT MIN({column}) AS min, MAX({column}) AS max, AVG({column}) AS avg FROM {self.table_name}"
                ).fetchone()
                num_summary[column] = {"min": res[0], "max": res[1], "avg": res[2]}
            except Exception:  # noqa: BLE001
                num_summary[column] = {"min": None, "max": None, "avg": None}

        cat_summary: Dict[str, Any] = {}
        for column in categorical_cols:
            try:
                res = self.con.execute(
                    f"""
                    SELECT {column} AS value, COUNT(*) AS cnt
                    FROM {self.table_name}
                    GROUP BY 1
                    ORDER BY cnt DESC
                    LIMIT {STATS_TOP_K}
                    """
                ).fetchdf()
                for col in res.columns:
                    if pd.api.types.is_datetime64_any_dtype(res[col]):
                        res[col] = res[col].astype(str)
                cat_summary[column] = res.to_dict(orient="records")
            except Exception:  # noqa: BLE001
                cat_summary[column] = []

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
                {"name": column["name"], "type": column["type"]}
                for column in self.meta["schema"]
            ],
            "numeric_cols": list(self.meta["numeric_summary"].keys()),
            "categorical_cols": list(self.meta["categorical_top"].keys()),
        }

        df_schema = self.con.execute(f"SELECT * FROM {self.table_name} LIMIT 0").fetchdf()
        schema = ", ".join([f"{col}:{dtype}" for col, dtype in zip(df_schema.columns, df_schema.dtypes)])
        extra = f"-- schema: {schema}\n-- table: {self.table_name}\n"

        prompt = extra + (
            f"Ты data-engineer. Напиши ОДИН ПРОСТОЙ DuckDB SQL-запрос (только SELECT) по таблице '{self.table_name}'. "
            "Учитывай типы столбцов. НЕЛЬЗЯ делать DDL/DML. НЕЛЬЗЯ читать внешние файлы. "
            "\n"
            "ВАЖНЫЕ ПРАВИЛА ДЛЯ SQL:\n"
            "1. НЕ используй оконные функции (RANK, DENSE_RANK, ROW_NUMBER, PERCENTILE_CONT, etc.)\n"
            "2. НЕ используй FILTER в COUNT или других агрегатных функциях\n"
            "3. НЕ используй агрегатные функции в GROUP BY\n"
            "4. НЕ используй сложные подзапросы с агрегациями\n"
            "5. Используй только базовые агрегатные функции: AVG(), MIN(), MAX(), COUNT(), SUM()\n"
            "6. Если нужна статистика — сделай простой SELECT с агрегациями БЕЗ GROUP BY или с GROUP BY по одной колонке\n"
            "7. Для просмотра данных используй SELECT * или перечисление колонок\n"
            "8. Сложный вопрос? Сделай SELECT всех данных, анализ будет в комментарии\n"
            "9. НЕ добавляй LIMIT если в вопросе не просят ограничить количество строк\n"
            "10. Если просят показать ВСЕ данные — не используй LIMIT\n"
            "11. ВАЖНО: Для идентификаторов (имен колонок и таблиц) используй ДВОЙНЫЕ КАВЫЧКИ (\"), а НЕ обратные кавычки (`)\n"
            "12. Если имя колонки содержит пробелы или специальные символы, обязательно используй двойные кавычки: \"Имя Колонки\"\n"
            "\n"
            f"СХЕМА И СВОДКИ (JSON):\n{json.dumps(meta_min, ensure_ascii=False)}\n\n"
            f"ВОПРОС ПОЛЬЗОВАТЕЛЯ:\n{question}\n\n"
            f"Верни ТОЛЬКО SQL, без пояснений. Используй только таблицу {self.table_name}. "
            "Помни: ПРОСТОЙ SQL запрос, без сложных конструкций! "
            "Если нужно показать все данные — НЕ используй LIMIT!"
        )
        return prompt

    def _gen_sql_via_llm(self, question: str, stream_callback=None) -> str:
        """Генерирует SQL через LLM с поддержкой streaming."""
        prompt = self._build_sql_prompt(question)
        stream = bool(stream_callback)

        def on_chunk(text: str) -> None:
            if stream_callback:
                stream_callback({"type": "sql_generation", "text": text})

        try:
            resp_text = self.llm_client.complete(
                prompt,
                num_predict=self.sql_generation_tokens,
                temperature=self.temperature_sql,
                stream=stream,
                stream_callback=on_chunk if stream else None,
            )
        except LLMClientError as exc:
            raise RuntimeError(f"Ошибка генерации SQL: {exc}") from exc

        sql_raw = _extract_sql_from_text(resp_text)
        sql = _only_select(sql_raw)
        return sql

    def _run_sql(self, sql: str) -> pd.DataFrame:
        """Выполняет SQL запрос."""
        t0 = time.time()
        try:
            df = self.con.execute(sql).fetchdf()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Ошибка выполнения SQL: {exc}\nSQL:\n{sql}") from exc

        elapsed = time.time() - t0
        if elapsed > SQL_TIMEOUT_SEC:
            raise TimeoutError(f"SQL выполнялся слишком долго: {elapsed:.1f}s")

        return df

    def _commentary(self, question: str, df: pd.DataFrame, stream_callback=None) -> str:
        """Генерирует короткий комментарий по результатам с поддержкой streaming."""
        sample = _shorten(df, 30)

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
            "Дай КРАТКИЙ вывод (максимум 2-3 предложения) по данным. Только ключевые находки.\n"
            f"Данные:\n{json.dumps(payload, ensure_ascii=False, default=str)}"
        )

        stream = bool(stream_callback)

        def on_chunk(text: str) -> None:
            if stream_callback:
                stream_callback({"type": "commentary", "text": text})

        try:
            resp_text = self.llm_client.complete(
                prompt,
                num_predict=self.commentary_tokens,
                temperature=self.temperature_commentary,
                stream=stream,
                stream_callback=on_chunk if stream else None,
            )
        except LLMClientError as exc:
            raise RuntimeError(f"Ошибка генерации комментария: {exc}") from exc

        return resp_text.strip()

    def ask(self, question: str, want_commentary: bool = True, stream_callback=None) -> Dict[str, Any]:
        """
        Основной метод: задать вопрос к данным.

        Args:
            question: Вопрос на естественном языке
            want_commentary: Нужен ли комментарий от LLM
            stream_callback: Функция обработки streaming-данных
        """
        if not self.table_name or not self.meta:
            raise RuntimeError("Сначала загрузите файл через load_file()")

        total_start = time.time()

        try:
            if stream_callback:
                stream_callback({"type": "stage", "text": "🔄 Генерирую SQL запрос..."})

            sql = self._gen_sql_via_llm(question, stream_callback)

            if stream_callback:
                stream_callback({"type": "sql", "text": sql})
                stream_callback({"type": "stage", "text": "⚡ Выполняю запрос к базе данных..."})

            df = self._run_sql(sql)

            if stream_callback:
                stream_callback({"type": "stage", "text": f"✅ Найдено строк: {len(df)}"})

            comment = ""
            if want_commentary and len(df) > 0:
                if stream_callback:
                    stream_callback({"type": "stage", "text": "💭 Анализирую результаты..."})
                comment = self._commentary(question, df, stream_callback)

            df_copy = df.copy()
            for col in df_copy.columns:
                if pd.api.types.is_datetime64_any_dtype(df_copy[col]):
                    df_copy[col] = df_copy[col].astype(str)

            return {
                "success": True,
                "sql": sql,
                "data": df_copy.to_dict(orient="records"),
                "comment": comment,
                "rows": len(df),
                "columns": list(df.columns) if len(df) > 0 else [],
                "duration": round(time.time() - total_start, 3),
            }

        except Exception as exc:  # noqa: BLE001
            if stream_callback:
                stream_callback({"type": "error", "text": str(exc)})

            return {
                "success": False,
                "error": str(exc),
                "sql": None,
                "data": [],
                "comment": "",
                "rows": 0,
                "columns": [],
            }

    def close(self) -> None:
        """Закрывает соединение с DuckDB."""
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
    """
    # Используем build_llm_client чтобы инициировать подключение к Ollama.
    try:
        client = build_llm_client(
            provider="ollama",
            model=model,
            base_url=OLLAMA_BASE_URL,
            request_timeout=5.0,
            stream_timeout=5.0,
            concurrency_limit=1,
            max_retries=0,
            keep_alive=keep_alive,
            provider_config={"base_url": OLLAMA_BASE_URL},
            device_config={},
        )
        client.complete(
            "ping",
            num_predict=1,
            temperature=0.0,
            stream=False,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


