import json
import logging
import os
from io import BytesIO
from queue import Queue, Empty
import threading

from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from src.core.ai_assistant.models import ChatSession, ChatMessage
from src.core.ai_assistant.rag import DocumentParserService
from src.core.ai_assistant.llm_utils import create_ollama_client
from src.core.utils.mixins import SwaggerSafeMixin

from .models import TechnologicalProcessDocument
from .converter import TPDocumentConverter

logger = logging.getLogger(__name__)


class TechnologicalProcessDocumentViewSet(ViewSet, SwaggerSafeMixin):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def list(self, request):
        user = self.get_safe_user()
        session_id = request.query_params.get('session_id')
        if not session_id:
            return Response({
                'success': False,
                'error': 'Не указан session_id. Укажите сессию чата для получения документов.'
            }, status=status.HTTP_400_BAD_REQUEST)
        try:
            session = ChatSession.objects.get(id=session_id, user=user, module='tp')
        except ChatSession.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Сессия чата не найдена.'
            }, status=status.HTTP_404_NOT_FOUND)
        queryset = TechnologicalProcessDocument.objects.filter(user=user, session=session)
        queryset = self.get_safe_queryset(queryset)
        documents = []
        for doc in queryset.order_by('-created_at'):
            file_size = None
            file_url = None
            if doc.file:
                try:
                    file_size = doc.file.size
                    file_url = doc.file.url if hasattr(doc.file, 'url') else None
                except Exception:
                    pass
            documents.append({
                'id': str(doc.id),
                'title': doc.title,
                'file_type': doc.file_type,
                'file_name': doc.file.name.split('/')[-1] if doc.file else None,
                'file_size': file_size,
                'file_url': file_url,
                'markdown_preview': (doc.markdown_content[:200] + '...' if doc.markdown_content and len(doc.markdown_content) > 200 else doc.markdown_content) if doc.markdown_content else None,
                'created_at': doc.created_at.isoformat(),
                'updated_at': doc.updated_at.isoformat(),
                'metadata': doc.metadata,
            })
        return Response({
            'success': True,
            'documents': documents,
            'count': len(documents),
        }, status=status.HTTP_200_OK)

    def create(self, request):
        user = self.get_safe_user()
        session_id = request.data.get('session_id')
        if not session_id:
            return Response({
                'success': False,
                'error': 'Не указан session_id. Документы должны быть привязаны к сессии чата.'
            }, status=status.HTTP_400_BAD_REQUEST)
        try:
            session = ChatSession.objects.get(id=session_id, user=user, module='tp')
        except ChatSession.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Сессия чата не найдена. Создайте новый чат перед загрузкой документов.'
            }, status=status.HTTP_404_NOT_FOUND)
        uploaded_files = request.FILES.getlist('files')
        if not uploaded_files:
            single_file = request.FILES.get('file')
            if single_file:
                uploaded_files = [single_file]
        metadata = request.data.get('metadata', {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        if not uploaded_files:
            return Response({
                'success': False,
                'error': 'Не указаны файлы. Укажите файлы DOCX для загрузки.'
            }, status=status.HTTP_400_BAD_REQUEST)
        documents = []
        errors = []
        for uploaded_file in uploaded_files:
            filename = uploaded_file.name
            title = os.path.splitext(filename)[0]
            try:
                file_type = DocumentParserService.get_file_type(filename)
                if file_type != 'docx':
                    errors.append({
                        'file': filename,
                        'error': f'Неподдерживаемый тип файла: {file_type}. Поддерживается только DOCX.'
                    })
                    continue
                file_obj = BytesIO(uploaded_file.read())
                markdown_content = TPDocumentConverter.docx_to_markdown(file_obj=file_obj)
                file_obj.seek(0)
                uploaded_file.seek(0)
                document = TechnologicalProcessDocument.objects.create(
                    user=user,
                    session=session,
                    title=title,
                    file_type=file_type,
                    markdown_content=markdown_content,
                    metadata=metadata,
                )
                document.file = uploaded_file
                document.save(update_fields=['file'])
                documents.append({
                    'id': str(document.id),
                    'title': document.title,
                    'file_type': document.file_type,
                    'file_name': document.file.name.split('/')[-1] if document.file else None,
                    'markdown_preview': (document.markdown_content[:200] + '...' if len(document.markdown_content) > 200 else document.markdown_content),
                    'created_at': document.created_at.isoformat(),
                    'updated_at': document.updated_at.isoformat(),
                    'metadata': document.metadata,
                })
            except ValueError as e:
                errors.append({'file': filename, 'error': f'Ошибка конвертации документа: {str(e)}'})
            except Exception as e:
                logger.error(f"Ошибка создания документа техпроцесса {filename}: {e}", exc_info=True)
                errors.append({'file': filename, 'error': f'Ошибка создания документа: {str(e)}'})
        if not documents and errors:
            return Response({
                'success': False,
                'error': 'Не удалось загрузить ни один файл',
                'errors': errors,
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'success': True,
            'documents': documents,
            'count': len(documents),
            'errors': errors if errors else None,
        }, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        user = self.get_safe_user()
        queryset = TechnologicalProcessDocument.objects.filter(user=user)
        queryset = self.get_safe_queryset(queryset)
        try:
            document = queryset.get(id=pk)
            file_size = None
            file_url = None
            if document.file:
                try:
                    file_size = document.file.size
                    file_url = document.file.url if hasattr(document.file, 'url') else None
                except Exception:
                    pass
            return Response({
                'success': True,
                'document': {
                    'id': str(document.id),
                    'title': document.title,
                    'file_type': document.file_type,
                    'file_name': document.file.name.split('/')[-1] if document.file else None,
                    'file_size': file_size,
                    'file_url': file_url,
                    'markdown_content': document.markdown_content,
                    'created_at': document.created_at.isoformat(),
                    'updated_at': document.updated_at.isoformat(),
                    'metadata': document.metadata,
                },
            }, status=status.HTTP_200_OK)
        except TechnologicalProcessDocument.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Документ не найден'
            }, status=status.HTTP_404_NOT_FOUND)

    def destroy(self, request, pk=None):
        user = self.get_safe_user()
        queryset = TechnologicalProcessDocument.objects.filter(user=user)
        queryset = self.get_safe_queryset(queryset)
        try:
            document = queryset.get(id=pk)
            document.delete()
            return Response({
                'success': True,
                'message': 'Документ успешно удален'
            }, status=status.HTTP_200_OK)
        except TechnologicalProcessDocument.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Документ не найден'
            }, status=status.HTTP_404_NOT_FOUND)


