"""
Файл содержащий конфигурацию для AI Assistant модуля.
"""

from src.config.env import env

# Базовый URL для подключения к Ollama API
OLLAMA_BASE_URL = env.str('OLLAMA_BASE_URL', default='http://localhost:11434')

# Модель Ollama по умолчанию
OLLAMA_DEFAULT_MODEL = env.str('OLLAMA_DEFAULT_MODEL', default='mistral7b-tuned')

# Использовать прямой API Ollama (быстрее в 10+ раз)
OLLAMA_USE_DIRECT_API = env.bool('OLLAMA_USE_DIRECT_API', default=True)



