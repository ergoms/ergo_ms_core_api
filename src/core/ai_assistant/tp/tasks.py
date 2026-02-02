"""
Celery-задачи модуля техпроцессов: загрузка документов и обработка ответа модели в очередях.
"""

import logging
import os
import time

from celery import shared_task
from django.core.files import File
from django.contrib.auth import get_user_model
from django.utils import timezone

from src.core.ai_assistant.models import ChatSession, ChatMessage
from src.core.ai_assistant.rag import DocumentParserService
from src.core.ai_assistant.llm_utils import create_ollama_client

from .models import TechnologicalProcessDocument
from .converter import TPDocumentConverter
from .prompt_utils import build_tp_chat_messages

User = get_user_model()
logger = logging.getLogger('celery.module.ai_assistant_tp.tasks')


def _build_upload_message_content(documents_list):
    if len(documents_list) > 1:
        table_lines = [
            '✅ Успешно загружено документов: ' + str(len(documents_list)) + '\n\n',
            '| № | Название документа |\n',
            '| --- | --- |\n',
        ]
        for idx, doc in enumerate(documents_list, 1):
            table_lines.append(f'| {idx} | {doc["title"]} |\n')
        table_lines.append('\nВсе документы будут использоваться при ответах на ваши вопросы.')
        return ''.join(table_lines)
    doc = documents_list[0]
    return (
        '✅ Документ успешно загружен и сконвертирован в Markdown.\n'
        '| Название документа |\n'
        '| --- |\n'
        f'| {doc["title"]} |\n'
        '\nДокумент будет использоваться при ответах на ваши вопросы.'
    )


@shared_task(bind=True, name='src.core.ai_assistant.tp.tasks.process_tp_documents')
def process_tp_documents(self, session_id: str, user_id: int, file_infos: list, metadata: dict = None):
    """
    Обрабатывает загруженные DOCX в очереди: конвертация в Markdown, создание документов и сообщения в чате.
    file_infos: [{"temp_path": str, "original_filename": str}, ...]
    """
    metadata = metadata or {}
    documents_result = []
    errors = []
    temp_paths_to_remove = []

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return {
            'success': False,
            'error': 'Пользователь не найден',
            'documents': [],
            'message': None,
        }

    try:
        session = ChatSession.objects.get(id=session_id, user=user, module='tp')
    except ChatSession.DoesNotExist:
        return {
            'success': False,
            'error': 'Сессия чата не найдена',
            'documents': [],
            'message': None,
        }

    for info in file_infos:
        temp_path = info.get('temp_path')
        original_filename = info.get('original_filename') or os.path.basename(temp_path or '')
        if not temp_path or not os.path.isfile(temp_path):
            errors.append({'file': original_filename, 'error': 'Временный файл не найден'})
            continue
        temp_paths_to_remove.append(temp_path)
        title = os.path.splitext(original_filename)[0]
        try:
            file_type = DocumentParserService.get_file_type(original_filename)
            if file_type != 'docx':
                errors.append({
                    'file': original_filename,
                    'error': f'Неподдерживаемый тип файла: {file_type}. Поддерживается только DOCX.',
                })
                continue
            markdown_content = TPDocumentConverter.docx_to_markdown(file_path=temp_path)
            document = TechnologicalProcessDocument.objects.create(
                user=user,
                session=session,
                title=title,
                file_type=file_type,
                markdown_content=markdown_content,
                metadata=metadata,
            )
            with open(temp_path, 'rb') as f:
                document.file.save(original_filename, File(f), save=True)
            documents_result.append({
                'id': str(document.id),
                'title': document.title,
                'file_type': document.file_type,
                'file_name': document.file.name.split('/')[-1] if document.file else None,
                'markdown_preview': (
                    (document.markdown_content[:200] + '...' if len(document.markdown_content) > 200 else document.markdown_content)
                    if document.markdown_content else None
                ),
                'created_at': document.created_at.isoformat(),
                'updated_at': document.updated_at.isoformat(),
                'metadata': document.metadata,
            })
        except ValueError as e:
            errors.append({'file': original_filename, 'error': f'Ошибка конвертации документа: {str(e)}'})
        except Exception as e:
            logger.error(f"Ошибка создания документа техпроцесса {original_filename}: {e}", exc_info=True)
            errors.append({'file': original_filename, 'error': f'Ошибка создания документа: {str(e)}'})

    for path in temp_paths_to_remove:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError as e:
            logger.warning(f"Не удалось удалить временный файл {path}: {e}")

    if not documents_result and errors:
        return {
            'success': False,
            'error': 'Не удалось загрузить ни один файл',
            'errors': errors,
            'documents': [],
            'message': None,
        }

    created_message = None
    if documents_result:
        content = _build_upload_message_content(documents_result)
        created_message = ChatMessage.objects.create(
            session=session,
            message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT,
            content=content,
        )

    return {
        'success': True,
        'documents': documents_result,
        'count': len(documents_result),
        'errors': errors if errors else None,
        'message': {
            'id': str(created_message.id),
            'type': created_message.message_type,
            'content': created_message.content,
            'created_at': created_message.created_at.isoformat(),
        } if created_message else None,
    }


