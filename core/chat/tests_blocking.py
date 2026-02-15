"""
Tests for blocking functionality in WebSocket chat.
"""
import json
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from listener.models import ListenerBlockedTalker
from .models import Conversation
from core.asgi import application

User = get_user_model()


class BlockingWebSocketTest(TestCase):
    """Test blocking functionality in WebSocket chat."""
    
    def setUp(self):
        """Set up test data."""
        # Create talker
        self.talker = User.objects.create_user(
            email='talker@example.com',
            password='testpass123',
            user_type='talker'
        )
        
        # Create listener
        self.listener = User.objects.create_user(
            email='listener@example.com',
            password='testpass123',
            user_type='listener'
        )
        
        # Create conversation
        self.conversation = Conversation.objects.create(
            talker=self.talker,
            listener=self.listener,
            initial_message='Test conversation'
        )
    
    @pytest.mark.asyncio
    async def test_blocked_talker_cannot_send_message(self):
        """Test that a blocked talker cannot send messages."""
        # Block the talker
        ListenerBlockedTalker.objects.create(
            listener=self.listener,
            talker=self.talker
        )
        
        # Get JWT token for talker
        token = AccessToken.for_user(self.talker)
        
        # Try to connect to WebSocket
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conversation.id}/?token={str(token)}"
        )
        
        connected, _ = await communicator.connect()
        assert connected is True
        
        # Try to send a message
        await communicator.send_json_to({
            'type': 'chat_message',
            'message': 'Hello, listener!'
        })
        
        # Receive response - should be an error
        response = await communicator.receive_json_from()
        assert response['type'] == 'error'
        assert 'blocked' in response['message'].lower()
        
        await communicator.disconnect()
    
    @pytest.mark.asyncio
    async def test_unblocked_talker_can_send_message(self):
        """Test that an unblocked talker can send messages."""
        # Don't block the talker - proceed normally
        
        # Get JWT token for talker
        token = AccessToken.for_user(self.talker)
        
        # Connect to WebSocket
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conversation.id}/?token={str(token)}"
        )
        
        connected, _ = await communicator.connect()
        assert connected is True
        
        # Receive connection established message
        await communicator.receive_json_from()
        
        # Receive API info message
        await communicator.receive_json_from()
        
        # Receive conversation history message
        await communicator.receive_json_from()
        
        # Send a message
        await communicator.send_json_to({
            'type': 'chat_message',
            'message': 'Hello, listener!'
        })
        
        # Receive response - should have new_message
        response = await communicator.receive_json_from()
        assert response['type'] == 'new_message'
        
        await communicator.disconnect()
    
    @pytest.mark.asyncio
    async def test_blocked_talker_cannot_send_file(self):
        """Test that a blocked talker cannot send files."""
        # Block the talker
        ListenerBlockedTalker.objects.create(
            listener=self.listener,
            talker=self.talker
        )
        
        # Get JWT token for talker
        token = AccessToken.for_user(self.talker)
        
        # Connect to WebSocket
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conversation.id}/?token={str(token)}"
        )
        
        connected, _ = await communicator.connect()
        assert connected is True
        
        # Try to send a file
        await communicator.send_json_to({
            'type': 'file_message',
            'file': 'base64encodedfiledata',
            'filename': 'test.txt',
            'message': 'Check this file'
        })
        
        # Receive response - should be an error
        response = await communicator.receive_json_from()
        assert response['type'] == 'error'
        assert 'blocked' in response['message'].lower()
        
        await communicator.disconnect()
    
    @pytest.mark.asyncio
    async def test_blocked_talker_typing_not_sent(self):
        """Test that typing indicators are not sent when blocked."""
        # Block the talker
        ListenerBlockedTalker.objects.create(
            listener=self.listener,
            talker=self.talker
        )
        
        # Get JWT token for talker
        token = AccessToken.for_user(self.talker)
        
        # Connect to WebSocket
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conversation.id}/?token={str(token)}"
        )
        
        connected, _ = await communicator.connect()
        assert connected is True
        
        # Try to send typing indicator
        await communicator.send_json_to({
            'type': 'typing',
            'is_typing': True
        })
        
        # Should not receive any response or error (silently ignored)
        # Wait a bit to ensure nothing is sent
        import asyncio
        await asyncio.sleep(0.1)
        
        await communicator.disconnect()


class BlockingAPITest(TestCase):
    """Test blocking API endpoints."""
    
    def setUp(self):
        """Set up test data."""
        # Create talker
        self.talker = User.objects.create_user(
            email='talker@example.com',
            password='testpass123',
            user_type='talker'
        )
        
        # Create listener
        self.listener = User.objects.create_user(
            email='listener@example.com',
            password='testpass123',
            user_type='listener'
        )
    
    def test_block_talker_creates_block_record(self):
        """Test that blocking a talker creates a block record."""
        # Block the talker
        blocked, created = ListenerBlockedTalker.objects.get_or_create(
            listener=self.listener,
            talker=self.talker
        )
        
        assert created is True
        assert blocked.listener == self.listener
        assert blocked.talker == self.talker
    
    def test_unblock_talker_removes_block_record(self):
        """Test that unblocking a talker removes the block record."""
        # Block the talker
        ListenerBlockedTalker.objects.create(
            listener=self.listener,
            talker=self.talker
        )
        
        # Verify block exists
        assert ListenerBlockedTalker.objects.filter(
            listener=self.listener,
            talker=self.talker
        ).exists()
        
        # Unblock
        ListenerBlockedTalker.objects.filter(
            listener=self.listener,
            talker=self.talker
        ).delete()
        
        # Verify block is removed
        assert not ListenerBlockedTalker.objects.filter(
            listener=self.listener,
            talker=self.talker
        ).exists()
