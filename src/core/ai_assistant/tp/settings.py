"""
Настройки модуля техпроцессов AI ассистента.
Значения ollama должны совпадать с core/client/src/core/ai-assistant/tp/config.js.
"""

# Подмешивать историю чата в промпт LLM (True) или только текущий запрос + документы (False).
# Сессия и сообщения в БД хранятся всегда.
TP_USE_CHAT_HISTORY_IN_PROMPT = False

TP_OLLAMA_CONFIG = {
    'num_gpu': 999,
    'temperature': 0.3,
    'max_tokens': 131072,
    'top_p': 0.9,
    'top_k': 40,
    'seed': 42,
    'repeat_penalty': 1.1,
}


def use_chat_history_in_prompt():
    """
    Если True — подмешивать историю чата в промпт LLM.
    Если False — в промпт только системный промпт + документы + текущий вопрос (без истории).
    Сессия и сообщения в БД хранятся всегда.
    """
    return TP_USE_CHAT_HISTORY_IN_PROMPT