@shared_task(
    bind=True,
    name='src.core.ai_assistant.tp.tasks.process_tp_chat_response',
    time_limit=600,
    soft_time_limit=540,
    max_retries=0,
)
def process_tp_chat_response(self, session_id: str, user_id: int, message: str, ollama_config: dict = None):
    """
    Обрабатывает запрос пользователя в чате техпроцессов в очереди: вызов LLM, сохранение ответа в БД.
    По опыту модулей video_analysis, porosity_analysis, impuls_analysis: логгер, таймауты, возврат dict.
    """
    ollama_config = ollama_config or {}
    request_started_at = timezone.now()
    start_ts = time.time()

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning("process_tp_chat_response: пользователь не найден, user_id=%s", user_id)
        return {
            'success': False,
            'error': 'Пользователь не найден',
            'full_response': '',
            'message_id': None,
            'session_id': session_id,
            'processing_time_ms': None,
        }

    try:
        session = ChatSession.objects.get(id=session_id, user=user, module='tp')
    except ChatSession.DoesNotExist:
        logger.warning("process_tp_chat_response: сессия не найдена, session_id=%s", session_id)
        return {
            'success': False,
            'error': 'Сессия чата не найдена',
            'full_response': '',
            'message_id': None,
            'session_id': session_id,
            'processing_time_ms': None,
        }

    try:
        tp_documents = TechnologicalProcessDocument.objects.filter(
            user=user,
            session=session,
        ).order_by('-created_at')
        documents_content = []
        for doc in tp_documents:
            if doc.markdown_content:
                documents_content.append(f"## {doc.title}\n\n{doc.markdown_content}\n\n")
        all_documents_markdown = "\n".join(documents_content)

        messages = build_tp_chat_messages(session, message, all_documents_markdown)
        runtime_config, client = create_ollama_client(ollama_config)
        temperature = ollama_config.get('temperature', 0.3)
        max_tokens = ollama_config.get('max_tokens', 4096)
        seed = ollama_config.get('seed')

        full_response = client.chat(
            messages,
            temperature=temperature,
            num_predict=max_tokens,
            seed=seed,
            stream=False,
        )
        full_response = (full_response or '').strip()

        response_received_at = timezone.now()
        processing_time_ms = int((response_received_at - request_started_at).total_seconds() * 1000)
        message_metadata = {
            'model': runtime_config.model,
            'documents_count': tp_documents.count(),
        }
        if ollama_config:
            message_metadata['ollama_config'] = ollama_config

        assistant_message = ChatMessage.objects.create(
            session=session,
            message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT,
            content=full_response,
            request_started_at=request_started_at,
            response_received_at=response_received_at,
            processing_time_ms=processing_time_ms,
            metadata=message_metadata,
        )
        session.updated_at = timezone.now()
        session.save(update_fields=['updated_at'])

        elapsed = time.time() - start_ts
        logger.info(
            "[TP Chat task] Ответ сохранён: session_id=%s, message_id=%s, len=%s, time_ms=%s, elapsed=%.2fs",
            session_id,
            assistant_message.id,
            len(full_response),
            processing_time_ms,
            elapsed,
        )

        return {
            'success': True,
            'full_response': full_response,
            'message_id': str(assistant_message.id),
            'session_id': str(session.id),
            'processing_time_ms': processing_time_ms,
            'timestamp': assistant_message.created_at.isoformat(),
        }
    except Exception as e:
        logger.error("process_tp_chat_response: ошибка %s", e, exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'full_response': '',
            'message_id': None,
            'session_id': str(session.id),
            'processing_time_ms': int((timezone.now() - request_started_at).total_seconds() * 1000),
        }
