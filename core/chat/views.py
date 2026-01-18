from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Conversation, Message, FileAttachment
from .serializers import (
    ConversationSerializer, 
    ConversationListSerializer,
    ConversationCreateSerializer,
    MessageSerializer,
    FileAttachmentSerializer
)

User = get_user_model()


class ConversationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing conversations."""
    
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return ConversationListSerializer
        elif self.action == 'create':
            return ConversationCreateSerializer
        return ConversationSerializer
    
    def get_queryset(self):
        """Return conversations for the authenticated user."""
        user = self.request.user
        return Conversation.objects.filter(
            Q(listener=user) | Q(talker=user)
        ).distinct()
    
    def create(self, request, *args, **kwargs):
        """Create a new conversation with initial message (talker only)."""
        if request.user.user_type != 'talker':
            return Response(
                {'error': 'Only talkers can initiate conversations'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        listener_id = serializer.validated_data['listener_id']
        initial_message = serializer.validated_data['initial_message']
        
        # Try to get listener by User ID first, then by ListenerProfile ID
        try:
            listener = User.objects.get(id=listener_id, user_type='listener')
        except User.DoesNotExist:
            # Try getting by ListenerProfile ID
            from listener.models import ListenerProfile
            try:
                listener_profile = ListenerProfile.objects.get(id=listener_id)
                listener = listener_profile.user
            except ListenerProfile.DoesNotExist:
                return Response(
                    {'error': f'Listener with ID {listener_id} not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Get or create conversation in pending status
        conversation, created = Conversation.objects.get_or_create(
            listener=listener,
            talker=request.user,
            defaults={'status': 'pending', 'initial_message': initial_message}
        )
        
        # If conversation exists and is still pending, update the initial message
        if not created and conversation.status == 'pending':
            conversation.initial_message = initial_message
            conversation.save()
        
        response_serializer = ConversationSerializer(conversation, context={'request': request})
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """Accept a conversation request (listener only)."""
        conversation = self.get_object()
        
        # Only listener can accept
        if request.user != conversation.listener:
            return Response(
                {'error': 'Only the listener can accept this conversation'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Can only accept pending conversations
        if conversation.status != 'pending':
            return Response(
                {'error': f'Cannot accept a {conversation.get_status_display().lower()} conversation'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        conversation.accept()
        serializer = ConversationSerializer(conversation, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a conversation request (listener only)."""
        conversation = self.get_object()
        
        # Only listener can reject
        if request.user != conversation.listener:
            return Response(
                {'error': 'Only the listener can reject this conversation'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Can only reject pending conversations
        if conversation.status != 'pending':
            return Response(
                {'error': f'Cannot reject a {conversation.get_status_display().lower()} conversation'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        conversation.reject()
        serializer = ConversationSerializer(conversation, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """Get all messages for a conversation."""
        conversation = self.get_object()
        messages = conversation.messages.all()
        
        # Pagination
        page = self.paginate_queryset(messages)
        if page is not None:
            serializer = MessageSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = MessageSerializer(messages, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark all messages in a conversation as read."""
        conversation = self.get_object()
        
        # Mark all messages from the other user as read
        updated = conversation.messages.filter(
            is_read=False
        ).exclude(sender=request.user).update(is_read=True)
        
        return Response({
            'success': True,
            'marked_read': updated
        })
    
    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_file(self, request, pk=None):
        """Upload a file to a conversation."""
        conversation = self.get_object()
        
        file = request.FILES.get('file')
        if not file:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create message
        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            message_type='file',
            content=request.data.get('content', '')
        )
        
        # Create file attachment
        file_attachment = FileAttachment.objects.create(
            message=message,
            file=file,
            filename=file.name,
            file_size=file.size,
            file_type=file.content_type
        )
        
        # Serialize and return
        message_serializer = MessageSerializer(message, context={'request': request})
        return Response(message_serializer.data, status=status.HTTP_201_CREATED)
