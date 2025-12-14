---
name: "Анализ"
description: "Шаблон для аналитических документов с выводами и рекомендациями"
format: ["docx", "pdf"]
variables:
  - name: "title"
    description: "Тема анализа"
    required: true
  - name: "summary"
    description: "Краткое резюме"
    required: true
  - name: "analysis"
    description: "Детальный анализ"
    required: true
  - name: "conclusions"
    description: "Выводы"
    required: true
  - name: "recommendations"
    description: "Рекомендации"
    required: false
---

# {{title}}

## Резюме

{{summary}}

## Анализ

{{analysis}}

## Выводы

{{conclusions}}

## Рекомендации

{{recommendations}}

---

*Аналитический документ сгенерирован системой ERGO MS*