def _tp_system_prompt():
    return (
        "Reasoning: high\n\n"
        "Ты - AI ассистент для работы с техпроцессами. "
        "Твоя задача - отвечать на вопросы пользователя на основе загруженных документов техпроцессов. "
        "Используй информацию из документов для точных и релевантных ответов. "
        "Если в документах есть таблицы, анализируй их структуру и извлекай нужные данные. "
        "При ответе указывай название документа, из которого взята информация.\n\n"
        "КРИТИЧЕСКИ ВАЖНО: Фильтрация документов по объему работ\n"
        "Если в вопросе пользователя указан объем работ (ТР-1, ТР-2, ТО-1, ТО-2, ТО-3 и т.д.), "
        "ты ОБЯЗАН использовать ТОЛЬКО документы, соответствующие этому объему работ. "
        "Например: если вопрос про \"ТР-1\", то НЕ используй документы про ТР-2, ТО-2, ТО-3 и т.д. "
        "Каждый документ техпроцесса относится к определенному объему работ - проверяй это в названии документа и его содержимом. "
        "Использование документа несоответствующего объема работ - это КРИТИЧЕСКАЯ ОШИБКА.\n\n"
        "СПРАВОЧНАЯ ИНФОРМАЦИЯ: Объемы работ техпроцессов\n"
        "Техническое обслуживание (ТО): ТО-1 (локомотивная бригада, при приёмке-сдаче), "
        "ТО-2 (пункты ТО, смотровые канавы), ТО-3 (локомотивное депо), "
        "ТО-4 (обточка бандажей), ТО-5а/б/в/г (подготовка к запасу/резерву/эксплуатации).\n"
        "Текущий ремонт (ТР, деповской): ТР-1 (малый/периодический), ТР-2 (большой периодический), ТР-3 (подъемочный).\n"
        "Заводской ремонт: СР (средний ремонт), КР-1 (капитальный ремонт первого объема), КР-2 (капитальный ремонт второго объема).\n"
        "Используй эту информацию для правильной идентификации и фильтрации документов по объему работ.\n\n"
        "ВАЖНО: Перед каждым ответом ОБЯЗАТЕЛЬНО используй блок <think> для размышлений. "
        "В блоке <think> ОБЯЗАТЕЛЬНО проверь: указан ли в вопросе объем работ? "
        "Если да - какие документы соответствуют этому объему работ? "
        "Какие документы нужно ИСКЛЮЧИТЬ из-за несоответствия объему работ?\n"
        "Формат ответа:\n"
        "<think>\n"
        "Твои размышления здесь: анализируй вопрос, определяй объем работ (если указан), "
        "определяй какие документы релевантны и соответствуют объему работ, "
        "планируй структуру ответа, думай о том, как лучше представить информацию.\n"
        "</think>\n\n"
        "После блока </think> давай финальный ответ пользователю."
    )


