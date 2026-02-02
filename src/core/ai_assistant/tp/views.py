import json
import logging
import os
import uuid

from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from src.core.ai_assistant.models import ChatSession, ChatMessage
from src.core.ai_assistant.rag import DocumentParserService
from src.core.utils.mixins import SwaggerSafeMixin

from .models import TechnologicalProcessDocument
from .converter import TPDocumentConverter
from .tasks import process_tp_documents, process_tp_chat_response
from .prompt_utils import get_tp_system_prompt, TP_INTRO_MESSAGE

logger = logging.getLogger(__name__)


def create_tp_intro_message(session):
    """Создаёт стартовое сообщение чата техпроцесса в БД."""
    ChatMessage.objects.create(
        session=session,
        message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT,
        content=TP_INTRO_MESSAGE,
    )


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

        temp_dir = os.path.join(settings.MEDIA_ROOT, 'tp_upload_temp')
        os.makedirs(temp_dir, exist_ok=True)
        file_infos = []
        saved_paths = []
        for uploaded_file in uploaded_files:
            filename = uploaded_file.name
            file_type = DocumentParserService.get_file_type(filename)
            if file_type != 'docx':
                continue
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            temp_path = os.path.join(temp_dir, unique_name)
            try:
                with open(temp_path, 'wb') as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)
                file_infos.append({'temp_path': temp_path, 'original_filename': filename})
                saved_paths.append(temp_path)
            except Exception as e:
                logger.error(f"Ошибка сохранения временного файла {filename}: {e}", exc_info=True)
                for p in saved_paths:
                    try:
                        if os.path.isfile(p):
                            os.remove(p)
                    except OSError:
                        pass
                return Response({
                    'success': False,
                    'error': f'Ошибка сохранения файла: {str(e)}',
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not file_infos:
            return Response({
                'success': False,
                'error': 'Нет подходящих файлов DOCX для загрузки.',
            }, status=status.HTTP_400_BAD_REQUEST)

        task = process_tp_documents.apply_async(
            args=[session_id, user.pk],
            kwargs={'file_infos': file_infos, 'metadata': metadata},
        )
        return Response(
            {
                'success': True,
                'task_id': task.id,
                'message': 'Документы поставлены в очередь на обработку.',
            },
            status=status.HTTP_202_ACCEPTED,
        )

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
    return get_tp_system_prompt()


class TPUploadStatusView(APIView):
    """Опрос статуса асинхронной загрузки документов техпроцесса по task_id."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, task_id):
        from celery.result import AsyncResult
        from src.config.celery import celery_app
        result = AsyncResult(task_id, app=celery_app)
        if result.state == 'PENDING':
            return Response({
                'success': True,
                'status': 'PENDING',
                'task_id': task_id,
                'message': 'Обработка в очереди.',
            }, status=status.HTTP_200_OK)
        if result.state == 'FAILURE':
            return Response({
                'success': False,
                'status': 'FAILURE',
                'task_id': task_id,
                'error': str(result.result) if result.result else 'Ошибка выполнения задачи.',
            }, status=status.HTTP_200_OK)
        if result.state == 'SUCCESS':
            data = result.result
            if isinstance(data, dict):
                return Response({
                    'success': data.get('success', True),
                    'status': 'SUCCESS',
                    'task_id': task_id,
                    'documents': data.get('documents', []),
                    'count': data.get('count', 0),
                    'errors': data.get('errors'),
                    'message': data.get('message'),
                }, status=status.HTTP_200_OK)
            return Response({
                'success': True,
                'status': 'SUCCESS',
                'task_id': task_id,
                'documents': [],
                'message': None,
            }, status=status.HTTP_200_OK)
        return Response({
            'success': True,
            'status': result.state,
            'task_id': task_id,
        }, status=status.HTTP_200_OK)


class TPChatStatusView(APIView):
    """Опрос статуса задачи ответа модели в чате техпроцессов по task_id."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, task_id):
        from celery.result import AsyncResult
        from src.config.celery import celery_app
        result = AsyncResult(task_id, app=celery_app)
        if result.state == 'PENDING':
            return Response({
                'success': True,
                'status': 'PENDING',
                'task_id': task_id,
                'message': 'Обработка в очереди.',
            }, status=status.HTTP_200_OK)
        if result.state == 'FAILURE':
            return Response({
                'success': False,
                'status': 'FAILURE',
                'task_id': task_id,
                'error': str(result.result) if result.result else 'Ошибка выполнения задачи.',
            }, status=status.HTTP_200_OK)
        if result.state == 'SUCCESS':
            data = result.result
            if isinstance(data, dict):
                return Response({
                    'success': data.get('success', True),
                    'status': 'SUCCESS',
                    'task_id': task_id,
                    'full_response': data.get('full_response', ''),
                    'message_id': data.get('message_id'),
                    'session_id': data.get('session_id'),
                    'processing_time_ms': data.get('processing_time_ms'),
                    'timestamp': data.get('timestamp'),
                    'error': data.get('error'),
                }, status=status.HTTP_200_OK)
            return Response({
                'success': True,
                'status': 'SUCCESS',
                'task_id': task_id,
                'full_response': '',
                'message_id': None,
                'session_id': None,
                'processing_time_ms': None,
            }, status=status.HTTP_200_OK)
        return Response({
            'success': True,
            'status': result.state,
            'task_id': task_id,
        }, status=status.HTTP_200_OK)


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
            create_tp_intro_message(session)
        ChatMessage.objects.create(
            session=session,
            message_type=ChatMessage.MESSAGE_TYPE_USER,
            content=message,
            metadata={'ollama_config': ollama_config} if ollama_config else {}
        )
        task = process_tp_chat_response.apply_async(
            args=[str(session.id), request.user.pk, message.strip()],
            kwargs={'ollama_config': ollama_config or {}},
        )
        return Response(
            {
                'success': True,
                'task_id': task.id,
                'session_id': str(session.id),
                'message': 'Запрос поставлен в очередь на обработку.',
            },
            status=status.HTTP_202_ACCEPTED,
        )
