"""
Основной конфигурационный файл Celery для Django-приложения.

Отвечает за:
- инициализацию Celery-приложения;
- интеграцию с Django settings;
- автообнаружение задач;
- модульную конфигурацию очередей и маршрутов;
- настройку Celery Beat.
"""

import logging
import os
import sys
import threading
from typing import Any, Dict

from celery import Celery
from django.conf import settings

from src.config.log_format import (
    CELERY_WORKER_LOG_FORMAT,
    CELERY_WORKER_TASK_LOG_FORMAT,
)
from src.core.utils.auto_api.auto_config import get_env_deploy_type

# ---------------------------------------------------------------------------
# БАЗОВАЯ НАСТРОЙКА DJANGO SETTINGS ДЛЯ CELERY
# ---------------------------------------------------------------------------

deploy_type = get_env_deploy_type()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", deploy_type)

logger = logging.getLogger("config.celery")

# Определяем тип процесса по отдельным аргументам (не substring в объединённой строке)
_argv_lower = {arg.lower() for arg in sys.argv}
IS_BEAT = "beat" in _argv_lower
IS_CELERY_PROCESS = bool(_argv_lower & {"worker", "beat"})

# ---------------------------------------------------------------------------
# СОЗДАНИЕ CELERY ПРИЛОЖЕНИЯ (ЛЁГКАЯ ОПЕРАЦИЯ)
# ---------------------------------------------------------------------------

celery_app = Celery("src")


# ---------------------------------------------------------------------------
# ПОЛНАЯ КОНФИГУРАЦИЯ CELERY — ТОЛЬКО ДЛЯ CELERY ПРОЦЕССОВ
# ---------------------------------------------------------------------------

MODULE_MANAGER = None
MODULE_TASK_ROUTES: Dict = {}
MODULE_TASK_QUEUES: Dict = {}