class TPChatStreamView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        message = request.data.get('message')
        ollama_config = request.data.get('ollama_config')
        session_id = request.data.get('session_id')
        if isinstance(ollama_config, str):
            try:
                ollama_config = json.loads(ollama_config)
            except (json.JSONDecodeError, TypeError):
                ollama_config = None
        if not message or not message.strip():
            return Response({
                'success': False,
                'error': 'Не указано сообщение'
            }, status=status.HTTP_400_BAD_REQUEST)
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id, user=request.user, module='tp')
            except ChatSession.DoesNotExist:
                session = None
        else:
            session = None
        if not session:
            session = ChatSession.objects.create(
                user=request.user,
                module='tp',
                title=message[:50] if message else 'Новый чат техпроцессов',
                metadata={}
            )
        ChatMessage.objects.create(
            session=session,
            message_type=ChatMessage.MESSAGE_TYPE_USER,
            content=message,
            metadata={'ollama_config': ollama_config} if ollama_config else {}
        )

        def event_stream():
            try:
                request_started_at = timezone.now()
                tp_documents = TechnologicalProcessDocument.objects.filter(
                    user=request.user,
                    session=session
                ).order_by('-created_at')
                documents_content = []
                for doc in tp_documents:
                    if doc.markdown_content:
                        documents_content.append(f"## {doc.title}\n\n{doc.markdown_content}\n\n")
                all_documents_markdown = "\n".join(documents_content)
                runtime_config, client = create_ollama_client(ollama_config)
                temperature = (ollama_config or {}).get('temperature', 0.3)
                max_tokens = (ollama_config or {}).get('max_tokens', 4096)
                top_p = (ollama_config or {}).get('top_p', 0.9)
                top_k = (ollama_config or {}).get('top_k', 40)
                repeat_penalty = (ollama_config or {}).get('repeat_penalty', 1.1)
                seed = (ollama_config or {}).get('seed')
                system_prompt = _tp_system_prompt()
                user_prompt_parts = []
                if all_documents_markdown:
                    user_prompt_parts.append(f"Загруженные документы техпроцессов:\n\n{all_documents_markdown}\n\n")
                else:
                    user_prompt_parts.append(
                        "Внимание: Загруженных документов техпроцессов нет. "
                        "Попроси пользователя загрузить документы для работы с техпроцессами.\n\n"
                    )
                user_prompt_parts.append(f"Вопрос пользователя: {message}")
                user_prompt_parts.append(
                    "\nКРИТИЧЕСКИ ВАЖНО: Фильтрация по объему работ\n"
                    "Если в вопросе указан объем работ (ТР-1, ТР-2, ТО-1, ТО-2, ТО-3 и т.д.), "
                    "используй ТОЛЬКО документы, соответствующие этому объему работ. "
                    "Документы других объемов работ НЕ должны использоваться.\n\n"
                    "ОБЯЗАТЕЛЬНО используй блок <think> перед ответом. "
                    "В блоке <think> ОБЯЗАТЕЛЬНО:\n"
                    "1. Определи, указан ли в вопросе объем работ (ТР-1, ТР-2, ТО-1, ТО-2, ТО-3 и т.д.)\n"
                    "2. Если объем работ указан - определи какие документы соответствуют этому объему работ\n"
                    "3. Явно исключи документы, которые НЕ соответствуют указанному объему работ\n"
                    "4. Спланируй структуру ответа\n\n"
                    "Формат ответа:\n"
                    "<think>\n"
                    "Твои размышления здесь\n"
                    "</think>\n\n"
                    "Финальный ответ здесь.\n\n"
                    "Ответь на вопрос, используя информацию из загруженных документов техпроцессов. "
                    "Если информация найдена в документах, обязательно укажи название документа. "
                    "Если информации нет в документах, сообщи об этом."
                )
                user_prompt = "\n".join(user_prompt_parts)
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
                previous_messages = session.messages.order_by('created_at')[:10]
                chat_history = []
                for msg in previous_messages:
                    if msg.message_type == ChatMessage.MESSAGE_TYPE_USER:
                        chat_history.append({"role": "user", "content": msg.content})
                    elif msg.message_type == ChatMessage.MESSAGE_TYPE_ASSISTANT:
                        chat_history.append({"role": "assistant", "content": msg.content})
                messages = [messages[0]] + chat_history + [messages[1]]
                streaming_chunks_queue = Queue()
                result_container = {}
                exception_container = {}

                def stream_callback(text):
                    streaming_chunks_queue.put(text)

                def run_chat():
                    try:
                        result = client.chat(
                            messages,
                            temperature=temperature,
                            num_predict=max_tokens,
                            seed=seed,
                            stream=True,
                            stream_callback=stream_callback,
                        )
                        result_container['response'] = result.strip()
                    except Exception as e:
                        exception_container['error'] = e
                    finally:
                        streaming_chunks_queue.put(None)

                chat_thread = threading.Thread(target=run_chat)
                chat_thread.start()
                while chat_thread.is_alive() or not streaming_chunks_queue.empty():
                    try:
                        chunk = streaming_chunks_queue.get(timeout=0.1)
                        if chunk is None:
                            break
                        yield f"data: {json.dumps({'type': 'chunk', 'text': chunk}, ensure_ascii=False)}\n\n"
                    except Empty:
                        continue
                chat_thread.join(timeout=5.0)
                if 'error' in exception_container:
                    raise exception_container['error']
                response_received_at = timezone.now()
                full_response = result_container.get('response', '')
                logger.info(f"[TP Chat] Полный ответ от LLM (длина: {len(full_response)}):\n{full_response}")
                processing_time = int((response_received_at - request_started_at).total_seconds() * 1000)
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
                    processing_time_ms=processing_time,
                    metadata=message_metadata
                )
                session.updated_at = timezone.now()
                session.save(update_fields=['updated_at'])
                done_event = {
                    'type': 'done',
                    'full_response': full_response,
                    'session_id': str(session.id),
                    'message_id': str(assistant_message.id),
                    'processing_time_ms': processing_time,
                    'timestamp': assistant_message.created_at.isoformat(),
                }
                yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"Ошибка в TPChatStreamView: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response
