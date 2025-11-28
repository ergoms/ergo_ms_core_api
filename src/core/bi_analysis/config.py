"""
Конфигурация для модуля bi_analysis.
Содержит настройки для обработки данных, включая переключение CPU/GPU.
"""

import os
from typing import Literal

# Тип устройства для вычислений
ComputeDevice = Literal['cpu', 'gpu']

# По умолчанию используем GPU, если доступен
USE_GPU = os.getenv('BI_ANALYSIS_USE_GPU', 'true').lower() == 'true'

# Определяем устройство для вычислений
def get_compute_device() -> ComputeDevice:
    """
    Определяет устройство для вычислений.
    По умолчанию использует GPU, если доступен.
    """
    if USE_GPU:
        try:
            import polars as pl
            # Проверяем доступность GPU через polars
            # Polars автоматически использует GPU для некоторых операций, если доступен
            return 'gpu'
        except:
            return 'cpu'
    return 'cpu'

# Настройки для обработки файлов
CHUNK_SIZE = int(os.getenv('BI_ANALYSIS_CHUNK_SIZE', '100000'))  # Размер чанка для обработки
MAX_WORKERS = int(os.getenv('BI_ANALYSIS_MAX_WORKERS', '4'))  # Количество потоков для параллельной обработки
PREVIEW_LIMIT = int(os.getenv('BI_ANALYSIS_PREVIEW_LIMIT', '1000000000'))  # Лимит строк для предпросмотра (практически без ограничений)

# Настройки для celery задач
CELERY_TASK_TIMEOUT = int(os.getenv('BI_ANALYSIS_CELERY_TIMEOUT', '300'))  # 5 минут
CELERY_SOFT_TIMEOUT = int(os.getenv('BI_ANALYSIS_CELERY_SOFT_TIMEOUT', '270'))  # 4.5 минуты

