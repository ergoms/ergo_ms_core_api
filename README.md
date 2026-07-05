# Сервер (Django API)

Серверная часть ERGO MS: REST API, CMS, права, уведомления, аудит, интеграции между модулями.

## Структура

| Каталог | Назначение |
|---------|------------|
| `src/config/` | настройки Django, Celery, URL, окружения (development и production) |
| `src/core/` | код ядра: CMS, utils, audit, integrations |
| `commands/` | команды ergoms для Django |
| `scripts/` | точки входа (запуск API, Celery, Jupyter) |

Модули подключаются из `modules/<имя>/api/` автоматически — см. [`.docs/architecture.md`](../../.docs/architecture.md).

## Правила для разработчиков

| Тема | Правило |
|------|---------|
| API, ViewSet, Swagger | [`.cursor/rules/api_code.mdc`](../../.cursor/rules/api_code.mdc) |
| Безопасность | [`.cursor/rules/security.mdc`](../../.cursor/rules/security.mdc) |

## Связанные части ядра

- Клиент: [`../client/README.md`](../client/README.md)
- Файлы: [`../media_api/README.md`](../media_api/README.md)
- Развёртывание: [`../deployment/logic.md`](../deployment/logic.md)
