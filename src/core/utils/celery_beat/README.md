# Модульная система конфигурации Celery Beat

## Обзор

Система позволяет каждому модулю настраивать свои собственные периодические задачи Celery Beat. Это обеспечивает:

- **Модульность**: Каждый модуль управляет своими периодическими задачами независимо
- **Специализированное логирование**: Каждый модуль имеет свои логгеры для Beat
- **Автоматическое обнаружение**: Система автоматически находит и загружает конфигурации Beat модулей
- **Гибкость**: Легко добавлять новые модули и настраивать их расписания
- **Периодические задачи**: Каждый модуль может настраивать свои расписания Beat

## Структура

```
src/core/utils/celery_beat/
├── base.py              # Базовый класс для конфигурации Beat модулей
├── manager.py           # Менеджер для автоматического обнаружения Beat модулей
└── README.md           # Эта документация

src/modules/{module_name}/
└── celery_beat_config.py # Конфигурация Beat для конкретного модуля
```

## Создание конфигурации Beat для нового модуля

Создайте файл `celery_beat_config.py` в папке модуля:

```python
"""
Конфигурация Celery Beat для модуля my_module.
"""

from typing import Dict, Any
from celery.schedules import crontab
from src.core.utils.celery_beat.base import CeleryBeatModuleConfig


class MyModuleBeatConfig(CeleryBeatModuleConfig):
    """
    Конфигурация Celery Beat для модуля my_module.
    """
    
    def get_beat_schedule(self) -> Dict[str, Dict[str, Any]]:
        """Расписание периодических задач для модуля"""
        return {
            'my-periodic-task': {
                'task': 'src.modules.my_module.tasks.my_periodic_task',
                'schedule': crontab(minute='*/15'),  # Каждые 15 минут
                'options': {
                    'queue': 'my_module',
                    'expires': 300,  # Задача истекает через 5 минут
                }
            },
            'daily-cleanup': {
                'task': 'src.modules.my_module.tasks.daily_cleanup',
                'schedule': crontab(hour=2, minute=0),  # Каждый день в 2:00
                'options': {
                    'queue': 'my_module',
                    'expires': 1800,  # Задача истекает через 30 минут
                }
            },
        }
    
    def get_additional_beat_config(self) -> Dict[str, Any]:
        """Дополнительные настройки Beat для модуля"""
        return {
            'my_module_beat_max_tasks_per_worker': 2,
            'my_module_beat_task_timeout': 900,  # 15 минут
            'my_module_beat_retry_delay': 300,  # 5 минут
        }
```

## Автоматическое обнаружение

Система автоматически:

1. Сканирует папку `src/modules/`
2. Ищет файл `celery_beat_config.py` в каждом модуле
3. Загружает конфигурацию Beat, если она найдена
4. Создает базовую конфигурацию Beat, если файл не найден

## Логирование

### Структура логов

```
api/logs/
├── celery_beat.log              # Логи планировщика Beat
└── celery/beat/
    ├── bi_analysis/
    │   └── beat.log
    ├── porosity_analysis/
    │   └── beat.log
    └── ...
```

### Доступные логгеры

Каждый модуль автоматически получает следующие логгеры:

- `celery.beat.module.{module_name}` - Основной логгер Beat модуля

## Настройки Beat (Периодические задачи)

### Расписание

```python
def get_beat_schedule(self) -> Dict[str, Dict[str, Any]]:
    return {
        'my-periodic-task': {
            'task': 'src.modules.my_module.tasks.my_periodic_task',
            'schedule': crontab(minute='*/15'),  # Каждые 15 минут
            'options': {
                'queue': 'my_module',
                'expires': 300,  # Задача истекает через 5 минут
            }
        },
    }
```

### Дополнительные настройки Beat

```python
def get_additional_beat_config(self) -> Dict[str, Any]:
    return {
        'my_module_beat_max_tasks_per_worker': 2,
        'my_module_beat_task_timeout': 900,  # 15 минут
        'my_module_beat_retry_delay': 300,  # 5 минут
    }
```

## Мониторинг

### Просмотр загруженных модулей

```python
from src.core.utils.celery_beat.manager import CeleryBeatModuleManager

# Beat модули
beat_manager = CeleryBeatModuleManager()
beat_modules = beat_manager.get_modules_list()
print(f"Загруженные Beat модули: {beat_modules}")
```

### Получение конфигурации модуля

```python
# Beat конфигурация
beat_config = beat_manager.get_module_config('bi_analysis')
if beat_config:
    schedule = beat_config.get_beat_schedule()
    print(f"Расписание Beat: {schedule}")
```

### Мониторинг Beat

- Расписание выполнения периодических задач
- Статистика выполнения Beat задач
- Логи планировщика Beat
- Мониторинг истечения задач

## Лучшие практики

1. **Именование**: Используйте понятные имена для расписаний задач
2. **Таймауты**: Устанавливайте разумные таймауты для Beat задач
3. **Логирование**: Логируйте важные события и ошибки
4. **Модульность**: Каждый модуль должен быть самодостаточным
5. **Документация**: Комментируйте конфигурации и задачи
6. **Beat планирование**: Используйте разумные интервалы для периодических задач
7. **Истечение задач**: Настраивайте время истечения для Beat задач

## Примеры

См. файлы `celery_beat_config.py` в модулях для подробных примеров использования. 