if IS_CELERY_PROCESS:
    from src.config.redis_runtime import sanitize_celery_redis_url
    from src.core.utils.celery.manager import CeleryModuleManager

    for _env_key in ('CELERY_BROKER_URL', 'CELERY_RESULT_BACKEND'):
        _raw_url = os.environ.get(_env_key, '').strip()
        if _raw_url:
            os.environ[_env_key] = sanitize_celery_redis_url(_raw_url)

    # Конфигурация Celery из Django settings
    if IS_BEAT:
        logger.info("Celery: запуск BEAT, используются настройки CELERY_BEAT_*")
        celery_app.config_from_object("django.conf:settings", namespace="CELERY_BEAT")

        # Дополнительно применяем CELERY_* для совместимости
        from django.conf import settings as django_settings

        for key in dir(django_settings):
            if key.startswith("CELERY_") and not key.startswith("CELERY_BEAT_"):
                celery_app.conf[key.replace("CELERY_", "").lower()] = getattr(django_settings, key)
    else:
        logger.info("Celery: запуск WORKER, используются настройки CELERY_*")
        celery_app.config_from_object("django.conf:settings", namespace="CELERY")

    from django.conf import settings as django_settings

    if hasattr(django_settings, 'CELERY_BROKER_URL'):
        celery_app.conf.broker_url = django_settings.CELERY_BROKER_URL
    if hasattr(django_settings, 'CELERY_RESULT_BACKEND'):
        celery_app.conf.result_backend = django_settings.CELERY_RESULT_BACKEND

    # Автообнаружение задач во всех приложениях
    celery_app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

    # Модульная конфигурация Celery (без файлового кэша — нужны annotations, queue_limits)
    MODULE_MANAGER = CeleryModuleManager(use_config_cache=False)
    from src.core.utils.celery.startup_format import celery_startup_verbose, format_name_list

    _celery_modules = MODULE_MANAGER.get_modules_list()
    logger.info(
        "Celery: загружено %d модулей: %s",
        len(_celery_modules),
        format_name_list(_celery_modules, verbose=celery_startup_verbose()),
    )

    MODULE_TASK_ROUTES = MODULE_MANAGER.get_all_task_routes()
    MODULE_TASK_QUEUES = MODULE_MANAGER.get_all_task_queues()

    # Настройка параллелизма по очередям (только для worker'ов)
    if not IS_BEAT:
        MODULE_MANAGER.setup_queue_concurrency()
        queue_limits = MODULE_MANAGER.get_all_queue_limits()
        if queue_limits:
            from src.core.utils.celery.concurrency import (
                queue_concurrency_manager,
                setup_concurrency_limited_tasks,
            )

            cache_backend = getattr(settings, 'CACHE_BACKEND', 'file')
            if cache_backend == 'redis':
                queue_concurrency_manager.configure(use_distributed=True)
                logger.info(
                    "Celery: распределённый лимит параллелизма (Redis cache)"
                )

            setup_concurrency_limited_tasks(celery_app)

    # Очередь по умолчанию
    if "default" not in MODULE_TASK_QUEUES:
        MODULE_TASK_QUEUES["default"] = {"exchange": "default", "routing_key": "default"}

    if "*" not in MODULE_TASK_ROUTES and "default" in MODULE_TASK_QUEUES:
        MODULE_TASK_ROUTES["*"] = {"queue": "default"}

    # -----------------------------------------------------------------------
    # Общая конфигурация для Worker и Beat
    # -----------------------------------------------------------------------

    def _build_common_celery_config(
        manager: 'CeleryModuleManager',
        task_routes: Dict,
        task_queues: Dict,
    ) -> Dict[str, Any]:
        config: Dict[str, Any] = {
            "task_routes": task_routes,
            "task_default_queue": "default",
            "task_queues": task_queues,
            "task_annotations": manager.get_all_task_annotations(),
            "task_acks_late": True,
            "worker_log_format": CELERY_WORKER_LOG_FORMAT,
            "worker_task_log_format": CELERY_WORKER_TASK_LOG_FORMAT,
            "worker_log_color": False,
            "worker_redirect_stdouts": False,
            "worker_redirect_stdouts_level": "INFO",
        }
        config.update(manager.get_additional_configs())
        return config

    if not IS_BEAT and MODULE_MANAGER is not None:
        celery_app.conf.update(
            **_build_common_celery_config(MODULE_MANAGER, MODULE_TASK_ROUTES, MODULE_TASK_QUEUES),
        )

    # -----------------------------------------------------------------------
    # Настройки Celery Beat
    # -----------------------------------------------------------------------

    CELERY_BEAT_SCHEDULER = None
    CELERY_BEAT_SCHEDULER_DB_ALIAS = None
    CELERY_BEAT_SCHEDULE_FILENAME = str(
        settings.VIRTUAL_ENV_DIR / "celery" / "celerybeat-schedule.db"
    )
    CELERY_BEAT_SCHEDULE = {}

    if IS_BEAT:
        try:
            import src.config.settings.celery_beat as beat_settings

            CELERY_BEAT_SCHEDULER = getattr(beat_settings, "CELERY_BEAT_SCHEDULER", None)
            CELERY_BEAT_SCHEDULER_DB_ALIAS = getattr(
                beat_settings, "CELERY_BEAT_SCHEDULER_DB_ALIAS", None
            )
            CELERY_BEAT_SCHEDULE_FILENAME = getattr(
                beat_settings,
                "CELERY_BEAT_SCHEDULE_FILENAME",
                CELERY_BEAT_SCHEDULE_FILENAME,
            )
            CELERY_BEAT_SCHEDULE = getattr(beat_settings, "CELERY_BEAT_SCHEDULE", {})

            if CELERY_BEAT_SCHEDULE:
                _beat_tasks = list(CELERY_BEAT_SCHEDULE.keys())
                logger.info(
                    "Beat: %d расписаний: %s",
                    len(_beat_tasks),
                    format_name_list(_beat_tasks, max_show=5, verbose=celery_startup_verbose()),
                )
            else:
                logger.info("Beat: расписаний нет")
        except Exception as exc:
            logger.error("Beat: ошибка загрузки расписаний: %s", exc)

    beat_scheduler_config: Dict = {}
    if IS_BEAT:
        if CELERY_BEAT_SCHEDULER:
            beat_scheduler_config["beat_scheduler"] = CELERY_BEAT_SCHEDULER
            if CELERY_BEAT_SCHEDULER_DB_ALIAS:
                beat_scheduler_config["beat_scheduler_db_alias"] = CELERY_BEAT_SCHEDULER_DB_ALIAS
        else:
            beat_scheduler_config["beat_schedule_filename"] = CELERY_BEAT_SCHEDULE_FILENAME

        if CELERY_BEAT_SCHEDULE:
            beat_scheduler_config["beat_schedule"] = CELERY_BEAT_SCHEDULE

        if MODULE_MANAGER is not None:
            celery_app.conf.update(
                **beat_scheduler_config,
                **_build_common_celery_config(MODULE_MANAGER, MODULE_TASK_ROUTES, MODULE_TASK_QUEUES),
            )

    # -----------------------------------------------------------------------
    # Синхронизация задач Beat с БД (django-celery-beat) — в фоне, не блокирует старт
    # -----------------------------------------------------------------------

    if IS_BEAT and CELERY_BEAT_SCHEDULER and CELERY_BEAT_SCHEDULER_DB_ALIAS:
        import threading

        def _run_beat_sync() -> None:
            try:
                import django
                from django.apps import apps

                if not apps.ready:
                    django.setup()

                from src.core.utils.celery_beat.sync import CeleryBeatSyncManager

                sync_manager = CeleryBeatSyncManager(
                    config_schedule=CELERY_BEAT_SCHEDULE or {},
                    db_alias=CELERY_BEAT_SCHEDULER_DB_ALIAS,
                )
                sync_results = sync_manager.sync_all()
                logger.info(
                    "Beat: синхронизация с БД завершена - создано: %s, обновлено: %s, удалено: %s",
                    sync_results["created"],
                    sync_results["updated"],
                    sync_results["deleted"],
                )
            except Exception as exc:
                logger.error("Beat: ошибка синхронизации задач с БД: %s", exc, exc_info=True)

        logger.info("Beat: запуск синхронизации с БД в фоне...")
        _sync_thread = threading.Thread(target=_run_beat_sync, daemon=True)
        _sync_thread.start()
else:
    # В процессе Django (runserver и т.д.): broker, result_backend.
    # Маршруты и очереди загружаются лениво при первом использовании Celery.
    try:
        if hasattr(settings, "CELERY_BROKER_URL"):
            celery_app.conf.broker_url = settings.CELERY_BROKER_URL
        if hasattr(settings, "CELERY_RESULT_BACKEND"):
            celery_app.conf.result_backend = settings.CELERY_RESULT_BACKEND
    except Exception:
        pass

    _django_celery_lock = threading.Lock()
    _django_celery_configured = False

    def _ensure_celery_routes_configured() -> None:
        global _django_celery_configured
        if _django_celery_configured:
            return
        with _django_celery_lock:
            if _django_celery_configured:
                return
            try:
                from src.core.utils.celery.manager import CeleryModuleManager
                manager = CeleryModuleManager()
                celery_app.conf.task_routes = manager.get_all_task_routes()
                celery_app.conf.task_default_queue = "default"
                celery_app.conf.task_queues = manager.get_all_task_queues()
                if "default" not in celery_app.conf.task_queues:
                    celery_app.conf.task_queues["default"] = {
                        "exchange": "default",
                        "routing_key": "default",
                    }
                _django_celery_configured = True
            except Exception as e:
                logger.warning("Failed to configure Celery routes: %s", e)

    _original_send_task = celery_app.send_task

    def _send_task_patched(name, args=None, kwargs=None, **opts):
        _ensure_celery_routes_configured()
        return _original_send_task(name, args=args, kwargs=kwargs, **opts)

    celery_app.send_task = _send_task_patched