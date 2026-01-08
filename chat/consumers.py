import json
from channels.generic.websocket import AsyncWebsocketConsumer

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Handle WebSocket connection"""
        self.room_name = "support_chat"
        self.room_group_name = f"chat_{self.room_name}"
        
        # Join Kafka topic/group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'system',
            'message': 'Connected to support chat'
        }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Receive message from WebSocket client"""
        data = json.loads(text_data)
        message = data['message']
        
        # Get username
        if self.scope['user'].is_authenticated:
            username = self.scope['user'].username
        else:
            username = 'Anonymous'
        
        # Send message to Kafka group (broadcasts to all connected clients)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'username': username
            }
        )

    async def chat_message(self, event):
        """Receive message from Kafka group and send to WebSocket"""
        message = event['message']
        username = event['username']
        
        # Send to WebSocket client
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': message,
            'username': username
        }))