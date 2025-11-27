# -*- coding: utf-8 -*-
"""
Сервис анализа табличных данных через Polars и ускоренные LLM.
Возможности:
- Быстрый HTTP клиент Ollama с пулами соединений и поддержкой GPU/CPU
- Возможность переопределять модель и параметры через module-config
Безопасность:
1. Промпт явно запрещает DDL/DML
2. `_only_select` проверяет тип запроса через sqlparse
4. Ограничение времени выполнения SQL
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

import polars as pl
import pandas as pd
import sqlparse
from django.conf import settings

from .config import RuntimeLLMConfig, build_runtime_config
from .llm_clients import LLMClientError, build_llm_client

logger = logging.getLogger(__name__)

# -----------------------------
# Константы (из настроек Django)
# -----------------------------
# Импортируем напрямую из settings, где уже есть fallback из env
DEFAULT_MODEL: str = settings.OLLAMA_DEFAULT_MODEL
OLLAMA_BASE_URL: str = settings.OLLAMA_BASE_URL
STATS_TOP_K = 10
SQL_TIMEOUT_SEC = 30


# -----------------------------
# Хелперы
# -----------------------------
def _normalize_sql_for_polars(sql: str) -> str:
    """
    Нормализует SQL для Polars SQL:
    - Заменяет обратные кавычки (`) на двойные кавычки (") для идентификаторов
    - Polars SQL использует двойные кавычки для идентификаторов с пробелами или специальными символами
    """
    # Заменяем обратные кавычки на двойные для идентификаторов
    # Используем регулярное выражение для замены `identifier` на "identifier"
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
    # Нормализуем SQL для Polars перед возвратом
    return _normalize_sql_for_polars(sql_single)


def _convert_polars_to_sql(text: str) -> Optional[str]:
    """
    Преобразует Python Polars код в SQL, если LLM сгенерировал Python вместо SQL.
    Возвращает SQL или None если не удалось преобразовать.
    """
    text_lower = text.lower().strip()
    
    # df.head(N) → SELECT * FROM df LIMIT N
    match = re.search(r'df\.head\s*\(\s*(\d+)\s*\)', text_lower)
    if match:
        limit = match.group(1)
        return f"SELECT * FROM df LIMIT {limit}"
    
    # df.head() → SELECT * FROM df LIMIT 5
    if 'df.head()' in text_lower or 'df.head' in text_lower:
        return "SELECT * FROM df LIMIT 5"
    
    # df.tail(N) → SELECT * FROM df ORDER BY rowid DESC LIMIT N (примерно)
    match = re.search(r'df\.tail\s*\(\s*(\d+)\s*\)', text_lower)
    if match:
        limit = match.group(1)
        return f"SELECT * FROM df LIMIT {limit}"
    
    # df.describe() → агрегации (упрощённо)
    if 'df.describe()' in text_lower:
        return "SELECT COUNT(*) as count FROM df"
    
    # df.select(...) - это уже Polars API, не SQL
    if 'df.select' in text_lower or 'df.filter' in text_lower:
        return None  # Не можем преобразовать сложный Polars код
    
    return None


def _extract_sql_from_text(text: str) -> str:
    """Пытаемся вытащить SQL из ответа LLM."""
    # Сначала ищем SQL в блоке кода
    match = re.search(r"```sql\s*(.*?)```", text, flags=re.S | re.I)
    if match:
        return match.group(1).strip()
    
    # Ищем SELECT в тексте
    idx = text.lower().find("select")
    if idx >= 0:
        return text[idx:].strip()
    
    # Проверяем, не сгенерировал ли LLM Python Polars код вместо SQL
    polars_sql = _convert_polars_to_sql(text)
    if polars_sql:
        logger.warning(f"LLM сгенерировал Python код, преобразовано в SQL: {polars_sql}")
        return polars_sql
    
    return text.strip()


def _shorten(df: pd.DataFrame, max_rows: int = 50) -> pd.DataFrame:
    """Обрезаем DataFrame для предпросмотра."""
    return df.head(max_rows).copy()


# -----------------------------
# Основной класс
# -----------------------------
class FastBIService:
    """
    Сервис для анализа табличных данных через Polars и LLM.
    Адаптирован для использования в Django и поддерживает streaming выдачу.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        keep_alive: str = "5m",
        ollama_config: Optional[Dict[str, Any]] = None,
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
            model=self.model or DEFAULT_MODEL,
            base_url=self.base_url or OLLAMA_BASE_URL,
            request_timeout=self._config.request_timeout,
            stream_timeout=self._config.stream_timeout,
            concurrency_limit=self._config.concurrency_limit,
            max_retries=self._config.max_retries,
            keep_alive=self.keep_alive,
            provider_config=self._config.provider_config,
            device_config=self._config.device_config,
        )

        # Используем Polars DataFrame напрямую (без соединений)
        self.df: Optional[pl.DataFrame] = None
        self.table_name: Optional[str] = None
        self.meta: Optional[Dict[str, Any]] = None

    def load_file(self, file_path: str, table_name: str = "t") -> Dict[str, Any]:
        """
        Загружает файл напрямую в Polars DataFrame.

        Args:
            file_path: Путь к файлу (CSV, XLSX, XLS, BIN)
            table_name: Имя таблицы (используется в SQL запросах)

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
                
                if not rows:
                    raise ValueError("Бинарный файл не содержит данных")
                
                # Создаем Polars DataFrame напрямую из списка строк
                self.df = pl.DataFrame(rows, schema=columns, orient="row")
                
            elif path.suffix.lower() in [".csv", ".tsv"]:
                # Читаем CSV напрямую в Polars
                self.df = pl.read_csv(path, try_parse_dates=True)
                
            elif path.suffix.lower() in [".xlsx", ".xls"]:
                # Читаем Excel через pandas (Polars не поддерживает Excel напрямую)
                # Затем конвертируем в Polars
                pandas_df = pd.read_excel(path)
                self.df = pl.from_pandas(pandas_df)
            else:
                raise ValueError(f"Неподдерживаемый формат файла: {path.suffix}")

            self._prepare_metadata()

            assert self.meta is not None, "Метаданные не подготовлены"
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
        assert self.df is not None, "DataFrame не загружен"
        assert self.table_name

        # Получаем схему из Polars DataFrame
        schema = self.df.schema
        n_rows = len(self.df)

        # Разделяем колонки на числовые и категориальные
        numeric_cols = []
        categorical_cols = []
        schema_list = []
        
        for col_name, dtype in schema.items():
            # Определяем тип для метаданных
            if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64):
                type_str = "INTEGER"
                numeric_cols.append(col_name)
            elif dtype in (pl.Float32, pl.Float64):
                type_str = "DOUBLE"
                numeric_cols.append(col_name)
            elif dtype == pl.Boolean:
                type_str = "BOOLEAN"
                categorical_cols.append(col_name)
            elif dtype in (pl.Date, pl.Datetime, pl.Duration, pl.Time):
                type_str = "DATE"
                categorical_cols.append(col_name)
            else:
                type_str = "VARCHAR"
                categorical_cols.append(col_name)
            
            schema_list.append({"name": col_name, "type": type_str})

        # Вычисляем статистику для числовых колонок (батчинг - все в одном запросе)
        num_summary: Dict[str, Dict[str, Any]] = {}
        if numeric_cols:
            # Используем Polars для быстрого вычисления всех статистик сразу
            stats = self.df.select([
                pl.col(col).min().alias(f"{col}_min")
                for col in numeric_cols
            ] + [
                pl.col(col).max().alias(f"{col}_max")
                for col in numeric_cols
            ] + [
                pl.col(col).mean().alias(f"{col}_avg")
                for col in numeric_cols
            ])
            
            # Извлекаем значения
            stats_dict = stats.to_dict(as_series=False)
            for col in numeric_cols:
                min_val = stats_dict.get(f"{col}_min", [None])[0]
                max_val = stats_dict.get(f"{col}_max", [None])[0]
                avg_val = stats_dict.get(f"{col}_avg", [None])[0]
                num_summary[col] = {
                    "min": float(min_val) if min_val is not None else None,
                    "max": float(max_val) if max_val is not None else None,
                    "avg": float(avg_val) if avg_val is not None else None,
                }

        # Вычисляем топ значения для категориальных колонок
        cat_summary: Dict[str, Any] = {}
        for column in categorical_cols:
            try:
                # Используем Polars для быстрого подсчета
                top_values = (
                    self.df.group_by(column)
                    .agg(pl.count().alias("cnt"))
                    .sort("cnt", descending=True)
                    .head(STATS_TOP_K)
                )
                
                # Конвертируем в список словарей
                result_list = []
                for row in top_values.iter_rows(named=True):
                    # Конвертируем значения в Python типы
                    value = row[column]
                    if isinstance(value, (pl.Date, pl.Datetime)):
                        value = str(value)
                    result_list.append({
                        "value": value,
                        "cnt": row["cnt"]
                    })
                
                cat_summary[column] = result_list
            except Exception:  # noqa: BLE001
                cat_summary[column] = []

        self.meta = {
            "table": self.table_name,
            "rows": int(n_rows),
            "schema": schema_list,
            "numeric_summary": num_summary,
            "categorical_top": cat_summary,
        }

    def _should_use_sql(self, question: str) -> bool:
        """Определяет, нужен ли SQL запрос для ответа на вопрос."""
        question_lower = question.lower().strip()
        
        # Вопросы, которые НЕ требуют SQL (можно ответить напрямую)
        no_sql_patterns = [
            "что в этом файле",
            "что содержит",
            "описание файла",
            "расскажи о файле",
            "что за файл",
            "какие данные",
            "какая информация",
            "опиши файл",
            "что это за данные",
        ]
        
        # Если вопрос слишком общий или про описание - не нужен SQL
        for pattern in no_sql_patterns:
            if pattern in question_lower:
                return False
        
        # Если вопрос содержит SQL-подобные слова - нужен SQL
        sql_keywords = [
            "покажи", "выведи", "найди", "посчитай", "среднее", "максимум", "минимум",
            "сумма", "количество", "сколько", "где", "фильтр", "отсортируй", "группируй",
            "топ", "первые", "последние", "выбери", "отбери"
        ]
        
        for keyword in sql_keywords:
            if keyword in question_lower:
                return True
        
        # По умолчанию - используем SQL для конкретных вопросов
        return len(question.split()) > 2  # Если вопрос достаточно конкретный
    
    def _build_direct_answer_prompt(self, question: str) -> str:
        """Строит промпт для прямого ответа без SQL."""
        assert self.meta is not None, "Метаданные не подготовлены"
        assert self.df is not None, "DataFrame не загружен"
        
        columns_info = [
            {"name": column["name"], "type": column["type"]}
            for column in self.meta["schema"][:30]
        ]
        
        # Добавляем примеры данных, чтобы LLM не выдумывал контекст
        sample_rows = self.df.head(3)
        sample_data = []
        for row in sample_rows.iter_rows(named=True):
            row_dict = {}
            for key, value in row.items():
                if value is None:
                    row_dict[key] = None
                elif isinstance(value, (pl.Date, pl.Datetime)):
                    row_dict[key] = str(value)
                else:
                    row_dict[key] = value
            sample_data.append(row_dict)
        sample_json = json.dumps(sample_data, ensure_ascii=False, default=str, separators=(',', ':'))
        
        prompt = (
            f"Ты аналитик данных. Ответь на вопрос о файле с табличными данными.\n\n"
            f"ВАЖНО: Используй ТОЛЬКО информацию из данных ниже. НЕ выдумывай и НЕ предполагай информацию, которой нет в данных!\n\n"
            f"Информация о файле:\n"
            f"- Количество строк: {self.meta['rows']}\n"
            f"- Количество колонок: {len(self.meta['schema'])}\n"
            f"- Колонки: {', '.join([col['name'] for col in columns_info[:20]])}\n\n"
            f"Примеры данных (первые 3 строки):\n{sample_json}\n\n"
            f"Вопрос: {question}\n\n"
            f"Ответь кратко и по делу на русском языке. Опиши ТОЛЬКО то, что видишь в данных. Не выдумывай названия организаций или другую информацию!"
        )
        return prompt
    
    def _build_sql_prompt(self, question: str) -> str:
        """Строит оптимизированный промпт для генерации SQL."""
        assert self.meta is not None, "Метаданные не подготовлены"
        assert self.df is not None, "DataFrame не загружен"
        
        # Компактная схема: все колонки (имя:тип)
        schema_cols = self.meta["schema"]
        schema_compact = ", ".join([f"{col['name']}:{col['type']}" for col in schema_cols])
        num_cols = len(schema_cols)

        # Оптимизация: используем формат "массив массивов" и ограничиваем размер
        # Для больших таблиц (много колонок) показываем только 1 строку и обрезаем длинные значения
        max_sample_rows = 1 if num_cols > 30 else 2  # Меньше строк для больших таблиц
        max_value_length = 50  # Обрезаем длинные строки
        
        # Получаем примеры данных в формате массива массивов
        sample_rows = self.df.head(max_sample_rows)
        sample_data = []
        for row in sample_rows.iter_rows():
            row_values = []
            for value in row:
                if value is None:
                    row_values.append(None)
                elif isinstance(value, (pl.Date, pl.Datetime)):
                    row_values.append(str(value))
                elif isinstance(value, str) and len(value) > max_value_length:
                    # Обрезаем длинные строки
                    row_values.append(value[:max_value_length] + "...")
                else:
                    row_values.append(value)
            sample_data.append(row_values)
        
        # Компактный формат: массив массивов
        sample_json = json.dumps(sample_data, ensure_ascii=False, default=str, separators=(',', ':'))
        
        # Компактный промпт для уменьшения размера
        prompt = (
            f"SQL для таблицы 'df':\n"
            f"Схема: {schema_compact}\n"
            f"Строк: {self.meta['rows']}\n"
            f"Пример: {sample_json}\n"
            f"Правила: SELECT только, \"колонки с пробелами\", таблица df\n"
            f"Вопрос: {question}\nSQL:"
        )
        return prompt

    def _gen_sql_via_llm(self, question: str, stream_callback=None) -> str:
        """Генерирует SQL через LLM с поддержкой streaming."""
        prompt = self._build_sql_prompt(question)
        stream = bool(stream_callback)

        # Логируем промпт перед отправкой в LLM
        logger.info("=== ПРОМПТ ДЛЯ ГЕНЕРАЦИИ SQL ===")
        logger.info(f"Длина промпта: {len(prompt)} символов ({len(prompt.split())} слов)")
        logger.info(f"Вопрос: {question}")
        logger.info(f"Параметры запроса:")
        logger.info(f"  - num_predict: {self.sql_generation_tokens}")
        logger.info(f"  - temperature: {self.temperature_sql}")
        logger.info(f"  - stream: {stream}")
        logger.info(f"  - request_timeout: {self._config.request_timeout}s")
        logger.info(f"  - stream_timeout: {self._config.stream_timeout}s")
        logger.info(f"  - model: {self.model}")
        logger.info(f"Промпт:\n{prompt}")
        logger.info("=" * 50)

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
            logger.error(f"Ошибка генерации SQL: {exc}")
            logger.error(f"Промпт был длиной {len(prompt)} символов")
            raise RuntimeError(f"Ошибка генерации SQL: {exc}") from exc

        sql_raw = _extract_sql_from_text(resp_text)
        sql = _only_select(sql_raw)
        
        # Заменяем имя таблицы на 'df' для Polars SQL
        # Заменяем как с кавычками, так и без
        if self.table_name:
            sql = sql.replace(f'"{self.table_name}"', 'df').replace(f"'{self.table_name}'", 'df')
            sql = re.sub(rf'\b{re.escape(self.table_name)}\b', 'df', sql)
        
        return sql

    def _run_sql(self, sql: str) -> pd.DataFrame:
        """Выполняет SQL запрос через Polars SQL."""
        assert self.df is not None, "DataFrame не загружен"
        
        t0 = time.time()
        try:
            # Используем правильный синтаксис Polars SQL
            # В Polars 1.34+ используется SQLContext с регистрацией через register или напрямую
            ctx = pl.SQLContext()
            ctx.register("df", self.df)
            result = ctx.execute(sql, eager=True)
            # Конвертируем результат в pandas для совместимости
            # Используем fallback без pyarrow, если библиотека недоступна
            try:
                # Пробуем конвертировать с отключением pyarrow extension arrays
                pandas_result = result.to_pandas(use_pyarrow_extension_array=False)
            except (ImportError, ModuleNotFoundError, AttributeError) as e:
                # Если pyarrow недоступен или метод не поддерживает параметр,
                # конвертируем через словари (iter_rows с named=True)
                logger.warning(f"PyArrow недоступен, используем альтернативную конвертацию: {e}")
                rows = []
                for row in result.iter_rows(named=True):
                    rows.append(row)
                pandas_result = pd.DataFrame(rows)
            
            elapsed = time.time() - t0
            if elapsed > SQL_TIMEOUT_SEC:
                raise TimeoutError(f"SQL выполнялся слишком долго: {elapsed:.1f}s")
            
            return pandas_result
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Ошибка выполнения SQL: {exc}\nSQL:\n{sql}") from exc

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
            "ВАЖНО: Описывай ТОЛЬКО то, что видишь в данных. НЕ выдумывай информацию, названия организаций или контекст!\n"
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
        Автоматически определяет, нужен ли SQL или можно ответить напрямую.

        Args:
            question: Вопрос на естественном языке
            want_commentary: Нужен ли комментарий от LLM
            stream_callback: Функция обработки streaming-данных
        """
        if self.df is None or not self.meta:
            raise RuntimeError("Сначала загрузите файл через load_file()")

        total_start = time.time()

        try:
            # Определяем, нужен ли SQL запрос
            use_sql = self._should_use_sql(question)
            
            if not use_sql:
                # Прямой ответ без SQL
                if stream_callback:
                    stream_callback({"type": "stage", "text": "💭 Анализирую файл..."})
                
                prompt = self._build_direct_answer_prompt(question)
                stream = bool(stream_callback)
                
                # Логируем промпт перед отправкой в LLM
                logger.info("=== ПРОМПТ ДЛЯ ПРЯМОГО ОТВЕТА (БЕЗ SQL) ===")
                logger.info(f"Длина промпта: {len(prompt)} символов ({len(prompt.split())} слов)")
                logger.info(f"Вопрос: {question}")
                logger.info(f"Параметры запроса:")
                logger.info(f"  - num_predict: {self.commentary_tokens * 2}")
                logger.info(f"  - temperature: {self.temperature_commentary}")
                logger.info(f"  - stream: {stream}")
                logger.info(f"  - request_timeout: {self._config.request_timeout}s")
                logger.info(f"  - stream_timeout: {self._config.stream_timeout}s")
                logger.info(f"  - model: {self.model}")
                logger.info(f"Промпт:\n{prompt}")
                logger.info("=" * 50)
                
                def on_chunk(text: str) -> None:
                    if stream_callback:
                        stream_callback({"type": "commentary", "text": text})
                
                answer = self.llm_client.complete(
                    prompt,
                    num_predict=self.commentary_tokens * 2,  # Больше токенов для описания
                    temperature=self.temperature_commentary,
                    stream=stream,
                    stream_callback=on_chunk if stream else None,
                ).strip()
                
                if stream_callback:
                    stream_callback({"type": "stage", "text": "✅ Анализ завершен"})
                
                return {
                    "success": True,
                    "sql": None,
                    "data": [],
                    "comment": answer,
                    "rows": self.meta["rows"],
                    "columns": [col["name"] for col in self.meta["schema"]],
                    "duration": round(time.time() - total_start, 3),
                }
            
            # Используем SQL для конкретных запросов
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
        """Очищает DataFrame из памяти."""
        self.df = None
        self.table_name = None
        self.meta = None


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

