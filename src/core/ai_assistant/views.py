from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.shortcuts import get_object_or_404
from django.http import StreamingHttpResponse
import json
import math

from src.core.bi_analysis.bi_datasets.models import FileUpload, Dataset
from .fast_bi_service import FastBIService, DEFAULT_MODEL, OLLAMA_BASE_URL
from .config import build_runtime_config
from .llm_clients import build_llm_client, LLMClientError
from src.core.bi_analysis.bi_charts.models import Chart
import pandas as pd
import numpy as np
from scipy import signal, stats


def _sanitize_for_json(obj):
    """
    Рекурсивно очищает объект от значений, которые не поддерживаются JSON.
    NaN, Infinity, -Infinity заменяются на None.
    """
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_for_json(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, (np.floating, np.integer)):
        val = float(obj) if isinstance(obj, np.floating) else int(obj)
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val
    elif pd.isna(obj):
        return None
    return obj


def _safe_json_dumps(obj, **kwargs):
    """Безопасная JSON сериализация с обработкой NaN/Infinity."""
    return json.dumps(_sanitize_for_json(obj), **kwargs)


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
    runtime_config = build_runtime_config(ollama_config or {})
    provider_name = runtime_config.provider.value if hasattr(runtime_config.provider, "value") else str(runtime_config.provider)
    base_url = runtime_config.provider_config.get("base_url", runtime_config.base_url or OLLAMA_BASE_URL)
    client = build_llm_client(
        provider=provider_name,
        model=runtime_config.model,
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
        
        # Если запрошен streaming режим
        if use_stream:
            return self._streaming_response(file_upload, question, want_commentary, ollama_config)
        
        # Обычный режим (без streaming)
        return self._regular_response(file_upload, question, want_commentary, ollama_config)
    
    def _streaming_response(self, file_upload, question, want_commentary, ollama_config=None):
        """Возвращает streaming ответ через Server-Sent Events."""
        def event_stream():
            service = None
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
                
                # Callback для streaming событий - отправляем сразу!
                def stream_callback(event):
                    # Отправляем событие немедленно
                    data = json.dumps(event, ensure_ascii=False)
                    # ВАЖНО: не return, а используем nonlocal для доступа к yield
                    streaming_events.append(event)
                
                # Список для временного хранения (используется в callback)
                streaming_events = []
                
                # Задаем вопрос с streaming
                # Используем генератор вместо накопления
                import threading
                result_container = {}
                exception_container = {}
                
                def run_ask():
                    try:
                        def immediate_callback(event):
                            streaming_events.append(event)
                        result_container['result'] = service.ask(question, want_commentary=want_commentary, stream_callback=immediate_callback)
                    except Exception as e:
                        exception_container['error'] = e
                
                # Запускаем в отдельном потоке
                ask_thread = threading.Thread(target=run_ask)
                ask_thread.start()
                
                # Отправляем события по мере их поступления
                while ask_thread.is_alive() or streaming_events:
                    while streaming_events:
                        event = streaming_events.pop(0)
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    # Небольшая пауза чтобы не спамить
                    import time
                    time.sleep(0.01)
                
                ask_thread.join()
                
                # Проверяем ошибки
                if 'error' in exception_container:
                    raise exception_container['error']
                
                result = result_container.get('result', {})
                
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
    
    def _regular_response(self, file_upload, question, want_commentary, ollama_config=None):
        """Возвращает обычный (не streaming) ответ."""
        try:
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
            
            if result['success']:
                return Response({
                    'success': True,
                    'file_name': file_upload.name,
                    'question': question,
                    'sql': result['sql'],
                    'data': result['data'],
                    'comment': result['comment'],
                    'rows': result['rows'],
                    'columns': result['columns'],
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
                z_scores = np.abs(stats.zscore(y_values))
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
                slope, intercept, r_value, p_value, std_err = stats.linregress(x_numeric, y_values)
                
                if abs(slope) < 0.01:
                    trend_type = "стабильный"
                elif slope > 0:
                    trend_type = "восходящий"
                else:
                    trend_type = "нисходящий"
                
                results['trend'] = {
                    'type': trend_type,
                    'slope': float(slope),
                    'r_squared': float(r_value ** 2),
                    'change_per_point': float(slope)
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
    Простой RAG чат для общих вопросов
    
    Body:
    {
        "message": "Как работает система?"
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        message = request.data.get('message')
        ollama_config = request.data.get('ollama_config')  # Настройки Ollama из module-config
        
        if not message or not message.strip():
            return Response({
                'success': False,
                'error': 'Не указано сообщение'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            runtime_config, client = _create_ollama_client(ollama_config)
            temperature = (ollama_config or {}).get('temperature', 0.3)
            max_tokens = (ollama_config or {}).get('max_tokens', 512)

            system_prompt = """Ты - полезный AI ассистент системы ERGO MS. 
Твоя задача - помогать пользователям с вопросами о системе, навигации и функционале.
Отвечай кратко, по делу и дружелюбно на русском языке.
Если не знаешь ответа, честно скажи об этом."""
            
            # Формируем сообщения
            full_prompt = f"{system_prompt}\n\nВопрос пользователя: {message}"
            
            answer = client.complete(
                full_prompt,
                num_predict=max_tokens,
                temperature=temperature,
                stream=False,
            ).strip()
            
            return Response({
                'success': True,
                'response': answer,
                'message': answer,  # Для совместимости
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




