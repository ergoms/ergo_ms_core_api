"""
Общие утилиты для построения промптов чата техпроцессов (используются в views и tasks).
"""

from src.core.ai_assistant.models import ChatMessage

from .settings import use_chat_history_in_prompt

TP_INTRO_MESSAGE = (
    'Привет! Я ваш AI ассистент для работы с техпроцессами.\n\n'
    '**Что я умею:**\n'
    '• Отвечать на вопросы на основе загруженных документов техпроцессов\n'
    '• Искать информацию в документах\n'
    '• Анализировать таблицы и извлекать данные\n\n'
    '**Начните работу:**\n'
    '1. Нажмите кнопку "Загрузить" для добавления документов DOCX\n'
    '2. После загрузки документы автоматически конвертируются в Markdown\n'
    '3. Затем задавайте вопросы к документам!'
)

_UPLOAD_MSG_PREFIX_SINGLE = '✅ Документ успешно загружен и сконвертирован в Markdown.'
_UPLOAD_MSG_PREFIX_MULTI = '✅ Успешно загружено документов:'


def _is_skip_for_context_assistant_message(content):
    """Сообщения ассистента, не передаваемые в контекст модели (приветствие и уведомления о загрузке)."""
    if not content:
        return True
    content = content.strip()
    if content == TP_INTRO_MESSAGE:
        return True
    if content.startswith(_UPLOAD_MSG_PREFIX_SINGLE) or content.startswith(_UPLOAD_MSG_PREFIX_MULTI):
        return True
    return False


def get_tp_system_prompt():
    return (
        "Reasoning: high\n\n"
        "Роль: AI-ассистент по техпроцессам. Отвечай только на основе загруженных документов, "
        "указывай источник (название документа). Таблицы — анализируй и извлекай данные. "
        "Отвечай только на русском языке.\n\n"
        "Документы: цельные объекты, разделены маркерами начала/конца. Не дроби на части.\n\n"
        "Фильтр по объёму работ: если в вопросе указан объём (ТР-1, ТР-2, ТО-1, ТО-2, ТО-3 и т.д.) — "
        "используй ТОЛЬКО документы этого объёма. Документ другого объёма = ошибка.\n"
        "Справка: ТО (ТО-1…ТО-5), ТР (ТР-1, ТР-2, ТР-3), заводской: СР, КР-1, КР-2.\n\n"
        "Формат ответа: блок <think> (проверь объём работ, выбери релевантные документы, исключи лишние, "
        "спланируй ответ), затем </think> и финальный ответ пользователю."
    )


def build_tp_chat_messages(session, user_message_text, all_documents_markdown):
    """Собирает список сообщений для LLM: system + история + текущий user prompt."""
    system_prompt = get_tp_system_prompt()
    user_prompt_parts = []
    if all_documents_markdown:
        # Подсчитываем количество документов по маркерам "ДОКУМЕНТ"
        doc_count = all_documents_markdown.count("# ДОКУМЕНТ")
        if doc_count == 1:
            user_prompt_parts.append(
                "Ниже представлен ОДИН ЦЕЛЬНЫЙ документ техпроцесса. "
                "Весь контент от начала до конца относится к одному документу.\n\n"
                f"{all_documents_markdown}\n\n"
            )
        else:
            user_prompt_parts.append(
                f"Ниже представлены {doc_count} документа(ов) техпроцессов. "
                "Каждый документ четко разделен маркерами начала и конца. "
                "Используй информацию из соответствующего документа при ответе.\n\n"
                f"{all_documents_markdown}\n\n"
            )
    else:
        user_prompt_parts.append(
            "Внимание: Загруженных документов техпроцессов нет. "
            "Попроси пользователя загрузить документы для работы с техпроцессами.\n\n"
        )
    user_prompt_parts.append(f"Вопрос пользователя: {user_message_text}")
    user_prompt_parts.append(
        "\nОтветь по документам (<think> + ответ). Если объём работ указан — только документы этого объёма. "
        "Указывай источник. Если данных нет — так и скажи. Только на русском."
    )
    user_prompt = "\n".join(user_prompt_parts)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    if not use_chat_history_in_prompt():
        return messages
    previous_messages = session.messages.order_by('created_at')[:10]
    chat_history = []
    for msg in previous_messages:
        if msg.message_type == ChatMessage.MESSAGE_TYPE_USER:
            chat_history.append({"role": "user", "content": msg.content})
        elif msg.message_type == ChatMessage.MESSAGE_TYPE_ASSISTANT:
            if not _is_skip_for_context_assistant_message(msg.content):
                chat_history.append({"role": "assistant", "content": msg.content})
    return [messages[0]] + chat_history + [messages[1]]
