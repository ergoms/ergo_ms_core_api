---
name: "Отчёт"
description: "Универсальный шаблон для создания отчётов и аналитических документов"
format: ["docx", "pdf"]
variables:
  - name: "title"
    description: "Заголовок отчёта"
    required: true
  - name: "content"
    description: "Основное содержимое отчёта"
    required: true
  - name: "author"
    description: "Автор отчёта"
    required: false
    default: "AI Ассистент"
  - name: "date"
    description: "Дата создания"
    required: false
---

# {{title}}

**Автор:** {{author}}  
**Дата:** {{date}}

---

{{content}}

---

*Документ сгенерирован системой ERGO MS*

