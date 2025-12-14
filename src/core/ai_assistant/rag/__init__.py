"""
Модуль RAG (Retrieval-Augmented Generation) для AI ассистента.

Содержит сервисы для:
- Генерации embeddings (embeddings.py)
- Парсинга документов (parser.py)
- Индексации документов (indexing.py)
- Поиска релевантных документов (retrieval.py)
"""

from .embeddings import OllamaEmbeddingsService, EmbeddingsError
from .parser import DocumentParserService, DocumentParseError
from .indexing import RAGIndexingService, RAGIndexingError
from .retrieval import RAGRetrievalService, RAGRetrievalError, cosine_similarity

__all__ = [
    'OllamaEmbeddingsService',
    'EmbeddingsError',
    'DocumentParserService',
    'DocumentParseError',
    'RAGIndexingService',
    'RAGIndexingError',
    'RAGRetrievalService',
    'RAGRetrievalError',
    'cosine_similarity',
]

