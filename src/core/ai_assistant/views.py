from typing import Tuple, cast
import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.http import StreamingHttpResponse, FileResponse
from django.utils import timezone
import json
import math
from datetime import datetime

from src.core.bi_analysis.bi_datasets.models import FileUpload, Dataset
from .fast_bi_service import FastBIService, DEFAULT_MODEL, OLLAMA_BASE_URL
from .config import build_runtime_config
from .llm_clients import build_llm_client, LLMClientError
from .llm_utils import create_ollama_client as _create_ollama_client
from .intent_detector import IntentDetector, UserIntent, detect_intent, select_chart_columns
from src.core.bi_analysis.bi_charts.models import Chart
from src.core.utils.mixins import SwaggerSafeMixin
from .models import ChatSession, ChatMessage, KnowledgeDocument, KnowledgeChunk
from .skills import get_skills_manager
from .skills.integration import build_skills_prompt, execute_skill_from_llm_response
from .rag import (
    OllamaEmbeddingsService,
    RAGRetrievalService,
    RAGRetrievalError,
    RAGIndexingService,
    RAGIndexingError,
    DocumentParserService,
    DocumentParseError,
)
from src.config.settings.ai_assistant import (
    OLLAMA_BASE_URL,
    OLLAMA_EMBEDDINGS_MODEL,
    RAG_CHUNK_SIZE,
    RAG_CHUNK_OVERLAP,
    RAG_TOP_K,
    RAG_SIMILARITY_THRESHOLD,
    RAG_MAX_CONTEXT_LENGTH,
    RAG_ENABLED,
    AI_ASSISTANT_REQUEST_TIMEOUT,
)
import pandas as pd
import numpy as np
from scipy import signal, stats

logger = logging.getLogger(__name__)

# Глобальный экземпляр сервиса математики (ленивая инициализация)




def _sanitize_for_json(obj):
    """
    Рекурсивно очищает объект от значений, которые не поддерживаются JSON.
    NaN, Infinity, -Infinity заменяются на None.
    """
    # Ранний выход для простых типов
    if obj is None:
        return None
    if isinstance(obj, (str, int, bool)):
        return obj
    if isinstance(obj, bytes):
        return obj.decode('utf-8', errors='ignore')
    
    # Оптимизация для float - самый частый случай
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    
    # Оптимизация для numpy/pandas типов
    if isinstance(obj, (np.floating, np.integer)):
        if isinstance(obj, np.floating):
            val = float(obj)
            if math.isnan(val) or math.isinf(val):
                return None
            return val
        return int(obj)
    
    # Проверка на numpy arrays и pandas структуры - обрабатываем их отдельно
    if isinstance(obj, np.ndarray):
        return [_sanitize_for_json(item) for item in obj.tolist()]
    
    if isinstance(obj, pd.Series):
        return [_sanitize_for_json(item) for item in obj.tolist()]
    
    if isinstance(obj, pd.DataFrame):
        # DataFrame преобразуем в список словарей (records)
        return obj.replace({np.nan: None, pd.NA: None}).to_dict(orient='records')
    
    # Проверка на NaN/None только для скалярных значений (не массивов)
    # pd.isna() для массивов возвращает массив, что вызывает ошибку в if
    try:
        if not isinstance(obj, (list, tuple, dict, np.ndarray, pd.Series, pd.DataFrame)):
            if pd.isna(obj):
                return None
    except (TypeError, ValueError):
        # Если pd.isna() не может обработать тип, пропускаем
        pass
    
    # Словари
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    
    # Списки
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(item) for item in obj]
    
    # Для остальных типов пробуем преобразовать в строку
    try:
        return str(obj)
    except Exception:
        return None


def _safe_json_dumps(obj, **kwargs):
    """Безопасная JSON сериализация с обработкой NaN/Infinity."""
    # Оптимизированные параметры JSON для скорости
    default_kwargs = {
        'ensure_ascii': False,
        'separators': (',', ':'),  # Без пробелов - быстрее и меньше размер
        'check_circular': False,   # Если уверены, что нет циклов
    }
    default_kwargs.update(kwargs)
    return json.dumps(_sanitize_for_json(obj), **default_kwargs)


