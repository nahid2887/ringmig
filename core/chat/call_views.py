from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from django.conf import settings
from decimal import Decimal
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import logging
import stripe

from .call_models import CallPackage, CallSession, UniversalCallPackage, CallRejection, ListenerPayout
from .call_serializers import (
    CallPackageSerializer,
    UniversalCallPackageSerializer,
    PurchaseCallPackageSerializer,
    CallSessionSerializer
)
from .serializers import CallRejectionSerializer, CallPayoutSerializer, CallPayoutListSerializer
from .call_payments import (
    create_call_package_payment_intent,
    confirm_call_package_payment,
    create_listener_payout
)

# Import Booking model
try:
    from payment.models import Booking, Payment
except ImportError:
    Booking = None
    Payment = None

User = get_user_model()
logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class UniversalCallPackageViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing universal call packages (admin-created)."""
    
    queryset = UniversalCallPackage.objects.filter(is_active=True)
    serializer_class = UniversalCallPackageSerializer
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        operation_description="List all available call packages",
        manual_parameters=[
            openapi.Parameter('package_type', openapi.IN_QUERY, type=openapi.TYPE_STRING, 
                            enum=['one_time', 'recurring'], description='Filter by package type')
        ],
        responses={200: UniversalCallPackageSerializer(many=True)},
        tags=['Call Packages']
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_description="Get details of a specific call package",
        responses={200: UniversalCallPackageSerializer},
        tags=['Call Packages']
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    def get_queryset(self):
        """Filter active packages."""
        queryset = UniversalCallPackage.objects.filter(is_active=True)
        
        # Filter by package type if provided
        package_type = self.request.query_params.get('package_type')
        if package_type:
            queryset = queryset.filter(package_type=package_type)
        
        return queryset.order_by('duration_minutes', 'price')


class CallPackageViewSet(viewsets.ModelViewSet):
    """ViewSet for managing call packages."""
    
    serializer_class = CallPackageSerializer
    permission_classes = [IsAuthenticated]
    
    # Hide unnecessary endpoints from Swagger
    swagger_schema = None  # Will be set per action
    
    def get_queryset(self):
        """Return packages for the current user."""
        user = self.request.user
        if user.user_type == 'talker':
            return CallPackage.objects.filter(talker=user)
        elif user.user_type == 'listener':
            return CallPackage.objects.filter(listener=user)
        return CallPackage.objects.none()
    
    # Hide standard CRUD from Swagger
    def list(self, request, *args, **kwargs):
        """Hidden from API docs - use /active or /history instead."""
        return super().list(request, *args, **kwargs)
    
    def create(self, request, *args, **kwargs):
        """Hidden from API docs - use /purchase instead."""
        return Response(
            {'error': 'Use /purchase endpoint to buy call packages'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Hidden from API docs."""
        return super().retrieve(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        """Not allowed."""
        return Response(
            {'error': 'Cannot update call packages'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    def destroy(self, request, *args, **kwargs):
        """Not allowed."""
        return Response(
            {'error': 'Cannot delete call packages'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    @swagger_auto_schema(
        operation_description="Purchase a call package for calling a listener",
        request_body=PurchaseCallPackageSerializer,
        responses={
            200: openapi.Response(
                description="Payment intent created successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'payment_intent_id': openapi.Schema(type=openapi.TYPE_STRING),
                        'client_secret': openapi.Schema(type=openapi.TYPE_STRING),
                        'call_package_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                    }
                )
            ),
            400: "Invalid request"
        },
        tags=['Call Packages & Calls - Purchase']
    )
    @action(detail=False, methods=['post'], url_path='purchase')
    def purchase_package(self, request):
        """
        Purchase a call package for a listener.
        
        Request body:
        {
            "listener_id": 4,
            "package_id": 1,
            "payment_method_id": "pm_xxx",  // optional, for immediate payment
            "is_extension": false
        }
        
        Response includes client_secret for Stripe payment.
        """
        serializer = PurchaseCallPackageSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        validated_data = serializer.validated_data
        listener = User.objects.get(id=validated_data['listener_id'])
        package = validated_data['package']
        talker = request.user
        is_extension = validated_data.get('is_extension', False)
        payment_method_id = validated_data.get('payment_method_id')
        
        # Check if listener is available
        if not is_extension and not CallSession.is_listener_available(listener):
            # Listener is busy, suggest available listeners
            available_listeners = User.objects.filter(
                user_type='listener',
                is_active=True
            ).exclude(id=listener.id)
            
            # Filter to only those not in active calls
            available_list = [
                u for u in available_listeners 
                if CallSession.is_listener_available(u)
            ]
            
            return Response(
                {
                    'error': f'{listener.email} is busy now. Please try again later.',
                    'message': 'Other listeners are available:',
                    'available_listeners': [
                        {'id': u.id, 'email': u.email, 'full_name': u.full_name}
                        for u in available_list[:10]
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                if is_extension:
                    # Extension: add time to existing call
                    active_session = validated_data['active_session']
                    
                    # Create extension package
                    call_package = CallPackage.objects.create(
                        talker=talker,
                        listener=listener,
                        package=package,
                        total_amount=package.price,
                        app_fee=package.app_fee,
                        listener_amount=package.listener_amount,
                        status='pending',
                        call_session=active_session,
                        is_extension=True
                    )
                    
                    # Create payment intent
                    payment_info = create_call_package_payment_intent(
                        call_package,
                        payment_method_id=payment_method_id
                    )
                    
                    # If payment succeeded immediately, add time
                    if payment_info['status'] == 'succeeded':
                        call_package.status = 'confirmed'
                        call_package.save()
                        active_session.add_time(package.duration_minutes)
                        
                        return Response({
                            'message': f'Successfully added {package.duration_minutes} minutes to your call',
                            'call_package': CallPackageSerializer(call_package).data,
                            'session': CallSessionSerializer(active_session).data,
                            'payment': payment_info
                        }, status=status.HTTP_200_OK)
                    
                    # Return client_secret for frontend to confirm payment
                    return Response({
                        'message': 'Complete payment to add time',
                        'call_package': CallPackageSerializer(call_package).data,
                        'payment': payment_info,
                        'requires_action': True,
                        'stripe_payment_link': {
                            'dashboard_url': f"https://dashboard.stripe.com/test/payments/{payment_info['payment_intent_id']}",
                            'confirm_url': f"https://api.stripe.com/v1/payment_intents/{payment_info['payment_intent_id']}/confirm",
                            'test_card': '4242424242424242',
                            'instructions': {
                                'postman': {
                                    'method': 'POST',
                                    'url': f"https://api.stripe.com/v1/payment_intents/{payment_info['payment_intent_id']}/confirm",
                                    'headers': {
                                        'Authorization': 'Bearer YOUR_STRIPE_SECRET_KEY',
                                        'Content-Type': 'application/x-www-form-urlencoded'
                                    },
                                    'body': 'payment_method=pm_card_visa'
                                }
                            }
                        }
                    }, status=status.HTTP_200_OK)
                    
                else:
                    # New call: create package purchase
                    call_package = CallPackage.objects.create(
                        talker=talker,
                        listener=listener,
                        package=package,
                        total_amount=package.price,
                        app_fee=package.app_fee,
                        listener_amount=package.listener_amount,
                        status='pending',
                        is_extension=False
                    )
                    
                    # Create payment intent
                    payment_info = create_call_package_payment_intent(
                        call_package,
                        payment_method_id=payment_method_id
                    )
                    
                    # If payment succeeded immediately
                    if payment_info['status'] == 'succeeded':
                        call_package.status = 'confirmed'
                        call_package.save()
                        
                        return Response({
                            'message': f'Package purchased successfully. You can now call {listener.email}',
                            'call_package': CallPackageSerializer(call_package).data,
                            'payment': payment_info,
                            'next_step': 'initiate_call'
                        }, status=status.HTTP_201_CREATED)
                    
                    # Return client_secret for frontend to confirm payment
                    return Response({
                        'message': 'Complete payment to purchase package',
                        'call_package': CallPackageSerializer(call_package).data,
                        'payment': payment_info,
                        'requires_action': True,
                        'stripe_payment_link': {
                            'dashboard_url': f"https://dashboard.stripe.com/test/payments/{payment_info['payment_intent_id']}",
                            'confirm_url': f"https://api.stripe.com/v1/payment_intents/{payment_info['payment_intent_id']}/confirm",
                            'test_card': '4242424242424242',
                            'instructions': {
                                'postman': {
                                    'method': 'POST',
                                    'url': f"https://api.stripe.com/v1/payment_intents/{payment_info['payment_intent_id']}/confirm",
                                    'headers': {
                                        'Authorization': 'Bearer YOUR_STRIPE_SECRET_KEY',
                                        'Content-Type': 'application/x-www-form-urlencoded'
                                    },
                                    'body': 'payment_method=pm_card_visa'
                                }
                            }
                        }
                    }, status=status.HTTP_201_CREATED)
                    
        except Exception as e:
            logger.error(f"Error purchasing package: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @swagger_auto_schema(
        operation_description="Check if a listener is available for a call",
        manual_parameters=[
            openapi.Parameter('listener_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=True)
        ],
        responses={
            200: openapi.Response(
                description="Availability status",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'available': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            )
        },
        tags=['Call Packages']
    )
    @action(detail=False, methods=['get'], url_path='check-availability')
    def check_availability(self, request):
        """
        Check if a listener is available for a call.
        Query params: listener_id
        """
        listener_id = request.query_params.get('listener_id')
        
        if not listener_id:
            return Response(
                {'error': 'listener_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            listener = User.objects.get(id=listener_id, user_type='listener')
        except User.DoesNotExist:
            return Response(
                {'error': 'Listener not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        is_available = CallSession.is_listener_available(listener)
        
        if is_available:
            return Response({
                'available': True,
                'message': f'{listener.email} is available for a call'
            })
        else:
            return Response({
                'available': False,
                'message': f'{listener.email} is busy now. Please try again later.'
            })
    
    @swagger_auto_schema(
        operation_description="Initiate a call session from an existing booking",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['booking_id'],
            properties={
                'booking_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of confirmed booking')
            }
        ),
        responses={
            201: CallSessionSerializer,
            400: "Invalid request",
            404: "Booking not found"
        },
        tags=['Call Sessions']
    )
    @action(detail=False, methods=['post'], url_path='initiate-from-booking')
    def initiate_from_booking(self, request):
        """
        Initiate a call session from an existing booking.
        
        Request body:
        - booking_id: ID of the confirmed booking
        """
        booking_id = request.data.get('booking_id')
        
        if not booking_id:
            return Response(
                {'error': 'booking_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not Booking:
            return Response(
                {'error': 'Booking system not available'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        try:
            # Get the booking
            booking = Booking.objects.select_related('talker', 'listener', 'package', 'payment').get(
                id=booking_id,
                status='confirmed'
            )
        except Booking.DoesNotExist:
            return Response(
                {'error': 'Booking not found or not confirmed'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Verify user is participant
        if booking.talker != request.user and booking.listener != request.user:
            return Response(
                {'error': 'You are not a participant in this booking'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validate payment status
        if hasattr(booking, 'payment'):
            if booking.payment.status != 'succeeded':
                return Response(
                    {'error': f'Payment status is {booking.payment.status}. Must be succeeded to start call.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Check if listener is still available
        if not CallSession.is_listener_available(booking.listener):
            return Response(
                {'error': f'{booking.listener.email} is busy now. Please try again later.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if booking already has a call session
        if hasattr(booking, 'call_session'):
            return Response(
                {'error': 'Call session already exists for this booking',
                 'session': CallSessionSerializer(booking.call_session).data},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Create call session from booking
                session = CallSession.objects.create(
                    talker=booking.talker,
                    listener=booking.listener,
                    booking=booking,
                    total_minutes_purchased=booking.package.duration_minutes,
                    status='connecting'
                )
                
                # Mark booking as in progress
                booking.start_session()
                
                return Response({
                    'message': 'Call session created. Connect to WebSocket to start call.',
                    'session': CallSessionSerializer(session).data,
                    'websocket_url': f'/ws/call/{session.id}/',
                    'booking_id': booking.id,
                    'duration_minutes': booking.package.duration_minutes
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @swagger_auto_schema(
        operation_description="Initiate a call session from a confirmed call package",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['call_package_id'],
            properties={
                'call_package_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of confirmed call package')
            }
        ),
        responses={
            201: CallSessionSerializer,
            400: "Invalid request",
            404: "Call package not found"
        },
        tags=['Call Packages & Calls - Start Call']
    )
    @action(detail=False, methods=['post'], url_path='initiate-from-package')
    def initiate_from_package(self, request):
        """
        Initiate a call session from a package.
        
        Request: {"listener_id": 4, "package_id": 1}
        
        package_id automatically detects:
        - Purchased package (CallPackage) if already bought
        - Universal package (UniversalCallPackage) if template ID - will auto-purchase
        """
        listener_id = request.data.get('listener_id')
        package_id = request.data.get('package_id')
        
        if not listener_id or not package_id:
            return Response(
                {'error': 'listener_id and package_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get listener
            listener = User.objects.get(id=listener_id, user_type='listener')
        except User.DoesNotExist:
            return Response(
                {'error': 'Listener not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Try to find as purchased package first, then as universal package
        call_package = None
        
        try:
            # Try as purchased CallPackage first
            call_package = CallPackage.objects.select_related('talker', 'listener', 'package').get(
                id=package_id,
                status='confirmed',
                talker=request.user,
                listener=listener
            )
        except CallPackage.DoesNotExist:
            # Try as UniversalCallPackage template
            try:
                universal_package = UniversalCallPackage.objects.get(
                    id=package_id,
                    is_active=True
                )
                
                # Auto-purchase from universal package with proper pricing
                call_package = CallPackage.objects.create(
                    talker=request.user,
                    listener=listener,
                    package=universal_package,
                    total_amount=universal_package.price,
                    app_fee=universal_package.app_fee,
                    listener_amount=universal_package.listener_amount,
                    status='confirmed',
                    is_extension=False
                )
            except UniversalCallPackage.DoesNotExist:
                return Response(
                    {'error': 'Package not found. Provide a valid purchased package ID or universal package ID.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Verify user is participant
        if call_package.talker != request.user and call_package.listener != request.user:
            return Response(
                {'error': 'You are not a participant in this call package'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if listener is still available
        if not CallSession.is_listener_available(listener):
            return Response(
                {'error': f'{listener.email} is busy now. Please try again later.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if call package already has an active call session
        if hasattr(call_package, 'active_call_session') and call_package.active_call_session:
            return Response(
                {'error': 'Call session already exists for this package',
                 'session': CallSessionSerializer(call_package.active_call_session).data},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Create call session from call package
                session = CallSession.objects.create(
                    talker=call_package.talker,
                    listener=call_package.listener,
                    call_package=call_package,
                    initial_package=call_package,
                    total_minutes_purchased=call_package.package.duration_minutes,
                    status='connecting'
                )
                
                # Don't mark as in_progress yet - wait for WebSocket connection
                # call_package.start_call() will be called by CallConsumer.start_call()
                
                return Response({
                    'message': 'Call session created. Connect to WebSocket to start call.',
                    'session': CallSessionSerializer(session).data,
                    'websocket_url': f'/ws/call/{session.id}/',
                    'websocket_full_url': f'ws://10.10.13.27:8005/ws/call/{session.id}/?token=YOUR_JWT_TOKEN',
                    'call_package_id': call_package.id,
                    'duration_minutes': call_package.package.duration_minutes
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CallSessionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing call sessions."""
    
    serializer_class = CallSessionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Return call sessions for the current user."""
        user = self.request.user
        if user.user_type == 'talker':
            return CallSession.objects.filter(talker=user)
        elif user.user_type == 'listener':
            return CallSession.objects.filter(listener=user)
        return CallSession.objects.none()
    
    # Hide list from Swagger - use /active or /history instead
    def list(self, request, *args, **kwargs):
        """Hidden from API docs - use /active instead."""
        return super().list(request, *args, **kwargs)
    
    def retrieve(self, request, *args, **kwargs):
        """Hidden from API docs - use /status endpoint instead."""
        return super().retrieve(request, *args, **kwargs)
    
    @swagger_auto_schema(
        operation_description="Get detailed status of a call session including remaining time",
        responses={
            200: openapi.Response(
                description="Call session status",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'session': openapi.Schema(type=openapi.TYPE_OBJECT),
                        'remaining_minutes': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'should_warn': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'is_active': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    }
                )
            )
        },
        tags=['Call Sessions']
    )
    @action(detail=True, methods=['get'], url_path='status')
    def get_status(self, request, pk=None):
        """Get detailed status of a call session."""
        session = self.get_object()
        
        return Response({
            'session': CallSessionSerializer(session).data,
            'remaining_minutes': round(session.get_remaining_minutes(), 2),
            'should_warn': session.should_send_warning(),
            'is_active': session.status == 'active',
            'packages': CallPackageSerializer(
                session.packages.all(), 
                many=True
            ).data
        })
    
    @swagger_auto_schema(
        operation_description="Get current active call session for logged-in user",
        responses={
            200: CallSessionSerializer,
            404: "No active session"
        },
        tags=['Call Sessions']
    )
    @action(detail=False, methods=['get'], url_path='active')
    def active_session(self, request):
        """Get the current active call session for the user."""
        user = request.user
        
        if user.user_type == 'talker':
            session = CallSession.objects.filter(
                talker=user,
                status__in=['connecting', 'active']
            ).first()
        else:
            session = CallSession.objects.filter(
                listener=user,
                status__in=['connecting', 'active']
            ).first()
        
        if session:
            return Response(CallSessionSerializer(session).data)
        else:
            return Response(
                {'message': 'No active call session'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @swagger_auto_schema(
        operation_description="Get list of previous (completed/ended) call sessions",
        responses={
            200: CallSessionSerializer(many=True)
        },
        tags=['Call Sessions']
    )
    @action(detail=False, methods=['get'], url_path='history')
    def call_history(self, request):
        """Get list of completed/ended call sessions for the user."""
        user = request.user
        
        if user.user_type == 'talker':
            sessions = CallSession.objects.filter(
                talker=user,
                status__in=['ended', 'timeout', 'completed']
            ).order_by('-ended_at')
        else:
            sessions = CallSession.objects.filter(
                listener=user,
                status__in=['ended', 'timeout', 'completed']
            ).order_by('-ended_at')
        
        serializer = CallSessionSerializer(sessions, many=True)
        return Response({
            'count': sessions.count(),
            'sessions': serializer.data
        })
    
    @swagger_auto_schema(
        operation_description="Get list of previous (completed/ended) call sessions - alias for /history",
        responses={
            200: CallSessionSerializer(many=True)
        },
        tags=['Call Sessions']
    )
    @action(detail=False, methods=['get'], url_path='previous-calls')
    def previous_calls(self, request):
        """Get list of completed/ended call sessions - alias for history endpoint."""
        return self.call_history(request)
    
    @swagger_auto_schema(
        operation_description="Get all listener calls (incoming/outgoing) with optional filtering",
        manual_parameters=[
            openapi.Parameter('status', openapi.IN_QUERY, type=openapi.TYPE_STRING, 
                            description='Filter by status: active, ended, pending, all (default: all)'),
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, 
                            description='Limit results (default: 50)'),
            openapi.Parameter('offset', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, 
                            description='Offset for pagination (default: 0)'),
        ],
        responses={200: CallSessionSerializer(many=True)},
        tags=['Call Sessions - Listener']
    )
    @action(detail=False, methods=['get'], url_path='listener-calls')
    def listener_calls(self, request):
        """
        Get all calls for a listener (both active and completed).
        
        Query parameters:
        - status: Filter by status (active, ended, pending, all) - default: all
        - limit: Number of results (default: 50)
        - offset: Pagination offset (default: 0)
        """
        user = request.user
        
        # Only listeners can use this endpoint
        if user.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can view listener calls'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get filter parameters
        status_filter = request.query_params.get('status', 'all')
        limit = int(request.query_params.get('limit', 50))
        offset = int(request.query_params.get('offset', 0))
        
        # Build query
        queryset = CallSession.objects.filter(listener=user)
        
        # Filter by status
        if status_filter == 'active':
            queryset = queryset.filter(status__in=['connecting', 'active'])
        elif status_filter == 'ended':
            queryset = queryset.filter(status__in=['ended', 'timeout', 'completed'])
        elif status_filter == 'pending':
            queryset = queryset.filter(status='connecting')
        # else: all statuses
        
        # Order by creation date
        queryset = queryset.order_by('-created_at')
        
        # Get total count before pagination
        total_count = queryset.count()
        
        # Apply pagination
        calls = queryset[offset:offset + limit]
        
        serializer = CallSessionSerializer(calls, many=True)
        return Response({
            'count': total_count,
            'limit': limit,
            'offset': offset,
            'results': serializer.data
        })
    
    @swagger_auto_schema(
        operation_description="Initiate a call session from a confirmed call package",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['call_package_id'],
            properties={
                'call_package_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of confirmed call package')
            }
        ),
        responses={
            201: CallSessionSerializer,
            400: "Invalid request",
            404: "Call package not found"
        },
        tags=['Call Sessions']
    )
    @action(detail=False, methods=['post'], url_path='initiate-from-package')
    def initiate_from_package(self, request):
        """
        Initiate a call session from an existing call package.
        
        Request body:
        - call_package_id: ID of the confirmed call package
        """
        call_package_id = request.data.get('call_package_id')
        
        if not call_package_id:
            return Response(
                {'error': 'call_package_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get the call package
            call_package = CallPackage.objects.select_related('talker', 'listener', 'package').get(
                id=call_package_id,
                status='confirmed'
            )
        except CallPackage.DoesNotExist:
            return Response(
                {'error': 'Call package not found or not confirmed'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Verify user is participant
        if call_package.talker != request.user and call_package.listener != request.user:
            return Response(
                {'error': 'You are not a participant in this call package'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if listener is still available
        if not CallSession.is_listener_available(call_package.listener):
            return Response(
                {'error': f'{call_package.listener.email} is busy now. Please try again later.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if call package already has an active call session
        if hasattr(call_package, 'active_call_session') and call_package.active_call_session:
            return Response(
                {'error': 'Call session already exists for this package',
                 'session': CallSessionSerializer(call_package.active_call_session).data},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Determine call type based on package
                package_type = call_package.package.package_type
                call_type = 'video' if package_type in ['video', 'both'] else 'audio'
                
                # Create call session from call package
                session = CallSession.objects.create(
                    talker=call_package.talker,
                    listener=call_package.listener,
                    call_package=call_package,
                    initial_package=call_package,
                    total_minutes_purchased=call_package.package.duration_minutes,
                    status='connecting',
                    call_type=call_type
                )
                
                # # Generate Agora tokens for both participants
                # from .agora_utils import agora_token_generator, agora_call_manager
                # 
                # tokens = agora_token_generator.generate_tokens_for_call(
                #     session_id=session.id,
                #     talker_uid=call_package.talker.id,
                #     listener_uid=call_package.listener.id
                # )
                # 
                # # Update session with Agora details
                # session.agora_channel_name = tokens['channel_name']
                # session.agora_talker_token = tokens['talker_token']
                # session.agora_listener_token = tokens['listener_token']
                # session.agora_talker_uid = tokens['talker_uid']
                # session.agora_listener_uid = tokens['listener_uid']
                # session.agora_tokens_generated_at = timezone.now()
                # session.save()
                # 
                # Don't mark as in_progress yet - wait for WebSocket connection
                # call_package.start_call() will be called by CallConsumer.start_call()
                
                # Send incoming call notification to listener via Channel Layer
                self.send_incoming_call_notification(session, call_package)
                
                # Agora system commented out
                tokens = {}
                user_token = None
                user_uid = None
                
                return Response({
                    'message': 'Call session created. Connect to WebSocket to start call.',
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
                        'call_type': session.call_type,
                        'created_at': session.created_at.isoformat(),
                        'updated_at': session.updated_at.isoformat()
                    },
                    # 'agora': {
                    #     'app_id': tokens['app_id'],
                    #     'channel_name': tokens['channel_name'],
                    #     'token': user_token,
                    #     'uid': user_uid,
                    #     'call_type': call_type,
                    #     'expires_in': tokens['expires_in'],
                    #     'video_config': agora_call_manager.get_call_config(package_type)
                    # },
                    'websocket_url': f'/ws/call/{session.id}/',
                    'websocket_full_url': f'ws://10.10.13.27:8005/ws/call/{session.id}/?token=',
                    'call_package_id': call_package.id,
                    'duration_minutes': call_package.package.duration_minutes
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='initiate')
    def initiate_call(self, request):
        """
        Initiate a call session using a purchased package.
        
        Request body:
        - package_id: ID of the purchased package to use
        """
        package_id = request.data.get('package_id')
        
        if not package_id:
            return Response(
                {'error': 'package_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get the package
            package = CallPackage.objects.select_related('talker', 'listener').get(
                id=package_id,
                talker=request.user,
                status='pending'
            )
        except CallPackage.DoesNotExist:
            return Response(
                {'error': 'Package not found or already used'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if listener is still available
        if not CallSession.is_listener_available(package.listener):
            return Response(
                {'error': f'{package.listener.email} is busy now. Please try again later.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Create call session
                session = CallSession.objects.create(
                    talker=package.talker,
                    listener=package.listener,
                    total_minutes_purchased=package.duration_minutes,
                    initial_package=package,
                    status='connecting'
                )
                
                # Link package to session
                package.call_session = session
                package.save()
                
                return Response({
                    'message': 'Call session created. Connect to WebSocket to start call.',
                    'session': CallSessionSerializer(session).data,
                    'websocket_url': f'/ws/call/{session.id}/'
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @swagger_auto_schema(
        operation_description="Extend call duration by purchasing additional minutes (only talker can do this during an active call)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['call_session_id', 'call_package_id'],
            properties={
                'call_session_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of active call session'),
                'call_package_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of call package to extend minutes from'),
            }
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'session': openapi.Schema(type=openapi.TYPE_OBJECT),
                    'added_minutes': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'new_total_minutes': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'websocket_event': openapi.Schema(type=openapi.TYPE_OBJECT)
                }
            ),
            400: "Invalid request or not authorized",
            404: "Call session or package not found"
        },
        tags=['Call Packages & Calls - Extend Minutes']
    )
    @action(detail=False, methods=['post'], url_path='extend-minutes')
    def extend_minutes(self, request):
        """
        Purchase additional minutes for active call (requires Stripe payment).
        
        Request: {"call_session_id": 5, "package_id": 1}
        
        Returns Stripe Checkout Session URL for payment.
        Minutes are added automatically after successful payment via webhook.
        """
        call_session_id = request.data.get('call_session_id')
        package_id = request.data.get('package_id')
        
        if not call_session_id or not package_id:
            return Response(
                {'error': 'call_session_id and package_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get the active call session
            call_session = CallSession.objects.select_related(
                'talker', 'listener', 'call_package'
            ).get(id=call_session_id, status__in=['connecting', 'active'])
            
        except CallSession.DoesNotExist:
            return Response(
                {'error': 'Call session not found or not active'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Verify user is the talker
        if call_session.talker != request.user:
            return Response(
                {'error': 'Only the talker can extend call minutes'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get the universal package to purchase
        try:
            universal_package = UniversalCallPackage.objects.get(
                id=package_id,
                is_active=True
            )
        except UniversalCallPackage.DoesNotExist:
            return Response(
                {'error': 'Package not found or not active'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Import stripe at function level
        import stripe
        
        try:
            with transaction.atomic():
                # Create extension package (pending payment)
                extend_package = CallPackage.objects.create(
                    talker=request.user,
                    listener=call_session.listener,
                    package=universal_package,
                    total_amount=universal_package.price,
                    app_fee=universal_package.app_fee,
                    listener_amount=universal_package.listener_amount,
                    status='pending',  # Will be confirmed after payment
                    is_extension=True  # Mark as extension - will NOT be counted in listener balance
                )
                
                # Create Stripe Checkout Session
                stripe.api_key = settings.STRIPE_SECRET_KEY
                
                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=[{
                        'price_data': {
                            'currency': 'usd',
                            'unit_amount': int(universal_package.price * 100),
                            'product_data': {
                                'name': f'Extend Call - {universal_package.name}',
                                'description': f'{universal_package.duration_minutes} minutes extension for active call'
                            },
                        },
                        'quantity': 1,
                    }],
                    mode='payment',
                    success_url="http://localhost:5174/dashboard/talker/payment-success-start-call",
                    cancel_url=getattr(settings, 'FRONTEND_URL', 'http://localhost:5173') + f'/call/{call_session_id}',
                    metadata={
                        'call_package_id': extend_package.id,
                        'call_session_id': call_session_id,
                        'is_extension': 'true',
                        'talker_id': request.user.id,
                        'listener_id': call_session.listener.id,
                        'package_id': universal_package.id,
                        'duration_minutes': universal_package.duration_minutes
                    }
                )
                
                # Store checkout session ID
                extend_package.stripe_checkout_session_id = checkout_session.id
                extend_package.save()
                
                return Response({
                    'message': 'Complete payment to extend call minutes',
                    'call_package': CallPackageSerializer(extend_package).data,
                    'payment': {
                        'checkout_session_id': checkout_session.id,
                        'payment_link': checkout_session.url,
                        'amount': float(universal_package.price),
                        'currency': 'usd',
                        'status': 'pending'
                    },
                    'call_session_id': call_session_id,
                    'note': 'Minutes will be added automatically after successful payment'
                }, status=status.HTTP_201_CREATED)
                
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error extending minutes: {str(e)}")
            return Response(
                {'error': f'Payment processing error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"Error extending minutes: {str(e)}")
            return Response(
                {'error': f'Failed to extend minutes: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @swagger_auto_schema(
        operation_description="Listener accepts an incoming call and starts the timer",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['call_session_id'],
            properties={
                'call_session_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of call session to accept')
            }
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'session': openapi.Schema(type=openapi.TYPE_OBJECT),
                    'agora': openapi.Schema(type=openapi.TYPE_OBJECT),
                    'talker_notified': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    'timer_started': openapi.Schema(type=openapi.TYPE_BOOLEAN)
                }
            ),
            400: "Invalid request",
            403: "Not authorized",
            404: "Call session not found"
        },
        tags=['Call Sessions - Listener Accept']
    )
    @action(detail=False, methods=['post'], url_path='accept')
    def accept_call(self, request):
        """
        Listener accepts incoming call and starts the timer.
        
        This endpoint:
        1. Changes call status from 'connecting' to 'active'
        2. Activates the call timer/duration calculation
        3. Notifies the talker via WebSocket that listener has accepted
        4. Returns Agora credentials to listener if needed
        
        Request body:
        {
            "call_session_id": 56
        }
        
        Response includes:
        - Session details (updated status)
        - Agora data (app_id, token, channel, uid, etc.)
        - Confirmation that talker was notified via WebSocket
        """
        call_session_id = request.data.get('call_session_id')
        
        if not call_session_id:
            return Response(
                {'error': 'call_session_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            call_session = CallSession.objects.get(id=call_session_id)
            
            # Verify listener is accepting their own call
            if call_session.listener != request.user:
                return Response(
                    {'error': 'You are not the listener for this call'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Check if call is in connecting status
            if call_session.status not in ['connecting']:
                return Response(
                    {'error': f'Call cannot be accepted. Current status: {call_session.status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update call status to active (timer will start)
            call_session.status = 'active'
            call_session.started_at = timezone.now()
            call_session.save(update_fields=['status', 'started_at', 'updated_at'])
            
            # Activate the initial call package(s)
            for package in call_session.packages.filter(status='pending'):
                package.status = 'active'
                package.activated_at = timezone.now()
                package.save(update_fields=['status', 'activated_at', 'updated_at'])
            
            # # Get Agora data - Agora system commented out
            # agora_data = {
            #     'app_id': getattr(settings, 'AGORA_APP_ID', '4cd28b722093446199a5db6a89ffda4f'),
            #     'channel_name': call_session.agora_channel_name,
            #     'token': call_session.agora_listener_token,
            #     'uid': call_session.agora_listener_uid,
            #     'call_type': call_session.call_type or 'audio',
            #     'expires_in': 7200,  # 2 hours default
            #     'video_config': {
            #         'video_enabled': call_session.call_type == 'video',
            #         'audio_enabled': True,
            #         'video_profile': None,
            #         'call_type': call_session.call_type or 'audio'
            #     }
            # }
            agora_data = {}
            
            # Notify talker via WebSocket that listener has accepted
            self.send_call_accepted_notification(call_session_id, call_session)
            
            logger.info(f"Listener {request.user.id} accepted call session {call_session_id}")
            
            return Response({
                'message': 'Call accepted successfully. Timer started.',
                'accepted': True,
                'session': CallSessionSerializer(call_session).data,
                'agora': agora_data,
                'talker_notified': True,
                'timer_started': True,
                'remaining_minutes': round(call_session.get_remaining_minutes(), 2),
                'started_at': call_session.started_at.isoformat()
            }, status=status.HTTP_200_OK)
        
        except CallSession.DoesNotExist:
            return Response(
                {'error': 'Call session not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error accepting call: {str(e)}")
            return Response(
                {'error': f'Failed to accept call: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def send_call_accepted_notification(self, session_id, call_session):
        """Send notification to talker via call WebSocket that listener has accepted."""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            
            if not channel_layer:
                logger.error("Channel layer is None - Redis might not be configured")
                return
            
            group_name = f'call_{session_id}'
            
            # Send call_accepted event to notify talker
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'call_event',
                    'data': {
                        'type': 'call_accepted',
                        'message': f'{call_session.listener.full_name or call_session.listener.email} has accepted the call',
                        'listener_id': call_session.listener.id,
                        'listener_name': call_session.listener.full_name or call_session.listener.email,
                        'session_id': str(session_id),
                        'timestamp': timezone.now().isoformat(),
                        'status': 'active',
                        'accepted': True,
                        'timer_started': True,
                        'total_minutes': round(call_session.get_total_minutes(), 2),
                        'remaining_minutes': round(call_session.get_remaining_minutes(), 2)
                    }
                }
            )
            
            logger.info(f"✅ Sent call_accepted notification to group {group_name} for session {session_id}")
            logger.info(f"   Listener: {call_session.listener.full_name or call_session.listener.email}")
            logger.info(f"   Remaining: {call_session.get_remaining_minutes()} minutes")
        
        except Exception as e:
            logger.error(f"❌ Failed to send call_accepted notification: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    @swagger_auto_schema(
        operation_description="End an active call session (manually terminate)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['call_session_id'],
            properties={
                'call_session_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of call session to end'),
                'reason': openapi.Schema(type=openapi.TYPE_STRING, description='Reason for ending (optional)')
            }
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'session': openapi.Schema(type=openapi.TYPE_OBJECT),
                    'duration_minutes': openapi.Schema(type=openapi.TYPE_NUMBER),
                    'end_reason': openapi.Schema(type=openapi.TYPE_STRING)
                }
            ),
            400: "Invalid request",
            404: "Call session not found"
        },
        tags=['Call Sessions - End Call']
    )
    @action(detail=False, methods=['post'], url_path='end-call')
    def end_call(self, request):
        """
        Manually end an active call session.
        
        Can be called by either talker or listener.
        Stops the call timer and finalizes the session.
        
        Request body:
        {
            "call_session_id": 1,
            "reason": "User ended call" (optional)
        }
        """
        call_session_id = request.data.get('call_session_id')
        reason = request.data.get('reason', 'User ended call')
        
        if not call_session_id:
            return Response(
                {'error': 'call_session_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            call_session = CallSession.objects.get(id=call_session_id)
            
            # Verify user is participant
            if call_session.talker != request.user and call_session.listener != request.user:
                return Response(
                    {'error': 'You are not a participant in this call'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Check if call is active
            if call_session.status not in ['connecting', 'in_progress', 'active']:
                return Response(
                    {'error': f'Call is already {call_session.status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Calculate duration if call was started
            if call_session.started_at:
                elapsed = (timezone.now() - call_session.started_at).total_seconds() / 60
                duration_minutes = round(elapsed, 2)
                call_session.minutes_used = Decimal(str(duration_minutes))
            else:
                duration_minutes = 0
            
            # Determine who ended the call
            ended_by = 'talker' if call_session.talker == request.user else 'listener'
            ended_by_name = request.user.full_name or request.user.email
            
            # End the call
            call_session.status = 'ended'
            call_session.ended_at = timezone.now()
            call_session.save()
            
            # Broadcast WebSocket event to call participants (to disconnect them)
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            if channel_layer:
                call_group_name = f'call_{call_session_id}'
                
                # Send call_ended event to call WebSocket
                async_to_sync(channel_layer.group_send)(
                    call_group_name,
                    {
                        'type': 'call_ended',
                        'data': {
                            'type': 'call_ended',
                            'message': f'Call ended by {ended_by_name}',
                            'reason': reason,
                            'duration_minutes': duration_minutes,
                            'ended_by': ended_by,
                            'ended_by_user_id': request.user.id,
                            'ended_by_name': ended_by_name,
                            'timestamp': timezone.now().isoformat(),
                            'session_id': str(call_session_id),
                            'status': 'ended'
                        }
                    }
                )
                
                # Send notification to both users via notification WebSocket
                other_user = call_session.listener if ended_by == 'talker' else call_session.talker
                
                # Notify the person who ended the call
                async_to_sync(channel_layer.group_send)(
                    f'user_{request.user.id}_notifications',
                    {
                        'type': 'call_ended_notification',
                        'message': f'You ended the call',
                        'session_id': str(call_session_id),
                        'duration_minutes': duration_minutes,
                        'ended_by': ended_by,
                        'timestamp': timezone.now().isoformat()
                    }
                )
                
                # Notify the other participant
                async_to_sync(channel_layer.group_send)(
                    f'user_{other_user.id}_notifications',
                    {
                        'type': 'call_ended_notification',
                        'message': f'Call ended by {ended_by_name}',
                        'session_id': str(call_session_id),
                        'duration_minutes': duration_minutes,
                        'ended_by': ended_by,
                        'ended_by_name': ended_by_name,
                        'timestamp': timezone.now().isoformat()
                    }
                )
            
            logger.info(f"Call {call_session_id} ended by {request.user.email} ({ended_by}): {reason}")
            
            return Response({
                'message': f'Call ended successfully',
                'session': CallSessionSerializer(call_session).data,
                'duration_minutes': duration_minutes,
                'end_reason': reason,
                'ended_by': ended_by,
                'websocket_notified': True
            }, status=status.HTTP_200_OK)
            
        except CallSession.DoesNotExist:
            return Response(
                {'error': 'Call session not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error ending call: {str(e)}")
            return Response(
                {'error': f'Failed to end call: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def send_incoming_call_notification(self, session, call_package):
        """Send incoming call notification to listener via Channel Layer."""
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        from talker.models import TalkerProfile
        
        try:
            channel_layer = get_channel_layer()
            notification_group = f'user_{session.listener.id}_notifications'
            
            # Get talker's profile image URL
            talker_image_url = None
            try:
                talker_profile = TalkerProfile.objects.get(user=session.talker)
                if talker_profile.profile_image:
                    talker_image_url = f'http://10.10.13.27:8005{talker_profile.profile_image.url}'
            except TalkerProfile.DoesNotExist:
                pass
            
            # Send notification via Channel Layer
            async_to_sync(channel_layer.group_send)(
                notification_group,
                {
                    'type': 'incoming_call',
                    'session_id': session.id,
                    'call_package_id': call_package.id,
                    'talker_id': session.talker.id,
                    'talker_email': session.talker.email,
                    'talker_name': session.talker.get_full_name(),
                    'talker_image': talker_image_url,
                    'call_type': call_package.package.package_type,
                    'total_minutes': call_package.package.duration_minutes,
                    'created_at': session.created_at.isoformat(),
                }
            )
            logger.info(f"Incoming call notification sent to listener {session.listener.id} for session {session.id}")

        except Exception as e:
            logger.error(f"Failed to send incoming call notification: {str(e)}")


class CallRejectionViewSet(viewsets.ModelViewSet):
    """ViewSet for call rejections and refunds."""
    
    serializer_class = CallRejectionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Return rejections for current listener or rejected calls for current talker."""
        user = self.request.user
        if user.user_type == 'listener':
            return CallRejection.objects.filter(listener=user)
        elif user.user_type == 'talker':
            return CallRejection.objects.filter(talker=user)
        return CallRejection.objects.none()
    
    @swagger_auto_schema(
        operation_description="Reject a call and issue refund to talker",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'call_package_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='Call package ID to reject'),
                'reason': openapi.Schema(type=openapi.TYPE_STRING, description='Rejection reason'),
                'notes': openapi.Schema(type=openapi.TYPE_STRING, description='Optional notes'),
            },
            required=['call_package_id', 'reason']
        )
    )
    @action(detail=False, methods=['post'])
    def reject_call(self, request):
        """Reject a call and process refund."""
        call_package_id = request.data.get('call_package_id')
        reason = request.data.get('reason')
        notes = request.data.get('notes', '')
        
        if not call_package_id or not reason:
            return Response(
                {'error': 'call_package_id and reason are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            call_package = CallPackage.objects.get(id=call_package_id)
            
            # Verify listener is rejecting their own call
            if call_package.listener != request.user:
                return Response(
                    {'error': 'You can only reject calls assigned to you'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Check if already rejected
            if hasattr(call_package, 'rejection') and call_package.rejection:
                return Response(
                    {'error': 'This call has already been rejected'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create rejection record
            rejection = CallRejection.objects.create(
                call_package=call_package,
                listener=request.user,
                talker=call_package.talker,
                reason=reason,
                notes=notes
            )
            
            # Process refund to talker
            refund_amount = call_package.total_amount
            
            if call_package.stripe_charge_id:
                try:
                    # Refund via Stripe
                    refund = stripe.Refund.create(
                        charge=call_package.stripe_charge_id,
                        amount=int(refund_amount * 100)  # Convert to cents
                    )
                    
                    rejection.refund_issued = True
                    rejection.refund_amount = refund_amount
                    rejection.refund_stripe_id = refund.id
                    rejection.refund_date = timezone.now()
                    rejection.save(update_fields=['refund_issued', 'refund_amount', 'refund_stripe_id', 'refund_date'])
                    
                    # Update call package status
                    call_package.status = 'refunded'
                    call_package.save(update_fields=['status', 'updated_at'])
                    
                    logger.info(f"Refund processed for call package {call_package_id}: Stripe ID {refund.id}")
                    
                except stripe.error.StripeError as e:
                    logger.error(f"Stripe refund error for call package {call_package_id}: {str(e)}")
                    return Response(
                        {'error': f'Refund failed: {str(e)}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Cancel listener's payout for this call
            ListenerPayout.objects.filter(call_package=call_package).update(
                status='cancelled',
                notes='Cancelled due to call rejection'
            )
            
            return Response({
                'message': 'Call rejected and refund processed',
                'rejection': CallRejectionSerializer(rejection).data
            }, status=status.HTTP_201_CREATED)
        
        except CallPackage.DoesNotExist:
            return Response(
                {'error': 'Call package not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error rejecting call: {str(e)}")
            return Response(
                {'error': f'Failed to reject call: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @swagger_auto_schema(
        operation_description="List call rejections"
    )
    def list(self, request):
        """List all rejections for current user."""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="List calls rejected BY me (for listeners only)",
        responses={
            200: CallRejectionSerializer(many=True)
        },
        tags=['Call Rejections']
    )
    @action(detail=False, methods=['get'], url_path='rejected-by-me')
    def rejected_by_me(self, request):
        """List calls I have rejected (for listeners)."""
        if request.user.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can view rejected calls'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        rejections = CallRejection.objects.filter(
            listener=request.user
        ).select_related('call_package', 'talker').order_by('-rejected_at')
        
        serializer = CallRejectionSerializer(rejections, many=True)
        return Response({
            'count': rejections.count(),
            'rejections': serializer.data
        })
    
    @swagger_auto_schema(
        operation_description="List calls rejected TO me - my calls that were rejected (for talkers only)",
        responses={
            200: CallRejectionSerializer(many=True)
        },
        tags=['Call Rejections']
    )
    @action(detail=False, methods=['get'], url_path='rejected-to-me')
    def rejected_to_me(self, request):
        """List my calls that were rejected by listeners (for talkers)."""
        if request.user.user_type != 'talker':
            return Response(
                {'error': 'Only talkers can view their rejected calls'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        rejections = CallRejection.objects.filter(
            talker=request.user
        ).select_related('call_package', 'listener').order_by('-rejected_at')
        
        serializer = CallRejectionSerializer(rejections, many=True)
        return Response({
            'count': rejections.count(),
            'rejections': serializer.data,
            'total_refunded': str(sum(r.refund_amount for r in rejections if r.refund_issued))
        })
    
    @swagger_auto_schema(
        operation_description="Process refund for a rejected call (talker requests refund)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'call_rejection_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of the call rejection'),
                'reason': openapi.Schema(type=openapi.TYPE_STRING, description='Reason for requesting refund'),
            },
            required=['call_rejection_id']
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'refund': openapi.Schema(type=openapi.TYPE_OBJECT),
                    'amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                }
            ),
            400: "Invalid request",
            404: "Rejection not found"
        },
        tags=['Call Rejections - Refund']
    )
    @action(detail=False, methods=['post'], url_path='process-refund')
    def process_refund(self, request):
        """
        Process refund for a call that was rejected by listener.
        Only talker can request refund for their own rejected calls.
        
        Request body:
        {
            "call_rejection_id": 1,
            "reason": "Listener rejected my call"
        }
        """
        call_rejection_id = request.data.get('call_rejection_id')
        reason = request.data.get('reason', 'Call was rejected by listener')
        
        if not call_rejection_id:
            return Response(
                {'error': 'call_rejection_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            rejection = CallRejection.objects.select_related('call_package', 'talker').get(
                id=call_rejection_id
            )
            
            # Verify talker is requesting refund for their own call
            if rejection.talker != request.user:
                return Response(
                    {'error': 'You can only request refund for your own rejected calls'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Check if refund already issued
            if rejection.refund_issued:
                return Response(
                    {'error': 'Refund has already been issued for this rejection',
                     'refund_id': rejection.refund_stripe_id,
                     'amount': str(rejection.refund_amount)},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Process refund using call_payments helper
            from .call_payments import refund_call_package
            
            call_package = rejection.call_package
            refund_result = refund_call_package(call_package, reason=reason)
            
            if refund_result['status'] == 'success':
                # Update rejection record
                rejection.refund_issued = True
                rejection.refund_amount = call_package.total_amount
                rejection.refund_date = timezone.now()
                rejection.save(update_fields=['refund_issued', 'refund_amount', 'refund_date'])
                
                logger.info(f"✓ Refund processed for talker {request.user.email}: ${call_package.total_amount} (Rejection ID: {call_rejection_id})")
                
                return Response({
                    'message': f'Refund of ${call_package.total_amount} processed successfully',
                    'refund': refund_result,
                    'amount': str(call_package.total_amount),
                    'rejection_id': call_rejection_id,
                }, status=status.HTTP_200_OK)
            else:
                logger.error(f"Refund failed for talker {request.user.email}: {refund_result['message']}")
                return Response(
                    {'error': refund_result['message']},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        except CallRejection.DoesNotExist:
            return Response(
                {'error': 'Call rejection not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error processing refund: {str(e)}")
            return Response(
                {'error': f'Failed to process refund: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ListenerPayoutViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listener payouts - read-only with custom actions for payout management."""
    
    serializer_class = CallPayoutSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Return payouts for current listener only."""
        if self.request.user.user_type == 'listener':
            return ListenerPayout.objects.filter(listener=self.request.user)
        return ListenerPayout.objects.none()
    
    @swagger_auto_schema(
        operation_description="Get listener's payout balance and summary"
    )
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get payouts and balance summary for current listener."""
        queryset = self.get_queryset()
        serializer = CallPayoutListSerializer(queryset, many=True)
        
        # Calculate balance
        balance = ListenerPayout.get_listener_balance(request.user)
        
        return Response({
            'payouts': serializer.data,
            'balance': str(balance),
            'total_earned': str(
                ListenerPayout.objects.filter(
                    listener=request.user,
                    status__in=['earned', 'pending', 'processing', 'completed']
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            )
        })
    
    @swagger_auto_schema(
        operation_description="Get listener's payout balance and summary"
    )
    @action(detail=False, methods=['get'])
    def balance(self, request):
        """Get listener's total payout balance."""
        from django.db.models import Sum
        
        listener = request.user
        if listener.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can view payout balance'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        payouts_qs = ListenerPayout.objects.filter(listener=listener)
        
        # Calculate various totals
        # Payouts waiting for call to end (payment confirmed, call in progress)
        waiting_for_call = payouts_qs.filter(status='processing').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # Payouts earned and ready to withdraw
        earned_ready = payouts_qs.filter(status='earned').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # Payouts in pending state (requested withdrawal)
        pending = payouts_qs.filter(status='pending').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # Completed payouts
        completed = payouts_qs.filter(status='completed').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # Cancelled payouts
        cancelled = payouts_qs.filter(status='cancelled').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        return Response({
            'waiting_for_call_to_end': str(waiting_for_call),
            'available_balance': str(earned_ready),
            'pending_withdrawal': str(pending),
            'total_completed': str(completed),
            'total_cancelled': str(cancelled),
            'total_earned': str(waiting_for_call + earned_ready + pending + completed),
            'payout_count': payouts_qs.filter(status='completed').count()
        })
    
    @swagger_auto_schema(
        operation_description="Get listener's call history - completed, rejected, and upcoming calls"
    )
    @action(detail=False, methods=['get'])
    def call_history(self, request):
        """Get listener's call history with completed, rejected, and upcoming calls."""
        listener = request.user
        if listener.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can view call history'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Completed calls (call session ended)
        completed_sessions = CallSession.objects.filter(
            listener=listener,
            status='ended'
        ).select_related('talker', 'call_package', 'initial_package').order_by('-ended_at')[:50]
        
        completed_calls = []
        for session in completed_sessions:
            pkg = session.call_package or session.initial_package
            completed_calls.append({
                'session_id': session.id,
                'talker_email': session.talker.email,
                'talker_name': getattr(session.talker, 'full_name', session.talker.email),
                'duration_minutes': float(session.minutes_used) if session.minutes_used else 0,
                'total_minutes_purchased': session.total_minutes_purchased,
                'started_at': session.started_at.isoformat() if session.started_at else None,
                'ended_at': session.ended_at.isoformat() if session.ended_at else None,
                'earnings': str(pkg.listener_amount) if pkg else '0.00',
                'status': 'completed'
            })
        
        # Rejected calls
        rejected = CallRejection.objects.filter(
            listener=listener
        ).select_related('call_package', 'talker').order_by('-rejected_at')[:50]
        
        rejected_calls = []
        for rejection in rejected:
            rejected_calls.append({
                'rejection_id': rejection.id,
                'call_package_id': rejection.call_package.id if rejection.call_package else None,
                'talker_email': rejection.talker.email,
                'talker_name': getattr(rejection.talker, 'full_name', rejection.talker.email),
                'reason': rejection.reason,
                'notes': rejection.notes,
                'rejected_at': rejection.rejected_at.isoformat(),
                'refund_issued': rejection.refund_issued,
                'refund_amount': str(rejection.refund_amount),
                'status': 'rejected'
            })
        
        # Upcoming/pending calls (confirmed packages not yet started)
        upcoming_packages = CallPackage.objects.filter(
            listener=listener,
            status__in=['confirmed', 'pending']
        ).select_related('talker', 'package').order_by('-created_at')[:50]
        
        upcoming_calls = []
        for pkg in upcoming_packages:
            upcoming_calls.append({
                'package_id': pkg.id,
                'talker_email': pkg.talker.email,
                'talker_name': getattr(pkg.talker, 'full_name', pkg.talker.email),
                'package_name': pkg.package.name if pkg.package else 'Unknown',
                'duration_minutes': pkg.package.duration_minutes if pkg.package else 0,
                'amount': str(pkg.total_amount),
                'listener_earnings': str(pkg.listener_amount),
                'purchased_at': pkg.purchased_at.isoformat() if pkg.purchased_at else None,
                'status': pkg.status
            })
        
        # Active calls
        active_sessions = CallSession.objects.filter(
            listener=listener,
            status__in=['connecting', 'active']
        ).select_related('talker', 'call_package').order_by('-started_at')
        
        active_calls = []
        for session in active_sessions:
            pkg = session.call_package or session.initial_package
            active_calls.append({
                'session_id': session.id,
                'talker_email': session.talker.email,
                'talker_name': getattr(session.talker, 'full_name', session.talker.email),
                'minutes_remaining': session.get_remaining_minutes(),
                'total_minutes_purchased': session.total_minutes_purchased,
                'started_at': session.started_at.isoformat() if session.started_at else None,
                'status': session.status
            })
        
        return Response({
            'completed_calls': completed_calls,
            'rejected_calls': rejected_calls,
            'upcoming_calls': upcoming_calls,
            'active_calls': active_calls,
            'summary': {
                'total_completed': len(completed_calls),
                'total_rejected': len(rejected_calls),
                'total_upcoming': len(upcoming_calls),
                'total_active': len(active_calls)
            }
        })
    
    @swagger_auto_schema(
        operation_description="Request payout - if stripe_account_id provided, instant transfer. Otherwise, generates Stripe link.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'amount': openapi.Schema(type=openapi.TYPE_STRING, description='Amount to payout'),
                'stripe_account_id': openapi.Schema(type=openapi.TYPE_STRING, description='Optional: Stripe Connected Account ID for instant transfer'),
            },
            required=['amount']
        )
    )
    @action(detail=False, methods=['post'], url_path='request-payout')
    def request_payout(self, request):
        """Request payout - creates Stripe link if no stripe_account_id provided."""
        from django.db.models import Sum
        
        listener = request.user
        if listener.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can request payouts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        amount = request.data.get('amount')
        stripe_account_id = request.data.get('stripe_account_id')
        
        if not amount:
            return Response(
                {'error': 'amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # If no stripe_account_id, redirect to create payout link
        if not stripe_account_id:
            return self.create_payout_link(request)
        
        try:
            amount = Decimal(str(amount))
        except:
            return Response(
                {'error': 'Invalid amount'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get available balance
        available = ListenerPayout.objects.filter(
            listener=listener,
            status='earned'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        if amount > available:
            return Response(
                {'error': f'Requested amount exceeds available balance. Available: ${available}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if amount <= 0:
            return Response(
                {'error': 'Amount must be greater than 0'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Get payouts to fulfill this request
                payouts_to_process = ListenerPayout.objects.filter(
                    listener=listener,
                    status='earned'
                ).order_by('earned_at')
                
                remaining = amount
                processed_payouts = []
                
                for payout in payouts_to_process:
                    if remaining <= 0:
                        break
                    
                    if payout.amount <= remaining:
                        processed_payouts.append(payout)
                        remaining -= payout.amount
                    else:
                        # Partial payout - would need to split, for now process full
                        processed_payouts.append(payout)
                        remaining = 0
                
                # Process Stripe payout
                amount_cents = int(amount * 100)
                
                try:
                    # Create Stripe Transfer to Connected Account
                    transfer = stripe.Transfer.create(
                        amount=amount_cents,
                        currency='usd',
                        destination=stripe_account_id,
                        description=f'Payout to listener {listener.email}',
                        metadata={
                            'listener_id': listener.id,
                            'listener_email': listener.email,
                            'payout_count': len(processed_payouts)
                        }
                    )
                    
                    # Update payouts status to completed
                    for payout in processed_payouts:
                        payout.status = 'completed'
                        payout.payout_requested_at = timezone.now()
                        payout.payout_completed_at = timezone.now()
                        payout.stripe_payout_id = transfer.id
                        payout.save(update_fields=[
                            'status', 'payout_requested_at', 'payout_completed_at', 
                            'stripe_payout_id', 'updated_at'
                        ])
                    
                    logger.info(f"✓ Payout processed for {listener.email}: ${amount}, Stripe Transfer ID: {transfer.id}")
                    
                    return Response({
                        'message': f'Payout of ${amount} processed successfully',
                        'payouts_count': len(processed_payouts),
                        'status': 'completed',
                        'stripe_transfer_id': transfer.id,
                        'amount': str(amount),
                        'destination_account': stripe_account_id
                    }, status=status.HTTP_200_OK)
                
                except stripe.error.StripeError as e:
                    logger.error(f"Stripe payout error: {str(e)}")
                    return Response(
                        {'error': f'Stripe error: {str(e)}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
        
        except Exception as e:
            logger.error(f"Error requesting payout: {str(e)}")
            return Response(
                {'error': f'Failed to request payout: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @swagger_auto_schema(
        operation_description="Request payout with bank account or debit card details",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'amount': openapi.Schema(type=openapi.TYPE_STRING, description='Amount to payout'),
                'bank_account_number': openapi.Schema(type=openapi.TYPE_STRING, description='Bank account number'),
                'routing_number': openapi.Schema(type=openapi.TYPE_STRING, description='Bank routing number'),
                'account_holder_name': openapi.Schema(type=openapi.TYPE_STRING, description='Account holder name'),
                'account_holder_type': openapi.Schema(type=openapi.TYPE_STRING, description='individual or company', enum=['individual', 'company']),
            },
            required=['amount', 'bank_account_number', 'routing_number', 'account_holder_name']
        )
    )
    @action(detail=False, methods=['post'], url_path='request-payout-simple')
    def request_payout_simple(self, request):
        """Request payout with bank account details - no Stripe account needed."""
        from django.db.models import Sum
        
        listener = request.user
        if listener.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can request payouts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        amount = request.data.get('amount')
        bank_account_number = request.data.get('bank_account_number')
        routing_number = request.data.get('routing_number')
        account_holder_name = request.data.get('account_holder_name')
        account_holder_type = request.data.get('account_holder_type', 'individual')
        
        # Validation
        if not all([amount, bank_account_number, routing_number, account_holder_name]):
            return Response(
                {'error': 'amount, bank_account_number, routing_number, and account_holder_name are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            amount = Decimal(str(amount))
        except:
            return Response(
                {'error': 'Invalid amount'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get available balance
        available = ListenerPayout.objects.filter(
            listener=listener,
            status='earned'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        if amount > available:
            return Response(
                {'error': f'Requested amount exceeds available balance. Available: ${available}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if amount <= 0:
            return Response(
                {'error': 'Amount must be greater than 0'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Get payouts to fulfill this request
                payouts_to_process = ListenerPayout.objects.filter(
                    listener=listener,
                    status='earned'
                ).order_by('earned_at')
                
                remaining = amount
                processed_payouts = []
                
                for payout in payouts_to_process:
                    if remaining <= 0:
                        break
                    
                    if payout.amount <= remaining:
                        processed_payouts.append(payout)
                        remaining -= payout.amount
                    else:
                        processed_payouts.append(payout)
                        remaining = 0
                
                # Create or get Stripe customer for listener
                try:
                    # Create Stripe Customer
                    customer = stripe.Customer.create(
                        email=listener.email,
                        name=account_holder_name,
                        description=f'Listener payout customer for {listener.email}',
                        metadata={
                            'listener_id': listener.id,
                            'user_type': 'listener'
                        }
                    )
                    
                    # Create Bank Account Token
                    bank_token = stripe.Token.create(
                        bank_account={
                            'country': 'US',
                            'currency': 'usd',
                            'account_holder_name': account_holder_name,
                            'account_holder_type': account_holder_type,
                            'routing_number': routing_number,
                            'account_number': bank_account_number,
                        }
                    )
                    
                    # Attach bank account to customer
                    bank_account = customer.sources.create(source=bank_token.id)
                    
                    # Verify bank account (in production, this would require micro-deposits)
                    # For now, we'll mark as verified in test mode
                    
                    # Create payout (ACH transfer)
                    amount_cents = int(amount * 100)
                    
                    # Use Stripe Payout to bank account
                    payout_obj = stripe.Payout.create(
                        amount=amount_cents,
                        currency='usd',
                        destination=bank_account.id,
                        description=f'Payout to listener {listener.email}',
                        metadata={
                            'listener_id': listener.id,
                            'listener_email': listener.email,
                            'payout_count': len(processed_payouts)
                        }
                    )
                    
                    # Update payouts status
                    for payout in processed_payouts:
                        payout.status = 'completed'
                        payout.payout_requested_at = timezone.now()
                        payout.payout_completed_at = timezone.now()
                        payout.stripe_payout_id = payout_obj.id
                        payout.notes = f'Bank transfer to {bank_account_number[-4:]}'
                        payout.save(update_fields=[
                            'status', 'payout_requested_at', 'payout_completed_at', 
                            'stripe_payout_id', 'notes', 'updated_at'
                        ])
                    
                    logger.info(f"✓ Bank payout processed for {listener.email}: ${amount}, Stripe Payout ID: {payout_obj.id}")
                    
                    return Response({
                        'message': f'Payout of ${amount} initiated successfully',
                        'payouts_count': len(processed_payouts),
                        'status': 'completed',
                        'stripe_payout_id': payout_obj.id,
                        'amount': str(amount),
                        'destination': f'Bank account ending in {bank_account_number[-4:]}',
                        'estimated_arrival': '3-5 business days'
                    }, status=status.HTTP_200_OK)
                
                except stripe.error.StripeError as e:
                    logger.error(f"Stripe bank payout error: {str(e)}")
                    return Response(
                        {'error': f'Stripe error: {str(e)}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
        
        except Exception as e:
            logger.error(f"Error processing bank payout: {str(e)}")
            return Response(
                {'error': f'Failed to process payout: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @swagger_auto_schema(
        operation_description="Process payout via Stripe",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'stripe_account_id': openapi.Schema(type=openapi.TYPE_STRING, description='Stripe account ID for payout'),
            },
            required=['stripe_account_id']
        )
    )
    @action(detail=False, methods=['post'])
    def process_payout(self, request):
        """Process pending payouts via Stripe."""
        from django.db.models import Sum
        
        listener = request.user
        if listener.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can process payouts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        stripe_account_id = request.data.get('stripe_account_id')
        if not stripe_account_id:
            return Response(
                {'error': 'stripe_account_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get all pending payouts for this listener
            pending_payouts = ListenerPayout.objects.filter(
                listener=listener,
                status='pending'
            )
            
            if not pending_payouts.exists():
                return Response(
                    {'error': 'No pending payouts to process'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            total_amount = pending_payouts.aggregate(total=Sum('amount'))['total']
            amount_cents = int(total_amount * 100)
            
            # Create Stripe payout
            payout = stripe.Payout.create(
                amount=amount_cents,
                currency='usd',
                destination=stripe_account_id,
                method='instant'
            )
            
            # Update payouts status
            pending_payouts.update(
                status='processing',
                stripe_payout_id=payout.id,
                updated_at=timezone.now()
            )
            
            logger.info(f"Payout processed for {listener.email}: ${total_amount}, Stripe ID: {payout.id}")
            
            return Response({
                'message': f'Payout of ${total_amount} processed',
                'stripe_payout_id': payout.id,
                'status': payout.status,
                'amount': str(total_amount)
            }, status=status.HTTP_200_OK)
        
        except stripe.error.StripeError as e:
            logger.error(f"Stripe payout error: {str(e)}")
            return Response(
                {'error': f'Stripe error: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error processing payout: {str(e)}")
            return Response(
                {'error': f'Failed to process payout: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @swagger_auto_schema(
        operation_description="Generate Stripe payout link - listener enters card details and receives money",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'amount': openapi.Schema(type=openapi.TYPE_STRING, description='Amount to payout'),
            },
            required=['amount']
        )
    )
    @action(detail=False, methods=['post'], url_path='create-payout-link')
    def create_payout_link(self, request):
        """Generate Stripe link for listener to enter card details and receive payout."""
        from django.db.models import Sum
        
        listener = request.user
        if listener.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can request payouts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        amount = request.data.get('amount')
        
        if not amount:
            return Response(
                {'error': 'amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            amount = Decimal(str(amount))
        except:
            return Response(
                {'error': 'Invalid amount'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get available balance
        available = ListenerPayout.objects.filter(
            listener=listener,
            status='earned'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        if amount > available:
            return Response(
                {'error': f'Requested amount exceeds available balance. Available: ${available}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if amount <= 0:
            return Response(
                {'error': 'Amount must be greater than 0'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            
            # Create Stripe customer
            customer = stripe.Customer.create(
                email=listener.email,
                name=listener.email,
                metadata={
                    'listener_id': listener.id,
                    'payout_amount': str(amount)
                }
            )
            
            # Create Checkout Session for payment method collection
            checkout_session = stripe.checkout.Session.create(
                customer=customer.id,
                mode='setup',
                payment_method_types=['card'],
                success_url=f'{frontend_url}/payout-success?session_id={{CHECKOUT_SESSION_ID}}',
                cancel_url=f'{frontend_url}/payout-cancelled',
                metadata={
                    'listener_id': listener.id,
                    'payout_amount': str(amount),
                    'type': 'payout_collection'
                }
            )
            
            # Mark payouts as pending - only up to the requested amount
            with transaction.atomic():
                payouts_to_process = ListenerPayout.objects.filter(
                    listener=listener,
                    status='earned'
                ).order_by('earned_at')
                
                remaining = amount
                processed_amount = Decimal('0.00')
                
                for payout in payouts_to_process:
                    if remaining <= 0:
                        break
                    
                    if payout.amount <= remaining:
                        # Full payout goes to pending
                        payout.status = 'pending'
                        payout.payout_requested_at = timezone.now()
                        payout.stripe_payout_id = checkout_session.id
                        payout.notes = f'Awaiting card details from Stripe link'
                        payout.save(update_fields=['status', 'payout_requested_at', 'stripe_payout_id', 'notes', 'updated_at'])
                        remaining -= payout.amount
                        processed_amount += payout.amount
                    else:
                        # Need to split this payout - only take what we need
                        # Create a new payout record for the remaining earned amount
                        leftover_amount = payout.amount - remaining
                        
                        # Create new record for leftover (stays as earned)
                        ListenerPayout.objects.create(
                            listener=listener,
                            call_package=payout.call_package,
                            amount=leftover_amount,
                            status='earned',
                            earned_at=payout.earned_at,
                            notes=f'Split from payout #{payout.id}'
                        )
                        
                        # Update original payout with partial amount
                        payout.amount = remaining
                        payout.status = 'pending'
                        payout.payout_requested_at = timezone.now()
                        payout.stripe_payout_id = checkout_session.id
                        payout.notes = f'Partial withdrawal - awaiting card details'
                        payout.save(update_fields=['amount', 'status', 'payout_requested_at', 'stripe_payout_id', 'notes', 'updated_at'])
                        
                        processed_amount += remaining
                        remaining = 0
            
            logger.info(f"✓ Payout link created for {listener.email}: ${amount}, Session: {checkout_session.id}")
            
            return Response({
                'message': f'Payout link created for ${amount}',
                'amount': str(amount),
                'stripe_link': checkout_session.url,
                'session_id': checkout_session.id,
                'instructions': 'Click the link and enter your card details. Money will be sent instantly.',
                'status': 'pending'
            }, status=status.HTTP_200_OK)
        
        except stripe.error.StripeError as e:
            logger.error(f"Stripe payout link error: {str(e)}")
            return Response(
                {'error': f'Stripe error: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating payout link: {str(e)}")
            return Response(
                {'error': f'Failed to create payout link: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
