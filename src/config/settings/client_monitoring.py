"""Настройки мониторинга клиентов (сессионный след для отладки)."""

from src.config.env import env

# Включение приёма событий и клиентского сбора (Vite bake-in CLIENT_MONITORING_ENABLED).
CLIENT_MONITORING_ENABLED = env.bool('CLIENT_MONITORING_ENABLED', default=False)

# Удаление сессий/событий старше N дней (0 — purge выключен). Beat + ergoms api client_monitor_purge.
CLIENT_MONITORING_RETENTION_DAYS = env.int('CLIENT_MONITORING_RETENTION_DAYS', default=7)

# Краткие строки в logs/client-monitor.log параллельно с БД.
CLIENT_MONITORING_LOG_FILE_ENABLED = env.bool('CLIENT_MONITORING_LOG_FILE_ENABLED', default=True)

# Максимум событий в одном POST ingest.
CLIENT_MONITORING_BATCH_MAX = env.int('CLIENT_MONITORING_BATCH_MAX', default=100)