class UserFilesListView(APIView):
    """
    GET /api/ai_assistant/files/
    Получить список загруженных файлов пользователя из BI модуля
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        files = FileUpload.objects.filter(owner=request.user).order_by('-uploaded_at')
        
        data = []
        for f in files:
            data.append({
                'id': f.id,
                'name': f.name,
                'original_filename': f.original_filename,
                'file_type': f.file_type,
                'uploaded_at': f.uploaded_at.isoformat() if f.uploaded_at else None,
                'file_path': f.file.path if f.file else None,
            })
        
        return Response({
            'success': True,
            'files': data,
            'count': len(data),
        })


# Глобальные экземпляры RAG сервисов (ленивая инициализация)
_rag_embeddings_service: OllamaEmbeddingsService | None = None
_rag_retrieval_service: RAGRetrievalService | None = None


def _get_rag_services(ollama_config=None):
    """
    Получает или создает RAG сервисы (embeddings и retrieval)
    
    Args:
        ollama_config: Настройки Ollama (опционально, берет из config если не указано)
        
    Returns:
        Кортеж (embeddings_service, retrieval_service)
    """
    global _rag_embeddings_service, _rag_retrieval_service
    
    # Получаем настройки Ollama для embeddings
    base_url = OLLAMA_BASE_URL
    embeddings_model = OLLAMA_EMBEDDINGS_MODEL
    
    if ollama_config:
        base_url = ollama_config.get('base_url', base_url)
        embeddings_model = ollama_config.get('embeddings_model', embeddings_model)
    
    # Создаем или обновляем сервисы если настройки изменились
    if (_rag_embeddings_service is None or 
        _rag_embeddings_service._base_url != base_url or 
        _rag_embeddings_service._model != embeddings_model):
        _rag_embeddings_service = OllamaEmbeddingsService(
            base_url=base_url,
            model=embeddings_model,
            request_timeout=AI_ASSISTANT_REQUEST_TIMEOUT,
        )
    
    if _rag_retrieval_service is None:
        _rag_retrieval_service = RAGRetrievalService(
            embeddings_service=_rag_embeddings_service,
            top_k=RAG_TOP_K,
            similarity_threshold=RAG_SIMILARITY_THRESHOLD,
        )
    
    return _rag_embeddings_service, _rag_retrieval_service


def _get_rag_context(query: str, user, ollama_config=None, enabled=None, document_ids=None):
    """
    Получает контекст из базы знаний RAG для запроса пользователя
    
    Args:
        query: Запрос пользователя
        user: Пользователь (для фильтрации документов)
        ollama_config: Настройки Ollama (опционально)
        enabled: Переопределить глобальную настройку RAG_ENABLED
        document_ids: Список ID документов для ограничения поиска (опционально)
        
    Returns:
        Кортеж (context, chunks_metadata):
        - context: Отформатированный контекст для промпта (пустая строка если RAG отключен или нет результатов)
        - chunks_metadata: Список метаданных найденных chunks (пустой список если RAG отключен или нет результатов)
    """
    # Проверяем, включен ли RAG
    if enabled is None:
        enabled = RAG_ENABLED
    
    if not enabled:
        return "", []
    
    try:
        embeddings_service, retrieval_service = _get_rag_services(ollama_config)
        
        # Получаем релевантные chunks и формируем контекст
        context, chunks = retrieval_service.retrieve_and_build_context(
            query=query,
            user=user,
            max_context_length=RAG_MAX_CONTEXT_LENGTH,
            document_ids=document_ids,
        )
        
        return context, chunks
        
    except RAGRetrievalError as e:
        # Логируем ошибку, но не прерываем работу чата
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Ошибка RAG retrieval: {e}")
        return "", []
    except Exception as e:
        # Логируем неожиданные ошибки
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Неожиданная ошибка RAG retrieval: {e}", exc_info=True)
        return "", []


class BIQueryView(APIView):
    """
    POST /api/ai_assistant/bi_query/
    Отправить вопрос к выбранному файлу через fast_bi
    
    Body:
    {
        "file_id": 123,
        "question": "Какая средняя цена по категориям?",
        "want_commentary": true,
        "stream": true  // опционально, для streaming
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        file_id = request.data.get('file_id')
        question = request.data.get('question')
        want_commentary = request.data.get('want_commentary', True)
        use_stream = request.data.get('stream', True)  # По умолчанию streaming включен
        ollama_config = request.data.get('ollama_config')  # Настройки Ollama из module-config
        session_id = request.data.get('session_id')  # ID сессии чата
        module = 'bi'  # BI модуль
        
        if not file_id:
            return Response({
                'success': False,
                'error': 'Не указан file_id'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not question or not question.strip():
            return Response({
                'success': False,
                'error': 'Не указан вопрос'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Получаем файл пользователя
        file_upload = get_object_or_404(FileUpload, id=file_id, owner=request.user)
        
        if not file_upload.file:
            return Response({
                'success': False,
                'error': 'Файл не найден на диске'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Получаем или создаем сессию чата
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id, user=request.user, module=module)
            except ChatSession.DoesNotExist:
                session = None
        else:
            session = None
        
        if not session:
            # Создаем новую сессию с названием на основе файла
            session = ChatSession.objects.create(
                user=request.user,
                module=module,
                title=f"BI: {file_upload.name}",
                metadata={'file_id': file_id, 'file_name': file_upload.name}
            )
        
        # Сохраняем сообщение пользователя
        user_message = ChatMessage.objects.create(
            session=session,
            message_type=ChatMessage.MESSAGE_TYPE_USER,
            content=question,
            metadata={
                'file_id': file_id,
                'file_name': file_upload.name,
                'ollama_config': ollama_config,
            } if ollama_config else {
                'file_id': file_id,
                'file_name': file_upload.name,
            }
        )
        
        # Если запрошен streaming режим
        if use_stream:
            return self._streaming_response(
                file_upload, question, want_commentary, ollama_config, 
                session, user_message, request.user
            )
        
        # Обычный режим (без streaming)
        return self._regular_response(
            file_upload, question, want_commentary, ollama_config, 
            session, user_message, request.user
        )
    
    def _streaming_response(self, file_upload, question, want_commentary, ollama_config=None, session=None, user_message=None, user=None):
        """Возвращает streaming ответ через Server-Sent Events."""
        chart_already_created = False
        
        def event_stream():
            nonlocal chart_already_created
            # Используем локальную переменную для вопроса (можем изменить её)
            current_question = question
            service = None
            assistant_message = None
            request_started_at = timezone.now()
            
            try:
                # Получаем контекст из последних 10 сообщений сессии
                chat_context = []
                if session:
                    last_messages = ChatMessage.objects.filter(
                        session=session
                    ).order_by('-created_at')[:10]
                    
                    # Преобразуем в формат для FastBIService (в обратном порядке - от старых к новым)
                    for msg in reversed(last_messages):
                        chat_context.append({
                            'type': msg.message_type,
                            'content': msg.content,
                            'metadata': msg.metadata or {}
                        })
                
                # Инициализируем сервис с настройками модуля и контекстом
                service = FastBIService(
                    ollama_config=ollama_config,
                    chat_context=chat_context
                )
                
                # Отправляем начальное событие
                yield f"data: {json.dumps({'type': 'start', 'message': 'Начинаю обработку...'})}\n\n"
                
                # Определяем намерение пользователя через контекстный анализ
                intent_result = self._detect_user_intent(current_question, chat_context)
                should_create_chart = intent_result.intent == UserIntent.CHART and intent_result.confidence >= 0.5
                
                # Отправляем debug-информацию о намерении
                yield f"data: {json.dumps({'type': 'debug', 'text': f'Intent: {intent_result.intent.value}, confidence: {intent_result.confidence:.2f}, reason: {intent_result.reason}'}, ensure_ascii=False)}\n\n"
                
                # Если это запрос на график, проверяем есть ли данные в предыдущем сообщении
                if should_create_chart and (session or intent_result.use_previous_data):
                    last_data_message = ChatMessage.objects.filter(
                        session=session,
                        message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT,
                        metadata__isnull=False
                    ).exclude(
                        metadata__data__isnull=True
                    ).order_by('-created_at').first()
                    
                    if last_data_message and last_data_message.metadata:
                        bi_data = last_data_message.metadata.get("data", [])
                        bi_columns = last_data_message.metadata.get("columns", [])
                        
                        if bi_data and bi_columns:
                            # Есть данные - создаём график сразу
                            logger.info(f"BI: Создание графика из предыдущих данных - строк: {len(bi_data)}, колонок: {len(bi_columns)}, chart_type={intent_result.chart_type}")
                            yield f"data: {json.dumps({'type': 'stage', 'message': 'Создаю график...'}, ensure_ascii=False)}\n\n"
                            chart_info = self._create_bi_chart(
                                question=current_question,
                                data=bi_data,
                                columns=bi_columns,
                                session=session,
                                chart_type=intent_result.chart_type
                            )
                            
                            if chart_info:
                                skill_name = 'Графики'
                                skill_call = {'tool': 'create_chart', 'parameters': {'title': chart_info.get('title')}}
                                
                                # Сохраняем сообщение ассистента с графиком
                                response_received_at = timezone.now()
                                processing_time = int((response_received_at - request_started_at).total_seconds() * 1000)
                                
                                commentary_text = f"График '{chart_info.get('title')}' создан на основе данных из предыдущего ответа."
                                
                                assistant_message = ChatMessage.objects.create(
                                    session=session,
                                    message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT,
                                    content=commentary_text,
                                    request_started_at=request_started_at,
                                    response_received_at=response_received_at,
                                    processing_time_ms=processing_time,
                                    metadata={
                                        'file_id': file_upload.id,
                                        'file_name': file_upload.name,
                                        'skill_name': skill_name,
                                        'skill_call': skill_call,
                                        'chart_config': chart_info,
                                    }
                                )
                                
                                # Отправляем график
                                yield f"data: {json.dumps({
                                    'type': 'chart_created',
                                    'chart_config': chart_info,
                                }, ensure_ascii=False)}\n\n"
                                
                                # Отправляем информацию о сессии
                                yield f"data: {json.dumps({
                                    'type': 'session_info',
                                    'session_id': str(session.id),
                                    'message_id': str(assistant_message.id),
                                    'processing_time_ms': processing_time,
                                    'skill_name': skill_name,
                                    'skill_call': skill_call,
                                    'chart_config': chart_info,
                                }, ensure_ascii=False)}\n\n"
                                
                                # Обновляем время сессии
                                session.updated_at = timezone.now()
                                session.save(update_fields=['updated_at'])
                                
                                chart_already_created = True
                                return  # Выходим, не вызывая service.ask
                    else:
                        # Нет данных в предыдущем сообщении - если это просто "График", 
                        # заменяем вопрос на запрос всех данных
                        if current_question.lower().strip() in ['график', 'диаграмма', 'построй график', 'создай график']:
                            logger.info(f"BI: Запрос на график без предыдущих данных, заменяю вопрос на 'Покажи все данные'")
                            current_question = "Покажи все данные"
                
                # Загружаем файл
                yield f"data: {json.dumps({'type': 'stage', 'message': 'Загружаю файл...'})}\n\n"
                load_result = service.load_file(
                    file_path=file_upload.file.path,
                    table_name="user_data"
                )
                
                if not load_result.get('success'):
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Ошибка загрузки файла'})}\n\n"
                    return
                
                # Оптимизация: используем Queue для эффективной передачи событий между потоками
                from queue import Queue, Empty
                import threading
                
                streaming_events_queue = Queue()
                result_container = {}
                exception_container = {}
                commentary_parts = []
                
                def run_ask():
                    try:
                        def immediate_callback(event):
                            streaming_events_queue.put(event)
                        result_container['result'] = service.ask(current_question, want_commentary=want_commentary, stream_callback=immediate_callback)
                    except Exception as e:
                        exception_container['error'] = e
                    finally:
                        # Отправляем сигнал завершения
                        streaming_events_queue.put(None)
                
                # Запускаем в отдельном потоке
                ask_thread = threading.Thread(target=run_ask)
                ask_thread.start()
                
                # Отправляем события по мере их поступления
                # Оптимизация: используем блокирующее ожидание вместо активного polling
                while ask_thread.is_alive() or not streaming_events_queue.empty():
                    try:
                        # Блокируемся максимум на 0.1 секунды - эффективнее чем sleep в цикле
                        event = streaming_events_queue.get(timeout=0.1)
                        if event is None:  # Сигнал завершения
                            break
                        
                        # Собираем комментарий для сохранения
                        if event.get('type') == 'commentary' and event.get('text'):
                            commentary_parts.append(event['text'])
                        
                        yield f"data: {_safe_json_dumps(event, ensure_ascii=False)}\n\n"
                    except Empty:
                        # Если очередь пуста, продолжаем проверять поток
                        continue
                
                ask_thread.join(timeout=5.0)  # Таймаут на завершение потока
                
                # Проверяем ошибки
                if 'error' in exception_container:
                    raise exception_container['error']
                
                result = result_container.get('result', {})
                response_received_at = timezone.now()
                processing_time = int((response_received_at - request_started_at).total_seconds() * 1000)
                
                # Отправляем финальные данные
                if result['success']:
                    final_data = {
                        'type': 'complete',
                        'file_name': file_upload.name,
                        'question': current_question,
                        'sql': result['sql'],
                        'data': result['data'],
                        'rows': result['rows'],
                        'columns': result['columns'],
                    }
                    # Используем _safe_json_dumps для обработки NaN/Infinity в данных
                    yield f"data: {_safe_json_dumps(final_data, ensure_ascii=False)}\n\n"
                    
                    # Проверяем через LLM нужно ли создать документ или график
                    document_info = None
                    chart_info = None
                    skill_name = None
                    skill_call = None
                    
                    # Спрашиваем у LLM нужно ли создать документ
                    should_create_doc = self._check_document_intent(
                        question=current_question,
                        commentary=''.join(commentary_parts) if commentary_parts else result.get('comment', ''),
                        ollama_config=ollama_config
                    )
                    
                    # Проверяем нужно ли создать график (если ещё не создан)
                    # Используем уже определённое намерение из intent_result
                    if not chart_already_created:
                        should_create_chart = intent_result.intent == UserIntent.CHART and intent_result.confidence >= 0.5
                    else:
                        should_create_chart = False
                    
                    logger.info(f"BI: Проверка графика - should_create_chart={should_create_chart}, intent={intent_result.intent.value}, confidence={intent_result.confidence:.2f}, data={bool(result.get('data'))}")
                    
                    if should_create_chart and result.get('data') and result.get('columns'):
                        yield f"data: {json.dumps({'type': 'stage', 'message': 'Создаю график...'}, ensure_ascii=False)}\n\n"
                        chart_info = self._create_bi_chart(
                            question=current_question,
                            data=result.get('data', []),
                            columns=result.get('columns', []),
                            session=session,
                            chart_type=intent_result.chart_type
                        )
                        logger.info(f"BI: Результат создания графика - chart_info={bool(chart_info)}")
                        if chart_info:
                            skill_name = 'Графики'
                            skill_call = {'tool': 'create_chart', 'parameters': {'title': chart_info.get('title')}}
                            yield f"data: {json.dumps({
                                'type': 'chart_created',
                                'chart_config': chart_info,
                            }, ensure_ascii=False)}\n\n"
                    
                    if should_create_doc:
                        yield f"data: {json.dumps({'type': 'stage', 'message': 'Создаю документ...'}, ensure_ascii=False)}\n\n"
                        document_info = self._create_bi_document(
                            file_name=file_upload.name,
                            question=current_question,
                            commentary=''.join(commentary_parts) if commentary_parts else result.get('comment', ''),
                            data=result.get('data', []),
                            columns=result.get('columns', []),
                            request=self.request,
                            sql=result.get('sql', ''),
                            user=user
                        )
                        if document_info:
                            skill_name = 'Документы'
                            skill_call = {'tool': 'document_creation', 'parameters': {'title': document_info.get('title')}}
                            yield f"data: {json.dumps({
                                'type': 'document_created',
                                'filename': document_info.get('filename'),
                                'download_url': document_info.get('download_url'),
                            }, ensure_ascii=False)}\n\n"
                    
                    # Сохраняем ответ ассистента
                    if session and user_message:
                        commentary_text = ''.join(commentary_parts) if commentary_parts else result.get('comment', '')
                        
                        # Добавляем ссылку на документ в текст если он был создан
                        if document_info:
                            commentary_text += f"\n\n[{document_info.get('filename')}]({document_info.get('download_url')})"
                        
                        message_metadata = {
                            'file_id': file_upload.id,
                            'file_name': file_upload.name,
                            'sql': result.get('sql'),
                            'rows': result.get('rows'),
                            'columns': result.get('columns'),
                            'data': result.get('data'),
                            'skill_name': skill_name,
                            'skill_call': skill_call,
                        }
                        if ollama_config:
                            message_metadata['ollama_config'] = ollama_config
                        if document_info:
                            message_metadata['document'] = document_info
                        if chart_info:
                            message_metadata['chart_config'] = chart_info
                        
                        assistant_message = ChatMessage.objects.create(
                            session=session,
                            message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT,
                            content=commentary_text,
                            request_started_at=request_started_at,
                            response_received_at=response_received_at,
                            processing_time_ms=processing_time,
                            metadata=message_metadata
                        )
                        
                        # Обновляем время сессии
                        session.updated_at = timezone.now()
                        session.save(update_fields=['updated_at'])
                        
                        # Отправляем информацию о сессии
                        session_info_event = {
                            'type': 'session_info',
                            'session_id': str(session.id),
                            'message_id': str(assistant_message.id),
                            'processing_time_ms': processing_time,
                            'skill_name': skill_name,
                            'skill_call': skill_call,
                        }
                        if chart_info:
                            session_info_event['chart_config'] = chart_info
                        yield f"data: {json.dumps(session_info_event, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'error', 'message': result.get('error', 'Ошибка')})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
            
            finally:
                if service:
                    service.close()
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response
    
    def _check_document_intent(self, question: str, commentary: str, ollama_config=None) -> bool:
        """
        Проверяет, хочет ли пользователь создать документ/отчёт.
        Сначала проверяет ключевые слова, затем через LLM если неясно.
        """
        question_lower = question.lower()
        
        # Быстрая проверка очевидных случаев по ключевым словам
        doc_keywords = [
            'создай отчёт', 'создай отчет', 'сделай отчёт', 'сделай отчет',
            'создай документ', 'сделай документ', 'сформируй отчёт', 'сформируй отчет',
            'выгрузи отчёт', 'выгрузи отчет', 'экспортируй', 'создай word',
            'создай pdf', 'сохрани как документ', 'сгенерируй отчёт', 'сгенерируй отчет',
            'выгрузи в файл', 'сохрани в файл', 'скачать отчёт', 'скачать отчет',
        ]
        
        # Если есть явное ключевое слово - сразу создаём документ
        if any(keyword in question_lower for keyword in doc_keywords):
            logger.info(f"Создание документа: найдено ключевое слово в вопросе '{question}'")
            return True
        
        # Если вопрос короткий и содержит слово "отчёт" или "документ" - создаём
        if len(question_lower.split()) <= 5 and ('отчёт' in question_lower or 'отчет' in question_lower or 'документ' in question_lower):
            logger.info(f"Создание документа: короткий вопрос со словом отчёт/документ '{question}'")
            return True
        
        # Для остальных случаев используем LLM
        try:
            runtime_config = build_runtime_config(ollama_config)
            
            model = runtime_config.model or 'mistral'
            base_url = runtime_config.base_url or OLLAMA_BASE_URL
            
            client = build_llm_client(
                provider=runtime_config.provider.value,
                model=model,
                base_url=base_url,
                request_timeout=15.0,
                stream_timeout=15.0,
                concurrency_limit=runtime_config.concurrency_limit,
                max_retries=1,
                keep_alive=runtime_config.keep_alive,
                provider_config=runtime_config.provider_config,
                device_config=runtime_config.device_config,
            )
            
            prompt = f"""Вопрос: "{question}"

Пользователь хочет СОЗДАТЬ ФАЙЛ (документ/отчёт для скачивания)?
Ответь ОДНИМ словом: ДА или НЕТ"""

            response = client.complete(
                prompt,
                temperature=0.0,
                stream=False,
            ).strip().upper()
            
            logger.info(f"LLM проверка документа: вопрос='{question}', ответ='{response}'")
            
            result = 'ДА' in response or 'YES' in response or 'DA' in response
            return result
            
        except Exception as e:
            logger.warning(f"Ошибка проверки намерения создать документ: {e}")
            return False
    
    def _detect_user_intent(self, question: str, chat_context: list | None = None):
        """
        Определяет намерение пользователя на основе контекста.
        Использует модульный IntentDetector без LLM-вызовов.
        
        Args:
            question: Вопрос пользователя
            chat_context: Контекст чата
            
        Returns:
            IntentResult с определённым намерением
        """
        return detect_intent(question, chat_context or [])
    
    def _check_chart_intent(self, question: str, ollama_config=None, session=None, chat_context: list | None = None) -> bool:
        """
        Проверяет, хочет ли пользователь создать график.
        Использует контекстный анализ без LLM-вызовов.
        
        Args:
            question: Вопрос пользователя
            ollama_config: Конфиг Ollama (не используется, для совместимости)
            session: Сессия чата (для получения контекста если chat_context не передан)
            chat_context: Контекст чата
            
        Returns:
            True если нужно создать график
        """
        # Если контекст не передан, получаем из сессии
        if chat_context is None and session:
            chat_context = []
            last_messages = ChatMessage.objects.filter(
                session=session
            ).order_by('-created_at')[:10]
            
            for msg in reversed(last_messages):
                chat_context.append({
                    'type': msg.message_type,
                    'content': msg.content,
                    'metadata': msg.metadata or {}
                })
        
        # Используем IntentDetector
        intent_result = detect_intent(question, chat_context)
        
        # Возвращаем True если намерение - график с достаточной уверенностью
        return intent_result.intent == UserIntent.CHART and intent_result.confidence >= 0.5
    
    def _create_bi_chart(self, question: str, data: list, columns: list, session=None, chart_type: str | None = None):
        """
        Создаёт график на основе данных BI анализа.
        Использует ChartSkill для генерации конфигурации.
        
        Args:
            question: Вопрос пользователя
            data: Данные для графика
            columns: Колонки данных
            session: Сессия чата
            chart_type: Тип графика (bar, line, pie, area, scatter). Если None - определяется автоматически.
        """
        logger.info(f"Создание графика: data_len={len(data) if data else 0}, columns={columns}, chart_type={chart_type}")
        
        if not data or not columns:
            logger.warning(f"Недостаточно данных для графика: data={bool(data)}, columns={bool(columns)}")
            return None
        
        try:
            from .skills import get_skills_manager
            
            skills_manager = get_skills_manager()
            chart_skill = skills_manager.get_skill('create_chart')
            
            if not chart_skill:
                logger.error("Навык create_chart не найден")
                return None
            
            # Используем переданный тип графика или определяем автоматически
            if not chart_type:
                question_lower = question.lower()
                chart_type = "bar"  # По умолчанию
                
                if 'линейный' in question_lower or 'тренд' in question_lower or 'временной' in question_lower:
                    chart_type = "line"
                elif 'круговой' in question_lower or 'pie' in question_lower or 'доля' in question_lower:
                    chart_type = "pie"
                elif 'площадной' in question_lower or 'area' in question_lower:
                    chart_type = "area"
                elif 'точечный' in question_lower or 'scatter' in question_lower or 'корреляция' in question_lower:
                    chart_type = "scatter"
            
            # Используем интеллектуальный выбор колонок на основе вопроса
            logger.info(f"=== DEBUG: Выбор колонок для графика ===")
            logger.info(f"Вопрос: {question}")
            logger.info(f"Колонки (первые 15): {columns[:15]}")
            
            x_col, y_col, title = select_chart_columns(question, columns, data)
            
            logger.info(f"Результат выбора: X={x_col}, Y={y_col}, title={title}")
            logger.info(f"=" * 50)
            
            if not x_col or not y_col:
                logger.warning(f"Не удалось выбрать колонки для графика: x={x_col}, y={y_col}")
                return None
            
            # Преобразуем данные BI в формат для графика
            chart_data = []
            if chart_type == "pie":
                # Для pie используем выбранные колонки
                for row in data[:20]:  # Ограничиваем до 20 элементов
                    if isinstance(row, dict):
                        label = str(row.get(x_col, ""))
                        try:
                            value = row.get(y_col)
                            if value is None or value == '' or value == '—':
                                value = 0
                            else:
                                value = float(value)
                        except (ValueError, TypeError):
                            value = 0
                        if label and value:
                            chart_data.append({"label": label, "value": value})
            else:
                # Для остальных типов используем выбранные колонки
                for row in data[:100]:  # Ограничиваем до 100 элементов
                    if isinstance(row, dict):
                        x = row.get(x_col, "")
                        try:
                            y_val = row.get(y_col)
                            if y_val is None or y_val == '' or y_val == '—':
                                y = 0
                            else:
                                y = float(y_val)
                        except (ValueError, TypeError):
                            y = 0
                        if x is not None and x != "":
                            chart_data.append({"x": str(x), "y": y})
                
                logger.info(f"Преобразовано {len(chart_data)} точек данных для графика")
            
            if not chart_data:
                logger.warning(f"Не удалось преобразовать данные BI в формат для графика. X={x_col}, Y={y_col}")
                return None
            
            logger.info(f"Создан график: тип={chart_type}, точек={len(chart_data)}")
            
            # Вызываем навык
            skill_result = chart_skill.execute(
                query=question,
                parameters={
                    "chart_type": chart_type,
                    "title": title,
                    "data": chart_data,
                    "x_axis_label": x_col or "",
                    "y_axis_label": y_col or "",
                    "series_name": y_col or "Данные",
                },
                context={'session': session, 'module': 'bi'}
            )
            
            if skill_result and skill_result.success and skill_result.metadata:
                return skill_result.metadata.get('chart_config')
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка создания графика: {e}", exc_info=True)
            return None
    
    def _create_bi_document(self, file_name, question, commentary, data, columns, sql, user=None, request=None):
        """Создаёт документ с результатами BI анализа."""
        # Формирование Word отчетов отключено
        logger.warning("Создание Word документов для BI отчетов отключено")
        return None
    
    def _regular_response(self, file_upload, question, want_commentary, ollama_config=None, session=None, user_message=None, user=None):
        """Возвращает обычный (не streaming) ответ."""
        try:
            request_started_at = timezone.now()
            
            # Получаем контекст из последних 10 сообщений сессии
            chat_context = []
            if session:
                last_messages = ChatMessage.objects.filter(
                    session=session
                ).order_by('-created_at')[:10]
                
                # Преобразуем в формат для FastBIService (в обратном порядке - от старых к новым)
                for msg in reversed(last_messages):
                    chat_context.append({
                        'type': msg.message_type,
                        'content': msg.content,
                        'metadata': msg.metadata or {}
                    })
            
            # Инициализируем сервис с настройками модуля и контекстом
            service = FastBIService(
                ollama_config=ollama_config,
                chat_context=chat_context
            )
            
            load_result = service.load_file(
                file_path=file_upload.file.path,
                table_name="user_data"
            )
            
            if not load_result.get('success'):
                return Response({
                    'success': False,
                    'error': 'Ошибка загрузки файла'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            result = service.ask(question, want_commentary=want_commentary)
            service.close()
            
            response_received_at = timezone.now()
            processing_time = int((response_received_at - request_started_at).total_seconds() * 1000)
            
            if result['success']:
                # Сохраняем ответ ассистента
                if session and user_message:
                    assistant_message = ChatMessage.objects.create(
                        session=session,
                        message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT,
                        content=result.get('comment', ''),
                        request_started_at=request_started_at,
                        response_received_at=response_received_at,
                        processing_time_ms=processing_time,
                        metadata={
                            'file_id': file_upload.id,
                            'file_name': file_upload.name,
                            'sql': result.get('sql'),
                            'rows': result.get('rows'),
                            'columns': result.get('columns'),
                            'data': result.get('data'),
                            'ollama_config': ollama_config,
                        } if ollama_config else {
                            'file_id': file_upload.id,
                            'file_name': file_upload.name,
                            'sql': result.get('sql'),
                            'rows': result.get('rows'),
                            'columns': result.get('columns'),
                            'data': result.get('data'),
                        }
                    )
                    
                    # Обновляем время сессии
                    session.updated_at = timezone.now()
                    session.save(update_fields=['updated_at'])
                
                return Response({
                    'success': True,
                    'file_name': file_upload.name,
                    'question': question,
                    'sql': result['sql'],
                    'data': result['data'],
                    'comment': result['comment'],
                    'rows': result['rows'],
                    'columns': result['columns'],
                    'session_id': str(session.id) if session else None,
                    'message_id': str(assistant_message.id) if session and user_message else None,
                    'processing_time_ms': processing_time,
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'error': result.get('error', 'Неизвестная ошибка'),
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OllamaStatusView(APIView):
    """
    GET /api/ai_assistant/ollama_status/
    Проверить доступность Ollama (быстрая проверка без загрузки модели)
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            _, client = _create_ollama_client({'model': DEFAULT_MODEL})
            
            # Используем быстрый health check без генерации
            health = client.check_health()
            
            if health.get('available'):
                return Response({
                    'available': True,
                    'message': 'Ollama доступен',
                    'model': DEFAULT_MODEL,
                    'model_exists': health.get('model_loaded', False),
                    'available_models': health.get('models', []),
                })
            else:
                return Response({
                    'available': False,
                    'message': health.get('error', 'Ollama недоступен'),
                })
        except Exception as e:
            return Response({
                'available': False,
                'message': f'Ошибка подключения к Ollama: {str(e)}'
            })


class EmbeddingsStatusView(APIView):
    """
    GET /api/ai_assistant/embeddings_status/
    Проверить доступность сервиса embeddings
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            embeddings_service, _ = _get_rag_services()
            health = embeddings_service.check_health()
            
            return Response({
                'success': True,
                **health,
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'available': False,
                'error': str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChartAnalysisView(APIView):
    """
    POST /api/ai_assistant/chart_analysis/
    Автоматический анализ данных графика
    
    Body:
    {
        "chart_id": 123,
        "stream": true
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        chart_id = request.data.get('chart_id')
        use_stream = request.data.get('stream', True)
        
        if not chart_id:
            return Response({
                'success': False,
                'error': 'Не указан chart_id'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Получаем график пользователя
        chart = get_object_or_404(Chart, id=chart_id, owner=request.user)
        
        # Если запрошен streaming режим
        if use_stream:
            return self._streaming_response(chart)
        
        # Обычный режим (без streaming)
        return self._regular_response(chart)
    
    def _streaming_response(self, chart):
        """Возвращает streaming ответ через Server-Sent Events."""
        def event_stream():
            try:
                # Отправляем начальное событие
                yield f"data: {json.dumps({'type': 'start', 'message': 'Начинаю анализ графика...'})}\n\n"
                
                # Получаем данные из датасета
                yield f"data: {json.dumps({'type': 'stage', 'message': 'Получаю данные из датасета...'})}\n\n"
                
                from django.db import connection
                from psycopg2 import sql
                
                # Получаем СЫРЫЕ данные из датасета БЕЗ агрегации для анализа
                # Определяем какие поля нужны
                field_names = set()
                for group_key, field_list in (chart.params or {}).items():
                    if isinstance(field_list, list):
                        for field in field_list:
                            if isinstance(field, dict):
                                field_names.add(field.get('name', ''))
                
                # Получаем имя таблицы датасета
                table_name = chart.dataset.table_ref
                
                # Определяем поле для сортировки (обычно ось X)
                x_field = None
                if chart.params and 'x' in chart.params and chart.params['x']:
                    if isinstance(chart.params['x'], list) and chart.params['x']:
                        x_field = chart.params['x'][0].get('name') if isinstance(chart.params['x'][0], dict) else None
                
                # Формируем запрос для получения ВСЕХ строк без агрегации
                if field_names:
                    select_fields = [sql.Identifier(fn) for fn in field_names if fn]
                    query = sql.SQL('SELECT {} FROM {}').format(
                        sql.SQL(', ').join(select_fields),
                        sql.Identifier(table_name)
                    )
                else:
                    # Если полей нет, берем все
                    query = sql.SQL('SELECT * FROM {}').format(sql.Identifier(table_name))
                
                # Добавляем сортировку
                if x_field:
                    query += sql.SQL(' ORDER BY {}').format(sql.Identifier(x_field))
                
                # Выполняем запрос
                with connection.cursor() as cursor:
                    cursor.execute(query)
                    columns = [col[0] for col in cursor.description]
                    rows = [
                        dict(zip(columns, row))
                        for row in cursor.fetchall()
                    ]
                
                if not rows:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Нет данных для анализа'})}\n\n"
                    return
                
                # Создаем DataFrame
                df = pd.DataFrame(rows)
                
                yield f"data: {json.dumps({'type': 'stage', 'message': '💭 Анализирую график...'})}\n\n"
                
                analysis_prompt = self._generate_analysis_prompt(chart, df)
                runtime_config, client = _create_ollama_client()
                try:
                    analysis_text = client.complete(
                        analysis_prompt,
                        temperature=runtime_config.temperature_commentary,
                        stream=False,
                    )
                except Exception as error:
                    yield f"data: {json.dumps({'type': 'error', 'message': str(error)}, ensure_ascii=False)}\n\n"
                    return
                
                if analysis_text:
                    yield f"data: {json.dumps({'type': 'commentary', 'text': analysis_text}, ensure_ascii=False)}\n\n"
                
                # Отправляем финальные данные
                final_data = {
                    'type': 'complete',
                    'chart_name': chart.name,
                    'sql': None,  # Нет SQL для анализа графика
                    'data': rows[:100],  # Отправляем первые 100 строк для отображения
                    'rows': len(rows),
                    'columns': list(df.columns),
                }
                # Используем _safe_json_dumps для обработки NaN/Infinity в данных
                yield f"data: {_safe_json_dumps(final_data, ensure_ascii=False)}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
            
            finally:
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response
    
    def _regular_response(self, chart):
        """Возвращает обычный (не streaming) ответ."""
        try:
            from django.db import connection
            from psycopg2 import sql
            
            # Получаем СЫРЫЕ данные из датасета БЕЗ агрегации для анализа
            field_names = set()
            for group_key, field_list in (chart.params or {}).items():
                if isinstance(field_list, list):
                    for field in field_list:
                        if isinstance(field, dict):
                            field_names.add(field.get('name', ''))
            
            # Получаем имя таблицы датасета
            table_name = chart.dataset.table_ref
            
            # Определяем поле для сортировки (обычно ось X)
            x_field = None
            if chart.params and 'x' in chart.params and chart.params['x']:
                if isinstance(chart.params['x'], list) and chart.params['x']:
                    x_field = chart.params['x'][0].get('name') if isinstance(chart.params['x'][0], dict) else None
            
            # Формируем запрос для получения ВСЕХ строк без агрегации
            if field_names:
                select_fields = [sql.Identifier(fn) for fn in field_names if fn]
                query = sql.SQL('SELECT {} FROM {}').format(
                    sql.SQL(', ').join(select_fields),
                    sql.Identifier(table_name)
                )
            else:
                # Если полей нет, берем все
                query = sql.SQL('SELECT * FROM {}').format(sql.Identifier(table_name))
            
            # Добавляем сортировку
            if x_field:
                query += sql.SQL(' ORDER BY {}').format(sql.Identifier(x_field))
            
            # Выполняем запрос
            with connection.cursor() as cursor:
                cursor.execute(query)
                columns = [col[0] for col in cursor.description]
                rows = [
                    dict(zip(columns, row))
                    for row in cursor.fetchall()
                ]
            
            if not rows:
                return Response({
                    'success': False,
                    'error': 'Нет данных для анализа'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Создаем DataFrame
            df = pd.DataFrame(rows)
            
            analysis_prompt = self._generate_analysis_prompt(chart, df)
            runtime_config, client = _create_ollama_client()
            response_text = client.complete(
                analysis_prompt,
                temperature=runtime_config.temperature_commentary,
                stream=False,
            )
            
            return Response({
                'success': True,
                'chart_name': chart.name,
                'sql': None,  # Нет SQL для анализа графика
                'data': rows[:100],  # Первые 100 строк
                'comment': response_text,
                'rows': len(rows),
                'columns': list(df.columns),
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _generate_analysis_prompt(self, chart, df):
        """Генерирует промпт для прямого анализа графика без SQL"""
        
        # Определяем тип графика
        chart_type_names = {
            'line': 'линейный график',
            'bar': 'столбчатая диаграмма',
            'pie': 'круговая диаграмма',
            'doughnut': 'кольцевая диаграмма',
            'scatter': 'точечная диаграмма',
            'radar': 'радарная диаграмма',
            'heatmap': 'тепловая карта',
        }
        
        chart_type_name = chart_type_names.get(chart.chart_type, 'график')
        
        # Получаем информацию о колонках
        numeric_columns = df.select_dtypes(include=['number']).columns.tolist()
        all_columns = df.columns.tolist()
        
        # Получаем размер данных
        rows_count = len(df)
        
        # Определяем оси графика из params
        x_axis = []
        y_axis = []
        if chart.params:
            x_fields = chart.params.get('x', [])
            y_fields = chart.params.get('y', [])
            if isinstance(x_fields, list) and x_fields:
                x_axis = [f.get('name', '') for f in x_fields if isinstance(f, dict)]
            if isinstance(y_fields, list) and y_fields:
                y_axis = [f.get('name', '') for f in y_fields if isinstance(f, dict)]
        
        # Формируем описание осей
        axes_info = ""
        if x_axis:
            axes_info += f"\n- Ось X (горизонтальная): {', '.join(x_axis)}"
        if y_axis:
            axes_info += f"\n- Ось Y (вертикальная): {', '.join(y_axis)}"
        
        # Преобразуем DataFrame в читаемый формат для модели
        # Показываем ВСЕ строки для анализа (без ограничения)
        data_preview = df.to_string(max_rows=None)
        
        # Подсчитываем базовую статистику
        stats = {}
        for col in numeric_columns:
            try:
                stats[col] = {
                    'min': float(df[col].min()),
                    'max': float(df[col].max()),
                    'mean': float(df[col].mean()),
                }
            except:
                pass
        
        stats_text = "\n".join([f"- {col}: мин={s['min']}, макс={s['max']}, среднее={s['mean']:.2f}" 
                                for col, s in stats.items()])
        
        # Определяем, что измеряется на Y (для бизнес-контекста)
        y_name = y_axis[0] if y_axis else 'значения'
        x_name = x_axis[0] if x_axis else all_columns[0]
        
        # Создаем визуальное описание данных для AI
        visual_description = self._create_visual_description(df, x_name, y_name)
        
        # МАТЕМАТИЧЕСКИЙ АНАЛИЗ - точные результаты
        math_analysis = self._analyze_data_mathematically(df, x_name, y_name)
        
        # Форматируем результаты математического анализа для промпта
        math_results = ""
        if math_analysis:
            math_results = "\n🔬 ТОЧНЫЕ РЕЗУЛЬТАТЫ МАТЕМАТИЧЕСКОГО АНАЛИЗА:\n"
            
            if math_analysis['peaks']:
                peaks_str = ", ".join([f"{x_name}={p['x']} (y={p['y']})" for p in math_analysis['peaks'][:5]])
                math_results += f"✓ ЛОКАЛЬНЫЕ МАКСИМУМЫ (пики): {peaks_str}\n"
            
            if math_analysis['troughs']:
                troughs_str = ", ".join([f"{x_name}={t['x']} (y={t['y']})" for t in math_analysis['troughs'][:5]])
                math_results += f"✓ ЛОКАЛЬНЫЕ МИНИМУМЫ (провалы): {troughs_str}\n"
            
            if math_analysis['plateaus']:
                for plateau in math_analysis['plateaus']:
                    math_results += f"✓ ПЛАТО: с {x_name}={plateau['start_x']} до {plateau['end_x']}, значение={plateau['value']}, длина={plateau['length']} точек\n"
            
            if math_analysis['anomalies']:
                anomalies_str = ", ".join([f"{x_name}={a['x']} (y={a['y']}, z={a['z_score']:.1f})" for a in math_analysis['anomalies']])
                math_results += f"✓ АНОМАЛИИ (выбросы): {anomalies_str}\n"
            
            if math_analysis['trend']:
                trend = math_analysis['trend']
                math_results += f"✓ ТРЕНД: {trend['type']}, наклон={trend['slope']:.4f}, R²={trend['r_squared']:.3f}\n"
            
            if math_analysis['correlation']:
                corr_str = ", ".join([f"{c['with']}={c['value']:.2f}" for c in math_analysis['correlation']])
                math_results += f"✓ КОРРЕЛЯЦИИ: {corr_str}\n"
        
        prompt = f"""Ты - профессиональный аналитик данных. Перед тобой {chart_type_name} "{chart.name}".

КОНТЕКСТ:{axes_info}
- По горизонтали ({x_name}): от {df[x_name].iloc[0]} до {df[x_name].iloc[-1]}
- По вертикали ({y_name}): от {df[y_name].min()} до {df[y_name].max()}
- Всего точек: {rows_count}

ВИЗУАЛЬНАЯ ХАРАКТЕРИСТИКА:
{visual_description}
{math_results}
ДАННЫЕ:
{data_preview}

СТАТИСТИКА:
{stats_text if stats_text else 'Нет числовых данных'}

ЗАДАЧА: Проанализируй этот график как визуализацию. Опиши что происходит, используя конкретные цифры и бизнес-термины.

Напиши связный анализ в свободной форме, БЕЗ заголовков и шаблонных фраз.

В своем анализе ОБЯЗАТЕЛЬНО укажи:

1) Что показывает график - опиши общую картину одним-двумя предложениями. Например: "График демонстрирует циклическое изменение показателя {y_name} с четырьмя повторяющимися циклами"

2) Как выглядит линия - опиши визуальный паттерн: линия растет / падает / волнами / стабильна, плавно или резко меняется, есть ли повторения

3) Ключевые точки с КОНКРЕТНЫМИ значениями:
   - Максимум: "{x_name}=? → {y_name}=?"
   - Минимум: "{x_name}=? → {y_name}=?"
   - Где резкие взлеты/падения

4) Статистика: среднее, диапазон изменения, на сколько изменился показатель от начала до конца

5) Бизнес-выводы: что это значит, хорошо или плохо, что рекомендуешь

ВАЖНО:
- Пиши ЕСТЕСТВЕННО, как обычный аналитик объясняет коллеге
- НЕ используй заголовки типа "## Что показывает график", "## Визуальные паттерны" и т.д.
- НЕ пиши шаблонные фразы типа "Опиши общую картину:"
- Используй конкретные ЦИФРЫ из данных, не "примерно"
- Говори про "{chart.name}" в бизнес-контексте
- Используй слова: линия растет/падает, пик в точке X, провал здесь, скачок с X до Y
- Для выделения важного используй **жирный текст**
- Пиши структурированно но БЕЗ явных заголовков"""
        
        return prompt
    
    def _analyze_data_mathematically(self, df, x_name, y_name):
        """
        Математический анализ данных с использованием научных библиотек.
        Возвращает точные результаты: экстремумы, аномалии, плато, корреляции.
        """
        try:
            y_values = np.array(df[y_name].tolist())
            x_values = df[x_name].tolist()
            
            results = {
                'peaks': [],
                'troughs': [],
                'plateaus': [],
                'anomalies': [],
                'trend': None,
                'correlation': None
            }
            
            # 1. ПОИСК ЛОКАЛЬНЫХ МАКСИМУМОВ (пиков)
            peaks, peak_properties = signal.find_peaks(y_values, prominence=0.1)
            for peak_idx in peaks:
                results['peaks'].append({
                    'x': x_values[peak_idx],
                    'y': float(y_values[peak_idx]),
                    'index': int(peak_idx)
                })
            
            # 2. ПОИСК ЛОКАЛЬНЫХ МИНИМУМОВ (провалов)
            troughs, trough_properties = signal.find_peaks(-y_values, prominence=0.1)
            for trough_idx in troughs:
                results['troughs'].append({
                    'x': x_values[trough_idx],
                    'y': float(y_values[trough_idx]),
                    'index': int(trough_idx)
                })
            
            # 3. ДЕТЕКЦИЯ ПЛАТО (участков стабильности)
            plateau_ranges = []
            if len(y_values) > 2:
                i = 0
                while i < len(y_values) - 1:
                    if abs(y_values[i] - y_values[i+1]) < 0.01:  # Практически одинаковые значения
                        start = i
                        while i < len(y_values) - 1 and abs(y_values[i] - y_values[i+1]) < 0.01:
                            i += 1
                        if i - start >= 2:  # Плато минимум из 3 точек
                            plateau_ranges.append({
                                'start_x': x_values[start],
                                'end_x': x_values[i],
                                'value': float(y_values[start]),
                                'length': i - start + 1
                            })
                    i += 1
            results['plateaus'] = plateau_ranges
            
            # 4. ВЫЯВЛЕНИЕ АНОМАЛИЙ (выбросы по z-score)
            if len(y_values) > 3:
                z_scores_raw = stats.zscore(y_values)
                z_scores: np.ndarray = np.abs(np.asarray(z_scores_raw))
                anomaly_indices = np.where(z_scores > 2)[0]  # |z-score| > 2
                for idx in anomaly_indices:
                    results['anomalies'].append({
                        'x': x_values[idx],
                        'y': float(y_values[idx]),
                        'z_score': float(z_scores[idx])
                    })
            
            # 5. ОПРЕДЕЛЕНИЕ ТРЕНДА (линейная регрессия)
            if len(y_values) > 2:
                x_numeric = np.arange(len(y_values))
                linreg_result = cast(
                    Tuple[float, float, float, float, float],
                    stats.linregress(x_numeric, y_values)
                )
                # LinregressResult: (slope, intercept, rvalue, pvalue, stderr)
                slope = linreg_result[0]
                r_value = linreg_result[2]
                
                if abs(slope) < 0.01:
                    trend_type = "стабильный"
                elif slope > 0:
                    trend_type = "восходящий"
                else:
                    trend_type = "нисходящий"
                
                results['trend'] = {
                    'type': trend_type,
                    'slope': slope,
                    'r_squared': r_value ** 2,
                    'change_per_point': slope
                }
            
            # 6. КОРРЕЛЯЦИЯ (если есть другие числовые колонки)
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if len(numeric_cols) > 1 and y_name in numeric_cols:
                correlations = []
                for col in numeric_cols:
                    if col != y_name:
                        corr = df[y_name].corr(df[col])
                        if abs(corr) > 0.5:  # Только значимые корреляции
                            correlations.append({
                                'with': col,
                                'value': float(corr)
                            })
                results['correlation'] = correlations if correlations else None
            
            return results
            
        except Exception as e:
            # Тихо игнорируем ошибки математического анализа
            return None
    
    def _create_visual_description(self, df, x_name, y_name):
        """Создает текстовое описание визуального вида графика"""
        try:
            y_values = df[y_name].tolist()
            
            if len(y_values) < 2:
                return "Недостаточно данных для визуального анализа"
            
            # Анализируем направление
            first_half_avg = sum(y_values[:len(y_values)//2]) / (len(y_values)//2)
            second_half_avg = sum(y_values[len(y_values)//2:]) / (len(y_values) - len(y_values)//2)
            
            if second_half_avg > first_half_avg * 1.1:
                trend = "📈 ВОСХОДЯЩИЙ ТРЕНД - линия идет ВВЕРХ"
            elif second_half_avg < first_half_avg * 0.9:
                trend = "📉 НИСХОДЯЩИЙ ТРЕНД - линия идет ВНИЗ"
            else:
                trend = "➡️ СТАБИЛЬНЫЙ - линия примерно на одном уровне"
            
            # Считаем изменения направления (волны)
            direction_changes = 0
            for i in range(1, len(y_values)-1):
                if (y_values[i] > y_values[i-1] and y_values[i] > y_values[i+1]) or \
                   (y_values[i] < y_values[i-1] and y_values[i] < y_values[i+1]):
                    direction_changes += 1
            
            if direction_changes > len(y_values) * 0.3:
                pattern = "🌊 ВОЛНООБРАЗНЫЙ паттерн - много пиков и провалов"
            elif direction_changes > len(y_values) * 0.1:
                pattern = "📊 УМЕРЕННАЯ изменчивость"
            else:
                pattern = "➖ ПЛАВНОЕ изменение"
            
            # Диапазон изменения
            min_val = min(y_values)
            max_val = max(y_values)
            range_val = max_val - min_val
            avg_val = sum(y_values) / len(y_values)
            
            volatility = f"Размах: от {min_val} до {max_val} (диапазон {range_val})"
            
            return f"{trend}\n{pattern}\n{volatility}\nСреднее значение: {avg_val:.2f}"
        except:
            return "Анализ визуального паттерна недоступен"


class ChatView(APIView):
    """
    POST /api/ai_assistant/chat/
    Простой RAG чат для общих вопросов (без streaming)
    
    Body (JSON или multipart/form-data):
    {
        "message": "Как работает система?",
        "session_id": "uuid",  # опционально, для продолжения существующего чата
        "module": "chat",  # опционально, модуль AI ассистента
        "file": <file>  # опционально, файл для анализа (Word, PDF, TXT)
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def post(self, request):
        message = request.data.get('message')
        ollama_config = request.data.get('ollama_config')  # Настройки Ollama из module-config
        session_id = request.data.get('session_id')
        module = request.data.get('module', 'chat')
        uploaded_files = request.FILES.getlist('files')  # Загруженные файлы (множественная загрузка)
        # Для обратной совместимости поддерживаем и одиночный файл
        if not uploaded_files:
            single_file = request.FILES.get('file')
            if single_file:
                uploaded_files = [single_file]
        
        # Получаем флаг векторизации
        enable_vectorization = request.data.get('enable_vectorization', False)
        if isinstance(enable_vectorization, str):
            enable_vectorization = enable_vectorization.lower() in ('true', '1', 'yes')
        
        # Обрабатываем ollama_config если он пришел как строка JSON (из FormData)
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
        
        try:
            # Получаем или создаем сессию чата
            if session_id:
                try:
                    session = ChatSession.objects.get(id=session_id, user=request.user)
                except ChatSession.DoesNotExist:
                    session = None
            else:
                session = None
            
            # Получаем document_id из запроса (для модуля docs)
            document_id = request.data.get('document_id')
            
            if not session:
                # Создаем новую сессию с metadata, если есть document_id
                session_metadata = {}
                if document_id:
                    session_metadata['document_id'] = document_id
                session = ChatSession.objects.create(
                    user=request.user,
                    module=module,
                    title=message[:50] if message else 'Новый чат',
                    metadata=session_metadata
                )
            else:
                # Обновляем metadata сессии, если передан document_id
                if document_id:
                    if not session.metadata:
                        session.metadata = {}
                    session.metadata['document_id'] = document_id
                    session.save(update_fields=['metadata'])
            
            # Сохраняем сообщение пользователя
            user_message = ChatMessage.objects.create(
                session=session,
                message_type=ChatMessage.MESSAGE_TYPE_USER,
                content=message,
                metadata={'ollama_config': ollama_config} if ollama_config else {}
            )
            
            # Засекаем время начала запроса
            request_started_at = timezone.now()

            runtime_config, client = _create_ollama_client(ollama_config)
            temperature = (ollama_config or {}).get('temperature', 0)
            
            # Формируем массив сообщений для chat API с сохранением контекста
            messages = []
            
            # Добавляем системный промпт с инструкциями по работе с файлами
            system_prompt_parts = []
            if uploaded_files:
                if enable_vectorization:
                    system_prompt_parts.append(
                        "Пользователь загрузил файлы, которые были проиндексированы с помощью векторного поиска. "
                        "Используй информацию из векторного поиска для точных и релевантных ответов. "
                        "Учитывай контекст из всех загруженных файлов при ответе на вопросы."
                    )
                else:
                    system_prompt_parts.append(
                        "Пользователь загрузил файлы. Используй информацию из загруженных файлов для ответа на вопросы. "
                        "Учитывай содержимое всех загруженных файлов при формировании ответа."
                    )
            
            if system_prompt_parts:
                messages.append({
                    "role": "system",
                    "content": "\n".join(system_prompt_parts)
                })
            
            # Добавляем историю чата из БД (последние 10 сообщений для контекста)
            previous_messages = session.messages.order_by('created_at')[:10]
            for msg in previous_messages:
                if msg.message_type == ChatMessage.MESSAGE_TYPE_USER:
                    messages.append({"role": "user", "content": msg.content})
                elif msg.message_type == ChatMessage.MESSAGE_TYPE_ASSISTANT:
                    messages.append({"role": "assistant", "content": msg.content})
            
            # Обрабатываем загруженные файлы, если они есть
            uploaded_file_context = ""
            vectorized_document_ids = []
            
            # Получаем уже проиндексированные документы из сессии (если есть)
            if session.metadata and 'vectorized_documents' in session.metadata:
                vectorized_document_ids = session.metadata['vectorized_documents']
            
            if uploaded_files:
                if enable_vectorization:
                    # Векторизация: создаем временные KnowledgeDocument и индексируем их
                    try:
                        embeddings_service, _ = _get_rag_services(ollama_config)
                        indexing_service = RAGIndexingService(
                            embeddings_service=embeddings_service,
                            chunk_size=RAG_CHUNK_SIZE,
                            chunk_overlap=RAG_CHUNK_OVERLAP,
                        )
                        
                        new_document_ids = []
                        for uploaded_file in uploaded_files:
                            try:
                                # Создаем временный KnowledgeDocument
                                temp_doc = KnowledgeDocument.objects.create(
                                    user=request.user,
                                    title=f"Временный документ: {uploaded_file.name}",
                                    file=uploaded_file,
                                    source=f"chat_upload_{session.id}",
                                    metadata={
                                        'session_id': str(session.id),
                                        'is_temporary': True,
                                        'uploaded_at': timezone.now().isoformat(),
                                    }
                                )
                                
                                # Индексируем документ
                                indexing_result = indexing_service.index_document(temp_doc, force_reindex=True)
                                
                                if indexing_result.get('success'):
                                    new_document_ids.append(str(temp_doc.id))
                                    logger.info(f"Файл {uploaded_file.name} успешно проиндексирован (ID: {temp_doc.id})")
                                else:
                                    logger.warning(f"Не удалось проиндексировать файл {uploaded_file.name}: {indexing_result.get('error')}")
                                    temp_doc.delete()  # Удаляем документ, если индексация не удалась
                                    
                            except Exception as e:
                                logger.error(f"Ошибка векторизации файла {uploaded_file.name}: {e}", exc_info=True)
                        
                        # Сохраняем ID новых документов в metadata сессии
                        if new_document_ids:
                            if not session.metadata:
                                session.metadata = {}
                            if 'vectorized_documents' not in session.metadata:
                                session.metadata['vectorized_documents'] = []
                            session.metadata['vectorized_documents'].extend(new_document_ids)
                            session.save(update_fields=['metadata'])
                            vectorized_document_ids.extend(new_document_ids)
                            
                    except Exception as e:
                        logger.error(f"Ошибка при векторизации файлов: {e}", exc_info=True)
                
                # Извлекаем текст из файлов для обычного контекста (если векторизация не включена)
                if not enable_vectorization:
                    file_contexts = []
                    for uploaded_file in uploaded_files:
                        try:
                            from io import BytesIO
                            file_obj = BytesIO(uploaded_file.read())
                            extracted_content, detected_type = DocumentParserService.parse_document(
                                file_obj=file_obj,
                                filename=uploaded_file.name
                            )
                            if extracted_content:
                                # Ограничиваем размер контекста из файла
                                max_file_context_length = 2000  # Примерно 2000 символов
                                if len(extracted_content) > max_file_context_length:
                                    extracted_content = extracted_content[:max_file_context_length] + "..."
                                file_contexts.append(f"[СОДЕРЖИМОЕ ФАЙЛА: {uploaded_file.name}]\n{extracted_content}\n[/СОДЕРЖИМОЕ ФАЙЛА]")
                        except DocumentParseError as e:
                            logger.warning(f"Не удалось извлечь текст из файла {uploaded_file.name}: {e}")
                        except Exception as e:
                            logger.error(f"Ошибка обработки файла {uploaded_file.name}: {e}", exc_info=True)
                    
                    if file_contexts:
                        uploaded_file_context = "\n\n".join(file_contexts) + "\n\nИспользуй информацию из загруженных файлов для ответа на вопрос пользователя."
            
            # Получаем контекст из базы знаний RAG
            rag_context = ""
            rag_chunks = []
            
            # Если векторизация включена, используем векторный поиск по загруженным файлам
            if enable_vectorization and vectorized_document_ids:
                rag_context, rag_chunks = _get_rag_context(
                    query=message,
                    user=request.user,
                    ollama_config=ollama_config,
                    document_ids=vectorized_document_ids,
                )
            elif module == 'docs':
                # Получаем document_id из metadata сессии или из запроса
                document_id = None
                if session.metadata and 'document_id' in session.metadata:
                    document_id = session.metadata['document_id']
                elif request.data.get('document_id'):
                    document_id = request.data.get('document_id')
                
                # Получаем контекст из базы знаний RAG только для модуля docs
                document_ids = [document_id] if document_id else None
                rag_context, rag_chunks = _get_rag_context(
                    query=message,
                    user=request.user,
                    ollama_config=ollama_config,
                    document_ids=document_ids,
                )
            
            # Формируем текущее сообщение пользователя с дополнительными контекстами
            user_message_parts = []
            
            if uploaded_file_context:
                user_message_parts.append(uploaded_file_context)
            
            if rag_context:
                user_message_parts.append(
                    f"[ИНФОРМАЦИЯ ИЗ БАЗЫ ЗНАНИЙ]\n{rag_context}\n[/ИНФОРМАЦИЯ ИЗ БАЗЫ ЗНАНИЙ]\n\n"
                    "Используй эту информацию для ответа на вопрос пользователя. "
                    "Если в базе знаний есть релевантная информация, обязательно используй её. "
                    "Если информации нет, отвечай на основе своих знаний."
                )
            
            user_message_parts.append(message)
            user_message = "\n\n".join(user_message_parts)
            
            # Добавляем текущее сообщение пользователя
            messages.append({"role": "user", "content": user_message})
            
            # Используем chat API для сохранения контекста
            answer = client.chat(
                messages,
                temperature=temperature,
                stream=False,
            ).strip()
            
            # Проверяем, нужно ли выполнить навык из ответа LLM
            skill_result, cleaned_answer, skill_display_name, skill_call = execute_skill_from_llm_response(
                answer,
                message,
                context={'user': request.user, 'session': session, 'module': module}
            )
            
            # Если навык был выполнен, добавляем результат в ответ
            if skill_result and skill_result.success:
                if cleaned_answer:
                    answer = f"{skill_result.result}\n\n{cleaned_answer}"
                else:
                    answer = skill_result.result
            elif skill_result and not skill_result.success:
                answer = f"{cleaned_answer}\n\n⚠️ Ошибка выполнения навыка: {skill_result.error}"
            else:
                answer = cleaned_answer if cleaned_answer else answer
            
            
            # Засекаем время получения ответа
            response_received_at = timezone.now()
            processing_time = int((response_received_at - request_started_at).total_seconds() * 1000)
            
            # Формируем metadata с данными навыка
            message_metadata = {
                'model': runtime_config.model,
                'skill_name': skill_display_name,
                'skill_call': skill_call,
            }
            if ollama_config:
                message_metadata['ollama_config'] = ollama_config
            
            # Добавляем данные навыка (например, конфигурацию графика)
            if skill_result and skill_result.success and skill_result.metadata:
                # Проверяем, это график?
                if 'chart_config' in skill_result.metadata:
                    message_metadata['chart_config'] = skill_result.metadata['chart_config']
            
            # Сохраняем ответ ассистента
            assistant_message = ChatMessage.objects.create(
                session=session,
                message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT,
                content=answer,
                request_started_at=request_started_at,
                response_received_at=response_received_at,
                processing_time_ms=processing_time,
                metadata=message_metadata
            )
            
            # Обновляем время сессии
            session.updated_at = timezone.now()
            session.save(update_fields=['updated_at'])
            
            # Формируем ответ
            response_data = {
                'success': True,
                'response': answer,
                'message': answer,  # Для совместимости
                'session_id': str(session.id),
                'message_id': str(assistant_message.id),
                'processing_time_ms': processing_time,
                'timestamp': assistant_message.created_at.isoformat(),
                'skill_name': skill_display_name,
                'skill_call': skill_call,
            }
            # Добавляем конфигурацию графика, если есть
            if 'chart_config' in message_metadata:
                response_data['chart_config'] = message_metadata['chart_config']
            
            return Response(response_data, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChatStreamView(APIView):
    """
    POST /api/ai_assistant/chat/stream/
    RAG чат с поддержкой Server-Sent Events (SSE) для streaming ответов
    
    Body (JSON или multipart/form-data):
    {
        "message": "Как работает система?",
        "session_id": "uuid",  # опционально, для продолжения существующего чата
        "module": "chat",  # опционально, модуль AI ассистента
        "file": <file>  # опционально, файл для анализа (Word, PDF, TXT)
    }
    
    Response: SSE stream с событиями:
    - {"type": "chunk", "text": "..."} - часть ответа
    - {"type": "done", "full_response": "...", "session_id": "...", "message_id": "...", "processing_time_ms": 123} - завершение
    - {"type": "error", "message": "..."} - ошибка
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def post(self, request):
        message = request.data.get('message')
        ollama_config = request.data.get('ollama_config')
        session_id = request.data.get('session_id')
        module = request.data.get('module', 'chat')
        uploaded_files = request.FILES.getlist('files')  # Загруженные файлы (множественная загрузка)
        # Для обратной совместимости поддерживаем и одиночный файл
        if not uploaded_files:
            single_file = request.FILES.get('file')
            if single_file:
                uploaded_files = [single_file]
        
        # Получаем флаг векторизации
        enable_vectorization = request.data.get('enable_vectorization', False)
        if isinstance(enable_vectorization, str):
            enable_vectorization = enable_vectorization.lower() in ('true', '1', 'yes')
        
        # Обрабатываем ollama_config если он пришел как строка JSON (из FormData)
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
        
        # Получаем или создаем сессию чата
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id, user=request.user)
            except ChatSession.DoesNotExist:
                session = None
        else:
            session = None
        
        # Получаем document_id из запроса (для модуля docs)
        document_id = request.data.get('document_id')
        
        if not session:
            # Создаем новую сессию с metadata, если есть document_id
            session_metadata = {}
            if document_id:
                session_metadata['document_id'] = document_id
            session = ChatSession.objects.create(
                user=request.user,
                module=module,
                title=message[:50] if message else 'Новый чат',
                metadata=session_metadata
            )
        else:
            # Обновляем metadata сессии, если передан document_id
            if document_id:
                if not session.metadata:
                    session.metadata = {}
                session.metadata['document_id'] = document_id
                session.save(update_fields=['metadata'])
        
        # Сохраняем сообщение пользователя
        user_message = ChatMessage.objects.create(
            session=session,
            message_type=ChatMessage.MESSAGE_TYPE_USER,
            content=message,
            metadata={'ollama_config': ollama_config} if ollama_config else {}
        )
        
        def event_stream():
            import threading
            
            try:
                # Засекаем время начала запроса
                request_started_at = timezone.now()
                
                runtime_config, client = _create_ollama_client(ollama_config)
                temperature = (ollama_config or {}).get('temperature', 0)
                
                # Формируем массив сообщений для chat API с сохранением контекста
                messages = []
                
                # Обрабатываем загруженные файлы, если они есть
                uploaded_file_context = ""
                vectorized_document_ids = []
                
                # Получаем уже проиндексированные документы из сессии (если есть)
                if session.metadata and 'vectorized_documents' in session.metadata:
                    vectorized_document_ids = session.metadata['vectorized_documents']
                
                if uploaded_files:
                    if enable_vectorization:
                        # Векторизация: создаем временные KnowledgeDocument и индексируем их
                        try:
                            embeddings_service, _ = _get_rag_services(ollama_config)
                            indexing_service = RAGIndexingService(
                                embeddings_service=embeddings_service,
                                chunk_size=RAG_CHUNK_SIZE,
                                chunk_overlap=RAG_CHUNK_OVERLAP,
                            )
                            
                            new_document_ids = []
                            for uploaded_file in uploaded_files:
                                try:
                                    # Создаем временный KnowledgeDocument
                                    temp_doc = KnowledgeDocument.objects.create(
                                        user=request.user,
                                        title=f"Временный документ: {uploaded_file.name}",
                                        file=uploaded_file,
                                        source=f"chat_upload_{session.id}",
                                        metadata={
                                            'session_id': str(session.id),
                                            'is_temporary': True,
                                            'uploaded_at': timezone.now().isoformat(),
                                        }
                                    )
                                    
                                    # Индексируем документ
                                    indexing_result = indexing_service.index_document(temp_doc, force_reindex=True)
                                    
                                    if indexing_result.get('success'):
                                        new_document_ids.append(str(temp_doc.id))
                                        logger.info(f"Файл {uploaded_file.name} успешно проиндексирован (ID: {temp_doc.id})")
                                    else:
                                        logger.warning(f"Не удалось проиндексировать файл {uploaded_file.name}: {indexing_result.get('error')}")
                                        temp_doc.delete()  # Удаляем документ, если индексация не удалась
                                        
                                except Exception as e:
                                    logger.error(f"Ошибка векторизации файла {uploaded_file.name}: {e}", exc_info=True)
                            
                            # Сохраняем ID новых документов в metadata сессии
                            if new_document_ids:
                                if not session.metadata:
                                    session.metadata = {}
                                if 'vectorized_documents' not in session.metadata:
                                    session.metadata['vectorized_documents'] = []
                                session.metadata['vectorized_documents'].extend(new_document_ids)
                                session.save(update_fields=['metadata'])
                                vectorized_document_ids.extend(new_document_ids)
                                
                        except Exception as e:
                            logger.error(f"Ошибка при векторизации файлов: {e}", exc_info=True)
                    
                    # Извлекаем текст из файлов для обычного контекста (если векторизация не включена)
                    if not enable_vectorization:
                        file_contexts = []
                        for uploaded_file in uploaded_files:
                            try:
                                from io import BytesIO
                                file_obj = BytesIO(uploaded_file.read())
                                extracted_content, detected_type = DocumentParserService.parse_document(
                                    file_obj=file_obj,
                                    filename=uploaded_file.name
                                )
                                if extracted_content:
                                    # Ограничиваем размер контекста из файла
                                    max_file_context_length = 2000  # Примерно 2000 символов
                                    if len(extracted_content) > max_file_context_length:
                                        extracted_content = extracted_content[:max_file_context_length] + "..."
                                    file_contexts.append(f"[СОДЕРЖИМОЕ ФАЙЛА: {uploaded_file.name}]\n{extracted_content}\n[/СОДЕРЖИМОЕ ФАЙЛА]")
                            except DocumentParseError as e:
                                logger.warning(f"Не удалось извлечь текст из файла {uploaded_file.name}: {e}")
                            except Exception as e:
                                logger.error(f"Ошибка обработки файла {uploaded_file.name}: {e}", exc_info=True)
                        
                        if file_contexts:
                            uploaded_file_context = "\n\n".join(file_contexts) + "\n\nИспользуй информацию из загруженных файлов для ответа на вопрос пользователя."
                
                # Получаем контекст из базы знаний RAG
                rag_context = ""
                rag_chunks = []
                
                # Если векторизация включена, используем векторный поиск по загруженным файлам
                if enable_vectorization and vectorized_document_ids:
                    rag_context, rag_chunks = _get_rag_context(
                        query=message,
                        user=request.user,
                        ollama_config=ollama_config,
                        document_ids=vectorized_document_ids,
                    )
                elif module == 'docs':
                    # Получаем document_id из metadata сессии или из запроса
                    document_id = None
                    if session.metadata and 'document_id' in session.metadata:
                        document_id = session.metadata['document_id']
                    elif request.data.get('document_id'):
                        document_id = request.data.get('document_id')
                    
                    # Получаем контекст из базы знаний RAG только для модуля docs
                    document_ids = [document_id] if document_id else None
                    rag_context, rag_chunks = _get_rag_context(
                        query=message,
                        user=request.user,
                        ollama_config=ollama_config,
                        document_ids=document_ids,
                    )
                
                # Добавляем системный промпт с инструкциями по работе с файлами
                system_prompt_parts = []
                if uploaded_files:
                    if enable_vectorization:
                        system_prompt_parts.append(
                            "Пользователь загрузил файлы, которые были проиндексированы с помощью векторного поиска. "
                            "Используй информацию из векторного поиска для точных и релевантных ответов. "
                            "Учитывай контекст из всех загруженных файлов при ответе на вопросы."
                        )
                    else:
                        system_prompt_parts.append(
                            "Пользователь загрузил файлы. Используй информацию из загруженных файлов для ответа на вопросы. "
                            "Учитывай содержимое всех загруженных файлов при формировании ответа."
                        )
                
                if system_prompt_parts:
                    messages.append({
                        "role": "system",
                        "content": "\n".join(system_prompt_parts)
                    })
                
                # Добавляем историю чата из БД (последние 10 сообщений для контекста)
                previous_messages = session.messages.order_by('created_at')[:10]
                for msg in previous_messages:
                    if msg.message_type == ChatMessage.MESSAGE_TYPE_USER:
                        messages.append({"role": "user", "content": msg.content})
                    elif msg.message_type == ChatMessage.MESSAGE_TYPE_ASSISTANT:
                        messages.append({"role": "assistant", "content": msg.content})
                
                # Формируем текущее сообщение пользователя с дополнительными контекстами
                user_message_parts = []
                
                if uploaded_file_context:
                    user_message_parts.append(uploaded_file_context)
                
                if rag_context:
                    user_message_parts.append(
                        f"[ИНФОРМАЦИЯ ИЗ БАЗЫ ЗНАНИЙ]\n{rag_context}\n[/ИНФОРМАЦИЯ ИЗ БАЗЫ ЗНАНИЙ]\n\n"
                        "Используй эту информацию для ответа на вопрос пользователя. "
                        "Если в базе знаний есть релевантная информация, обязательно используй её. "
                        "Если информации нет, отвечай на основе своих знаний."
                    )
                
                user_message_parts.append(message)
                user_message = "\n\n".join(user_message_parts)
                
                # Добавляем текущее сообщение пользователя
                messages.append({"role": "user", "content": user_message})
                
                # Оптимизация: используем Queue вместо списка
                from queue import Queue, Empty
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
                            stream=True,
                            stream_callback=stream_callback,
                        )
                        result_container['response'] = result.strip()
                    except Exception as e:
                        exception_container['error'] = e
                    finally:
                        # Сигнал завершения
                        streaming_chunks_queue.put(None)
                
                # Запускаем в отдельном потоке
                chat_thread = threading.Thread(target=run_chat)
                chat_thread.start()
                
                # Оптимизация: используем блокирующее ожидание вместо активного polling
                while chat_thread.is_alive() or not streaming_chunks_queue.empty():
                    try:
                        chunk = streaming_chunks_queue.get(timeout=0.1)
                        if chunk is None:  # Сигнал завершения
                            break
                        yield f"data: {_safe_json_dumps({'type': 'chunk', 'text': chunk}, ensure_ascii=False)}\n\n"
                    except Empty:
                        continue
                
                chat_thread.join(timeout=5.0)
                
                # Проверяем ошибки
                if 'error' in exception_container:
                    raise exception_container['error']
                
                # Засекаем время получения ответа
                response_received_at = timezone.now()
                
                # Получаем полный ответ
                raw_response = result_container.get('response', '')
                
                # Проверяем, нужно ли выполнить навык из ответа LLM
                skill_result, cleaned_response, skill_display_name, skill_call = execute_skill_from_llm_response(
                    raw_response,
                    message,
                    context={'user': request.user, 'session': session, 'module': module}
                )
                
                # Формируем финальный ответ
                if skill_result and skill_result.success:
                    if cleaned_response:
                        full_response = f"{skill_result.result}\n\n{cleaned_response}"
                    else:
                        full_response = str(skill_result.result)
                elif skill_result and not skill_result.success:
                    full_response = f"{cleaned_response if cleaned_response else raw_response}\n\n⚠️ Ошибка выполнения навыка: {skill_result.error}"
                else:
                    full_response = cleaned_response if cleaned_response else raw_response
                
                processing_time = int((response_received_at - request_started_at).total_seconds() * 1000)
                
                # Формируем metadata с данными навыка
                message_metadata = {
                    'model': runtime_config.model,
                    'skill_name': skill_display_name,
                    'skill_call': skill_call,
                }
                if ollama_config:
                    message_metadata['ollama_config'] = ollama_config
                
                # Добавляем данные навыка (например, конфигурацию графика)
                if skill_result and skill_result.success and skill_result.metadata:
                    # Проверяем, это график?
                    if 'chart_config' in skill_result.metadata:
                        message_metadata['chart_config'] = skill_result.metadata['chart_config']
                
                # Сохраняем ответ ассистента
                assistant_message = ChatMessage.objects.create(
                    session=session,
                    message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT,
                    content=full_response,
                    request_started_at=request_started_at,
                    response_received_at=response_received_at,
                    processing_time_ms=processing_time,
                    metadata=message_metadata
                )
                
                # Обновляем время сессии
                session.updated_at = timezone.now()
                session.save(update_fields=['updated_at'])
                
                # Формируем финальное событие
                done_event = {
                    'type': 'done',
                    'full_response': full_response,
                    'session_id': str(session.id),
                    'message_id': str(assistant_message.id),
                    'processing_time_ms': processing_time,
                    'timestamp': assistant_message.created_at.isoformat(),
                    'skill_name': skill_display_name,
                    'skill_call': skill_call,
                }
                # Добавляем конфигурацию графика, если есть
                if 'chart_config' in message_metadata:
                    done_event['chart_config'] = message_metadata['chart_config']
                
                yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        
        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


class ChatSessionViewSet(ViewSet, SwaggerSafeMixin):
    """
    ViewSet для работы с сессиями чатов
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def list(self, request):
        """
        GET /api/ai_assistant/chat_sessions/
        Получить список сессий чатов пользователя
        """
        user = self.get_safe_user()
        queryset = ChatSession.objects.filter(user=user)
        queryset = self.get_safe_queryset(queryset)
        
        # Фильтрация по модулю
        module = request.query_params.get('module')
        if module:
            queryset = queryset.filter(module=module)
        
        sessions = []
        for session in queryset[:50]:  # Ограничиваем 50 последними
            sessions.append({
                'id': str(session.id),
                'title': session.title or 'Без названия',
                'module': session.module,
                'message_count': session.message_count,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'metadata': session.metadata or {},
            })
        
        return Response({
            'success': True,
            'sessions': sessions,
            'count': len(sessions),
        })
    
    def retrieve(self, request, pk=None):
        """
        GET /api/ai_assistant/chat_sessions/{id}/
        Получить сессию чата с сообщениями
        """
        user = self.get_safe_user()
        queryset = ChatSession.objects.filter(user=user)
        queryset = self.get_safe_queryset(queryset)
        
        try:
            session = queryset.get(id=pk)
        except ChatSession.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Сессия не найдена'
            }, status=status.HTTP_404_NOT_FOUND)
        
        messages = []
        for msg in session.messages.all():
            messages.append({
                'id': str(msg.id),
                'type': msg.message_type,
                'content': msg.content,
                'created_at': msg.created_at.isoformat(),
                'request_started_at': msg.request_started_at.isoformat() if msg.request_started_at else None,
                'response_received_at': msg.response_received_at.isoformat() if msg.response_received_at else None,
                'processing_time_ms': msg.processing_time_ms,
                'metadata': msg.metadata,
            })
        
        return Response({
            'success': True,
            'session': {
                'id': str(session.id),
                'title': session.title or 'Без названия',
                'module': session.module,
                'message_count': session.message_count,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'metadata': session.metadata or {},
            },
            'messages': messages,
        })
    
    def create(self, request):
        """
        POST /api/ai_assistant/chat_sessions/
        Создать новую сессию чата
        """
        user = self.get_safe_user()
        if not user:
            return Response({
                'success': False,
                'error': 'Пользователь не найден'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        title = request.data.get('title', 'Новый чат')
        module = request.data.get('module', 'chat')
        
        session = ChatSession.objects.create(
            user=user,
            title=title,
            module=module
        )
        return Response({
            'success': True,
            'session': {
                'id': str(session.id),
                'title': session.title,
                'module': session.module,
                'message_count': session.message_count,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
            }
        }, status=status.HTTP_201_CREATED)
    
    def destroy(self, request, pk=None):
        """
        DELETE /api/ai_assistant/chat_sessions/{id}/
        Удалить сессию чата
        """
        user = self.get_safe_user()
        queryset = ChatSession.objects.filter(user=user)
        queryset = self.get_safe_queryset(queryset)
        
        try:
            session = queryset.get(id=pk)
            session.delete()
            return Response({
                'success': True,
                'message': 'Сессия удалена'
            }, status=status.HTTP_200_OK)
        except ChatSession.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Сессия не найдена'
            }, status=status.HTTP_404_NOT_FOUND)


class KnowledgeDocumentViewSet(ViewSet, SwaggerSafeMixin):
    """
    ViewSet для управления документами базы знаний RAG
    
    Поддерживает:
    - Загрузку файлов (Word, PDF, TXT) через multipart/form-data
    - Создание документов из текста через JSON
    - Автоматическое извлечение текста из файлов при индексации
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def list(self, request):
        """
        GET /api/ai_assistant/knowledge_documents/
        Получить список документов пользователя
        """
        user = self.get_safe_user()
        queryset = KnowledgeDocument.objects.filter(user=user)
        queryset = self.get_safe_queryset(queryset)
        
        documents = []
        for doc in queryset.order_by('-created_at'):
            # Определяем размер файла
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
                'source': doc.source,
                'has_file': bool(doc.file),
                'file_type': doc.file_type,
                'file_name': doc.file.name.split('/')[-1] if doc.file else None,
                'file_size': file_size,
                'file_url': file_url,
                'content_preview': (doc.content[:200] + '...' if doc.content and len(doc.content) > 200 else doc.content) if doc.content else None,
                'is_indexed': doc.is_indexed,
                'chunks_count': doc.chunks_count,
                'indexed_at': doc.indexed_at.isoformat() if doc.indexed_at else None,
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
        """
        POST /api/ai_assistant/knowledge_documents/
        Создать новый документ
        
        Поддерживает два режима:
        1. Загрузка файла (multipart/form-data):
           - file: файл (Word, PDF, TXT)
           - title: название документа
           - source: источник (опционально)
           - metadata: JSON метаданные (опционально)
           - index_immediately: индексировать сразу (опционально, default: false)
        
        2. Создание из текста (JSON):
           - title: название документа
           - content: текстовое содержимое
           - source: источник (опционально)
           - metadata: метаданные (опционально)
           - index_immediately: индексировать сразу (опционально)
        
        Если указан и файл, и content, приоритет у файла.
        """
        user = self.get_safe_user()
        
        title = request.data.get('title')
        uploaded_file = request.FILES.get('file')
        content = request.data.get('content')
        source = request.data.get('source', '')
        metadata = request.data.get('metadata', {})
        index_immediately = request.data.get('index_immediately', False)
        
        # Обработка metadata если это строка JSON
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        
        if not title:
            return Response({
                'success': False,
                'error': 'Не указано обязательное поле: title'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not uploaded_file and not content:
            return Response({
                'success': False,
                'error': 'Не указаны ни файл, ни текстовое содержимое. Укажите одно из: file или content'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            file_type = None
            extracted_content = None
            
            # Если загружен файл - определяем его тип
            if uploaded_file:
                file_type = DocumentParserService.get_file_type(uploaded_file.name)
                # Для файлов контент не обязателен, он извлечется при индексации
                # Но можно попробовать извлечь сразу, если index_immediately
                if index_immediately:
                    try:
                        from io import BytesIO
                        file_obj = BytesIO(uploaded_file.read())
                        extracted_content, detected_type = DocumentParserService.parse_document(
                            file_obj=file_obj,
                            filename=uploaded_file.name
                        )
                        file_type = detected_type
                        file_obj.seek(0)  # Возвращаемся в начало для сохранения файла
                        uploaded_file.seek(0)  # Возвращаемся в начало
                    except DocumentParseError as e:
                        # Если не удалось извлечь, продолжаем - извлечем при индексации
                        logger.warning(f"Не удалось извлечь текст из файла сразу: {e}")
            
            # Используем извлеченный контент или переданный
            final_content = extracted_content or content
            
            # Создаем документ
            document = KnowledgeDocument.objects.create(
                user=user,
                title=title,
                content=final_content,
                source=source or (uploaded_file.name if uploaded_file else ''),
                metadata=metadata,
                file_type=file_type,
            )
            
            # Сохраняем файл, если он был загружен
            if uploaded_file:
                document.file = uploaded_file
                document.save(update_fields=['file'])
            
            # Индексируем документ, если запрошено
            indexing_result = None
            if index_immediately:
                try:
                    embeddings_service, _ = _get_rag_services()
                    indexing_service = RAGIndexingService(
                        embeddings_service=embeddings_service,
                        chunk_size=RAG_CHUNK_SIZE,
                        chunk_overlap=RAG_CHUNK_OVERLAP,
                    )
                    indexing_result = indexing_service.index_document(document)
                    # Обновляем объект документа из БД, чтобы получить актуальный chunks_count
                    document.refresh_from_db()
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Ошибка индексации документа {document.id}: {e}", exc_info=True)
                    # Не прерываем создание документа, просто логируем ошибку
            
            return Response({
                'success': True,
                'document': {
                    'id': str(document.id),
                    'title': document.title,
                    'source': document.source,
                    'has_file': bool(document.file),
                    'file_type': document.file_type,
                    'file_name': document.file.name.split('/')[-1] if document.file else None,
                    'is_indexed': document.is_indexed,
                    'chunks_count': document.chunks_count,
                    'indexed_at': document.indexed_at.isoformat() if document.indexed_at else None,
                    'created_at': document.created_at.isoformat(),
                    'metadata': document.metadata,
                },
                'indexing_result': indexing_result,
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Ошибка создания документа: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def retrieve(self, request, pk=None):
        """
        GET /api/ai_assistant/knowledge_documents/{id}/
        Получить документ с chunks
        """
        user = self.get_safe_user()
        queryset = KnowledgeDocument.objects.filter(user=user)
        queryset = self.get_safe_queryset(queryset)
        
        try:
            document = queryset.get(id=pk)
            
            chunks = []
            for chunk in document.chunks.all().order_by('chunk_index'):
                chunks.append({
                    'id': str(chunk.id),
                    'chunk_index': chunk.chunk_index,
                    'content': chunk.content,
                    'start_char': chunk.start_char,
                    'end_char': chunk.end_char,
                    'embedding_model': chunk.embedding_model,
                    'has_embedding': bool(chunk.embedding),
                    'metadata': chunk.metadata,
                })
            
            # Информация о файле
            file_info = None
            if document.file:
                try:
                    file_info = {
                        'name': document.file.name.split('/')[-1],
                        'size': document.file.size,
                        'url': document.file.url if hasattr(document.file, 'url') else None,
                        'type': document.file_type,
                    }
                except Exception:
                    pass
            
            return Response({
                'success': True,
                'document': {
                    'id': str(document.id),
                    'title': document.title,
                    'content': document.content,
                    'source': document.source,
                    'file': file_info,
                    'file_type': document.file_type,
                    'is_indexed': document.is_indexed,
                    'chunks_count': document.chunks_count,
                    'indexed_at': document.indexed_at.isoformat() if document.indexed_at else None,
                    'created_at': document.created_at.isoformat(),
                    'updated_at': document.updated_at.isoformat(),
                    'metadata': document.metadata,
                    'chunks': chunks,
                },
            }, status=status.HTTP_200_OK)
            
        except KnowledgeDocument.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Документ не найден'
            }, status=status.HTTP_404_NOT_FOUND)
    
    def update(self, request, pk=None):
        """
        PUT /api/ai_assistant/knowledge_documents/{id}/
        Обновить документ
        """
        user = self.get_safe_user()
        queryset = KnowledgeDocument.objects.filter(user=user)
        queryset = self.get_safe_queryset(queryset)
        
        try:
            document = queryset.get(id=pk)
            
            # Обновляем поля
            if 'title' in request.data:
                document.title = request.data['title']
            if 'content' in request.data:
                document.content = request.data['content']
                # Если изменили содержимое, сбрасываем статус индексации
                if document.is_indexed:
                    document.is_indexed = False
                    document.indexed_at = None
            if 'source' in request.data:
                document.source = request.data['source']
            if 'metadata' in request.data:
                document.metadata = request.data['metadata']
            
            document.save()
            
            return Response({
                'success': True,
                'document': {
                    'id': str(document.id),
                    'title': document.title,
                    'is_indexed': document.is_indexed,
                    'chunks_count': document.chunks_count,
                },
            }, status=status.HTTP_200_OK)
            
        except KnowledgeDocument.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Документ не найден'
            }, status=status.HTTP_404_NOT_FOUND)
    
    def destroy(self, request, pk=None):
        """
        DELETE /api/ai_assistant/knowledge_documents/{id}/
        Удалить документ (вместе с chunks)
        """
        user = self.get_safe_user()
        queryset = KnowledgeDocument.objects.filter(user=user)
        queryset = self.get_safe_queryset(queryset)
        
        try:
            document = queryset.get(id=pk)
            document.delete()  # Каскадное удаление chunks
            return Response({
                'success': True,
                'message': 'Документ удален'
            }, status=status.HTTP_200_OK)
            
        except KnowledgeDocument.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Документ не найден'
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['post'], url_path='index')
    def index(self, request, pk=None):
        """
        POST /api/ai_assistant/knowledge_documents/{id}/index/
        Индексировать или переиндексировать документ
        """
        user = self.get_safe_user()
        queryset = KnowledgeDocument.objects.filter(user=user)
        queryset = self.get_safe_queryset(queryset)
        
        force_reindex = request.data.get('force', False)
        
        try:
            document = queryset.get(id=pk)
            
            embeddings_service, _ = _get_rag_services()
            indexing_service = RAGIndexingService(
                embeddings_service=embeddings_service,
                chunk_size=RAG_CHUNK_SIZE,
                chunk_overlap=RAG_CHUNK_OVERLAP,
            )
            
            if force_reindex:
                result = indexing_service.reindex_document(document)
            else:
                result = indexing_service.index_document(document)
            
            # Обновляем объект документа из БД, чтобы получить актуальный chunks_count
            document.refresh_from_db()
            
            return Response({
                'success': True,
                'result': result,
                'document': {
                    'id': str(document.id),
                    'title': document.title,
                    'is_indexed': document.is_indexed,
                    'chunks_count': document.chunks_count,
                    'indexed_at': document.indexed_at.isoformat() if document.indexed_at else None,
                },
            }, status=status.HTTP_200_OK)
            
        except KnowledgeDocument.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Документ не найден'
            }, status=status.HTTP_404_NOT_FOUND)
        except RAGIndexingError as e:
            return Response({
                'success': False,
                'error': f'Ошибка индексации: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='unindex')
    def unindex(self, request, pk=None):
        """
        POST /api/ai_assistant/knowledge_documents/{id}/unindex/
        Деиндексировать документ (удалить chunks)
        """
        user = self.get_safe_user()
        queryset = KnowledgeDocument.objects.filter(user=user)
        queryset = self.get_safe_queryset(queryset)
        
        try:
            document = queryset.get(id=pk)
            
            embeddings_service, _ = _get_rag_services()
            indexing_service = RAGIndexingService(
                embeddings_service=embeddings_service,
                chunk_size=RAG_CHUNK_SIZE,
                chunk_overlap=RAG_CHUNK_OVERLAP,
            )
            
            indexing_service.delete_document_index(document)
            
            return Response({
                'success': True,
                'message': 'Документ деиндексирован',
                'document': {
                    'id': str(document.id),
                    'title': document.title,
                    'is_indexed': document.is_indexed,
                    'chunks_count': document.chunks_count,
                },
            }, status=status.HTTP_200_OK)
            
        except KnowledgeDocument.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Документ не найден'
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['get'], url_path='download')
    def download_file(self, request, pk=None):
        """
        GET /api/ai_assistant/knowledge_documents/{id}/download/
        Скачать файл документа
        """
        user = self.get_safe_user()
        queryset = KnowledgeDocument.objects.filter(user=user)
        queryset = self.get_safe_queryset(queryset)
        
        try:
            document = queryset.get(id=pk)
            
            if not document.file:
                return Response({
                    'success': False,
                    'error': 'У документа нет файла'
                }, status=status.HTTP_404_NOT_FOUND)
            
            try:
                file_handle = document.file.open('rb')
                filename = document.file.name.split('/')[-1]
                response = FileResponse(file_handle, as_attachment=True, filename=filename)
                return response
            except Exception as e:
                logger.error(f"Ошибка открытия файла документа {document.id}: {e}")
                return Response({
                    'success': False,
                    'error': f'Ошибка открытия файла: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        except KnowledgeDocument.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Документ не найден'
            }, status=status.HTTP_404_NOT_FOUND)


class GeneratedDocumentDownloadView(APIView):
    """
    GET /api/ai_assistant/documents/download/<path:file_path>
    Скачать сгенерированный документ
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, file_path):
        from pathlib import Path
        from django.conf import settings
        from urllib.parse import unquote
        import mimetypes
        import os
        
        # Декодируем URL (убираем %D0%A1 и т.д.)
        decoded_path = unquote(file_path)
        
        # Нормализуем путь (заменяем forward slashes на системные)
        normalized_path = decoded_path.replace('/', os.sep)
        
        # Строим полный путь к файлу
        media_root = Path(settings.MEDIA_ROOT)
        full_path = media_root / normalized_path
        
        logger.info(f"Запрос скачивания: file_path={file_path}, full_path={full_path}")
        
        # Проверяем безопасность пути (чтобы не выйти за пределы media)
        try:
            full_path = full_path.resolve()
            media_root = media_root.resolve()
            
            if not str(full_path).startswith(str(media_root)):
                return Response({
                    'success': False,
                    'error': 'Недопустимый путь к файлу'
                }, status=status.HTTP_403_FORBIDDEN)
        except Exception:
            return Response({
                'success': False,
                'error': 'Неверный путь к файлу'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Проверяем существование файла
        if not full_path.exists() or not full_path.is_file():
            logger.error(f"Файл не найден: {full_path}")
            return Response({
                'success': False,
                'error': f'Файл не найден: {full_path}'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Проверяем размер файла
        file_size = full_path.stat().st_size
        logger.info(f"Размер файла: {file_size} байт")
        
        if file_size == 0:
            logger.error(f"Файл пустой: {full_path}")
            return Response({
                'success': False,
                'error': 'Файл пустой'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Определяем MIME тип
        content_type, _ = mimetypes.guess_type(str(full_path))
        if not content_type:
            content_type = 'application/octet-stream'
        
        # Возвращаем файл
        try:
            response = FileResponse(
                open(full_path, 'rb'),
                content_type=content_type,
                as_attachment=True,
                filename=full_path.name
            )
            return response
        except Exception as e:
            logger.error(f"Ошибка скачивания документа {full_path}: {e}")
            return Response({
                'success': False,
                'error': f'Ошибка скачивания файла: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


