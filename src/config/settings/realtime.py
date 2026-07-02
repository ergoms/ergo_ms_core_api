"""
Транспорт realtime: websocket (Channels) или http_polling (REST + short polling на клиенте).
"""

from src.config.env import env

REALTIME_TRANSPORT = env.str('REALTIME_TRANSPORT', default='websocket').strip().lower()
if REALTIME_TRANSPORT not in ('websocket', 'http_polling'):
    REALTIME_TRANSPORT = 'websocket'

REALTIME_POLL_PRESENCE_INTERVAL = env.int('REALTIME_POLL_PRESENCE_INTERVAL', default=45)
REALTIME_POLL_NOTIFICATIONS_INTERVAL = env.int('REALTIME_POLL_NOTIFICATIONS_INTERVAL', default=15)
REALTIME_POLL_ADMIN_PRESENCE_INTERVAL = env.int('REALTIME_POLL_ADMIN_PRESENCE_INTERVAL', default=10)
REALTIME_POLL_MESSENGER_INTERVAL = env.int('REALTIME_POLL_MESSENGER_INTERVAL', default=5)
