# -*- coding: utf-8 -*-
"""
Модуль определения намерений пользователя в BI-чате.
Использует контекстный анализ без лишних LLM-вызовов.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class UserIntent(Enum):
    """Типы намерений пользователя."""
    CHART = "chart"           # Построить график
    DATA_QUERY = "data_query" # Запрос данных (SQL)
    DOCUMENT = "document"     # Создать документ/отчёт
    DESCRIPTION = "description"  # Описание файла/данных
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    """Результат определения намерения."""
    intent: UserIntent
    confidence: float  # 0.0 - 1.0
    chart_type: Optional[str] = None  # Тип графика если intent == CHART
    use_previous_data: bool = False  # Использовать данные из предыдущего ответа
    reason: str = ""  # Причина определения


class ChartKeywords:
    """Ключевые слова для определения графиков."""
    
    # Явные запросы на график (высокая уверенность)
    EXPLICIT_CHART = [
        'построй график', 'создай график', 'покажи график', 'нарисуй график',
        'сделай график', 'выведи график', 'отобрази график',
        'построй диаграмму', 'создай диаграмму', 'покажи диаграмму',
        'нарисуй диаграмму', 'сделай диаграмму',
    ]
    
    # Слова указывающие на график (средняя уверенность)
    CHART_WORDS = [
        'график', 'диаграмма', 'диаграмму', 'графике', 'графиком',
        'гистограмма', 'гистограмму', 'визуализация', 'визуализируй',
        'chart', 'plot', 'diagram',
    ]
    
    # Слова указывающие на тип графика
    CHART_TYPE_KEYWORDS = {
        'line': ['линейный', 'линия', 'тренд', 'временной', 'динамика', 'line'],
        'bar': ['столбчатый', 'столбцы', 'бар', 'гистограмма', 'bar', 'column'],
        'pie': ['круговой', 'пирог', 'доля', 'доли', 'процент', 'pie'],
        'area': ['площадной', 'площадь', 'area'],
        'scatter': ['точечный', 'scatter', 'корреляция', 'разброс'],
    }
    
    # Слова указывающие на использование предыдущих данных
    PREVIOUS_DATA_INDICATORS = [
        'по этим данным', 'по этой таблице', 'по результатам',
        'на основе этих', 'из этих данных', 'по полученным',
        'визуализируй это', 'покажи это', 'отобрази это',
        'по ним', 'их', 'эти данные', 'эту таблицу',
    ]


class DocumentKeywords:
    """Ключевые слова для определения документов."""
    
    EXPLICIT_DOC = [
        'создай отчёт', 'создай отчет', 'сделай отчёт', 'сделай отчет',
        'создай документ', 'сделай документ', 'сформируй отчёт', 'сформируй отчет',
        'выгрузи отчёт', 'выгрузи отчет', 'экспортируй',
        'создай word', 'создай pdf', 'сохрани как документ',
        'сгенерируй отчёт', 'сгенерируй отчет',
        'выгрузи в файл', 'сохрани в файл', 'скачать отчёт', 'скачать отчет',
    ]
    
    DOC_WORDS = [
        'отчёт', 'отчет', 'документ', 'word', 'pdf', 'экспорт',
    ]


class IntentDetector:
    """
    Детектор намерений пользователя на основе контекста.
    Не использует LLM для определения - только анализ текста и контекста.
    """
    
    def __init__(self, chat_context: Optional[List[Dict[str, Any]]] = None):
        """
        Args:
            chat_context: Контекст чата - список сообщений
        """
        self.chat_context = chat_context or []
    
    def detect(self, question: str) -> IntentResult:
        """
        Определяет намерение пользователя на основе вопроса и контекста.
        
        Args:
            question: Вопрос пользователя
            
        Returns:
            IntentResult с определённым намерением
        """
        question_lower = question.lower().strip()
        
        # 1. Проверяем явные запросы на график
        chart_result = self._check_chart_intent(question_lower)
        if chart_result.confidence >= 0.8:
            return chart_result
        
        # 2. Проверяем явные запросы на документ
        doc_result = self._check_document_intent(question_lower)
        if doc_result.confidence >= 0.8:
            return doc_result
        
        # 3. Проверяем описательные вопросы
        desc_result = self._check_description_intent(question_lower)
        if desc_result.confidence >= 0.7:
            return desc_result
        
        # 4. Если есть слова графика со средней уверенностью
        if chart_result.confidence >= 0.5:
            return chart_result
        
        # 5. Если есть слова документа со средней уверенностью
        if doc_result.confidence >= 0.5:
            return doc_result
        
        # 6. По умолчанию - запрос данных
        return IntentResult(
            intent=UserIntent.DATA_QUERY,
            confidence=0.6,
            reason="По умолчанию - запрос данных"
        )
    
    def _check_chart_intent(self, question_lower: str) -> IntentResult:
        """Проверяет намерение построить график."""
        
        # Проверяем явные запросы (высокая уверенность)
        for keyword in ChartKeywords.EXPLICIT_CHART:
            if keyword in question_lower:
                chart_type = self._detect_chart_type(question_lower)
                use_prev = self._should_use_previous_data(question_lower)
                return IntentResult(
                    intent=UserIntent.CHART,
                    confidence=0.95,
                    chart_type=chart_type,
                    use_previous_data=use_prev,
                    reason=f"Явный запрос: '{keyword}'"
                )
        
        # Проверяем слова графика (средняя уверенность)
        for word in ChartKeywords.CHART_WORDS:
            if word in question_lower:
                chart_type = self._detect_chart_type(question_lower)
                use_prev = self._should_use_previous_data(question_lower)
                
                # Повышаем уверенность если есть данные в контексте
                confidence = 0.7
                if self._has_data_in_context():
                    confidence = 0.85
                    use_prev = True
                
                return IntentResult(
                    intent=UserIntent.CHART,
                    confidence=confidence,
                    chart_type=chart_type,
                    use_previous_data=use_prev,
                    reason=f"Слово графика: '{word}'"
                )
        
        # Проверяем контекст: если просят "покажи/выведи" и есть данные
        show_words = ['покажи', 'выведи', 'отобрази', 'визуализируй']
        if any(w in question_lower for w in show_words):
            if self._has_data_in_context() and self._should_use_previous_data(question_lower):
                chart_type = self._detect_chart_type(question_lower)
                return IntentResult(
                    intent=UserIntent.CHART,
                    confidence=0.6,
                    chart_type=chart_type,
                    use_previous_data=True,
                    reason="Запрос визуализации с данными в контексте"
                )
        
        return IntentResult(
            intent=UserIntent.CHART,
            confidence=0.0,
            reason="Нет признаков графика"
        )
    
    def _check_document_intent(self, question_lower: str) -> IntentResult:
        """Проверяет намерение создать документ."""
        
        # Проверяем явные запросы
        for keyword in DocumentKeywords.EXPLICIT_DOC:
            if keyword in question_lower:
                return IntentResult(
                    intent=UserIntent.DOCUMENT,
                    confidence=0.95,
                    reason=f"Явный запрос документа: '{keyword}'"
                )
        
        # Проверяем слова документа
        for word in DocumentKeywords.DOC_WORDS:
            if word in question_lower:
                # Короткий вопрос со словом документа
                if len(question_lower.split()) <= 5:
                    return IntentResult(
                        intent=UserIntent.DOCUMENT,
                        confidence=0.8,
                        reason=f"Короткий запрос со словом: '{word}'"
                    )
                return IntentResult(
                    intent=UserIntent.DOCUMENT,
                    confidence=0.6,
                    reason=f"Слово документа: '{word}'"
                )
        
        return IntentResult(
            intent=UserIntent.DOCUMENT,
            confidence=0.0,
            reason="Нет признаков документа"
        )
    
    def _check_description_intent(self, question_lower: str) -> IntentResult:
        """Проверяет намерение получить описание файла/данных."""
        
        description_patterns = [
            'что в этом файле', 'что содержит', 'описание файла',
            'расскажи о файле', 'что за файл', 'какие данные',
            'какая информация', 'опиши файл', 'что это за данные',
            'что здесь', 'какие колонки', 'структура данных',
        ]
        
        for pattern in description_patterns:
            if pattern in question_lower:
                return IntentResult(
                    intent=UserIntent.DESCRIPTION,
                    confidence=0.9,
                    reason=f"Запрос описания: '{pattern}'"
                )
        
        return IntentResult(
            intent=UserIntent.DESCRIPTION,
            confidence=0.0,
            reason="Нет признаков описания"
        )
    
    def _detect_chart_type(self, question_lower: str) -> str:
        """Определяет тип графика из вопроса."""
        
        for chart_type, keywords in ChartKeywords.CHART_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in question_lower:
                    return chart_type
        
        # По умолчанию - столбчатый график
        return 'bar'
    
    def _should_use_previous_data(self, question_lower: str) -> bool:
        """Определяет, нужно ли использовать данные из предыдущего ответа."""
        
        # Проверяем явные указатели
        for indicator in ChartKeywords.PREVIOUS_DATA_INDICATORS:
            if indicator in question_lower:
                return True
        
        # Если вопрос короткий и есть данные в контексте - вероятно про них
        if len(question_lower.split()) <= 4 and self._has_data_in_context():
            return True
        
        return False
    
    def _has_data_in_context(self) -> bool:
        """Проверяет, есть ли данные в контексте чата."""
        
        for msg in reversed(self.chat_context):
            if msg.get('type') == 'assistant':
                metadata = msg.get('metadata', {})
                if metadata.get('data') and metadata.get('columns'):
                    return True
        
        return False
    
    def get_last_data_from_context(self) -> Tuple[Optional[List], Optional[List]]:
        """
        Получает последние данные из контекста.
        
        Returns:
            Tuple (data, columns) или (None, None)
        """
        for msg in reversed(self.chat_context):
            if msg.get('type') == 'assistant':
                metadata = msg.get('metadata', {})
                data = metadata.get('data')
                columns = metadata.get('columns')
                if data and columns:
                    return data, columns
        
        return None, None
    
    def get_context_summary(self) -> str:
        """
        Получает краткое описание контекста для логирования.
        """
        if not self.chat_context:
            return "Контекст пуст"
        
        summary_parts = []
        for i, msg in enumerate(self.chat_context[-5:]):
            msg_type = msg.get('type', 'unknown')
            content = msg.get('content', '')[:50]
            metadata = msg.get('metadata', {})
            has_data = bool(metadata.get('data'))
            
            summary_parts.append(
                f"  [{i+1}] {msg_type}: {content}{'...' if len(msg.get('content', '')) > 50 else ''}"
                f"{' [ДАННЫЕ]' if has_data else ''}"
            )
        
        return "Контекст (последние 5):\n" + "\n".join(summary_parts)


def detect_intent(question: str, chat_context: Optional[List[Dict[str, Any]]] = None) -> IntentResult:
    """
    Удобная функция для определения намерения.
    
    Args:
        question: Вопрос пользователя
        chat_context: Контекст чата
        
    Returns:
        IntentResult
    """
    detector = IntentDetector(chat_context)
    result = detector.detect(question)
    
    # Логируем результат
    logger.info(
        f"Intent Detection:\n"
        f"  Вопрос: {question}\n"
        f"  Намерение: {result.intent.value}\n"
        f"  Уверенность: {result.confidence:.2f}\n"
        f"  Причина: {result.reason}\n"
        f"  Тип графика: {result.chart_type}\n"
        f"  Использовать пред. данные: {result.use_previous_data}\n"
        f"  {detector.get_context_summary()}"
    )
    
    return result

