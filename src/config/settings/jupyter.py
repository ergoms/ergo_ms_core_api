from src.config.settings.base import BASE_DIR, SYSTEM_DIR
from src.config.jupyter_runtime import build_jupyter_server_argv
import os
import sys

try:
    import jupyterlab
    notebook_default_url = '/lab'  # Using JupyterLab
except ImportError:
    notebook_default_url = '/tree'  # Using Jupyter

# Путь к директории notebooks в корне проекта.
PATH_TO_NOTEBOOK_DIR = SYSTEM_DIR / 'notebooks'

# Аргументы для запуска сервера jupyter (effective-значения из jupyter_runtime).
NOTEBOOK_ARGUMENTS = [
    *build_jupyter_server_argv(str(PATH_TO_NOTEBOOK_DIR)),
    '--NotebookApp.default_url', notebook_default_url,
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
    ('pandas', ('DataFrame', 'Series', 'read_csv', 'read_excel', 'read_json')),
    ('numpy', ('array', 'arange', 'linspace', 'zeros', 'ones')),
]

# Настройки для автоматической инициализации Django в Jupyter
def setup_django_for_jupyter():
    """Настройка Django для работы в Jupyter notebooks (ручной вызов из .py скриптов)."""
    import django

    for path in [str(SYSTEM_DIR), str(BASE_DIR)]:
        if path not in sys.path:
            sys.path.insert(0, path)

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.config.patterns.development')
    django.setup()

    return django
