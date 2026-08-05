"""Настройки централизованного поиска (Meilisearch)."""

from src.config.env import env

ERGO_SEARCH_ENABLED = env.bool('ERGO_SEARCH_ENABLED', default=True)
MEILI_HOST = (env('MEILI_HOST', default='http://127.0.0.1:8004') or '').strip().rstrip('/')
# Должен совпадать с ключом процесса Meilisearch (install_meilisearch / служба).
MEILI_MASTER_KEY = (
    env('MEILI_MASTER_KEY', default='ergo_ms_dev_meili_key') or ''
).strip()
MEILI_SEARCH_TIMEOUT_SEC = float(env('MEILI_SEARCH_TIMEOUT_SEC', default='5.0'))
