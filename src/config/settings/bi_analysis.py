"""
Настройки для модуля BI Analysis (Аналитика)
"""

import os
from src.config.env import env

# Максимальное количество строк для асинхронной обработки
# Если запрошено больше строк, чем этот лимит, используется Celery task
BI_PREVIEW_ASYNC_THRESHOLD = env.int('BI_PREVIEW_ASYNC_THRESHOLD', default=5000)  # type: ignore

