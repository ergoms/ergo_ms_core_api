"""
Транспорт realtime: websocket, sse или http_polling (REST + short polling на клиенте).
"""

from src.config.env import env

REALTIME_TRANSPORT = env.str('REALTIME_TRANSPORT', default='websocket').strip().lower()
if REALTIME_TRANSPORT not in ('websocket', 'sse', 'http_polling'):
    REALTIME_TRANSPORT = 'websocket'

REALTIME_SSE_KEEPALIVE_INTERVAL = env.int('REALTIME_SSE_KEEPALIVE_INTERVAL', default=25)

REALTIME_POLL_PRESENCE_INTERVAL = env.int('REALTIME_POLL_PRESENCE_INTERVAL', default=45)
REALTIME_POLL_NOTIFICATIONS_INTERVAL = env.int('REALTIME_POLL_NOTIFICATIONS_INTERVAL', default=15)
REALTIME_POLL_ADMIN_PRESENCE_INTERVAL = env.int('REALTIME_POLL_ADMIN_PRESENCE_INTERVAL', default=10)
REALTIME_POLL_MESSENGER_INTERVAL = env.int('REALTIME_POLL_MESSENGER_INTERVAL', default=5)

REALTIME_CAPABILITIES = {
    'typing': REALTIME_TRANSPORT == 'websocket',
    'bidirectional': REALTIME_TRANSPORT == 'websocket',
    'push': REALTIME_TRANSPORT in ('websocket', 'sse'),
}
