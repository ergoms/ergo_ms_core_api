import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger('core.messenger')


class MessengerConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer для мессенджера.

    Группирует клиентов по content_type + object_id, обеспечивая
    real-time доставку сообщений всем участникам одного чата.
    """

    async def connect(self):
        self.content_type_name = self.scope['url_route']['kwargs']['content_type']
        self.object_id = self.scope['url_route']['kwargs']['object_id']
        self.room_group_name = f'messenger_{self.content_type_name}_{self.object_id}'

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        event_type = content.get('type')

        if event_type == 'typing':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_indicator',
                    'user_id': content.get('user_id'),
                    'username': content.get('username', ''),
                },
            )

    async def new_message(self, event):
        await self.send_json({
            'type': 'new_message',
            'message': event['message'],
        })

    async def message_edited(self, event):
        await self.send_json({
            'type': 'message_edited',
            'message': event['message'],
        })

    async def message_deleted(self, event):
        await self.send_json({
            'type': 'message_deleted',
            'message_id': event['message_id'],
        })

    async def typing_indicator(self, event):
        await self.send_json({
            'type': 'typing',
            'user_id': event['user_id'],
            'username': event.get('username', ''),
        })
