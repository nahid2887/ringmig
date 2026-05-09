from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, BasePermission
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Conversation, Message, FileAttachment
from .models import Notification, PrivacyPolicy, TermsAndConditions
from listener.models import ListenerBlockedTalker
from .serializers import (
    ConversationSerializer, 
    ConversationListSerializer,
    ConversationCreateSerializer,
    MessageSerializer,
    FileAttachmentSerializer,
    NotificationSerializer,
    PrivacyPolicySerializer,
    TermsAndConditionsSerializer,
)

User = get_user_model()


class IsSuperUser(BasePermission):
    """Allow access only to authenticated superusers."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class SingletonPolicyAPIView(APIView):
    """Shared behavior for public singleton policy documents."""

    serializer_class = None
    model = None
    document_name = ''

    def get_permissions(self):
        if self.request.method == 'PATCH':
            permission_classes = [IsSuperUser]
        else:
            permission_classes = [AllowAny]
        return [permission() for permission in permission_classes]

    def get_object(self):
        return self.model.load()

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def get_policy(self, request):
        policy = self.get_object()
        serializer = self.get_serializer(policy, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch_policy(self, request):
        policy = self.get_object()
        serializer = self.get_serializer(policy, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class PrivacyPolicyView(SingletonPolicyAPIView):
    serializer_class = PrivacyPolicySerializer
    model = PrivacyPolicy
    document_name = 'privacy policy'

    @swagger_auto_schema(
        operation_id='chat_privacy_policy_retrieve',
        operation_description='Get the current privacy policy content',
        responses={200: PrivacyPolicySerializer},
        tags=['Policies'],
    )
    def get(self, request):
        return self.get_policy(request)

    @swagger_auto_schema(
        operation_id='chat_privacy_policy_partial_update',
        operation_description='Update the privacy policy content',
        request_body=PrivacyPolicySerializer,
        responses={200: PrivacyPolicySerializer},
        tags=['Policies'],
    )
    def patch(self, request):
        return self.patch_policy(request)


class TermsAndConditionsView(SingletonPolicyAPIView):
    serializer_class = TermsAndConditionsSerializer
    model = TermsAndConditions
    document_name = 'terms and conditions'

    @swagger_auto_schema(
        operation_id='chat_terms_and_conditions_retrieve',
        operation_description='Get the current terms and conditions content',
        responses={200: TermsAndConditionsSerializer},
        tags=['Policies'],
    )
    def get(self, request):
        return self.get_policy(request)

    @swagger_auto_schema(
        operation_id='chat_terms_and_conditions_partial_update',
        operation_description='Update the terms and conditions content',
        request_body=TermsAndConditionsSerializer,
        responses={200: TermsAndConditionsSerializer},
        tags=['Policies'],
    )
    def patch(self, request):
        return self.patch_policy(request)


class UserNotificationListView(APIView):
    """API for users to fetch their notification history."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id='chat_notifications_list',
        operation_description='Get notification history for authenticated user',
        manual_parameters=[
            openapi.Parameter(
                'unread_only',
                openapi.IN_QUERY,
                description='Filter unread notifications only (true/false)',
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                'limit',
                openapi.IN_QUERY,
                description='Number of notifications to return (default 50, max 200)',
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                'offset',
                openapi.IN_QUERY,
                description='Pagination offset (default 0)',
                type=openapi.TYPE_INTEGER,
            ),
        ],
        responses={200: openapi.Response('Notifications list')},
        tags=['Notifications']
    )
    def get(self, request):
        unread_only = str(request.query_params.get('unread_only', '')).lower() in ['1', 'true', 'yes']
        limit = int(request.query_params.get('limit', 50) or 50)
        offset = int(request.query_params.get('offset', 0) or 0)
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        queryset = Notification.objects.filter(user=request.user).order_by('-created_at')
        if unread_only:
            queryset = queryset.filter(is_read=False)

        total_count = queryset.count()
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        rows = queryset[offset:offset + limit]

        serializer = NotificationSerializer(rows, many=True)
        return Response(
            {
                'count': total_count,
                'unread_count': unread_count,
                'limit': limit,
                'offset': offset,
                'results': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class NotificationUnreadCountView(APIView):
    """Return unread notification count for authenticated user."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id='chat_notifications_unread_count',
        operation_description='Get unread notification count for authenticated user',
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'unread_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                },
            )
        },
        tags=['Notifications']
    )
    def get(self, request):
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({'unread_count': unread_count}, status=status.HTTP_200_OK)


class NotificationMarkAllReadView(APIView):
    """Mark all notifications as read for authenticated user."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id='chat_notifications_mark_all_read',
        operation_description='Mark all unread notifications as read for authenticated user',
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    'updated_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                },
            )
        },
        tags=['Notifications']
    )
    def post(self, request):
        updated_count = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response(
            {
                'success': True,
                'updated_count': updated_count,
            },
            status=status.HTTP_200_OK,
        )


