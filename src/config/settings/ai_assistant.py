"""
Файл содержащий конфигурацию для AI Assistant модуля.

Поддерживаемые LLM провайдеры:
- ollama (по умолчанию) - Ollama сервер
- llama_cpp - llama.cpp сервер (OpenAI-совместимый API)

Переключение между провайдерами через переменную окружения LLM_PROVIDER.
"""

from src.config.env import env

# ============================================================================
# Общие настройки LLM
# ============================================================================

# Выбор LLM провайдера: ollama | llama_cpp
# По умолчанию используется ollama
LLM_PROVIDER = env.str('LLM_PROVIDER', default='ollama')

# Таймауты для запросов
AI_ASSISTANT_REQUEST_TIMEOUT = env.float('AI_ASSISTANT_REQUEST_TIMEOUT', default=180.0)
AI_ASSISTANT_STREAM_TIMEOUT = env.float('AI_ASSISTANT_STREAM_TIMEOUT', default=300.0)

# Количество параллельных запросов
AI_ASSISTANT_CONCURRENCY_LIMIT = env.int('AI_ASSISTANT_CONCURRENCY_LIMIT', default=8)

# Количество повторных попыток при ошибке
AI_ASSISTANT_MAX_RETRIES = env.int('AI_ASSISTANT_MAX_RETRIES', default=2)

# Токены для генерации SQL и комментариев
AI_ASSISTANT_SQL_TOKENS = env.int('AI_ASSISTANT_SQL_TOKENS', default=256)
AI_ASSISTANT_COMMENTARY_TOKENS = env.int('AI_ASSISTANT_COMMENTARY_TOKENS', default=192)

# Температура для генерации SQL (низкая для точности)
AI_ASSISTANT_TEMPERATURE_SQL = env.float('AI_ASSISTANT_TEMPERATURE_SQL', default=0.08)

# Температура для генерации комментариев (средняя для естественности)
AI_ASSISTANT_TEMPERATURE_COMMENTARY = env.float('AI_ASSISTANT_TEMPERATURE_COMMENTARY', default=0.24)

# Время удержания модели в памяти (для Ollama)
AI_ASSISTANT_KEEP_ALIVE = env.str('AI_ASSISTANT_KEEP_ALIVE', default='10m')

# ============================================================================
# Настройки Ollama
# ============================================================================

# Базовый URL для подключения к Ollama API
OLLAMA_BASE_URL = env.str('OLLAMA_BASE_URL', default='http://localhost:11434')

# Модель Ollama по умолчанию
OLLAMA_DEFAULT_MODEL = env.str('OLLAMA_DEFAULT_MODEL', default='mistral:7b')

# Использовать прямой API Ollama (быстрее в 10+ раз)
OLLAMA_USE_DIRECT_API = env.bool('OLLAMA_USE_DIRECT_API', default=True)

# ============================================================================
# Настройки llama.cpp
# ============================================================================

# Базовый URL для подключения к llama.cpp серверу
LLAMA_CPP_BASE_URL = env.str('LLAMA_CPP_BASE_URL', default='http://localhost:8080')

# Путь к модели GGUF (относительно virtual_env/packages/models или абсолютный)
LLAMA_CPP_MODEL = env.str('LLAMA_CPP_MODEL', default='')

# Количество слоёв модели на GPU (0 = только CPU, -1 = все слои)
LLAMA_CPP_GPU_LAYERS = env.int('LLAMA_CPP_GPU_LAYERS', default=35)

# Количество потоков CPU для вычислений
LLAMA_CPP_THREADS = env.int('LLAMA_CPP_THREADS', default=8)

# Размер контекста (количество токенов)
LLAMA_CPP_CONTEXT_SIZE = env.int('LLAMA_CPP_CONTEXT_SIZE', default=4096)

# Размер батча для обработки
LLAMA_CPP_BATCH_SIZE = env.int('LLAMA_CPP_BATCH_SIZE', default=512)

# Количество параллельных запросов к llama.cpp серверу
LLAMA_CPP_PARALLEL = env.int('LLAMA_CPP_PARALLEL', default=1)

# Включить Flash Attention (требует CUDA)
LLAMA_CPP_FLASH_ATTN = env.bool('LLAMA_CPP_FLASH_ATTN', default=False)

# Заблокировать модель в RAM (предотвращает swap)
LLAMA_CPP_MLOCK = env.bool('LLAMA_CPP_MLOCK', default=False)

# Хост для llama.cpp сервера
LLAMA_CPP_HOST = env.str('LLAMA_CPP_HOST', default='127.0.0.1')

# Порт для llama.cpp сервера
LLAMA_CPP_PORT = env.int('LLAMA_CPP_PORT', default=8080)
