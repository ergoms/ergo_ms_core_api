"""
Утилиты для работы с бинарным хранением данных в формате .bin
Использует Polars IPC (Arrow IPC format) для эффективной векторизации и сжатия данных.
"""

import os
import logging
import math
from typing import Optional, Tuple, List, Any
from pathlib import Path

logger = logging.getLogger(__name__)


def convert_to_binary(source_path: str, output_path: str, sheet_name: Optional[str] = None, 
                      file_type: str = 'xlsx') -> bool:
    """
    Конвертирует файл (Excel/CSV) в бинарный формат .bin используя Polars IPC.
    
    Args:
        source_path: Путь к исходному файлу
        output_path: Путь для сохранения бинарного файла
        sheet_name: Имя листа для Excel файлов (опционально)
        file_type: Тип исходного файла ('xlsx', 'csv', 'txt')
    
    Returns:
        True если конвертация успешна, False иначе
    """
    try:
        import polars as pl
    except ImportError:
        logger.error("Polars не установлен, невозможно конвертировать в бинарный формат")
        return False
    
    try:
        # Проверяем существование исходного файла
        if not os.path.exists(source_path):
            logger.error(f"Исходный файл не найден: {source_path}")
            return False
        
        logger.info(f"Начинаем чтение файла: {source_path}, тип: {file_type}, лист: {sheet_name}")
        
        # Читаем данные из исходного файла
        df = None
        if file_type == 'xlsx':
            try:
                # Если sheet_name не указан, Polars прочитает первый лист
                if sheet_name:
                    df = pl.read_excel(source_path, sheet_name=sheet_name)
                else:
                    df = pl.read_excel(source_path)
                logger.info(f"Excel файл прочитан, строк: {len(df)}, колонок: {len(df.columns)}")
            except Exception as e:
                logger.error(f"Ошибка при чтении Excel файла через Polars: {str(e)}", exc_info=True)
                # Fallback: пробуем через pandas, затем конвертируем в Polars
                try:
                    import pandas as pd
                    logger.info("Пробуем прочитать Excel через pandas (fallback)")
                    if sheet_name:
                        pd_df = pd.read_excel(source_path, sheet_name=sheet_name, engine='openpyxl')
                    else:
                        pd_df = pd.read_excel(source_path, engine='openpyxl')
                    df = pl.from_pandas(pd_df)
                    logger.info(f"Excel файл прочитан через pandas->polars, строк: {len(df)}, колонок: {len(df.columns)}")
                except Exception as e2:
                    logger.error(f"Ошибка при чтении Excel файла через pandas: {str(e2)}", exc_info=True)
                    return False
        elif file_type in ('csv', 'txt'):
            # Пробуем разные кодировки
            try:
                df = pl.read_csv(source_path, encoding='utf8', try_parse_dates=True)
                logger.info(f"CSV файл прочитан (UTF-8), строк: {len(df)}, колонок: {len(df.columns)}")
            except Exception as e1:
                try:
                    df = pl.read_csv(source_path, encoding='cp1251', try_parse_dates=True)
                    logger.info(f"CSV файл прочитан (CP1251), строк: {len(df)}, колонок: {len(df.columns)}")
                except Exception as e2:
                    logger.error(f"Ошибка при чтении CSV файла (UTF-8: {e1}, CP1251: {e2})", exc_info=True)
                    return False
        else:
            logger.error(f"Неподдерживаемый тип файла для конвертации: {file_type}")
            return False
        
        if df is None:
            logger.error("DataFrame не был создан")
            return False
        
        # Сохраняем в бинарный формат IPC (Arrow IPC format)
        # Это эффективный бинарный формат с поддержкой векторизации
        logger.info(f"Сохраняем в бинарный формат: {output_path}")
        
        # Используем сжатие zstd если доступно, иначе без сжатия
        try:
            df.write_ipc(output_path, compression='zstd')
            logger.info(f"Файл сохранен со сжатием zstd: {output_path}")
        except Exception as e:
            logger.warning(f"Не удалось сохранить со сжатием zstd: {str(e)}, пробуем без сжатия")
            try:
                df.write_ipc(output_path)
                logger.info(f"Файл сохранен без сжатия: {output_path}")
            except Exception as e2:
                logger.error(f"Ошибка при сохранении бинарного файла: {str(e2)}", exc_info=True)
                return False
        
        # Проверяем, что файл был создан
        if not os.path.exists(output_path):
            logger.error(f"Бинарный файл не был создан: {output_path}")
            return False
        
        file_size = os.path.getsize(output_path)
        logger.info(f"Файл успешно конвертирован в бинарный формат: {output_path}, размер: {file_size} байт")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при конвертации файла в бинарный формат: {str(e)}", exc_info=True)
        return False


def read_from_binary(binary_path: str, row_limit: Optional[int] = None) -> Tuple[List[str], List[List[Any]]]:
    """
    Читает данные из бинарного файла .bin используя Polars IPC.
    
    Args:
        binary_path: Путь к бинарному файлу
        row_limit: Лимит строк для чтения (опционально)
    
    Returns:
        Tuple[columns, rows] - список колонок и список строк
    """
    try:
        import polars as pl
    except ImportError:
        logger.error("Polars не установлен, невозможно прочитать бинарный файл")
        raise ImportError("Polars не установлен")
    
    try:
        # Читаем из бинарного формата IPC
        # read_ipc автоматически определяет сжатие (zstd, lz4, uncompressed)
        # Отключаем memory_map для сжатых файлов, чтобы избежать предупреждений
        try:
            df = pl.read_ipc(binary_path, memory_map=False)
        except Exception:
            # Если не удалось с memory_map=False, пробуем без параметра
            df = pl.read_ipc(binary_path)
        
        # Применяем лимит если указан
        if row_limit and row_limit > 0:
            df = df.head(row_limit)
        
        # Векторизованная конвертация в списки
        columns = df.columns
        
        # Конвертируем в список строк, заменяя NaN на None для JSON-совместимости
        rows_list = []
        for row in df.iter_rows(named=False):
            # Заменяем NaN и infinity на None для JSON-совместимости
            cleaned_row = []
            for value in row:
                if value is None:
                    cleaned_row.append(None)
                elif isinstance(value, float):
                    if math.isnan(value) or math.isinf(value):
                        cleaned_row.append(None)
                    else:
                        cleaned_row.append(value)
                else:
                    cleaned_row.append(value)
            rows_list.append(cleaned_row)
        
        return list(columns), rows_list
        
    except Exception as e:
        logger.error(f"Ошибка при чтении бинарного файла: {str(e)}")
        raise


def is_binary_file(file_path: str) -> bool:
    """
    Проверяет, является ли файл бинарным (.bin).
    
    Args:
        file_path: Путь к файлу
    
    Returns:
        True если файл имеет расширение .bin
    """
    return Path(file_path).suffix.lower() == '.bin'


def get_binary_path(original_path: str) -> str:
    """
    Генерирует путь для бинарного файла на основе оригинального пути.
    
    Args:
        original_path: Оригинальный путь к файлу
    
    Returns:
        Путь к бинарному файлу с расширением .bin
    """
    path = Path(original_path)
    return str(path.with_suffix('.bin'))