class NotificationMarkReadView(APIView):
    """Mark one notification as read for authenticated user."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id='chat_notifications_mark_read',
        operation_description='Mark a single notification as read',
        responses={200: NotificationSerializer},
        tags=['Notifications']
    )
    def patch(self, request, notification_id):
        notification = get_object_or_404(Notification, id=notification_id, user=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        serializer = NotificationSerializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationDeleteView(APIView):
    """Delete one notification for authenticated user."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id='chat_notifications_delete',
        operation_description='Delete a single notification from authenticated user history',
        responses={204: 'Notification deleted successfully'},
        tags=['Notifications']
    )
    def delete(self, request, notification_id):
        notification = get_object_or_404(Notification, id=notification_id, user=request.user)
        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        # Exclude conversations that were rejected by the listener
        return Conversation.objects.filter(
            Q(listener=user) | Q(talker=user)
        ).exclude(status='rejected').distinct()
    
    @action(detail=False, methods=['get'])
    def pending_requests(self, request):
        """Get all pending conversation requests for the listener."""
        if request.user.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can view pending requests'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        pending = Conversation.objects.filter(
            listener=request.user,
            status='pending'
        ).select_related('talker').order_by('-created_at')
        
        serializer = ConversationListSerializer(pending, many=True, context={'request': request})
        return Response({
            'count': pending.count(),
            'results': serializer.data
        })
    
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
        # Prevent creating conversation if listener has blocked this talker
        if ListenerBlockedTalker.objects.filter(listener=listener, talker=request.user).exists():
            return Response(
                {'error': 'You cannot start a conversation with this listener'},
                status=status.HTTP_403_FORBIDDEN
            )
        conversation, created = Conversation.objects.get_or_create(
            listener=listener,
            talker=request.user,
            defaults={'status': 'pending', 'initial_message': initial_message}
        )
        
        # If conversation exists and is still pending, update the initial message
        if not created and conversation.status == 'pending':
            conversation.initial_message = initial_message
            conversation.save()
        
        # Send WebSocket notification to listener
        if created:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'user_{listener.id}_notifications',
                {
                    'type': 'conversation_request',
                    'conversation_id': conversation.id,
                    'talker_id': request.user.id,
                    'talker_email': request.user.email,
                    'talker_name': request.user.full_name or request.user.email,
                    'initial_message': initial_message,
                    'created_at': conversation.created_at.isoformat()
                }
            )
        
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
        
        # Send WebSocket notification to talker
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'user_{conversation.talker.id}_notifications',
            {
                'type': 'conversation_accepted',
                'conversation_id': conversation.id,
                'listener_id': request.user.id,
                'listener_email': request.user.email,
                'listener_name': request.user.full_name or request.user.email,
                'accepted_at': conversation.accepted_at.isoformat()
            }
        )
        
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
        
        # Send WebSocket notification to talker
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'user_{conversation.talker.id}_notifications',
            {
                'type': 'conversation_rejected',
                'conversation_id': conversation.id,
                'listener_id': request.user.id,
                'listener_email': request.user.email,
                'listener_name': request.user.full_name or request.user.email,
                'rejected_at': conversation.rejected_at.isoformat()
            }
        )
        
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
        """Upload a file to a conversation and broadcast via WebSocket."""
        conversation = self.get_object()

        # Prevent file upload/messages if listener has blocked the talker
        if ListenerBlockedTalker.objects.filter(listener=conversation.listener, talker=conversation.talker).exists():
            return Response(
                {'error': 'Messaging is blocked between these users'},
                status=status.HTTP_403_FORBIDDEN
            )
        
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
        
        # Serialize message with full URLs
        message_serializer = MessageSerializer(message, context={'request': request})
        message_data = message_serializer.data
        
        # Broadcast via WebSocket to all users in this conversation
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        room_group_name = f'chat_{conversation.id}'
        
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'chat_message',
                'message': message_data
            }
        )
        
        return Response(message_data, status=status.HTTP_201_CREATED)
