from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.shortcuts import get_object_or_404
from django.http import StreamingHttpResponse
import json

from src.core.bi_analysis.bi_datasets.models import FileUpload
from .fast_bi_service import FastBIService, OLLAMA_AVAILABLE


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
        if not OLLAMA_AVAILABLE:
            return Response({
                'success': False,
                'error': 'Ollama не установлен. Установите: pip install llama-index-llms-ollama'
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
        file_id = request.data.get('file_id')
        question = request.data.get('question')
        want_commentary = request.data.get('want_commentary', True)
        use_stream = request.data.get('stream', True)  # По умолчанию streaming включен
        
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
            return self._streaming_response(file_upload, question, want_commentary)
        
        # Обычный режим (без streaming)
        return self._regular_response(file_upload, question, want_commentary)
    
    def _streaming_response(self, file_upload, question, want_commentary):
        """Возвращает streaming ответ через Server-Sent Events."""
        def event_stream():
            service = None
            try:
                # Инициализируем сервис
                service = FastBIService()
                
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
                
                # Callback для streaming событий
                def stream_callback(event):
                    data = json.dumps(event, ensure_ascii=False)
                    return f"data: {data}\n\n"
                
                # Переменная для накопления streaming событий
                events = []
                def collect_events(event):
                    events.append(event)
                
                # Задаем вопрос с streaming
                result = service.ask(question, want_commentary=want_commentary, stream_callback=collect_events)
                
                # Отправляем все накопленные события
                for event in events:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                
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
                    yield f"data: {json.dumps(final_data, ensure_ascii=False)}\n\n"
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
    
    def _regular_response(self, file_upload, question, want_commentary):
        """Возвращает обычный (не streaming) ответ."""
        try:
            service = FastBIService()
            
            load_result = service.load_file(
                file_path=file_upload.file.path,
                table_name="user_data"
            )
            
            if not load_result.get('success'):
                return Response({
                    'success': False,
                    'error': 'Ошибка загрузки файла в DuckDB'
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
    Проверить доступность Ollama
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        if not OLLAMA_AVAILABLE:
            return Response({
                'available': False,
                'message': 'llama-index-llms-ollama не установлен'
            })
        
        try:
            from llama_index.llms.ollama import Ollama
            # Пробуем создать клиент
            llm = Ollama(model="mistral7b-tuned", request_timeout=5.0)
            
            return Response({
                'available': True,
                'message': 'Ollama доступен'
            })
        except Exception as e:
            return Response({
                'available': False,
                'message': f'Ошибка подключения к Ollama: {str(e)}'
            })




