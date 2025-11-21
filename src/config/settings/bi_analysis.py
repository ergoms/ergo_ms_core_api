"""
Настройки для модуля BI Analysis (Аналитика)
"""

import os
from src.config.env import env

# Количество строк для предпросмотра датасетов
# По умолчанию: 200 (как в .env.example)
BI_PREVIEW_ROWS_LIMIT = int(os.environ.get('VITE_BI_PREVIEW_ROWS_LIMIT', '200'))

# Максимальное количество строк для асинхронной обработки
# Если запрошено больше строк, чем этот лимит, используется Celery task
BI_PREVIEW_ASYNC_THRESHOLD = env.int('BI_PREVIEW_ASYNC_THRESHOLD', default=5000)  # type: ignore

# Максимальное количество строк для VALUES clause в SQL
# Ограничивает размер SQL запроса для производительности
BI_PREVIEW_MAX_VALUES_ROWS = env.int('BI_PREVIEW_MAX_VALUES_ROWS', default=10000)  # type: ignore

