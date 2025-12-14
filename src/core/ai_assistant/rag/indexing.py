"""
Сервис для индексации документов в RAG системе
Разбивает документы на chunks и создает embeddings
"""
import logging
from typing import List, Dict, Any, Optional
from django.utils import timezone
from django.db import transaction

from ..models import KnowledgeDocument, KnowledgeChunk
from .embeddings import OllamaEmbeddingsService, EmbeddingsError
from .parser import DocumentParserService, DocumentParseError

logger = logging.getLogger(__name__)


class RAGIndexingError(Exception):
    """Общее исключение для ошибок индексации RAG."""
    pass


class RAGIndexingService:
    """
    Сервис для индексации документов в векторную базу знаний
    
    Функционал:
    - Разбиение документов на chunks (по размеру или по предложениям)
    - Генерация embeddings для каждого chunk
    - Сохранение в базу данных
    """
    
    def __init__(
        self,
        embeddings_service: OllamaEmbeddingsService,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        """
        Инициализация сервиса индексации
        
        Args:
            embeddings_service: Сервис для генерации embeddings
            chunk_size: Максимальный размер chunk в символах
            chunk_overlap: Размер перекрытия между chunks в символах (для сохранения контекста)
        """
        self.embeddings_service = embeddings_service
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def _split_text_into_chunks(self, text: str) -> List[Dict[str, Any]]:
        """
        Разбивает текст на chunks
        
        Args:
            text: Текст для разбиения
            
        Returns:
            Список словарей с ключами: content, start_char, end_char
        """
        if not text or not text.strip():
            return []
        
        chunks = []
        text_length = len(text)
        
        # Минимальный размер chunk (чтобы не создавать слишком мелкие chunks)
        min_chunk_size = max(50, self.chunk_size // 10)
        
        # Разбиваем текст на chunks с перекрытием
        start = 0
        chunk_index = 0
        
        while start < text_length:
            # Базовый конец chunk (по максимальному размеру)
            end = min(start + self.chunk_size, text_length)
            
            # Если не последний chunk и не конец текста, пытаемся разбить по границе предложения или слова
            if end < text_length:
                # Сначала ищем ближайшую границу предложения (ищем назад от конца chunk)
                # Увеличиваем область поиска для лучшего разбиения
                sentence_end = None
                search_start = max(start, end - min(300, self.chunk_size // 2))
                for i in range(end - 1, search_start - 1, -1):
                    if text[i] in '.!?\n':
                        sentence_end = i + 1
                        break
                
                # Если нашли границу предложения в пределах разумного, используем её
                # Уменьшаем минимальный порог для более агрессивного разбиения
                if sentence_end and sentence_end > start + min_chunk_size:
                    end = sentence_end
                else:
                    # Если не нашли границу предложения, ищем границу слова (пробел, перенос строки, табуляция)
                    word_end = None
                    search_start = max(start, end - min(150, self.chunk_size // 3))
                    for i in range(end - 1, search_start - 1, -1):
                        if text[i] in ' \n\t':
                            word_end = i + 1
                            break
                    
                    # Если нашли границу слова в пределах разумного, используем её
                    if word_end and word_end > start + min_chunk_size:
                        end = word_end
                    # Если не нашли ни границу предложения, ни слова, оставляем end как есть
                    # (это может произойти для очень длинных слов или строк без пробелов)
            
            chunk_content = text[start:end].strip()
            if chunk_content:
                chunks.append({
                    "content": chunk_content,
                    "start_char": start,
                    "end_char": end,
                    "chunk_index": chunk_index,
                })
            
            # Переходим к следующему chunk с учетом overlap
            # Вычисляем начальную позицию следующего chunk с учетом overlap
            next_start = end - self.chunk_overlap
            
            # Убеждаемся, что мы продвигаемся вперед (хотя бы на минимальный шаг)
            if next_start <= start:
                # Если overlap слишком большой, просто идем вперед минимум на половину chunk_size
                next_start = start + max(min_chunk_size, self.chunk_size - self.chunk_overlap)
            
            # Также ищем границу слова для начала следующего chunk (чтобы не начинать с середины слова)
            if next_start < text_length and next_start > 0:
                # Если мы не в начале текста и не на границе слова, ищем ближайшую границу слова вперед
                if text[next_start] not in ' \n\t':
                    # Ищем ближайший пробел или перенос строки вперед (увеличиваем область поиска)
                    for i in range(next_start, min(text_length, next_start + 100)):
                        if text[i] in ' \n\t':
                            next_start = i + 1
                            break
            
            start = next_start
            chunk_index += 1
            
            # Защита от бесконечного цикла
            if chunk_index > 10000:  # Увеличиваем лимит для больших документов
                logger.warning(f"Превышен лимит chunks (10000), останавливаем разбиение. Текст: {text[:100]}...")
                break
        
        return chunks
    
    def index_document(
        self,
        document: KnowledgeDocument,
        force_reindex: bool = False,
    ) -> Dict[str, Any]:
        """
        Индексирует документ: извлекает текст (если есть файл), разбивает на chunks и создает embeddings
        
        Args:
            document: Документ для индексации
            force_reindex: Если True, переиндексирует документ даже если он уже индексирован
            
        Returns:
            Словарь с результатами индексации:
            {
                "success": bool,
                "chunks_created": int,
                "chunks_updated": int,
                "chunks_deleted": int,
                "error": str (если была ошибка)
            }
            
        Raises:
            RAGIndexingError: При ошибке индексации
        """
        if document.is_indexed and not force_reindex:
            logger.info(f"Документ {document.id} уже индексирован, пропускаем")
            return {
                "success": True,
                "chunks_created": 0,
                "chunks_updated": 0,
                "chunks_deleted": 0,
                "message": "Документ уже индексирован",
            }
        
        try:
            # Если есть файл, но нет контента - извлекаем текст из файла
            text_content = document.content
            if document.file and not text_content:
                try:
                    logger.info(f"Извлекаем текст из файла {document.file.name} для документа {document.id}")
                    file_path = document.file.path if hasattr(document.file, 'path') else None
                    text_content, file_type = DocumentParserService.parse_document(
                        file_path=file_path,
                        filename=document.file.name
                    )
                    
                    # Сохраняем извлеченный контент и тип файла
                    document.content = text_content
                    if not document.file_type:
                        document.file_type = file_type
                    document.save(update_fields=['content', 'file_type'])
                    
                    logger.info(f"Успешно извлечен текст из файла (тип: {file_type}, длина: {len(text_content)} символов)")
                except DocumentParseError as e:
                    raise RAGIndexingError(f"Ошибка парсинга файла: {e}") from e
                except Exception as e:
                    raise RAGIndexingError(f"Неожиданная ошибка при извлечении текста из файла: {e}") from e
            
            if not text_content or not text_content.strip():
                raise RAGIndexingError(
                    "Документ не содержит текстового контента. "
                    "Убедитесь, что указан текст или загружен файл с текстом."
                )
            
            # Разбиваем текст на chunks
            chunks_data = self._split_text_into_chunks(text_content)
            
            if not chunks_data:
                raise RAGIndexingError("Не удалось разбить документ на chunks (возможно, документ пуст)")
            
            logger.info(f"Разбили документ {document.id} на {len(chunks_data)} chunks")
            
            # Генерируем embeddings для всех chunks батчем
            texts_for_embedding = [chunk["content"] for chunk in chunks_data]
            
            try:
                embeddings_list = self.embeddings_service.generate_embeddings_batch(texts_for_embedding)
            except EmbeddingsError as e:
                raise RAGIndexingError(f"Ошибка генерации embeddings: {e}") from e
            
            if len(embeddings_list) != len(chunks_data):
                logger.warning(
                    f"Количество embeddings ({len(embeddings_list)}) не совпадает с количеством chunks ({len(chunks_data)})"
                )
                # Обрезаем или дополняем до нужного количества
                if len(embeddings_list) < len(chunks_data):
                    raise RAGIndexingError(
                        f"Получено недостаточно embeddings: {len(embeddings_list)} из {len(chunks_data)}"
                    )
                embeddings_list = embeddings_list[:len(chunks_data)]
            
            # Сохраняем chunks в базу данных в транзакции
            with transaction.atomic():
                chunks_created = 0
                chunks_updated = 0
                chunks_deleted = 0
                
                # Если переиндексируем, удаляем старые chunks
                if force_reindex:
                    old_chunks_count = document.chunks.count()
                    if old_chunks_count > 0:
                        document.chunks.all().delete()
                        chunks_deleted = old_chunks_count
                        logger.info(f"Удалили {chunks_deleted} старых chunks документа {document.id}")
                
                # Создаем новые chunks
                embedding_model = self.embeddings_service._model
                
                for i, (chunk_data, embedding) in enumerate(zip(chunks_data, embeddings_list)):
                    chunk, created = KnowledgeChunk.objects.update_or_create(
                        document=document,
                        chunk_index=i,
                        defaults={
                            "content": chunk_data["content"],
                            "start_char": chunk_data["start_char"],
                            "end_char": chunk_data["end_char"],
                            "embedding": embedding,
                            "embedding_model": embedding_model,
                        }
                    )
                    
                    if created:
                        chunks_created += 1
                    else:
                        chunks_updated += 1
                
                # Обновляем статус индексации документа
                document.is_indexed = True
                document.indexed_at = timezone.now()
                document.save(update_fields=["is_indexed", "indexed_at"])
                
                logger.info(
                    f"Успешно проиндексирован документ {document.id}: "
                    f"создано {chunks_created}, обновлено {chunks_updated}, удалено {chunks_deleted} chunks"
                )
                
                return {
                    "success": True,
                    "chunks_created": chunks_created,
                    "chunks_updated": chunks_updated,
                    "chunks_deleted": chunks_deleted,
                    "total_chunks": len(chunks_data),
                }
                
        except RAGIndexingError:
            raise
        except Exception as e:
            logger.error(f"Неожиданная ошибка при индексации документа {document.id}: {e}", exc_info=True)
            raise RAGIndexingError(f"Ошибка индексации: {e}") from e
    
    def reindex_document(self, document: KnowledgeDocument) -> Dict[str, Any]:
        """
        Переиндексирует документ (удаляет старые chunks и создает новые)
        
        Args:
            document: Документ для переиндексации
            
        Returns:
            Результаты индексации (см. index_document)
        """
        return self.index_document(document, force_reindex=True)
    
    def delete_document_index(self, document: KnowledgeDocument) -> None:
        """
        Удаляет все chunks документа (деиндексирует)
        
        Args:
            document: Документ для деиндексации
        """
        with transaction.atomic():
            chunks_count = document.chunks.count()
            document.chunks.all().delete()
            document.is_indexed = False
            document.indexed_at = None
            document.save(update_fields=["is_indexed", "indexed_at"])
            logger.info(f"Деиндексирован документ {document.id}: удалено {chunks_count} chunks")

