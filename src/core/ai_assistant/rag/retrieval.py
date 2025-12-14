"""
Сервис для поиска релевантных документов в RAG системе
Использует векторный поиск по схожести embeddings
"""
import logging
import math
from typing import List, Dict, Any, Optional, Tuple

from ..models import KnowledgeDocument, KnowledgeChunk
from .embeddings import OllamaEmbeddingsService, EmbeddingsError

logger = logging.getLogger(__name__)


class RAGRetrievalError(Exception):
    """Общее исключение для ошибок retrieval в RAG."""
    pass


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Вычисляет косинусное сходство между двумя векторами
    
    Args:
        vec1: Первый вектор
        vec2: Второй вектор
        
    Returns:
        Косинусное сходство (от -1 до 1, где 1 - максимальное сходство)
    """
    if len(vec1) != len(vec2):
        raise ValueError(f"Векторы должны иметь одинаковую длину: {len(vec1)} != {len(vec2)}")
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(a * a for a in vec2))
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)


class RAGRetrievalService:
    """
    Сервис для поиска релевантных chunks документов по запросу пользователя
    
    Использует векторный поиск: генерирует embedding для запроса и ищет
    наиболее похожие chunks по косинусному сходству.
    """
    
    def __init__(
        self,
        embeddings_service: OllamaEmbeddingsService,
        top_k: int = 5,
        similarity_threshold: float = 0.0,
    ):
        """
        Инициализация сервиса retrieval
        
        Args:
            embeddings_service: Сервис для генерации embeddings
            top_k: Количество наиболее релевантных chunks для возврата
            similarity_threshold: Минимальный порог схожести (0.0 - 1.0). Chunks с меньшей схожестью игнорируются
        """
        self.embeddings_service = embeddings_service
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
    
    def retrieve_relevant_chunks(
        self,
        query: str,
        user: Optional[Any] = None,
        document_ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Находит наиболее релевантные chunks для запроса пользователя
        
        Args:
            query: Текст запроса пользователя
            user: Пользователь (для фильтрации по владельцу документов). Если None, ищет по всем документам
            document_ids: Список ID документов для ограничения поиска. Если None, ищет по всем документам
            limit: Максимальное количество chunks для возврата (переопределяет top_k)
            
        Returns:
            Список словарей с информацией о найденных chunks:
            {
                "chunk_id": str,
                "document_id": str,
                "document_title": str,
                "content": str,
                "chunk_index": int,
                "similarity": float,
                "metadata": dict,
            }
            Отсортированы по убыванию схожести
            
        Raises:
            RAGRetrievalError: При ошибке поиска
        """
        if not query or not query.strip():
            raise RAGRetrievalError("Запрос не может быть пустым")
        
        try:
            # Генерируем embedding для запроса
            query_embedding = self.embeddings_service.generate_embedding(query.strip())
            
            # Получаем все проиндексированные chunks
            chunks_query = KnowledgeChunk.objects.select_related('document').filter(
                document__is_indexed=True,
                embedding_model=self.embeddings_service._model,  # Только chunks с той же моделью embeddings
            )
            
            # Фильтруем по пользователю, если указан
            if user is not None:
                chunks_query = chunks_query.filter(document__user=user)
            
            # Фильтруем по документам, если указаны
            if document_ids:
                chunks_query = chunks_query.filter(document_id__in=document_ids)
            
            # Вычисляем схожесть для каждого chunk
            results = []
            for chunk in chunks_query:
                try:
                    similarity = cosine_similarity(query_embedding, chunk.embedding)
                    
                    if similarity >= self.similarity_threshold:
                        results.append({
                            "chunk_id": str(chunk.id),
                            "document_id": str(chunk.document.id),
                            "document_title": chunk.document.title,
                            "content": chunk.content,
                            "chunk_index": chunk.chunk_index,
                            "similarity": similarity,
                            "metadata": chunk.metadata,
                            "document_metadata": chunk.document.metadata,
                        })
                except Exception as e:
                    logger.warning(f"Ошибка при вычислении схожести для chunk {chunk.id}: {e}")
                    continue
            
            # Сортируем по убыванию схожести
            results.sort(key=lambda x: x["similarity"], reverse=True)
            
            # Ограничиваем количество результатов
            limit = limit or self.top_k
            results = results[:limit]
            
            logger.info(
                f"Найдено {len(results)} релевантных chunks для запроса "
                f"'{query[:50]}...' (проверено {chunks_query.count()} chunks)"
            )
            
            return results
            
        except EmbeddingsError as e:
            raise RAGRetrievalError(f"Ошибка генерации embedding для запроса: {e}") from e
        except Exception as e:
            logger.error(f"Неожиданная ошибка при поиске релевантных chunks: {e}", exc_info=True)
            raise RAGRetrievalError(f"Ошибка поиска: {e}") from e
    
    def build_context_from_chunks(
        self,
        chunks: List[Dict[str, Any]],
        max_context_length: Optional[int] = None,
    ) -> str:
        """
        Формирует контекст из найденных chunks для передачи в LLM
        
        Args:
            chunks: Список найденных chunks (результат retrieve_relevant_chunks)
            max_context_length: Максимальная длина контекста в символах. Если None, используется весь контекст
            
        Returns:
            Отформатированный контекст для промпта
        """
        if not chunks:
            return ""
        
        context_parts = []
        current_length = 0
        
        for i, chunk in enumerate(chunks, 1):
            chunk_text = f"[Документ: {chunk['document_title']}]\n{chunk['content']}\n\n"
            chunk_length = len(chunk_text)
            
            # Проверяем ограничение по длине
            if max_context_length and (current_length + chunk_length) > max_context_length:
                # Пытаемся обрезать последний chunk
                remaining = max_context_length - current_length
                if remaining > 100:  # Минимум 100 символов для chunk
                    chunk_text = chunk_text[:remaining] + "...\n\n"
                    context_parts.append(chunk_text)
                break
            
            context_parts.append(chunk_text)
            current_length += chunk_length
        
        return "".join(context_parts).strip()
    
    def retrieve_and_build_context(
        self,
        query: str,
        user: Optional[Any] = None,
        document_ids: Optional[List[str]] = None,
        max_context_length: Optional[int] = 4000,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Комбинированный метод: находит релевантные chunks и формирует контекст
        
        Args:
            query: Текст запроса пользователя
            user: Пользователь для фильтрации
            document_ids: Список ID документов для ограничения поиска
            max_context_length: Максимальная длина контекста в символах
        
        Returns:
            Кортеж (context, chunks):
            - context: Отформатированный контекст для промпта
            - chunks: Список найденных chunks с метаданными
        """
        chunks = self.retrieve_relevant_chunks(query, user=user, document_ids=document_ids)
        context = self.build_context_from_chunks(chunks, max_context_length=max_context_length)
        return context, chunks

