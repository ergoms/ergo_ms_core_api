"""
Файл содержащий конфигурацию шаблонов, WSGI и ASGI для Django-API-приложения.
Он включает настройки корневого URL-конфигуратора, шаблонов, WSGI и ASGI приложений.
"""

# Путь к корневому URL-конфигуратор для Django-API-приложения.
ROOT_URLCONF = 'src.config.patterns.base'

# Конфигурация шаблонов для приложения.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        
        # Список директорий, в которых искать шаблоны. 
        # В данном случае пустой, так как используется APP_DIRS.
        'DIRS': [],

        # Флаг, указывающий, искать ли шаблоны в директориях приложений.
        'APP_DIRS': True,

        # Дополнительные опции для шаблонов.
        'OPTIONS': {
            # Контекстные процессоры, которые будут доступны в шаблонах.
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Путь к файлу, содержащему WSGI-приложение.
WSGI_APPLICATION = 'src.config.wsgi.application'

# Путь к файлу, содержащему ASGI-приложение.
ASGI_APPLICATION = "src.config.asgi.application"