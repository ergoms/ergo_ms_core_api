# Интеллектуальный анализ графиков с помощью AI-ассистента

## Описание

Система позволяет проводить интеллектуальный анализ данных графика по запросу пользователя. AI-ассистент:
- Находит основные статистические показатели (среднее, минимум, максимум)
- Определяет локальные экстремумы (точки максимума и минимума)
- Выявляет аномалии и выбросы в данных
- Определяет тренды и закономерности
- Дает общую оценку данных

## Новый API Endpoint

### POST `/api/ai_assistant/chart_analysis/`

Автоматический анализ данных графика через Ollama.

**Request Body:**
```json
{
  "chart_id": 123,
  "stream": true
}
```

**Response:** Server-Sent Events (SSE) stream

**События:**
- `start` - начало анализа
- `stage` - текущий этап анализа
- `sql_generation` - генерация SQL запроса
- `sql` - финальный SQL запрос
- `commentary` - комментарий от AI
- `complete` - завершение с данными
- `error` - ошибка
- `done` - завершение streaming

## Архитектура

```
ChartPage.vue
    ↓
AssistantWidget.vue (analyzeChart)
    ↓
bi-client.js (analyzeChart)
    ↓
POST /api/ai_assistant/chart_analysis/
    ↓
ChartAnalysisView
    ↓
FastBIService
    ↓
Ollama (mistral7b-tuned)
```

## Как это работает

1. **Загрузка страницы графика** (`ChartPage.vue`)
   - При загрузке страницы с графиком (`/bi/chart/:id`)
   - Система загружает данные графика из датасета
   - Появляется кнопка "Интеллектуальный анализ" (только если есть данные)

2. **Запуск анализа по кнопке**
   - Пользователь нажимает кнопку "Интеллектуальный анализ"
   - Автоматически открывается глобальный чат AI-ассистента
   - Запускается анализ через `assistantService.openAndAnalyzeChart(chartId)`

3. **Обработка на сервере**
   - Получение данных из датасета графика
   - Загрузка данных в Polars DataFrame
   - Генерация вопроса для анализа
   - Обработка через Ollama с streaming

4. **Отображение результатов**
   - Streaming результаты отображаются в реальном времени
   - SQL запросы, комментарии, данные
   - Структурированный анализ с выводами

## Примеры использования

### Использование через кнопку (рекомендуется)
```vue
<template>
  <button @click="runChartAnalysis">
    Интеллектуальный анализ
  </button>
</template>

<script setup>
import { useAssistant } from '@/core/ai-assistant/js/assistantService.js'

const assistant = useAssistant()

function runChartAnalysis() {
  // Открывает чат и запускает анализ
  assistant.openAndAnalyzeChart(chartId.value)
}
</script>
```

### Программный запуск из любого компонента
```javascript
import { useAssistant } from '@/core/ai-assistant/js/assistantService.js'

const assistant = useAssistant()

// Просто открыть чат
assistant.openChat()

// Запустить анализ (чат должен быть открыт)
assistant.analyzeChart(chartId)

// Открыть чат и запустить анализ
assistant.openAndAnalyzeChart(chartId)
```

### Низкоуровневый API (для расширенного использования)
```javascript
import { biClient } from '@/core/ai-assistant/js/bi-client.js'

await biClient.analyzeChart(chartId, (event) => {
  console.log('Event:', event)
  // Обработка событий
})
```

## Требования

- **Ollama** должен быть запущен и доступен
- **Модель** `mistral7b-tuned` должна быть загружена
- График должен содержать данные для анализа

## Безопасность

- ✅ Только авторизованные пользователи
- ✅ Доступ только к своим графикам
- ✅ Временные файлы автоматически удаляются
- ✅ Изоляция данных по пользователям

## Troubleshooting

**Ollama не доступен:**
```bash
# Проверьте, что Ollama запущен
ollama serve

# Проверьте, что модель загружена
ollama list
```

**Ошибка "Нет данных для анализа":**
- Проверьте, что график содержит данные
- Убедитесь, что датасет подключен к графику

**Долгий анализ:**
- Нормально для больших датасетов
- Streaming позволяет видеть прогресс в реальном времени

