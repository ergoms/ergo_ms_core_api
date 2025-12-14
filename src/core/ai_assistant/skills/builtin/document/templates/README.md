# Шаблоны документов

Эта папка содержит MD шаблоны для генерации документов.

## Структура шаблона

Каждый MD файл - это шаблон документа. Название файла = ID шаблона.

### Метаданные шаблона (YAML frontmatter)

```yaml
---
name: "Название шаблона"
description: "Описание для LLM когда использовать"
format: ["docx", "pdf"]  # Поддерживаемые форматы
variables:
  - name: "title"
    description: "Заголовок документа"
    required: true
  - name: "author"
    description: "Автор документа"
    required: false
    default: "Система ERGO MS"
---
```

### Тело шаблона

Используй Markdown разметку и переменные в формате `{{variable_name}}`.

## Пример шаблона

```markdown
---
name: "Отчёт"
description: "Шаблон для создания отчётов"
format: ["docx", "pdf"]
variables:
  - name: "title"
    required: true
  - name: "content"
    required: true
---

# {{title}}

{{content}}

---
*Документ сгенерирован системой ERGO MS*
```

