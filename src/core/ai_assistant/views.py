from typing import Tuple, cast

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from rest_framework.viewsets import ViewSet
from django.shortcuts import get_object_or_404
from django.http import StreamingHttpResponse
from django.utils import timezone
import json
import math
from datetime import datetime

from src.core.bi_analysis.bi_datasets.models import FileUpload, Dataset
from .fast_bi_service import FastBIService, DEFAULT_MODEL, OLLAMA_BASE_URL
from .config import build_runtime_config
from .llm_clients import build_llm_client, LLMClientError
from src.core.bi_analysis.bi_charts.models import Chart
from src.core.utils.mixins import SwaggerSafeMixin
from .models import ChatSession, ChatMessage
from .math_tools import MathToolsService
import pandas as pd
import numpy as np
from scipy import signal, stats

# Глобальный экземпляр сервиса математики (ленивая инициализация)
_math_service: MathToolsService | None = None


def _get_math_service() -> MathToolsService:
    """Получает или создаёт сервис математических вычислений."""
    global _math_service
    if _math_service is None:
        _math_service = MathToolsService()
    return _math_service


def _process_math_query(message: str) -> tuple[bool, str | None, dict | None]:
    """
    Проверяет и обрабатывает математический запрос.
    
    Returns:
        (is_math, result_text, metadata) - если is_math=True, result_text содержит результат
    """
    math_service = _get_math_service()
    
    if not math_service.is_math_query(message):
        return False, None, None
    
    result = math_service.calculate(message)
    if result.success:
        formatted = math_service.format_result_for_chat(result)
        metadata = {
            'math_result': True,
            'operation_type': result.operation_type,
            'result': str(result.result),
            'result_latex': result.result_latex,
        }
        return True, formatted, metadata
    
    return False, None, None


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


