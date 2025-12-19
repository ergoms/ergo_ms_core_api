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


class ChartColumnSelector:
    """
    Интеллектуальный выбор колонок для графика на основе вопроса.
    """
    
    # Ключевые слова для группировки (X-ось)
    # Включаем все падежные формы для русского языка
    GROUP_KEYWORDS = {
        'группа': ['группа', 'группы', 'группе', 'группу', 'группой', 'группам', 'группами', 'группах'],
        'категория': ['категория', 'категории', 'категорию', 'категорией', 'категориям', 'категориями', 'категориях'],
        'дисциплина': ['дисциплина', 'дисциплины', 'дисциплине', 'дисциплину', 'дисциплиной', 'дисциплинам', 'дисциплинами', 'дисциплинах', 'предмет', 'предметы', 'предметам', 'предметах'],
        'кафедра': ['кафедра', 'кафедры', 'кафедре', 'кафедру', 'кафедрой', 'кафедрам', 'кафедрами', 'кафедрах'],
        'факультет': ['факультет', 'факультета', 'факультету', 'факультетом', 'факультеты', 'факультетам', 'факультетами', 'факультетах'],
        'преподаватель': ['преподаватель', 'преподавателя', 'преподавателю', 'преподавателем', 'преподаватели', 'преподавателям', 'преподавателями', 'преподавателях', 'препод'],
        'курс': ['курс', 'курса', 'курсу', 'курсом', 'курсы', 'курсам', 'курсами', 'курсах'],
        'семестр': ['семестр', 'семестра', 'семестру', 'семестром', 'семестры', 'семестрам', 'семестрами', 'семестрах'],
        'год': ['год', 'года', 'году', 'годом', 'годы', 'годам', 'годами', 'годах'],
        'месяц': ['месяц', 'месяца', 'месяцу', 'месяцем', 'месяцы', 'месяцам', 'месяцами', 'месяцах'],
        'форма': ['форма', 'формы', 'форме', 'форму', 'формой', 'формам', 'формами', 'формах'],
        'уровень': ['уровень', 'уровня', 'уровню', 'уровнем', 'уровни', 'уровням', 'уровнями', 'уровнях'],
        'блок': ['блок', 'блока', 'блоку', 'блоком', 'блоки', 'блокам', 'блоками', 'блоках'],
        'вид': ['вид', 'вида', 'виду', 'видом', 'виды', 'видам', 'видами', 'видах', 'тип', 'типа', 'типу', 'типом', 'типы', 'типам', 'типами', 'типах'],
    }
    
    # Ключевые слова для значений (Y-ось)
    # Включаем все падежные формы для русского языка
    # Также добавляем синонимы и связанные понятия
    VALUE_KEYWORDS = {
        # Нагрузка измеряется в часах, поэтому включаем "часов", "итого"
        'нагрузка': ['нагрузка', 'нагрузки', 'нагрузке', 'нагрузку', 'нагрузкой', 'нагрузкам', 'нагрузками', 'нагрузках', 'часов', 'итого', 'аудитор'],
        'часы': ['час', 'часа', 'часу', 'часом', 'часы', 'часов', 'часам', 'часами', 'часах', 'итого', 'аудитор'],
        'количество': ['количество', 'количества', 'количеству', 'количеством', 'кол-во', 'кол', 'число', 'числа', 'числу', 'числом'],
        'студенты': ['студент', 'студента', 'студенту', 'студентом', 'студенты', 'студентов', 'студентам', 'студентами', 'студентах', 'обучающихся', 'обучающимся', 'кол-во студентов'],
        'сумма': ['сумма', 'суммы', 'сумме', 'сумму', 'суммой', 'суммам', 'суммами', 'суммах', 'итого', 'всего'],
        'среднее': ['среднее', 'средняя', 'средний', 'среднего', 'среднему', 'средним', 'avg', 'average'],
        'зет': ['зет', 'зета', 'зету', 'зетом', 'кредит', 'кредита', 'кредиту', 'кредитом', 'кредиты', 'кредитов', 'кредитам', 'кредитами', 'кредитах'],
        'оценка': ['оценка', 'оценки', 'оценке', 'оценку', 'оценкой', 'оценкам', 'оценками', 'оценках', 'балл', 'балла', 'баллу', 'баллом', 'баллы', 'баллов', 'баллам', 'баллами', 'баллах', 'рейтинг', 'рейтинга', 'рейтингу', 'рейтингом'],
    }
    
    # Колонки которые обычно содержат числовые значения
    NUMERIC_COLUMN_PATTERNS = [
        'час', 'кол', 'количество', 'число', 'сумма', 'итого', 'всего',
        'зет', 'балл', 'оценка', 'рейтинг', 'недел', 'аудитор',
        'студент', 'сам', 'экзамен', 'консульт',
    ]
    
    # Колонки для исключения из X-оси (обычно ID или технические)
    EXCLUDE_X_PATTERNS = [
        'id', 'номер', 'столбец', 'index', 'idx',
    ]
    
    @classmethod
    def select_columns(
        cls,
        question: str,
        columns: List[str],
        data: List[Dict[str, Any]]
    ) -> Tuple[Optional[str], Optional[str], str]:
        """
        Выбирает колонки для графика на основе вопроса.
        
        Args:
            question: Вопрос пользователя
            columns: Список колонок
            data: Данные для анализа
            
        Returns:
            Tuple (x_column, y_column, title)
        """
        if not columns or len(columns) < 2:
            return None, None, "График"
        
        question_lower = question.lower()
        
        # Анализируем вопрос для X-оси (группировка)
        x_column = cls._find_group_column(question_lower, columns)
        
        # Анализируем вопрос для Y-оси (значения)
        y_column = cls._find_value_column(question_lower, columns, data, x_column)
        
        # Если не нашли через вопрос, используем эвристику
        if not x_column:
            x_column = cls._find_best_x_column(columns, data)
        
        if not y_column:
            y_column = cls._find_best_y_column(columns, data, x_column)
        
        # Формируем заголовок на основе колонок
        title = cls._generate_title(question_lower, x_column, y_column)
        
        logger.info(
            f"ChartColumnSelector:\n"
            f"  Вопрос: {question}\n"
            f"  Колонки: {columns[:10]}{'...' if len(columns) > 10 else ''}\n"
            f"  Выбрано: X={x_column}, Y={y_column}\n"
            f"  Заголовок: {title}"
        )
        
        return x_column, y_column, title
    
    @classmethod
    def _find_group_column(cls, question_lower: str, columns: List[str]) -> Optional[str]:
        """Ищет колонку для группировки на основе вопроса."""
        
        # Ищем ключевые слова группировки в вопросе
        for keyword_group, keywords in cls.GROUP_KEYWORDS.items():
            for keyword in keywords:
                if keyword in question_lower:
                    # Приоритет 1: Точное совпадение названия колонки
                    for col in columns:
                        col_lower = col.lower().strip()
                        if col_lower == keyword_group or col_lower in keywords:
                            return col
                    
                    # Приоритет 2: Колонка начинается с ключевого слова
                    for col in columns:
                        col_lower = col.lower().strip()
                        if col_lower.startswith(keyword_group) or any(col_lower.startswith(k) for k in keywords):
                            return col
                    
                    # Приоритет 3: Колонка содержит ключевое слово (выбираем самую короткую)
                    matching_cols = []
                    for col in columns:
                        col_lower = col.lower()
                        if keyword_group in col_lower or any(k in col_lower for k in keywords):
                            matching_cols.append(col)
                    
                    if matching_cols:
                        # Возвращаем самую короткую колонку (вероятно более точное совпадение)
                        return min(matching_cols, key=len)
        
        return None
    
    @classmethod
    def _find_value_column(
        cls,
        question_lower: str,
        columns: List[str],
        data: List[Dict[str, Any]],
        exclude_column: Optional[str]
    ) -> Optional[str]:
        """Ищет колонку для значений на основе вопроса."""
        
        # Ищем ключевые слова значений в вопросе
        for keyword_group, keywords in cls.VALUE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in question_lower:
                    # Собираем все подходящие числовые колонки
                    matching_cols = []
                    for col in columns:
                        if col == exclude_column:
                            continue
                        col_lower = col.lower()
                        if keyword_group in col_lower or any(k in col_lower for k in keywords):
                            # Проверяем что колонка числовая
                            if cls._is_numeric_column(col, data):
                                matching_cols.append(col)
                    
                    if matching_cols:
                        # Предпочитаем колонки с "итого" или "всего"
                        for col in matching_cols:
                            col_lower = col.lower()
                            if 'итого' in col_lower or 'всего' in col_lower:
                                return col
                        # Иначе возвращаем первую подходящую
                        return matching_cols[0]
        
        return None
    
    @classmethod
    def _find_best_x_column(cls, columns: List[str], data: List[Dict[str, Any]]) -> str:
        """Эвристика для выбора лучшей X-колонки."""
        
        # Приоритет: категориальные колонки с небольшим числом уникальных значений
        best_col = None
        best_score = -1
        
        for col in columns:
            col_lower = col.lower()
            
            # Исключаем технические колонки
            if any(pattern in col_lower for pattern in cls.EXCLUDE_X_PATTERNS):
                continue
            
            # Подсчитываем уникальные значения
            unique_values = set()
            for row in data[:100]:
                if isinstance(row, dict):
                    val = row.get(col)
                    if val is not None:
                        unique_values.add(str(val))
            
            # Предпочитаем колонки с 2-20 уникальными значениями
            num_unique = len(unique_values)
            if 2 <= num_unique <= 20:
                score = 100 - num_unique  # Меньше уникальных - лучше для группировки
                
                # Бонус за ключевые слова в названии
                for keywords in cls.GROUP_KEYWORDS.values():
                    if any(k in col_lower for k in keywords):
                        score += 50
                        break
                
                if score > best_score:
                    best_score = score
                    best_col = col
        
        # Если не нашли хорошую колонку, берём первую не-числовую
        if not best_col:
            for col in columns:
                col_lower = col.lower()
                if any(pattern in col_lower for pattern in cls.EXCLUDE_X_PATTERNS):
                    continue
                if not cls._is_numeric_column(col, data):
                    return col
            # Если всё числовое, берём первую колонку
            return columns[0]
        
        return best_col
    
    @classmethod
    def _find_best_y_column(
        cls,
        columns: List[str],
        data: List[Dict[str, Any]],
        exclude_column: Optional[str]
    ) -> str:
        """Эвристика для выбора лучшей Y-колонки."""
        
        best_col = None
        best_score = -1
        
        for col in columns:
            if col == exclude_column:
                continue
            
            col_lower = col.lower()
            
            # Проверяем что колонка числовая
            if not cls._is_numeric_column(col, data):
                continue
            
            score = 10  # Базовый скор для числовой колонки
            
            # Бонус за ключевые слова в названии
            for pattern in cls.NUMERIC_COLUMN_PATTERNS:
                if pattern in col_lower:
                    score += 30
                    break
            
            # Бонус за слова "итого", "всего", "сумма"
            if 'итого' in col_lower or 'всего' in col_lower or 'сумма' in col_lower:
                score += 20
            
            if score > best_score:
                best_score = score
                best_col = col
        
        # Если не нашли числовую колонку, берём вторую
        if not best_col and len(columns) >= 2:
            for i, col in enumerate(columns):
                if col != exclude_column:
                    return col
        
        return best_col or (columns[1] if len(columns) > 1 else columns[0])
    
    @classmethod
    def _is_numeric_column(cls, column: str, data: List[Dict[str, Any]]) -> bool:
        """Проверяет, является ли колонка числовой."""
        
        numeric_count = 0
        total_count = 0
        
        for row in data[:20]:  # Проверяем первые 20 строк
            if isinstance(row, dict):
                val = row.get(column)
                if val is not None and val != '' and val != '—':
                    total_count += 1
                    try:
                        float(val)
                        numeric_count += 1
                    except (ValueError, TypeError):
                        pass
        
        # Считаем числовой если >60% значений числовые
        return total_count > 0 and (numeric_count / total_count) > 0.6
    
    @classmethod
    def _generate_title(
        cls,
        question_lower: str,
        x_column: Optional[str],
        y_column: Optional[str]
    ) -> str:
        """Генерирует заголовок графика."""
        
        # Извлекаем суть из вопроса
        title_parts = []
        
        # Ищем что анализируем
        for keyword_group, keywords in cls.VALUE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in question_lower:
                    if keyword_group == 'нагрузка':
                        title_parts.append('Нагрузка')
                    elif keyword_group == 'часы':
                        title_parts.append('Часы')
                    elif keyword_group == 'количество':
                        title_parts.append('Количество')
                    elif keyword_group == 'студенты':
                        title_parts.append('Студенты')
                    break
            if title_parts:
                break
        
        # Ищем по чему группируем
        for keyword_group, keywords in cls.GROUP_KEYWORDS.items():
            for keyword in keywords:
                if keyword in question_lower:
                    if keyword_group == 'группа':
                        title_parts.append('по группам')
                    elif keyword_group == 'дисциплина':
                        title_parts.append('по дисциплинам')
                    elif keyword_group == 'кафедра':
                        title_parts.append('по кафедрам')
                    elif keyword_group == 'преподаватель':
                        title_parts.append('по преподавателям')
                    elif keyword_group == 'факультет':
                        title_parts.append('по факультетам')
                    break
            if len(title_parts) > 1:
                break
        
        if title_parts:
            return ' '.join(title_parts)
        
        # Если не нашли, используем колонки
        if x_column and y_column:
            return f"{y_column} по {x_column}"
        
        return "График данных"


def select_chart_columns(
    question: str,
    columns: List[str],
    data: List[Dict[str, Any]]
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Удобная функция для выбора колонок графика.
    
    Args:
        question: Вопрос пользователя
        columns: Список колонок
        data: Данные
        
    Returns:
        Tuple (x_column, y_column, title)
    """
    return ChartColumnSelector.select_columns(question, columns, data)

