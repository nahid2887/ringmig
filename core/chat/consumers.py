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
from listener.models import ListenerBlockedTalker

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
        
        # Send file upload API info
        await self.send(text_data=json.dumps({
            'type': 'api_info',
            'endpoint': f'/api/chat/conversations/{self.conversation_id}/upload_file/',
            'method': 'POST',
            'description': 'Upload image or file to conversation',
            'content_type': 'multipart/form-data',
            'parameters': {
                'file': 'Required - The image or file to upload',
                'content': 'Optional - Message description'
            },
            'headers': {
                'Authorization': 'Bearer YOUR_JWT_TOKEN'
            },
            'example_url': f'http://10.10.13.27:8005/api/chat/conversations/{self.conversation_id}/upload_file/',
            'message': 'Use the endpoint above to upload files. Files will be automatically broadcasted to all connected users.'
        }))
        
        # Send previous messages from this conversation
        messages = await self.get_conversation_messages()
        await self.send(text_data=json.dumps({
            'type': 'conversation_history',
            'messages': messages,
            'count': len(messages),
            'message': f'Loaded {len(messages)} previous message(s)'
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
            
            # Ignore system messages (sent by server)
            if message_type in ['connection_established', 'new_message', 'typing', 'read_receipt']:
                return
            
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
        """Send all conversation messages when a new message arrives."""
        # Load all messages in the conversation (newest first)
        all_messages = await self.get_conversation_messages()
        
        await self.send(text_data=json.dumps({
            'type': 'new_message',
            'messages': all_messages,
            'count': len(all_messages),
            'latest_message': event['message']
        }))
        
        # Also broadcast conversation list update to both users
        # Get both talker and listener for this conversation
        conversation = await self.get_conversation()
        if conversation:
            # Send to talker's conversation list
            await self.channel_layer.group_send(
                f'user_{conversation.talker.id}_conversations',
                {
                    'type': 'conversation_update',
                    'conversation_id': conversation.id
                }
            )
            # Send to listener's conversation list
            await self.channel_layer.group_send(
                f'user_{conversation.listener.id}_conversations',
                {
                    'type': 'conversation_update',
                    'conversation_id': conversation.id
                }
            )
    
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
            # If listener has blocked the talker, disallow access to the conversation
            if ListenerBlockedTalker.objects.filter(listener=conversation.listener, talker=conversation.talker).exists():
                return None
            if self.user in [conversation.listener, conversation.talker]:
                return conversation
            return None
        except Conversation.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_conversation_messages(self):
        """Get all previous messages for this conversation."""
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            messages = conversation.messages.all().order_by('-created_at')
            
            # Manually build message list with proper file URLs
            result = []
            for msg in messages:
                msg_data = {
                    'id': msg.id,
                    'conversation': msg.conversation.id,
                    'sender': {
                        'id': msg.sender.id,
                        'email': msg.sender.email,
                        'full_name': msg.sender.full_name or msg.sender.email,
                        'user_type': msg.sender.user_type
                    },
                    'content': msg.content,
                    'message_type': msg.message_type,
                    'created_at': msg.created_at.isoformat(),
                    'is_read': msg.is_read,
                    'file_attachment': None
                }
                
                # Add file attachment with full URL if exists
                if hasattr(msg, 'file_attachment') and msg.file_attachment:
                    file_att = msg.file_attachment
                    # Build absolute URL
                    file_url = f'http://10.10.13.27:8005{file_att.file.url}' if file_att.file else None
                    
                    msg_data['file_attachment'] = {
                        'id': file_att.id,
                        'filename': file_att.filename,
                        'file_url': file_url,
                        'file_size': file_att.file_size,
                        'file_type': file_att.file_type
                    }
                
                result.append(msg_data)
            
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return []
    
    @database_sync_to_async
    def save_message(self, content, message_type):
        """Save message to database."""
        from django.utils import timezone
        conversation = Conversation.objects.get(id=self.conversation_id)
        # Prevent saving messages if listener blocked the talker
        if ListenerBlockedTalker.objects.filter(listener=conversation.listener, talker=conversation.talker).exists():
            raise PermissionError("Messaging is blocked between these users")
        message = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            content=content,
            message_type=message_type
        )
        # Update conversation last_message_at
        conversation.last_message_at = timezone.now()
        conversation.save(update_fields=['last_message_at'])
        return message
    
    @database_sync_to_async
    def save_file_message(self, file_data, filename, content):
        """Save file message to database."""
        from django.utils import timezone
        conversation = Conversation.objects.get(id=self.conversation_id)
        # Prevent saving messages if listener blocked the talker
        if ListenerBlockedTalker.objects.filter(listener=conversation.listener, talker=conversation.talker).exists():
            raise PermissionError("Messaging is blocked between these users")
        
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
        
        # Update conversation last_message_at
        conversation.last_message_at = timezone.now()
        conversation.save(update_fields=['last_message_at'])
        
        return message
    
    @database_sync_to_async
    def serialize_message(self, message):
        """Serialize message for sending - direct serialization (faster)."""
        msg_data = {
            'id': message.id,
            'conversation': message.conversation.id,
            'sender': {
                'id': message.sender.id,
                'email': message.sender.email,
                'full_name': message.sender.full_name or message.sender.email,
                'user_type': message.sender.user_type
            },
            'content': message.content,
            'message_type': message.message_type,
            'created_at': message.created_at.isoformat(),
            'is_read': message.is_read,
            'file_attachment': None
        }
        
        # Add file attachment with full URL if exists
        if hasattr(message, 'file_attachment') and message.file_attachment:
            file_att = message.file_attachment
            file_url = f'http://10.10.13.27:8005{file_att.file.url}' if file_att.file else None
            
            msg_data['file_attachment'] = {
                'id': file_att.id,
                'filename': file_att.filename,
                'file_url': file_url,
                'file_size': file_att.file_size,
                'file_type': file_att.file_type
            }
        
        return msg_data
    
    @database_sync_to_async
    def mark_messages_read(self):
        """Mark all messages from other user as read."""
        conversation = Conversation.objects.get(id=self.conversation_id)
        conversation.messages.filter(
            is_read=False
        ).exclude(sender=self.user).update(is_read=True)


class NotificationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time notifications."""
    
    async def connect(self):
        """Handle WebSocket connection for notifications."""
        # Authenticate user
        self.user = await self.get_user_from_token()
        if not self.user:
            await self.close(code=4001)
            return
        
        # Create user-specific notification group
        self.notification_group_name = f'user_{self.user.id}_notifications'
        
        # Join notification group
        await self.channel_layer.group_add(
            self.notification_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send connection success message
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to notifications'
        }))
        
        # Send pending conversations if listener
        if self.user.user_type == 'listener':
            pending_conversations = await self.get_pending_conversations()
            if pending_conversations:
                await self.send(text_data=json.dumps({
                    'type': 'pending_conversations_list',
                    'conversations': pending_conversations,
                    'count': len(pending_conversations),
                    'message': f"You have {len(pending_conversations)} pending conversation(s)"
                }))
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave notification group
        if hasattr(self, 'notification_group_name'):
            await self.channel_layer.group_discard(
                self.notification_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Receive message from WebSocket (not used for notifications)."""
        pass
    
    async def conversation_request(self, event):
        """Send conversation request notification to listener."""
        await self.send(text_data=json.dumps({
            'type': 'conversation_request',
            'conversation_id': event['conversation_id'],
            'talker_id': event['talker_id'],
            'talker_email': event['talker_email'],
            'talker_name': event['talker_name'],
            'initial_message': event['initial_message'],
            'created_at': event['created_at'],
            'message': f"New conversation request from {event['talker_name']}"
        }))
    
    async def conversation_accepted(self, event):
        """Send conversation accepted notification to talker."""
        await self.send(text_data=json.dumps({
            'type': 'conversation_accepted',
            'conversation_id': event['conversation_id'],
            'listener_id': event['listener_id'],
            'listener_email': event['listener_email'],
            'listener_name': event['listener_name'],
            'accepted_at': event['accepted_at'],
            'message': f"Your conversation request was accepted by {event['listener_name']}"
        }))
    
    async def conversation_rejected(self, event):
        """Send conversation rejected notification to talker."""
        await self.send(text_data=json.dumps({
            'type': 'conversation_rejected',
            'conversation_id': event['conversation_id'],
            'listener_id': event['listener_id'],
            'listener_email': event['listener_email'],
            'listener_name': event['listener_name'],
            'rejected_at': event['rejected_at'],
            'message': f"Your conversation request was rejected by {event['listener_name']}"
        }))
    
    async def incoming_call(self, event):
        """Send incoming call notification to listener."""
        await self.send(text_data=json.dumps({
            'type': 'incoming_call',
            'message': f"Incoming call from {event['talker_name']}",
            'session_id': event['session_id'],
            'call_package_id': event['call_package_id'],
            'talker': {
                'id': event['talker_id'],
                'email': event['talker_email'],
                'full_name': event['talker_name'],
                'profile_image': event.get('talker_image')
            },
            'call_type': event['call_type'],
            'total_minutes': event['total_minutes'],
            'created_at': event['created_at']
        }))

    async def call_ended_notification(self, event):
        """Send call ended notification to user."""
        await self.send(text_data=json.dumps({
            'type': 'call_ended',
            'message': event['message'],
            'session_id': event['session_id'],
            'duration_minutes': event['duration_minutes'],
            'ended_by': event['ended_by'],
            'ended_by_name': event.get('ended_by_name'),
            'timestamp': event['timestamp']
        }))
    
    async def call_ending_notification(self, event):
        """Send call ending notification to user (call time expired)."""
        await self.send(text_data=json.dumps(event['data']))
    
    # Database operations
    @database_sync_to_async
    def get_user_from_token(self):
        """Authenticate user from JWT token."""
        try:
            # Get token from query string
            query_string = self.scope.get('query_string', b'').decode()
            params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
            token = params.get('token')
            
            if not token:
                return None
            
            # Validate JWT token
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            user = User.objects.get(id=user_id)
            return user
        except (InvalidToken, TokenError, User.DoesNotExist, KeyError):
            return None
    
    @database_sync_to_async
    def get_pending_conversations(self):
        """Get all pending conversations for listener."""
        conversations = Conversation.objects.filter(
            listener=self.user,
            status='pending'
        ).select_related('talker')
        
        result = []
        for conv in conversations:
            result.append({
                'id': conv.id,
                'talker_id': conv.talker.id,
                'talker_email': conv.talker.email,
                'talker_name': conv.talker.full_name or conv.talker.email,
                'initial_message': conv.initial_message,
                'created_at': conv.created_at.isoformat()
            })
        return result


class ConversationListConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time conversation list updates."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        # Authenticate user
        self.user = await self.get_user_from_token()
        if not self.user:
            await self.close(code=4001)
            return
        
        # Create user-specific conversation list group
        self.conversation_list_group = f'user_{self.user.id}_conversations'
        
        # Join conversation list group
        await self.channel_layer.group_add(
            self.conversation_list_group,
            self.channel_name
        )
        
        await self.accept()
        
        # Send connection success message
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to conversation list updates'
        }))
        
        # Send current conversation list
        conversations = await self.get_user_conversations()
        await self.send(text_data=json.dumps({
            'type': 'conversation_list',
            'conversations': conversations,
            'count': len(conversations),
            'message': f'You have {len(conversations)} conversation(s)'
        }))
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection.""" 
        # Leave conversation list group
        if hasattr(self, 'conversation_list_group'):
            await self.channel_layer.group_discard(
                self.conversation_list_group,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Receive message from WebSocket (not used for conversation list)."""
        pass
    
    async def conversation_update(self, event):
        """Send updated conversation list when a new message arrives."""
        conversations = await self.get_user_conversations()
        await self.send(text_data=json.dumps({
            'type': 'conversation_list_updated',
            'conversations': conversations,
            'count': len(conversations),
            'latest_conversation_id': event.get('conversation_id'),
            'message': f'Conversation {event.get("conversation_id")} updated with new message'
        }))
    
    # Database operations
    @database_sync_to_async
    def get_user_from_token(self):
        """Authenticate user from JWT token."""
        try:
            # Get token from query string
            query_string = self.scope.get('query_string', b'').decode()
            params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
            token = params.get('token')
            
            if not token:
                return None
            
            # Validate JWT token
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            user = User.objects.get(id=user_id)
            return user
        except (InvalidToken, TokenError, User.DoesNotExist, KeyError):
            return None
    
    @database_sync_to_async
    def get_user_conversations(self):
        """Get all conversations for user, ordered by latest message."""
        from django.db.models import Q
        
        conversations = Conversation.objects.filter(
            Q(listener=self.user) | Q(talker=self.user)
        ).order_by('-last_message_at', '-created_at').select_related('listener', 'talker')
        
        result = []
        for conv in conversations:
            # Determine the other user
            other_user = conv.talker if conv.listener == self.user else conv.listener
            
            # Get latest message
            latest_msg = conv.messages.order_by('-created_at').first()
            latest_message_preview = latest_msg.content[:50] if latest_msg else ""
            last_message_sender_id = latest_msg.sender_id if latest_msg else (conv.talker_id if conv.initial_message else None)
            
            result.append({
                'id': conv.id,
                'listener_id': conv.listener.id,
                'listener_email': conv.listener.email,
                'listener_name': conv.listener.full_name or conv.listener.email,
                'talker_id': conv.talker.id,
                'talker_email': conv.talker.email,
                'talker_name': conv.talker.full_name or conv.talker.email,
                'other_user_id': other_user.id,
                'other_user_email': other_user.email,
                'other_user_name': other_user.full_name or other_user.email,
                'status': conv.status,
                'initial_message': conv.initial_message,
                'last_message_preview': latest_message_preview,
                'last_message_sender_id': last_message_sender_id,
                'last_message_at': conv.last_message_at.isoformat() if conv.last_message_at else conv.created_at.isoformat(),
                'total_messages': conv.messages.count(),
                'created_at': conv.created_at.isoformat()
            })
        
        return result
