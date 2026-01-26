"""
Agora-based calling API views.
Handles real-time voice and video calling using Agora SDK.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import logging

from .call_models import CallPackage, CallSession, UniversalCallPackage
from .call_serializers import CallSessionSerializer
from .agora_utils import agora_token_generator, agora_call_manager

User = get_user_model()
logger = logging.getLogger(__name__)


class AgoraCallViewSet(viewsets.GenericViewSet):
    """API endpoints for Agora-based calling system."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = CallSessionSerializer
    
    def get_queryset(self):
        """Return call sessions for the current user."""
        user = self.request.user
        if user.user_type == 'talker':
            return CallSession.objects.filter(talker=user)
        elif user.user_type == 'listener':
            return CallSession.objects.filter(listener=user)
        return CallSession.objects.none()
    
    @swagger_auto_schema(
        operation_description="Start a new call based on purchased package",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['call_package_id'],
            properties={
                'call_package_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='ID of purchased call package'
                )
            }
        ),
        responses={
            201: "Call session created successfully",
            400: 'Bad Request',
            404: 'Call package not found',
            403: 'Permission denied'
        },
        tags=['Agora Calling']
    )
    @action(detail=False, methods=['post'])
    def start_call(self, request):
        """Start a new call session based on purchased call package."""
        call_package_id = request.data.get('call_package_id')
        
        if not call_package_id:
            return Response(
                {'error': 'call_package_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get the call package
            call_package = CallPackage.objects.select_related(
                'talker', 'listener', 'package'
            ).get(id=call_package_id)
            
            # Verify user is the talker for this package
            if request.user != call_package.talker:
                return Response(
                    {'error': 'Only the talker can start this call'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Verify payment status
            if call_package.status != 'confirmed':
                return Response(
                    {'error': f'Call package must be confirmed. Current status: {call_package.status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if listener is available
            if not CallSession.is_listener_available(call_package.listener):
                return Response(
                    {'error': 'Listener is currently busy'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if there's already an active session for this package
            existing_session = CallSession.objects.filter(
                call_package=call_package,
                status__in=['connecting', 'active']
            ).first()
            
            if existing_session:
                return Response(
                    {'error': 'Call session already active for this package'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            with transaction.atomic():
                # Determine call type based on package
                package_type = call_package.package.package_type
                call_type = 'video' if package_type in ['video', 'both'] else 'audio'
                
                # Create call session
                session = CallSession.objects.create(
                    talker=call_package.talker,
                    listener=call_package.listener,
                    call_package=call_package,
                    initial_package=call_package,
                    total_minutes_purchased=call_package.package.duration_minutes,
                    status='connecting',
                    call_type=call_type
                )
                
                # Generate Agora tokens
                tokens = agora_token_generator.generate_tokens_for_call(
                    session_id=session.id,
                    talker_uid=call_package.talker.id,
                    listener_uid=call_package.listener.id
                )
                
                # Update session with Agora details
                session.agora_channel_name = tokens['channel_name']
                session.agora_talker_token = tokens['talker_token']
                session.agora_listener_token = tokens['listener_token']
                session.agora_talker_uid = tokens['talker_uid']
                session.agora_listener_uid = tokens['listener_uid']
                session.agora_tokens_generated_at = timezone.now()
                session.save()
                
                # Update call package status
                call_package.status = 'in_progress'
                call_package.save()
                
                logger.info(f"Call started: {session.id} between {call_package.talker.email} and {call_package.listener.email}")
                
                # Prepare response with user's token
                user_token = tokens['talker_token']
                user_uid = tokens['talker_uid']
                
                return Response({
                    'session': {
                        'id': session.id,
                        'talker': session.talker.id,
                        'talker_email': session.talker.email,
                        'listener': session.listener.id,
                        'listener_email': session.listener.email,
                        'listener_name': session.listener.get_full_name(),
                        'status': session.status,
                        'total_minutes_purchased': session.total_minutes_purchased,
                        'minutes_used': str(session.minutes_used),
                        'remaining_minutes': session.get_remaining_minutes(),
                        'elapsed_minutes': 0,
                        'started_at': session.started_at,
                        'ended_at': session.ended_at,
                        'last_warning_sent': session.last_warning_sent,
                        'created_at': session.created_at.isoformat(),
                        'updated_at': session.updated_at.isoformat()
                    },
                    'agora': {
                        'app_id': tokens['app_id'],
                        'channel_name': tokens['channel_name'],
                        'token': user_token,
                        'uid': user_uid,
                        'call_type': call_type,
                        'expires_in': tokens['expires_in'],
                        'video_config': agora_call_manager.get_call_config(package_type)
                    }
                }, status=status.HTTP_201_CREATED)
                
        except CallPackage.DoesNotExist:
            return Response(
                {'error': 'Call package not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error starting call: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Failed to start call: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @swagger_auto_schema(
        operation_description="Join an existing call session (for listener)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['session_id'],
            properties={
                'session_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='ID of call session to join'
                )
            }
        ),
        responses={
            200: "Successfully joined call session",
            400: 'Bad Request',
            404: 'Session not found',
            403: 'Permission denied'
        },
        tags=['Agora Calling']
    )
    @action(detail=False, methods=['post'])
    def join_call(self, request):
        """Join an existing call session (for listener)."""
        session_id = request.data.get('session_id')
        
        if not session_id:
            return Response(
                {'error': 'session_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            session = CallSession.objects.select_related(
                'talker', 'listener', 'initial_package__package'
            ).get(id=session_id)
            
            # Verify user is the listener for this session
            if request.user != session.listener:
                return Response(
                    {'error': 'Only the listener can join this call'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Validate call can be joined
            is_valid, error_message = agora_call_manager.validate_call_requirements(
                session, request.user
            )
            
            if not is_valid:
                return Response(
                    {'error': error_message},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update session status to active and set start time if not already set
            if session.status == 'connecting':
                session.status = 'active'
                session.started_at = timezone.now()
                session.save()
            
            # Get call configuration
            package_type = session.initial_package.package.package_type if session.initial_package else 'audio'
            
            # Prepare response with listener's token
            user_token = session.agora_listener_token
            user_uid = session.agora_listener_uid
            
            return Response({
                'session': {
                    'id': session.id,
                    'talker': session.talker.id,
                    'talker_email': session.talker.email,
                    'listener': session.listener.id,
                    'listener_email': session.listener.email,
                    'listener_name': session.listener.get_full_name(),
                    'status': session.status,
                    'total_minutes_purchased': session.total_minutes_purchased,
                    'minutes_used': str(session.minutes_used),
                    'remaining_minutes': session.get_remaining_minutes(),
                    'elapsed_minutes': int((timezone.now() - session.started_at).total_seconds() / 60) if session.started_at else 0,
                    'started_at': session.started_at,
                    'ended_at': session.ended_at,
                    'last_warning_sent': session.last_warning_sent,
                    'created_at': session.created_at.isoformat(),
                    'updated_at': session.updated_at.isoformat()
                },
                'agora': {
                    'app_id': agora_token_generator.app_id,
                    'channel_name': session.agora_channel_name,
                    'token': user_token,
                    'uid': user_uid,
                    'call_type': session.call_type,
                    'video_config': agora_call_manager.get_call_config(package_type)
                }
            })
            
        except CallSession.DoesNotExist:
            return Response(
                {'error': 'Call session not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error joining call: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Failed to join call: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )