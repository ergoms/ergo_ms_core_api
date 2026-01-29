"""
Утилита для синхронизации периодических задач из конфига в БД.
Обеспечивает автоматическую синхронизацию задач при использовании DatabaseScheduler.
"""

import logging
from typing import Dict, Any, Optional
from celery.schedules import crontab, schedule, solar

from django.db import transaction
from django_celery_beat.models import PeriodicTask, CrontabSchedule, IntervalSchedule, SolarSchedule

logger = logging.getLogger('celery.beat.sync')


class CeleryBeatSyncManager:
    """
    Менеджер для синхронизации периодических задач из конфига в БД.
    """
    
    def __init__(self, config_schedule: Dict[str, Dict[str, Any]], db_alias: Optional[str] = None):
        """
        Инициализация менеджера синхронизации.
        
        Args:
            config_schedule: Словарь с расписанием задач из конфига
            db_alias: Алиас БД для работы с django-celery-beat
        """
        self.config_schedule = config_schedule
        self.db_alias = db_alias
        self.logger = logger
    
    def sync_all(self) -> Dict[str, int]:
        """
        Синхронизирует все задачи из конфига с БД.
        
        Returns:
            Dict с результатами синхронизации:
            - created: количество созданных задач
            - updated: количество обновленных задач
            - deleted: количество удаленных задач
        """
        results = {
            'created': 0,
            'updated': 0,
            'deleted': 0,
        }
        
        self.logger.debug(f"Начало синхронизации: задач в конфиге={len(self.config_schedule)}")
        
        # Находим БД, где существует таблица (может отличаться от указанной)
        actual_db_alias = self._find_database_with_table()
        
        if not actual_db_alias:
            self.logger.warning(
                f"Таблица django_celery_beat_periodictask не найдена ни в одной БД. "
                f"Возможно, миграции не применены. Пропускаем синхронизацию."
            )
            return results
        
        # Используем найденную БД для синхронизации
        if actual_db_alias != self.db_alias:
            self.logger.debug(
                f"Используем БД '{actual_db_alias}' для синхронизации "
                f"(вместо указанной '{self.db_alias}')"
            )
            self.db_alias = actual_db_alias
        
        try:
            # Используем транзакцию для атомарности операций
            atomic = transaction.atomic(using=self.db_alias)
            with atomic:  # type: ignore
                # Получаем все задачи из БД
                db_tasks = self._get_db_tasks()
                self.logger.debug(f"Задач в БД: {len(db_tasks)}")
                
                # Синхронизируем задачи из конфига
                config_task_names = set(self.config_schedule.keys())
                
                for task_name, task_config in self.config_schedule.items():
                    if task_name in db_tasks:
                        # Обновляем существующую задачу
                        self._update_task(db_tasks[task_name], task_name, task_config)
                        results['updated'] += 1
                    else:
                        # Создаем новую задачу
                        self._create_task(task_name, task_config)
                        results['created'] += 1
                
                # Удаляем задачи из БД, которых нет в конфиге
                # Исключаем системные задачи (например, celery.backend_cleanup)
                db_task_names = set(db_tasks.keys())
                tasks_to_delete = db_task_names - config_task_names
                
                if tasks_to_delete:
                    self.logger.debug(
                        f"Задач для удаления: {len(tasks_to_delete)} "
                        f"(в БД: {len(db_task_names)}, в конфиге: {len(config_task_names)})"
                    )
                    self.logger.debug(f"Список задач для удаления: {', '.join(sorted(tasks_to_delete))}")
                
                # Удаляем только задачи, которые не являются системными
                for task_name in tasks_to_delete:
                    if not self._is_system_task(task_name):
                        self.logger.debug(f"Удаление задачи: {task_name}")
                        self._delete_task(db_tasks[task_name])
                        results['deleted'] += 1
                        self.logger.debug(f"Удалена задача из БД (отсутствует в конфиге): {task_name}")
                    else:
                        self.logger.debug(f"Пропущена системная задача: {task_name}")
                
                self.logger.info(
                    f"Синхронизация завершена: создано={results['created']}, "
                    f"обновлено={results['updated']}, удалено={results['deleted']}"
                )
        
        except Exception as e:
            self.logger.error(f"Ошибка синхронизации задач: {e}", exc_info=True)
            raise
        
        return results
        
        return results
    
    def _check_table_exists(self, db_alias: Optional[str] = None) -> bool:
        """
        Проверяет существование таблицы django_celery_beat_periodictask в указанной БД.
        
        Args:
            db_alias: Alias БД для проверки (если None, используется self.db_alias)
        
        Returns:
            True если таблица существует, иначе False
        """
        check_alias = db_alias or self.db_alias
        if not check_alias:
            return False
        
        try:
            from django.db import connections
            from django.conf import settings
            
            if check_alias not in settings.DATABASES:
                return False
            
            db_connection = connections[check_alias]
            with db_connection.cursor() as cursor:
                # Проверяем для PostgreSQL
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'django_celery_beat_periodictask'
                    );
                """)
                return cursor.fetchone()[0]
        except Exception as e:
            self.logger.debug(f"Ошибка при проверке таблицы в БД '{check_alias}': {e}")
            return False
    
    def _find_database_with_table(self) -> Optional[str]:
        """
        Находит БД, где существует таблица django_celery_beat_periodictask.
        Сначала проверяет указанную БД, затем все доступные БД.
        
        Returns:
            Alias БД с таблицей или None
        """
        from django.db import connections
        from django.conf import settings
        
        # Сначала проверяем указанную БД
        if self.db_alias and self._check_table_exists(self.db_alias):
            return self.db_alias
        
        # Затем проверяем все доступные БД
        for db_name in settings.DATABASES.keys():
            if db_name == self.db_alias:
                continue  # Уже проверили
            if self._check_table_exists(db_name):
                self.logger.warning(
                    f"Таблица найдена в БД '{db_name}' вместо указанной '{self.db_alias}'. "
                    f"Используем БД '{db_name}' для синхронизации."
                )
                return db_name
        
        return None
    
    def _get_db_tasks(self) -> Dict[str, PeriodicTask]:
        """Получает все периодические задачи из БД."""
        if not self.db_alias:
            self.logger.warning(
                "БД для синхронизации не указана. Пропускаем синхронизацию."
            )
            return {}
        
        queryset = PeriodicTask.objects.using(self.db_alias).all()
        return {task.name: task for task in queryset}
    
    def _is_system_task(self, task_name: str) -> bool:
        """
        Проверяет, является ли задача системной.
        Системные задачи не удаляются автоматически.
        """
        system_tasks = [
            'celery.backend_cleanup',
        ]
        return task_name in system_tasks
    
    def _create_task(self, task_name: str, task_config: Dict[str, Any]):
        """Создает новую периодическую задачу в БД."""
        schedule_obj = self._get_or_create_schedule(task_config['schedule'])
        
        # Подготавливаем параметры для создания задачи
        task_params = {
            'name': task_name,
            'task': task_config['task'],
            'enabled': task_config.get('enabled', True),
            'kwargs': self._serialize_kwargs(task_config.get('kwargs', {})),
        }
        
        # Устанавливаем расписание в зависимости от типа
        if hasattr(schedule_obj, 'minute'):  # CrontabSchedule
            task_params['crontab'] = schedule_obj
        elif hasattr(schedule_obj, 'every'):  # IntervalSchedule
            task_params['interval'] = schedule_obj
        elif hasattr(schedule_obj, 'event'):  # SolarSchedule
            task_params['solar'] = schedule_obj
        
        # Добавляем опции задачи
        options = self._get_task_options(task_config.get('options', {}))
        task_params.update(options)
        
        task = PeriodicTask.objects.using(self.db_alias).create(**task_params)  # type: ignore
        
        self.logger.info(f"Создана новая задача: {task_name}")
        return task
    
    def _update_task(self, db_task: PeriodicTask, task_name: str, task_config: Dict[str, Any]):
        """Обновляет существующую задачу в БД."""
        schedule_obj = self._get_or_create_schedule(task_config['schedule'])
        serialized_kwargs = self._serialize_kwargs(task_config.get('kwargs', {}))
        
        # Проверяем текущее расписание задачи
        current_schedule_id = None
        if hasattr(db_task, 'crontab') and db_task.crontab:  # type: ignore
            current_schedule_id = db_task.crontab.id if hasattr(db_task.crontab, 'id') else None  # type: ignore
        elif hasattr(db_task, 'interval') and db_task.interval:  # type: ignore
            current_schedule_id = db_task.interval.id if hasattr(db_task.interval, 'id') else None  # type: ignore
        elif hasattr(db_task, 'solar') and db_task.solar:  # type: ignore
            current_schedule_id = db_task.solar.id if hasattr(db_task.solar, 'id') else None  # type: ignore
        
        new_schedule_id = schedule_obj.id if hasattr(schedule_obj, 'id') else None
        
        # Проверяем, нужно ли обновлять задачу
        needs_update = (
            db_task.task != task_config['task'] or
            current_schedule_id != new_schedule_id or
            db_task.enabled != task_config.get('enabled', True) or
            db_task.kwargs != serialized_kwargs
        )
        
        if needs_update:
            db_task.task = task_config['task']
            # Обновляем расписание через crontab, interval или solar
            if hasattr(schedule_obj, 'minute'):  # CrontabSchedule
                db_task.crontab = schedule_obj  # type: ignore
                db_task.interval = None  # type: ignore
                db_task.solar = None  # type: ignore
            elif hasattr(schedule_obj, 'every'):  # IntervalSchedule
                db_task.interval = schedule_obj  # type: ignore
                db_task.crontab = None  # type: ignore
                db_task.solar = None  # type: ignore
            elif hasattr(schedule_obj, 'event'):  # SolarSchedule
                db_task.solar = schedule_obj  # type: ignore
                db_task.crontab = None  # type: ignore
                db_task.interval = None  # type: ignore
            
            db_task.enabled = task_config.get('enabled', True)
            db_task.kwargs = serialized_kwargs  # type: ignore
            
            # Обновляем опции задачи (если они поддерживаются моделью)
            options = task_config.get('options', {})
            if 'queue' in options and hasattr(db_task, 'queue'):
                db_task.queue = options['queue']  # type: ignore
            if 'priority' in options and hasattr(db_task, 'priority'):
                db_task.priority = options['priority']  # type: ignore
            if 'expires' in options and hasattr(db_task, 'expires'):
                # expires может быть числом (секунды) или datetime
                expires_value = options['expires']
                if isinstance(expires_value, (int, float)):
                    # Преобразуем секунды в timezone-aware datetime
                    from django.utils import timezone
                    from datetime import timedelta
                    db_task.expires = timezone.now() + timedelta(seconds=expires_value)  # type: ignore
                else:
                    db_task.expires = expires_value  # type: ignore
            
            db_task.save(using=self.db_alias)
            self.logger.debug(f"Обновлена задача: {task_name}")
    
    def _delete_task(self, db_task: PeriodicTask):
        """Удаляет задачу из БД."""
        task_name = db_task.name
        try:
            db_task.delete(using=self.db_alias)
            self.logger.debug(f"Удалена задача: {task_name}")
        except Exception as e:
            self.logger.error(f"Ошибка при удалении задачи {task_name}: {e}", exc_info=True)
            raise
    
    def _get_or_create_schedule(self, schedule_obj) -> Any:
        """
        Получает или создает объект расписания в БД.
        Поддерживает crontab, interval и solar расписания.
        """
        if isinstance(schedule_obj, crontab):
            # Crontab расписание
            crontab_obj, _ = CrontabSchedule.objects.using(self.db_alias).get_or_create(  # type: ignore
                minute=schedule_obj.minute or '*',
                hour=schedule_obj.hour or '*',
                day_of_week=schedule_obj.day_of_week or '*',
                day_of_month=schedule_obj.day_of_month or '*',
                month_of_year=schedule_obj.month_of_year or '*',
                timezone=schedule_obj.tz or None
            )
            return crontab_obj
        
        elif isinstance(schedule_obj, schedule):
            # Interval расписание
            interval_obj, _ = IntervalSchedule.objects.using(self.db_alias).get_or_create(  # type: ignore
                every=schedule_obj.run_every.total_seconds(),
                period=IntervalSchedule.SECONDS
            )
            return interval_obj
        
        elif isinstance(schedule_obj, solar):
            # Solar расписание
            solar_obj, _ = SolarSchedule.objects.using(self.db_alias).get_or_create(  # type: ignore
                event=schedule_obj.event,
                latitude=schedule_obj.lat,
                longitude=schedule_obj.lon
            )
            return solar_obj
        
        else:
            raise ValueError(f"Неподдерживаемый тип расписания: {type(schedule_obj)}")
    
    def _serialize_kwargs(self, kwargs: Dict[str, Any]) -> str:
        """Сериализует kwargs для хранения в БД."""
        import json
        return json.dumps(kwargs) if kwargs else '{}'
    
    def _get_task_options(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Извлекает опции задачи из конфига.
        Возвращает только те опции, которые поддерживаются моделью PeriodicTask.
        """
        result = {}
        # Проверяем наличие полей в модели через создание временного объекта
        # Это безопаснее, чем проверка через hasattr на классе
        if 'queue' in options:
            result['queue'] = options['queue']
        if 'priority' in options:
            result['priority'] = options['priority']
        if 'expires' in options:
            # expires может быть числом (секунды) или datetime
            expires_value = options['expires']
            if isinstance(expires_value, (int, float)):
                # Преобразуем секунды в timezone-aware datetime
                from django.utils import timezone
                from datetime import timedelta
                result['expires'] = timezone.now() + timedelta(seconds=expires_value)
            else:
                result['expires'] = expires_value
        return result

