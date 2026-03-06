"""
Файл содержащий конфигурацию для AI Assistant модуля.

Поддерживаемый LLM провайдер:
- ollama (по умолчанию) - Ollama сервер

Переключение через переменную окружения LLM_PROVIDER.
"""

from src.config.env import env

# ============================================================================
# Общие настройки LLM
# ============================================================================

# Выбор LLM провайдера: ollama
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
# Настройки RAG (Retrieval-Augmented Generation)
# ============================================================================

# Модель Ollama для генерации embeddings (векторных представлений текста)
# Рекомендуемые модели:
#   - embeddinggemma (по умолчанию, Google Gemma 2B)
#   - qwen3-embedding (Alibaba Qwen, хорошее качество)
#   - all-minilm (Microsoft, быстрая и легкая)
# 
# Установка модели: ollama pull <model_name>
# Пример: ollama pull qwen3-embedding
#
# Настройка через переменную окружения:
#   OLLAMA_EMBEDDINGS_MODEL=qwen3-embedding
OLLAMA_EMBEDDINGS_MODEL = env.str('OLLAMA_EMBEDDINGS_MODEL', default='embeddinggemma')

# Размер chunk при разбиении документов (в символах)
# Рекомендуемые значения: 200-500 для более точного поиска, 1000 для больших контекстов
# Меньший размер = больше chunks = более точный поиск, но больше embeddings для хранения
RAG_CHUNK_SIZE = env.int('RAG_CHUNK_SIZE', default=300)

# Перекрытие между chunks (в символах) для сохранения контекста
# Обычно составляет 20-30% от chunk_size
RAG_CHUNK_OVERLAP = env.int('RAG_CHUNK_OVERLAP', default=60)

# Количество наиболее релевантных chunks для использования в контексте
RAG_TOP_K = env.int('RAG_TOP_K', default=5)

# Минимальный порог схожести для chunks (0.0 - 1.0)
RAG_SIMILARITY_THRESHOLD = env.float('RAG_SIMILARITY_THRESHOLD', default=0.0)

# Максимальная длина контекста из RAG для промпта (в символах)
RAG_MAX_CONTEXT_LENGTH = env.int('RAG_MAX_CONTEXT_LENGTH', default=4000)

# Включить RAG по умолчанию в чате
RAG_ENABLED = env.bool('RAG_ENABLED', default=True)
