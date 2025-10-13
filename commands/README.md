# Система команд Poetry для Django

Функционал для автоматического создания poetry команд дублирующих все Django команд (встроенные и пользовательские).
Реализовано для упрощения синтаксиса обращения к Django командам.

## Использование

### Вид команд
```bash
# Запуск сервера разработки
api dev

# Создание миграций
api makemigrations

# Применение миграций
api migrate

# Пользовательские команды
api clear_cache
api clear_pycache
```

### Альтернативный синтаксис
```bash
# Можно использовать poetry run
poetry run api dev

# Или просто api
api dev
```

## Создание пользовательской команды

1. Создайте файл в папке `management/commands/` вашего приложения:

```python
# src/modules/myapp/management/commands/my_command.py
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Описание команды'

    def add_arguments(self, parser):
        parser.add_argument('--option', type=str, help='Опция')

    def handle(self, *args, **options):
        self.stdout.write('Команда выполнена!')
```

2. Команда автоматически станет доступной:
```bash
api my_command --option value
```

## Конфигурация

### pyproject.toml
```toml
[tool.poetry.scripts]
api = "commands.__main__:main"
```

## Базовые команды

### Core-команды (инфраструктура и сервис)
- **add_module** — добавить модуль
- **dev** — запуск dev-сервера
- **discover_modules** — обнаружение модулей
- **generate_swagger** — генерация swagger схемы
- **generateschema** — генерация схемы
- **optimizemigration** — оптимизация миграций
- **sendtestemail** — отправка тестового письма
- **clear_cache** — очистка кэша
- **clear_pycache** — очистка pycache
- **flushexpiredtokens** — очистка устаревших токенов
- **update_routes** — обновление маршрутов клиентского приложения
- **update_dependencies** — обновление зависимостей
- **start_celery_beat** — запуск celery beat
- **start_celery_worker** — запуск celery worker
- **celery_beat_stop** — остановка celery beat
- **celery_worker_stop** — остановка celery worker
- **stop_prod** — остановка production сервера
- **start_prod** — запуск production сервера

### Стандартные команды Django
- **makemigrations** — создание миграций
- **migrate** — применение миграций
- **createsuperuser** — создать суперпользователя
- **shell** — интерактивная консоль
- **runserver** — запуск dev-сервера
- **test** — запуск тестов
- **testserver** — запуск тестового сервера
- **dbshell** — SQL shell
- **loaddata** — загрузка фикстур
- **dumpdata** — дамп данных
- **collectstatic** — сбор статики
- **findstatic** — поиск статики
- **check** — проверка проекта
- **showmigrations** — показать миграции
- **sqlmigrate** — SQL для миграции
- **sqlflush** — SQL для очистки БД
- **flush** — очистка БД
- **remove_stale_contenttypes** — удаление устаревших contenttypes
- **changepassword** — смена пароля пользователя
- **inspectdb** — генерация моделей из БД
- **startapp** — создать приложение
- **startproject** — создать проект
- **compilemessages** — компиляция переводов
- **makemessages** — генерация файлов переводов
- **squashmigrations** — объединение миграций
- **createcachetable** — создать таблицу кэша
- **diffsettings** — разница настроек