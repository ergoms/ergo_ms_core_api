# Модульная система конфигурации Celery

## Обзор

Система позволяет каждому модулю настраивать свои собственные задачи Celery и логирование. Это обеспечивает:

- **Модульность**: Каждый модуль управляет своими задачами независимо
- **Специализированное логирование**: Каждый модуль имеет свои логгеры
- **Автоматическое обнаружение**: Система автоматически находит и загружает конфигурации модулей
- **Гибкость**: Легко добавлять новые модули и настраивать их

## Структура

```
src/core/utils/celery/
├── base.py              # Базовый класс для конфигурации Celery модулей
├── manager.py           # Менеджер для автоматического обнаружения Celery модулей
└── README.md           # Эта документация

src/modules/{module_name}/
└── celery_config.py     # Конфигурация Celery для конкретного модуля
```

## Создание конфигурации для нового модуля

### 1. Создайте файл `celery_config.py` в папке модуля

```python
"""
Конфигурация Celery для модуля my_module.
"""

from typing import Dict, Any
from src.core.celery.base import CeleryModuleConfig


class MyModuleCeleryConfig(CeleryModuleConfig):
    """
    Конфигурация Celery для модуля my_module.
    """
    
    def get_task_routes(self) -> Dict[str, Dict[str, Any]]:
        """Маршруты задач для модуля"""
        return {
            'src.modules.my_module.tasks.*': {'queue': 'my_module'},
        }
    
    def get_task_queues(self) -> Dict[str, Dict[str, Any]]:
        """Очереди задач для модуля"""
        return {
            'my_module': {
                'exchange': 'my_module',
                'routing_key': 'my_module',
            }
        }
    
    def get_task_annotations(self) -> Dict[str, Dict[str, Any]]:
        """Аннотации задач для модуля"""
        return {
            'src.modules.my_module.tasks.my_task': {
                'time_limit': 1800,   # Таймаут 30 минут
                'soft_time_limit': 1500,  # Мягкий таймаут 25 минут
            },
        }
    
    def get_module_loggers(self) -> Dict[str, Any]:
        """Специализированные логгеры для модуля"""
        loggers = super().get_module_loggers()
        
        # Добавляем специализированные логгеры
        loggers.update({
            'processing': self._get_logger('processing'),
            'analysis': self._get_logger('analysis'),
        })
        
        return loggers
    
    def _get_logger(self, logger_name: str):
        """Создает специализированный логгер для модуля"""
        import logging
        return logging.getLogger(f'celery.module.{self.module_name}.{logger_name}')
    
    def get_additional_config(self) -> Dict[str, Any]:
        """Дополнительные настройки для модуля"""
        return {
            'my_module_max_concurrent_tasks': 3,
            'my_module_batch_size': 100,
        }
```

### 2. Использование логгеров в задачах

```python
import logging
from celery import shared_task


@shared_task
def my_task():
    """Пример задачи с использованием логгеров модуля"""
    # Основной логгер модуля
    logger = logging.getLogger('celery.module.my_module')
    
    # Специализированный логгер
    processing_logger = logging.getLogger('celery.module.my_module.processing')
    
    logger.info("Начинаем выполнение задачи")
    
    try:
        processing_logger.debug("Обрабатываем данные")
        # ... логика задачи ...
        logger.info("Задача выполнена успешно")
        
    except Exception as e:
        logger.error(f"Ошибка при выполнении задачи: {e}")
        raise
```

## Автоматическое обнаружение

Система автоматически:

1. Сканирует папку `src/modules/`
2. Ищет файл `celery_config.py` в каждом модуле
3. Загружает конфигурацию, если она найдена
4. Создает базовую конфигурацию, если файл не найден

## Логирование

### Структура логов

```
api/logs/
├── celery.log                    # Основные логи Celery
├── celery_worker.log             # Логи воркеров
├── celery_beat.log              # Логи планировщика
├── celery_tasks.log             # Логи задач
└── modules/
    ├── porosity_analysis/
    │   └── porosity_analysis.log
    ├── video_analysis/
    │   └── video_analysis.log
    └── ...
```

### Доступные логгеры

Каждый модуль автоматически получает следующие логгеры:

- `celery.module.{module_name}` - Основной логгер модуля
- `celery.module.{module_name}.tasks` - Логгер для задач
- `celery.module.{module_name}.worker` - Логгер для воркеров

Дополнительные специализированные логгеры можно добавить в методе `get_module_loggers()`.

## Настройки задач

### Таймауты

```python
def get_task_annotations(self) -> Dict[str, Dict[str, Any]]:
    return {
        'src.modules.my_module.tasks.my_task': {
            'time_limit': 3600,      # Жесткий таймаут (1 час)
            'soft_time_limit': 3300,  # Мягкий таймаут (55 минут)
        },
    }
```

### Очереди

```python
def get_task_queues(self) -> Dict[str, Dict[str, Any]]:
    return {
        'my_module': {
            'exchange': 'my_module',
            'routing_key': 'my_module',
        }
    }
```

### Маршруты

```python
def get_task_routes(self) -> Dict[str, Dict[str, Any]]:
    return {
        'src.modules.my_module.tasks.*': {'queue': 'my_module'},
    }
```



## Дополнительные настройки

```python
def get_additional_config(self) -> Dict[str, Any]:
    return {
        'my_module_max_concurrent_tasks': 3,
        'my_module_batch_size': 100,
        'my_module_rate_limit': '10/m',
    }
```

## Мониторинг

### Просмотр загруженных модулей

```python
from src.core.utils.celery.manager import CeleryModuleManager

# Celery модули
celery_manager = CeleryModuleManager()
celery_modules = celery_manager.get_modules_list()
print(f"Загруженные Celery модули: {celery_modules}")
```

### Получение конфигурации модуля

```python
# Celery конфигурация
celery_config = celery_manager.get_module_config('porosity_analysis')
if celery_config:
    routes = celery_config.get_task_routes()
    print(f"Маршруты задач: {routes}")
```



## Лучшие практики

1. **Именование**: Используйте понятные имена для логгеров и очередей
2. **Таймауты**: Устанавливайте разумные таймауты для задач
3. **Логирование**: Логируйте важные события и ошибки
4. **Модульность**: Каждый модуль должен быть самодостаточным
5. **Документация**: Комментируйте конфигурации и задачи
6. **Документация**: Комментируйте конфигурации и задачи

## Примеры

См. файл `examples.py` для подробных примеров использования логгеров в задачах. 