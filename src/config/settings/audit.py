"""Настройки журнала действий (запись, retention)."""

from src.config.env import env

# Асинхронная запись через Celery (снижает latency HTTP-запроса).
# Требует запущенный worker; при ошибке постановки в очередь — см. fallback ниже.
AUDIT_ASYNC_PERSIST = env.bool('AUDIT_ASYNC_PERSIST', default=False)

# Синхронная запись, если Celery-брокер недоступен при AUDIT_ASYNC_PERSIST=true.
AUDIT_ASYNC_PERSIST_FALLBACK_SYNC = env.bool('AUDIT_ASYNC_PERSIST_FALLBACK_SYNC', default=True)

# Удаление записей старше N дней (0 — отключено). Периодическая задача beat + ergoms api audit_purge.
AUDIT_RETENTION_DAYS = env.int('AUDIT_RETENTION_DAYS', default=0)

# Дублирование записей журнала в logs/audit.log (параллельно с БД).
AUDIT_LOG_FILE_ENABLED = env.bool('AUDIT_LOG_FILE_ENABLED', default=True)