def _create_ollama_client(ollama_config=None):
    # Принудительно используем Ollama если провайдер не указан явно
    config_with_defaults = ollama_config or {}
    if 'provider' not in config_with_defaults:
        config_with_defaults = {**config_with_defaults, 'provider': 'ollama'}
    
    runtime_config = build_runtime_config(config_with_defaults)
    provider_name = runtime_config.provider.value if hasattr(runtime_config.provider, "value") else str(runtime_config.provider)
    base_url = runtime_config.provider_config.get("base_url", runtime_config.base_url or OLLAMA_BASE_URL)
    client = build_llm_client(
        provider=provider_name,
        model=runtime_config.model or DEFAULT_MODEL,
        base_url=base_url,
        request_timeout=runtime_config.request_timeout,
        stream_timeout=runtime_config.stream_timeout,
        concurrency_limit=runtime_config.concurrency_limit,
        max_retries=runtime_config.max_retries,
        keep_alive=runtime_config.keep_alive,
        provider_config=runtime_config.provider_config,
        device_config=runtime_config.device_config,
    )
    return runtime_config, client


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
            return self._streaming_response(file_upload, question, want_commentary, ollama_config, session, user_message)
        
        # Обычный режим (без streaming)
        return self._regular_response(file_upload, question, want_commentary, ollama_config, session, user_message)
    
    def _streaming_response(self, file_upload, question, want_commentary, ollama_config=None, session=None, user_message=None):
        """Возвращает streaming ответ через Server-Sent Events."""
        def event_stream():
            service = None
            assistant_message = None
            request_started_at = timezone.now()
            
            try:
                # Инициализируем сервис с настройками модуля
                service = FastBIService(ollama_config=ollama_config)
                
                # Отправляем начальное событие
                yield f"data: {json.dumps({'type': 'start', 'message': 'Начинаю обработку...'})}\n\n"
                
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
                        result_container['result'] = service.ask(question, want_commentary=want_commentary, stream_callback=immediate_callback)
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
                        'question': question,
                        'sql': result['sql'],
                        'data': result['data'],
                        'rows': result['rows'],
                        'columns': result['columns'],
                    }
                    # Используем _safe_json_dumps для обработки NaN/Infinity в данных
                    yield f"data: {_safe_json_dumps(final_data, ensure_ascii=False)}\n\n"
                    
                    # Сохраняем ответ ассистента
                    if session and user_message:
                        commentary_text = ''.join(commentary_parts) if commentary_parts else result.get('comment', '')
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
                        
                        # Отправляем информацию о сессии
                        yield f"data: {json.dumps({
                            'type': 'session_info',
                            'session_id': str(session.id),
                            'message_id': str(assistant_message.id),
                            'processing_time_ms': processing_time,
                        }, ensure_ascii=False)}\n\n"
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
    
    def _regular_response(self, file_upload, question, want_commentary, ollama_config=None, session=None, user_message=None):
        """Возвращает обычный (не streaming) ответ."""
        try:
            request_started_at = timezone.now()
            
            # Инициализируем сервис с настройками модуля
            service = FastBIService(ollama_config=ollama_config)
            
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
                        num_predict=runtime_config.commentary_tokens,
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
                num_predict=runtime_config.commentary_tokens,
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
    
    Body:
    {
        "message": "Как работает система?",
        "session_id": "uuid",  # опционально, для продолжения существующего чата
        "module": "chat"  # опционально, модуль AI ассистента
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        message = request.data.get('message')
        ollama_config = request.data.get('ollama_config')  # Настройки Ollama из module-config
        session_id = request.data.get('session_id')
        module = request.data.get('module', 'chat')
        
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
            
            if not session:
                session = ChatSession.objects.create(
                    user=request.user,
                    module=module,
                    title=message[:50] if message else 'Новый чат'
                )
            
            # Сохраняем сообщение пользователя
            user_message = ChatMessage.objects.create(
                session=session,
                message_type=ChatMessage.MESSAGE_TYPE_USER,
                content=message,
                metadata={'ollama_config': ollama_config} if ollama_config else {}
            )
            
            # Засекаем время начала запроса
            request_started_at = timezone.now()
            
            # Проверяем математический запрос
            is_math, math_result, math_metadata = _process_math_query(message)
            
            runtime_config, client = _create_ollama_client(ollama_config)
            temperature = (ollama_config or {}).get('temperature', 0.3)
            max_tokens = (ollama_config or {}).get('max_tokens', 2048)

            system_prompt = """Ты - полезный AI ассистент системы ERGO MS. 
Твоя задача - помогать пользователям с вопросами о системе, навигации и функционале.
Ты умеешь выполнять математические вычисления: арифметика, алгебра, производные, интегралы, пределы, решение уравнений.
Отвечай кратко, по делу и дружелюбно на русском языке.
Если не знаешь ответа, честно скажи об этом."""
            
            # Загружаем контекст из истории чата
            previous_messages = session.messages.filter(
                message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT
            ).order_by('-created_at')[:5]  # Последние 5 ответов для контекста
            
            context = ""
            if previous_messages.exists():
                context_parts = []
                for msg in reversed(previous_messages):
                    context_parts.append(f"Предыдущий ответ: {msg.content[:200]}")
                context = "\n".join(context_parts) + "\n\n"
            
            # Если математический запрос - добавляем результат в контекст
            if is_math and math_result:
                math_context = f"\n\n[МАТЕМАТИЧЕСКИЙ РЕЗУЛЬТАТ]\n{math_result}\n[/МАТЕМАТИЧЕСКИЙ РЕЗУЛЬТАТ]\n\nПрокомментируй этот результат кратко, объясни что получилось."
                full_prompt = f"{system_prompt}\n\n{context}Вопрос пользователя: {message}{math_context}"
            else:
                full_prompt = f"{system_prompt}\n\n{context}Вопрос пользователя: {message}"
            
            answer = client.complete(
                full_prompt,
                num_predict=max_tokens,
                temperature=temperature,
                stream=False,
            ).strip()
            
            # Если был математический результат, добавляем его в начало ответа
            if is_math and math_result:
                answer = f"{math_result}\n\n{answer}"
            
            # Засекаем время получения ответа
            response_received_at = timezone.now()
            processing_time = int((response_received_at - request_started_at).total_seconds() * 1000)
            
            # Сохраняем ответ ассистента
            assistant_message = ChatMessage.objects.create(
                session=session,
                message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT,
                content=answer,
                request_started_at=request_started_at,
                response_received_at=response_received_at,
                processing_time_ms=processing_time,
                metadata={
                    'ollama_config': ollama_config,
                    'model': runtime_config.model,
                } if ollama_config else {'model': runtime_config.model}
            )
            
            # Обновляем время сессии
            session.updated_at = timezone.now()
            session.save(update_fields=['updated_at'])
            
            return Response({
                'success': True,
                'response': answer,
                'message': answer,  # Для совместимости
                'session_id': str(session.id),
                'message_id': str(assistant_message.id),
                'processing_time_ms': processing_time,
                'timestamp': assistant_message.created_at.isoformat(),
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChatStreamView(APIView):
    """
    POST /api/ai_assistant/chat/stream/
    RAG чат с поддержкой Server-Sent Events (SSE) для streaming ответов
    
    Body:
    {
        "message": "Как работает система?",
        "session_id": "uuid",  # опционально, для продолжения существующего чата
        "module": "chat"  # опционально, модуль AI ассистента
    }
    
    Response: SSE stream с событиями:
    - {"type": "chunk", "text": "..."} - часть ответа
    - {"type": "done", "full_response": "...", "session_id": "...", "message_id": "...", "processing_time_ms": 123} - завершение
    - {"type": "error", "message": "..."} - ошибка
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        message = request.data.get('message')
        ollama_config = request.data.get('ollama_config')
        session_id = request.data.get('session_id')
        module = request.data.get('module', 'chat')
        
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
        
        if not session:
            session = ChatSession.objects.create(
                user=request.user,
                module=module,
                title=message[:50] if message else 'Новый чат'
            )
        
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
                
                # Проверяем математический запрос
                is_math, math_result, math_metadata = _process_math_query(message)
                math_prefix = ""
                
                # Если математический запрос - сначала отправляем результат
                if is_math and math_result:
                    yield f"data: {_safe_json_dumps({'type': 'math_result', 'text': math_result}, ensure_ascii=False)}\n\n"
                    math_prefix = f"{math_result}\n\n"
                
                runtime_config, client = _create_ollama_client(ollama_config)
                temperature = (ollama_config or {}).get('temperature', 0.3)
                max_tokens = (ollama_config or {}).get('max_tokens', 2048)

                system_prompt = """Ты - полезный AI ассистент системы ERGO MS. 
Твоя задача - помогать пользователям с вопросами о системе, навигации и функционале.
Ты умеешь выполнять математические вычисления: арифметика, алгебра, производные, интегралы, пределы, решение уравнений.
Отвечай кратко, по делу и дружелюбно на русском языке.
Если не знаешь ответа, честно скажи об этом."""
                
                # Загружаем контекст из истории чата
                previous_messages = session.messages.filter(
                    message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT
                ).order_by('-created_at')[:5]  # Последние 5 ответов для контекста
                
                context = ""
                if previous_messages.exists():
                    context_parts = []
                    for msg in reversed(previous_messages):
                        context_parts.append(f"Предыдущий ответ: {msg.content[:200]}")
                    context = "\n".join(context_parts) + "\n\n"
                
                # Если математический запрос - добавляем результат в контекст
                if is_math and math_result:
                    math_context = f"\n\n[МАТЕМАТИЧЕСКИЙ РЕЗУЛЬТАТ]\n{math_result}\n[/МАТЕМАТИЧЕСКИЙ РЕЗУЛЬТАТ]\n\nПрокомментируй этот результат кратко, объясни что получилось."
                    full_prompt = f"{system_prompt}\n\n{context}Вопрос пользователя: {message}{math_context}"
                else:
                    full_prompt = f"{system_prompt}\n\n{context}Вопрос пользователя: {message}"
                
                # Оптимизация: используем Queue вместо списка
                from queue import Queue, Empty
                streaming_chunks_queue = Queue()
                result_container = {}
                exception_container = {}
                
                def stream_callback(text):
                    streaming_chunks_queue.put(text)
                
                def run_complete():
                    try:
                        result = client.complete(
                            full_prompt,
                            num_predict=max_tokens,
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
                complete_thread = threading.Thread(target=run_complete)
                complete_thread.start()
                
                # Оптимизация: используем блокирующее ожидание вместо активного polling
                while complete_thread.is_alive() or not streaming_chunks_queue.empty():
                    try:
                        chunk = streaming_chunks_queue.get(timeout=0.1)
                        if chunk is None:  # Сигнал завершения
                            break
                        yield f"data: {_safe_json_dumps({'type': 'chunk', 'text': chunk}, ensure_ascii=False)}\n\n"
                    except Empty:
                        continue
                
                complete_thread.join(timeout=5.0)
                
                # Проверяем ошибки
                if 'error' in exception_container:
                    raise exception_container['error']
                
                # Засекаем время получения ответа
                response_received_at = timezone.now()
                processing_time = int((response_received_at - request_started_at).total_seconds() * 1000)
                
                # Отправляем финальное событие
                full_response = math_prefix + result_container.get('response', '')
                
                # Сохраняем ответ ассистента
                assistant_message = ChatMessage.objects.create(
                    session=session,
                    message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT,
                    content=full_response,
                    request_started_at=request_started_at,
                    response_received_at=response_received_at,
                    processing_time_ms=processing_time,
                    metadata={
                        'ollama_config': ollama_config,
                        'model': runtime_config.model,
                    } if ollama_config else {'model': runtime_config.model}
                )
                
                # Обновляем время сессии
                session.updated_at = timezone.now()
                session.save(update_fields=['updated_at'])
                
                yield f"data: {json.dumps({
                    'type': 'done',
                    'full_response': full_response,
                    'session_id': str(session.id),
                    'message_id': str(assistant_message.id),
                    'processing_time_ms': processing_time,
                    'timestamp': assistant_message.created_at.isoformat(),
                }, ensure_ascii=False)}\n\n"
                
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
                'message_count': 0,
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




