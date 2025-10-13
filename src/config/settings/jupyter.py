from src.config.settings.base import BASE_DIR
from src.config.env import env
import os
import sys

try:
    import jupyterlab
    notebook_default_url = '/lab'  # Using JupyterLab
except ImportError:
    notebook_default_url = '/tree'  # Using Jupyter

# Путь к корневой директории проекта в Jupyter.
PATH_TO_NOTEBOOK_DIR = BASE_DIR

# Хост сервера jupyter, полученный из переменной окружения.
API_JUPYTER_HOST = env.str('API_JUPYTER_HOST', default='localhost')

# Порт сервера jupyter, полученный из переменной окружения.
API_JUPYTER_PORT = env.str('API_JUPYTER_PORT', default='8002')

# Аргументы для запуска сервера jupyter.
NOTEBOOK_ARGUMENTS = [
    '--ip', API_JUPYTER_HOST,
    '--port', API_JUPYTER_PORT,
    '--notebook-dir', str(PATH_TO_NOTEBOOK_DIR),
    '--NotebookApp.default_url', notebook_default_url,
    '--NotebookApp.allow_origin', '*',
    '--NotebookApp.allow_remote_access', 'True',
    '--NotebookApp.open_browser', 'False',
    '--NotebookApp.token', '',
    '--NotebookApp.password', '',
    '--ServerApp.allow_origin', '*',
    '--ServerApp.allow_remote_access', 'True',
    '--ServerApp.open_browser', 'False',
    '--ServerApp.token', '',
    '--ServerApp.password', '',
]

# Имя ядра IPython, полученное из переменной окружения.
IPYTHON_KERNEL_DISPLAY_NAME = 'Django Kernel'

# Настройки для интеграции с Django
SHELL_PLUS_PRE_IMPORTS = [
    ('django.db', ('connection', 'connections', 'reset_queries', 'close_old_connections')),
    ('django.conf', ('settings',)),
    ('django.core.management', ('execute_from_command_line',)),
    ('django.core.management.base', ('BaseCommand', 'CommandError', 'CommandParser')),
    ('django.db.models', ('Avg', 'Count', 'F', 'Max', 'Min', 'Q', 'Sum', 'Value')),
    ('django.utils', ('timezone',)),
    ('datetime', ('datetime', 'timedelta', 'date')),
    ('decimal', ('Decimal',)),
    ('functools', ('reduce',)),
    ('itertools', ('chain', 'islice')),
    ('json', ('dumps', 'loads')),
    ('operator', ('itemgetter', 'attrgetter')),
    ('pathlib', ('Path',)),
    ('pprint', ('pprint',)),
    ('random', ('choice', 'randint', 'random', 'sample', 'shuffle')),
    ('string', ('ascii_letters', 'ascii_lowercase', 'ascii_uppercase', 'digits', 'hexdigits', 'octdigits', 'printable', 'punctuation', 'whitespace')),
    ('textwrap', ('dedent', 'indent', 'shorten')),
    ('time', ('sleep',)),
    ('urllib.parse', ('quote_plus', 'urlencode', 'urljoin', 'urlparse', 'urlsplit', 'urlunparse')),
]

# Настройки для автоматической инициализации Django в Jupyter
def setup_django_for_jupyter():
    """
    Настройка Django для работы в Jupyter notebooks
    """
    import django
    from django.conf import settings
    
    # Добавляем путь к проекту в sys.path
    project_root = str(BASE_DIR)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # Устанавливаем переменную окружения для Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.config.patterns.development')
    
    # Инициализируем Django
    django.setup()
    
    return django