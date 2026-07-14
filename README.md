# Сервер (Django API)

Серверная часть ERGO MS: REST API, CMS, права, уведомления, аудит, интеграции между модулями. Запуск для разработки — через ASGI (Django Channels) для WebSocket.

## Структура

| Каталог | Назначение |
|---------|------------|
| `src/config/` | настройки Django, Celery, URL, ASGI, окружения (development и production) |
| `src/core/` | код ядра: CMS, ADP (роли, регистрация, приглашения), utils, audit, integrations |
| `src/core/cms/adp/` | пользователи, роли, приглашения, WebSocket consumers (presence) |
| `commands/` | команды ergoms для Django |
| `scripts/` | точки входа (запуск API, Celery, Jupyter) |

Модули подключаются из `modules/<имя>/api/` автоматически — см. [`.docs/architecture.md`](../../.docs/architecture.md).

## Правила для разработчиков

| Тема | Правило |
|------|---------|
| API, ViewSet, Swagger | [`.cursor/rules/api_code.mdc`](../../.cursor/rules/api_code.mdc) |
| Django, регистрация, ASGI | [`.cursor/rules/django.mdc`](../../.cursor/rules/django.mdc) |
| Redis, nginx, channel layer | [`.cursor/rules/deployment-infra.mdc`](../../.cursor/rules/deployment-infra.mdc) |
| WebSocket, realtime | [`.cursor/rules/realtime.mdc`](../../.cursor/rules/realtime.mdc) |
| Безопасность | [`.cursor/rules/security.mdc`](../../.cursor/rules/security.mdc) |
| GeoIP | [`../deployment/logic.md`](../deployment/logic.md#geoip-db-ip-city-lite) |

## Связанные части ядра

- Клиент: [`../client/README.md`](../client/README.md)
- Файлы: [`../media_api/README.md`](../media_api/README.md)
- Развёртывание: [`../deployment/logic.md`](../deployment/logic.md)
