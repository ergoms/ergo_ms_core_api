"""
Channel layer для Django Channels (WebSocket, SSE stream).

BACKEND: memory (dev, один процесс) | postgres | redis
"""

from src.config.env import env
from src.config.redis_runtime import redis_channel_connection_options
from src.config.settings.database import DATABASES

CHANNEL_LAYER_BACKEND = env.str('CHANNEL_LAYER_BACKEND', default='memory').strip().lower()

if CHANNEL_LAYER_BACKEND == 'redis':
    _redis_url = env.str('CHANNEL_LAYER_REDIS_URL', default='redis://127.0.0.1:6379/0')
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [{'address': _redis_url, **redis_channel_connection_options()}],
            },
        },
    }
elif CHANNEL_LAYER_BACKEND == 'postgres':
    db = DATABASES['default']
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_postgres.core.PostgresChannelLayer',
            'CONFIG': {
                'ENGINE': db['ENGINE'],
                'NAME': db['NAME'],
                'USER': db.get('USER', ''),
                'PASSWORD': db.get('PASSWORD', ''),
                'HOST': db.get('HOST', ''),
                'PORT': db.get('PORT', ''),
                'OPTIONS': db.get('OPTIONS', {}),
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }
