import json
import base64
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from .models import Conversation, Message, FileAttachment
from .serializers import MessageSerializer

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time chat."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'
        
        # Authenticate user
        self.user = await self.get_user_from_token()
        if not self.user:
            await self.close(code=4001)
            return
        
        # Verify user is part of this conversation
        conversation = await self.get_conversation()
        if not conversation:
            await self.close(code=4004)
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send connection success message
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to chat'
        }))
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave room group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Receive message from WebSocket."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'file_message':
                await self.handle_file_message(data)
            elif message_type == 'typing':
                await self.handle_typing(data)
            elif message_type == 'mark_read':
                await self.handle_mark_read(data)
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'Unknown message type: {message_type}'
                }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))
    
    async def handle_chat_message(self, data):
        """Handle text chat message."""
        content = data.get('message', '')
        
        if not content:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Message content is required'
            }))
            return
        
        # Save message to database
        message = await self.save_message(content, 'text')
        
        # Serialize message
        message_data = await self.serialize_message(message)
        
        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message_data
            }
        )
    
    async def handle_file_message(self, data):
        """Handle file upload message."""
        file_data = data.get('file')
        filename = data.get('filename')
        content = data.get('message', '')
        
        if not file_data or not filename:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'File data and filename are required'
            }))
            return
        
        # Save message and file to database
        message = await self.save_file_message(file_data, filename, content)
        
        # Serialize message
        message_data = await self.serialize_message(message)
        
        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message_data
            }
        )
    
    async def handle_typing(self, data):
        """Handle typing indicator."""
        is_typing = data.get('is_typing', False)
        
        # Broadcast typing status to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_indicator',
                'user_id': self.user.id,
                'user_email': self.user.email,
                'is_typing': is_typing
            }
        )
    
    async def handle_mark_read(self, data):
        """Handle marking messages as read."""
        await self.mark_messages_read()
        
        # Notify other user
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'messages_read',
                'user_id': self.user.id
            }
        )
    
    # Handlers for group messages
    async def chat_message(self, event):
        """Send chat message to WebSocket."""
        await self.send(text_data=json.dumps(event['message']))
    
    async def typing_indicator(self, event):
        """Send typing indicator to WebSocket."""
        # Don't send typing indicator to the user who is typing
        if event['user_id'] != self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'user_id': event['user_id'],
                'user_email': event['user_email'],
                'is_typing': event['is_typing']
            }))
    
    async def messages_read(self, event):
        """Send read receipt to WebSocket."""
        if event['user_id'] != self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'read_receipt',
                'user_id': event['user_id']
            }))
    
    # Database operations
    @database_sync_to_async
    def get_user_from_token(self):
        """Authenticate user from JWT token."""
        try:
            # Get token from query string
            query_string = self.scope.get('query_string', b'').decode()
            token = None
            
            for param in query_string.split('&'):
                if param.startswith('token='):
                    token = param.split('=')[1]
                    break
            
            if not token:
                return None
            
            # Validate token
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            user = User.objects.get(id=user_id)
            return user
        except (InvalidToken, TokenError, User.DoesNotExist):
            return None
    
    @database_sync_to_async
    def get_conversation(self):
        """Get conversation and verify user is a participant."""
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            if self.user in [conversation.listener, conversation.talker]:
                return conversation
            return None
        except Conversation.DoesNotExist:
            return None
    
    @database_sync_to_async
    def save_message(self, content, message_type):
        """Save message to database."""
        conversation = Conversation.objects.get(id=self.conversation_id)
        message = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            content=content,
            message_type=message_type
        )
        return message
    
    @database_sync_to_async
    def save_file_message(self, file_data, filename, content):
        """Save file message to database."""
        conversation = Conversation.objects.get(id=self.conversation_id)
        
        # Decode base64 file data
        try:
            file_content = base64.b64decode(file_data)
        except Exception:
            raise ValueError("Invalid file data")
        
        # Create message
        message = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            content=content,
            message_type='file'
        )
        
        # Create file attachment
        file_obj = ContentFile(file_content, name=filename)
        file_attachment = FileAttachment.objects.create(
            message=message,
            file=file_obj,
            filename=filename,
            file_size=len(file_content)
        )
        
        return message
    
    @database_sync_to_async
    def serialize_message(self, message):
        """Serialize message for sending."""
        serializer = MessageSerializer(message)
        return serializer.data
    
    @database_sync_to_async
    def mark_messages_read(self):
        """Mark all messages from other user as read."""
        conversation = Conversation.objects.get(id=self.conversation_id)
        conversation.messages.filter(
            is_read=False
        ).exclude(sender=self.user).update(is_read=True)
