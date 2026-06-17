from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from decimal import Decimal, InvalidOperation
from .models import ListenerProfile, ListenerRating, ListenerBalance, ListenerBlockedTalker, ListenerBookingRefund
from .serializers import (ListenerProfileSerializer, ListenerListSerializer, ListenerRatingSerializer,
                         BlockTalkerSerializer, UnblockTalkerSerializer, BlockedTalkerListSerializer,
                         ListenerCallAttemptSerializer, ListenerCallAttemptDetailSerializer,
                         ListenerBalanceSerializer, ListenerTransactionSerializer,
                         RefundBookingSerializer)
from bokking.booking_payments import process_stripe_refund, reverse_booking_listener_transfer


class IsListenerUser(IsAuthenticated):
    """Custom permission to ensure user has listener role."""
    
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.user_type == 'listener'


class IsTalkerUser(IsAuthenticated):
    """Custom permission to ensure user has talker role."""
    
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.user_type == 'talker'


class ListenerProfileViewSet(viewsets.ModelViewSet):
    """ViewSet for listener profile management."""
    queryset = ListenerProfile.objects.all()
    serializer_class = ListenerProfileSerializer
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_permissions(self):
        """
        Return the appropriate permission based on the action.
        - list, retrieve: AllowAny
        - my_profile, create, update, partial_update, destroy: IsListenerUser
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsListenerUser]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        if self.action == 'list':
            return ListenerListSerializer
        return ListenerProfileSerializer

    def get_serializer_class(self):
        if self.action in ['list', 'available_listeners', 'all_listeners']:
            return ListenerListSerializer
        elif self.action == 'rate_listener':
            return ListenerRatingSerializer
        return ListenerProfileSerializer

    def get_object(self):
        """Get the listener profile by user_id or profile id."""
        pk = self.kwargs.get('pk')
        
        # For my_profile action, get current user's profile
        if self.action == 'my_profile':
            return get_object_or_404(ListenerProfile, user=self.request.user)
        
        # For detail actions (retrieve, update, destroy), try to get by user_id first
        # This allows endpoints like /api/listener/profiles/<user_id>/ to work
        if pk:
            try:
                # Try to get by user_id (user's ID)
                return get_object_or_404(ListenerProfile, user_id=int(pk))
            except (ValueError, ListenerProfile.DoesNotExist):
                # If not found by user_id, try by ListenerProfile.id
                return super().get_object()
        
        return super().get_object()
    
    def get_queryset(self):
        """Filter queryset based on action."""
        if self.action == 'available_listeners':
            return ListenerProfile.objects.filter(is_available=True)
        return ListenerProfile.objects.all()

    def _sync_user_full_name(self, listener_profile):
        """Keep auth profile full_name in sync with listener profile names."""
        combined = listener_profile.get_full_name()

        if listener_profile.user.full_name != combined:
            listener_profile.user.full_name = combined
            listener_profile.user.save(update_fields=['full_name', 'updated_at'])

    def perform_update(self, serializer):
        """Override default update to ensure auth profile name stays synced."""
        listener_profile = serializer.save()
        self._sync_user_full_name(listener_profile)

    def destroy(self, request, *args, **kwargs):
        """Delete listener profile and deactivate the associated user account.
        
        When a listener profile is deleted, the user account is marked as inactive
        so they cannot login again.
        """
        listener_profile = self.get_object()
        user = listener_profile.user
        
        # Delete the profile
        listener_profile.delete()
        
        # Deactivate the user account
        user.is_active = False
        user.save()
        
        return Response(
            {
                'message': f'Listener profile deleted and account deactivated',
                'user_id': user.id,
                'email': user.email
            },
            status=status.HTTP_204_NO_CONTENT
        )

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def available(self, request):
        """Get all available listeners."""
        listeners = ListenerProfile.objects.filter(is_available=True).order_by('-average_rating')
        serializer = ListenerListSerializer(listeners, many=True, context={'request': request})
        return Response({
            'count': listeners.count(),
            'results': serializer.data
        })

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def details(self, request, pk=None):
        """Get detailed information about a specific listener (public endpoint for talkers)."""
        try:
            listener = ListenerProfile.objects.get(user_id=pk)
        except ListenerProfile.DoesNotExist:
            return Response(
                {'error': f'Listener with ID {pk} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ListenerProfileSerializer(listener, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get', 'put', 'patch'], permission_classes=[IsListenerUser], parser_classes=[JSONParser, MultiPartParser, FormParser])
    def my_profile(self, request):
        """Get or update the authenticated listener user's profile."""
        try:
            listener_profile = ListenerProfile.objects.get(user=request.user)
        except ListenerProfile.DoesNotExist:
            return Response(
                {'error': 'Listener profile not found. Please ensure you are registered as a listener.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'GET':
            serializer = self.get_serializer(listener_profile, context={'request': request})
            return Response(serializer.data)

        elif request.method in ['PUT', 'PATCH']:
            payload = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
            invalid_tokens = {'undefined', 'null', 'none'}

            language_value = str(payload.get('language', '')).strip().lower()
            if language_value in invalid_tokens:
                language_value = ''

            # Normalize direct first_name/last_name values from frontend placeholders.
            for key in ['first_name', 'last_name']:
                if key in payload:
                    value = str(payload.get(key, '')).strip()
                    if value.lower() in invalid_tokens:
                        payload[key] = ''

            # Accept full_name as input and split into first_name/last_name.
            full_name_input = str(payload.get('full_name', '')).strip()
            if full_name_input.lower() in invalid_tokens:
                full_name_input = ''

            if full_name_input:
                parts = full_name_input.split(None, 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ''

                if first_name.lower() in invalid_tokens:
                    first_name = ''
                if last_name.lower() in invalid_tokens:
                    last_name = ''

                if not str(payload.get('first_name', '')).strip():
                    payload['first_name'] = first_name
                if not str(payload.get('last_name', '')).strip():
                    payload['last_name'] = last_name

            # Serializer exposes full_name as read-only output, so drop incoming key.
            if 'full_name' in payload:
                payload.pop('full_name')

            # Language is stored on the User model and mirrored to ListenerProfile.languages.
            if 'language' in payload:
                payload.pop('language')

            serializer = self.get_serializer(listener_profile, data=payload, partial=True, context={'request': request})
            if serializer.is_valid():
                serializer.save()

                if language_value:
                    if request.user.language != language_value:
                        request.user.language = language_value
                        request.user.save(update_fields=['language'])

                    existing_languages = list(listener_profile.languages or [])
                    if language_value not in existing_languages:
                        existing_languages = [language_value] + existing_languages
                    listener_profile.languages = existing_languages or [language_value]
                    listener_profile.save(update_fields=['languages'])

                self._sync_user_full_name(listener_profile)
                # Refresh to get updated image
                request.user.refresh_from_db()
                listener_profile.refresh_from_db()
                response_data = serializer.data
                # Ensure profile_image_url is included
                if listener_profile.profile_image:
                    response_data['profile_image_url'] = request.build_absolute_uri(listener_profile.profile_image.url)
                return Response(response_data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[IsListenerUser])
    def block_talker(self, request):
        """Block a talker.
        
        Endpoint: POST /api/listener/profiles/block_talker/
        Request body: { "talker_id": 5 }
        
        When a listener blocks a talker, that talker will not see this listener
        in their available_listeners or all_listeners endpoints.
        """
        serializer = BlockTalkerSerializer(data=request.data)
        if serializer.is_valid():
            talker_id = serializer.validated_data['talker_id']
            
            try:
                blocked, created = ListenerBlockedTalker.objects.get_or_create(
                    listener=request.user,
                    talker_id=talker_id
                )
                
                if created:
                    return Response(
                        {
                            'message': f'Talker with ID {talker_id} has been blocked',
                            'talker_id': talker_id,
                            'blocked_at': blocked.blocked_at
                        },
                        status=status.HTTP_201_CREATED
                    )
                else:
                    return Response(
                        {
                            'message': f'Talker with ID {talker_id} is already blocked',
                            'talker_id': talker_id,
                            'blocked_at': blocked.blocked_at
                        },
                        status=status.HTTP_200_OK
                    )
            except Exception as e:
                return Response(
                    {'error': f'An error occurred while blocking talker: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[IsListenerUser])
    def unblock_talker(self, request):
        """Unblock a previously blocked talker.
        
        Endpoint: POST /api/listener/profiles/unblock_talker/
        Request body: { "talker_id": 5 }
        """
        serializer = UnblockTalkerSerializer(data=request.data)
        if serializer.is_valid():
            talker_id = serializer.validated_data['talker_id']
            
            try:
                blocked = ListenerBlockedTalker.objects.get(
                    listener=request.user,
                    talker_id=talker_id
                )
                blocked.delete()
                
                return Response(
                    {
                        'message': f'Talker with ID {talker_id} has been unblocked',
                        'talker_id': talker_id
                    },
                    status=status.HTTP_200_OK
                )
            except ListenerBlockedTalker.DoesNotExist:
                return Response(
                    {'message': f'Talker with ID {talker_id} is not blocked'},
                    status=status.HTTP_200_OK
                )
            except Exception as e:
                return Response(
                    {'error': f'An error occurred while unblocking talker: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], permission_classes=[IsListenerUser])
    def blocked_talkers(self, request):
        """Get list of blocked talkers for the authenticated listener.
        
        Endpoint: GET /api/listener/profiles/blocked_talkers/
        """
        blocked_talkers = ListenerBlockedTalker.objects.filter(listener=request.user).select_related('talker', 'talker__talker_profile')
        serializer = BlockedTalkerListSerializer(blocked_talkers, many=True, context={'request': request})
        return Response({
            'count': blocked_talkers.count(),
            'results': serializer.data
        })

    @swagger_auto_schema(
        operation_description="Get all call attempts for the authenticated listener",
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'results': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT))
                }
            ),
            401: "Unauthorized",
            403: "Only listeners can access this endpoint"
        },
        tags=['Listener Call Attempts']
    )
    @action(detail=False, methods=['get'], url_path='call-attempts', permission_classes=[IsListenerUser])
    def call_attempts(self, request):
        """
        Get all call attempts for the authenticated listener.
        Shows previous calls and their details.
        
        Endpoint: GET /api/listener/profiles/call-attempts/
        
        Returns:
        - List of all call sessions where this listener received calls
        - Includes basic information about talker, call duration, status
        - Sorted by most recent first
        """
        from chat.models import CallSession
        
        # Get all call sessions where this user is the listener
        call_sessions = CallSession.objects.filter(
            listener=request.user
        ).select_related('talker', 'call_package__package').order_by('-created_at')
        
        # Pass actual CallSession objects to serializer
        serializer = ListenerCallAttemptSerializer(call_sessions, many=True)
        return Response({
            'count': call_sessions.count(),
            'results': serializer.data
        }, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Get detailed information about a specific call attempt",
        manual_parameters=[
            openapi.Parameter('call_session_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, 
                            description='ID of the call session')
        ],
        responses={
            200: openapi.Schema(type=openapi.TYPE_OBJECT),
            401: "Unauthorized",
            403: "Not authorized to view this call",
            404: "Call session not found"
        },
        tags=['Listener Call Attempts']
    )
    @action(detail=False, methods=['get'], url_path='call-attempts/(?P<call_session_id>[0-9]+)', 
            permission_classes=[IsListenerUser])
    def call_attempt_detail(self, request, call_session_id=None):
        """
        Get detailed information about a specific call attempt.
        
        Endpoint: GET /api/listener/profiles/call-attempts/{call_session_id}/
        
        Returns:
        - Complete call details including talker profile
        - Call timing and duration information
        - Call package details
        - Call status and end reason
        - Agora channel information
        """
        from chat.models import CallSession
        
        try:
            call_session = CallSession.objects.select_related(
                'talker', 'call_package__package'
            ).get(id=call_session_id, listener=request.user)
        except CallSession.DoesNotExist:
            return Response(
                {'error': 'Call session not found or you are not authorized to view it'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ListenerCallAttemptDetailSerializer(call_session)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Report a talker for inappropriate behavior",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['talker_id', 'reason'],
            properties={
                'talker_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of the talker to report'),
                'reason': openapi.Schema(type=openapi.TYPE_STRING, enum=['harassment', 'inappropriate_content', 'scam', 'hate_speech', 'threatening', 'fake_profile', 'other']),
                'description': openapi.Schema(type=openapi.TYPE_STRING, description='Detailed description of the issue')
            }
        ),
        responses={
            201: openapi.Schema(type=openapi.TYPE_OBJECT),
            400: "Bad request - invalid data",
            401: "Unauthorized",
            403: "Only listeners can report talkers",
            404: "Talker not found"
        },
        tags=['Listener Report Talker']
    )
    @action(detail=False, methods=['post'], url_path='report-talker', permission_classes=[IsListenerUser])
    def report_talker(self, request):
        """
        Report a talker for inappropriate behavior.
        
        If a talker receives 3 or more reports, their account will be automatically suspended for 7 days.
        During suspension:
        - The talker will be logged out automatically
        - They cannot login, receiving error message with remaining suspension days
        - After 7 days, they can login normally again
        
        Endpoint: POST /api/listener/profiles/report-talker/
        
        Request body:
        {
            "talker_id": 10,
            "reason": "harassment",
            "description": "The talker was very rude and abusive during the call"
        }
        """
        from talker.models import TalkerReport, TalkerSuspension
        from talker.serializers import CreateTalkerReportSerializer
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        from datetime import timedelta
        
        User = get_user_model()
        
        # Validate request data
        serializer = CreateTalkerReportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        talker_id = serializer.validated_data['talker_id']
        reason = serializer.validated_data['reason']
        description = serializer.validated_data.get('description', '')
        
        # Get the talker
        try:
            talker = User.objects.get(id=talker_id, user_type='talker')
        except User.DoesNotExist:
            return Response(
                {'error': f'Talker with ID {talker_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if listener already reported this talker
        existing_report = TalkerReport.objects.filter(
            talker=talker,
            reporter=request.user,
            reason=reason
        ).exists()
        
        if existing_report:
            return Response(
                {'message': 'You have already reported this talker for this reason'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create the report
        report = TalkerReport.objects.create(
            talker=talker,
            reporter=request.user,
            reason=reason,
            description=description,
            status='pending'
        )
        
        # Check total reports for this talker
        total_reports = TalkerReport.objects.filter(talker=talker).count()
        
        # If 3 or more reports, suspend the talker
        suspension_triggered = False
        if total_reports >= 3:
            # Check if already suspended
            existing_suspension = TalkerSuspension.objects.filter(
                talker=talker,
                is_active=True
            ).first()
            
            if not existing_suspension:
                # Create suspension
                suspension_days = 7
                resume_at = timezone.now() + timedelta(days=suspension_days)
                
                suspension = TalkerSuspension.objects.create(
                    talker=talker,
                    reason='reports',
                    resume_at=resume_at,
                    days_suspended=suspension_days,
                    is_active=True,
                    notes=f'Account suspended due to {total_reports} reports from listeners'
                )
                
                suspension_triggered = True
                
                # Logout the talker from all sessions
                from rest_framework.authtoken.models import Token
                from django.contrib.auth.models import Session
                import json
                
                # Delete all tokens for this user
                Token.objects.filter(user=talker).delete()
                
                # Delete all sessions for this user
                sessions = Session.objects.all()
                for session in sessions:
                    data = session.get_decoded()
                    if data.get('_auth_user_id') == str(talker.id):
                        session.delete()
        
        # Prepare response
        response_data = {
            'message': 'Report submitted successfully',
            'report': {
                'id': report.id,
                'talker_id': talker.id,
                'talker_email': talker.email,
                'reason': reason,
                'status': 'pending',
                'created_at': report.created_at
            },
            'total_reports_for_talker': total_reports,
            'suspension_triggered': suspension_triggered
        }
        
        if suspension_triggered:
            response_data['message'] = f'Report submitted. Talker account suspended for 7 days due to {total_reports} reports.'
            response_data['suspension_info'] = {
                'reason': 'Multiple reports from listeners',
                'days_suspended': 7,
                'talker_will_be_logged_out': True,
                'talker_cannot_login_for_days': 7
            }
        
        return Response(response_data, status=status.HTTP_201_CREATED)



class ListenerBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing listener balance (read-only)."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = ListenerBalanceSerializer
    
    def get_queryset(self):
        """Only show balance for current listener."""
        if getattr(self, 'swagger_fake_view', False) or self.request is None:
            return ListenerBalance.objects.none()

        user = self.request.user
        if user.user_type == 'listener':
            return ListenerBalance.objects.filter(listener=user)
        return ListenerBalance.objects.none()
    
    @action(detail=False, methods=['get'], url_path='my-balance')
    def my_balance(self, request):
        """Get current user's balance."""
        user = request.user
        
        if user.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can view balance'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get or create balance account
        balance, created = ListenerBalance.objects.get_or_create(
            listener=user,
            defaults={'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00')}
        )
        
        # For debugging - also get payout data for comparison
        from django.db.models import Sum
        from chat.call_models import ListenerPayout, CallPackage
        from bokking.models import SessionBooking
        
        # Calculate what balance should be based on payout data
        earned_payouts = ListenerPayout.objects.filter(
            listener=user,
            status='earned',
            is_extension=False
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        extension_earnings = CallPackage.objects.filter(
            listener=user,
            is_extension=True,
            status__in=['confirmed', 'used', 'completed']
        ).aggregate(total=Sum('listener_amount'))['total'] or Decimal('0.00')
        
        completed_withdrawals = ListenerPayout.objects.filter(
            listener=user,
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        pending_withdrawals = ListenerPayout.objects.filter(
            listener=user,
            status='pending'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        processing_payouts = ListenerPayout.objects.filter(
            listener=user,
            status='processing',
            is_extension=False
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        released_booking_earnings = SessionBooking.objects.filter(
            listener=user,
            status='completed',
            listener_earnings_released=True,
        ).aggregate(total=Sum('listener_amount'))['total'] or Decimal('0.00')
        
        calculated_balance = earned_payouts + extension_earnings + released_booking_earnings - completed_withdrawals
        
        return Response({
            'available_balance': str(balance.available_balance),
            'total_earned': str(balance.total_earned),
            'last_updated': balance.updated_at,
            
            # Debugging information
            'debug_info': {
                'earned_payouts': str(earned_payouts),
                'extension_earnings': str(extension_earnings), 
                'completed_withdrawals': str(completed_withdrawals),
                'pending_withdrawals': str(pending_withdrawals),
                'processing_payouts': str(processing_payouts),
                'released_session_booking_earnings': str(released_booking_earnings),
                'calculated_balance': str(calculated_balance),
                'balance_difference': str(balance.available_balance - calculated_balance),
                'balance_created_now': created
            }
        })

    @swagger_auto_schema(
        operation_description='Get listener transaction history (listener only)',
        manual_parameters=[
            openapi.Parameter('page', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Page number (default: 1)'),
            openapi.Parameter('page_size', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Items per page (default: 20, max: 100)'),
        ],
        responses={200: openapi.Response('Paginated transaction history for listener')},
        tags=['Listener Balance']
    )
    @action(detail=False, methods=['get'], url_path='transaction-history')
    def transaction_history(self, request):
        """Get transaction history for the authenticated listener only."""
        user = request.user

        if user.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can view transaction history'},
                status=status.HTTP_403_FORBIDDEN
            )

        from chat.call_models import CallPackage
        from bokking.models import SessionBooking

        transactions = []

        # Call package earnings transactions
        call_packages = CallPackage.objects.filter(
            listener=user,
            status__in=['confirmed', 'used', 'completed']
        ).select_related('talker').order_by('-created_at')

        for pkg in call_packages:
            talker_name = pkg.talker.full_name or pkg.talker.email
            transaction_at = pkg.used_at or pkg.ended_at or pkg.purchased_at or pkg.created_at
            transactions.append({
                'transaction_id': f'call_{pkg.id}',
                'source': 'call',
                'title': f'Session with {talker_name}',
                'counterparty_name': talker_name,
                'counterparty_email': pkg.talker.email,
                'amount': pkg.listener_amount,
                'currency': 'USD',
                'status': 'completed',
                'transaction_type': 'credit',
                'transaction_at': transaction_at,
                'reference_id': str(pkg.id),
            })

        # Booking earnings transactions (released only)
        bookings = SessionBooking.objects.filter(
            listener=user,
            status='completed',
            listener_earnings_released=True,
        ).select_related('talker').order_by('-listener_earnings_released_at', '-updated_at')

        for booking in bookings:
            talker_name = booking.talker.full_name or booking.talker.email
            transaction_at = booking.listener_earnings_released_at or booking.updated_at
            transactions.append({
                'transaction_id': f'booking_{booking.id}',
                'source': 'booking',
                'title': f'Session with {talker_name}',
                'counterparty_name': talker_name,
                'counterparty_email': booking.talker.email,
                'amount': booking.listener_amount,
                'currency': 'USD',
                'status': 'completed',
                'transaction_type': 'credit',
                'transaction_at': transaction_at,
                'reference_id': str(booking.id),
            })

        # Refunded bookings (show as debit rows so refunds are visible on the dashboard)
        refunded_bookings = SessionBooking.objects.filter(
            listener=user,
            status='refunded',
        ).select_related('talker').order_by('-refunded_at', '-updated_at')

        for booking in refunded_bookings:
            talker_name = booking.talker.full_name or booking.talker.email
            transaction_at = booking.refunded_at or booking.updated_at
            refund_amount = booking.refund_amount or booking.listener_amount or Decimal('0.00')
            transactions.append({
                'transaction_id': f'booking_refund_{booking.id}',
                'source': 'booking_refund',
                'title': f'Refund for session with {talker_name}',
                'counterparty_name': talker_name,
                'counterparty_email': booking.talker.email,
                'amount': -abs(refund_amount),
                'currency': 'USD',
                'status': 'refunded',
                'transaction_type': 'debit',
                'transaction_at': transaction_at,
                'reference_id': str(booking.id),
            })

        transactions.sort(key=lambda row: row['transaction_at'], reverse=True)

        # Simple pagination
        page = request.query_params.get('page', 1)
        page_size = request.query_params.get('page_size', 20)
        try:
            page = max(1, int(page))
            page_size = max(1, min(int(page_size), 100))
        except (ValueError, TypeError):
            page = 1
            page_size = 20

        total_count = len(transactions)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_transactions = transactions[start:end]

        serializer = ListenerTransactionSerializer(paginated_transactions, many=True)
        total_pages = (total_count + page_size - 1) // page_size if total_count else 0

        return Response(
            {
                'count': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
                'results': serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_description='Refund booking earnings and automatically refund talker payment card',
        request_body=RefundBookingSerializer,
        responses={200: 'Refund processed successfully', 400: 'Bad request', 404: 'Booking not found'},
        tags=['Listener Balance']
    )
    @action(detail=False, methods=['post'], url_path='refund-booking')
    def refund_booking(self, request):
        """
        Refund a booking payment back to the talker.
        The total refund amount is split using the booking's 90/10 pricing snapshot,
        so the listener share is reversed from Stripe Connect when possible and the
        admin share is accounted for separately.

        Payload:
        {
            "booking_id": "<uuid>",
            "refund_amount": "10.00",    # optional - exact amount in USD
            "refund_percent": "5",       # optional - as percentage (0-100)
            "reason": "Changed my mind"  # optional
        }

        Rules:
        - Only listener who accepted the booking can refund.
        - Provide EITHER refund_amount OR refund_percent, not both.
        - If neither provided: refunds full remaining refundable amount.
        - Refund amount is applied to the total booking price.
        - Listener share is reversed from the listener's Stripe transfer when available.
        - Admin share is kept as platform revenue in the split calculation.
        - Refund automatically processed to talker's payment card via Stripe.
        - Cannot refund more than the original booking price.
        """
        if request.user.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can refund booking earnings'},
                status=status.HTTP_403_FORBIDDEN,
            )

        booking_id = request.data.get('booking_id')
        refund_amount_raw = request.data.get('refund_amount')
        refund_percent_raw = request.data.get('refund_percent')

        if not booking_id:
            return Response({'error': 'booking_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        if refund_amount_raw is not None and refund_percent_raw is not None:
            return Response(
                {'error': 'Provide either refund_amount or refund_percent, not both'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from bokking.models import SessionBooking

            with transaction.atomic():
                booking = SessionBooking.objects.select_for_update().select_related('talker', 'listener').get(
                    id=booking_id,
                    listener=request.user,
                )

                refund_tracker, _ = ListenerBookingRefund.objects.select_for_update().get_or_create(
                    booking=booking,
                    defaults={'listener': request.user, 'total_refunded': Decimal('0.00')},
                )

                if booking.payment_completed_at is None:
                    return Response(
                        {'error': 'Booking is not paid, refund is not allowed'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                max_refundable = Decimal(str(booking.price))
                if max_refundable <= 0:
                    return Response({'error': 'This booking has no refundable amount'}, status=status.HTTP_400_BAD_REQUEST)

                already_refunded = Decimal(str(refund_tracker.total_refunded))
                remaining_refundable = (max_refundable - already_refunded).quantize(Decimal('0.01'))

                if remaining_refundable <= 0:
                    return Response(
                        {
                            'error': 'This booking is already fully refunded (100%)',
                            'max_refundable': str(max_refundable),
                            'already_refunded': str(already_refunded),
                            'remaining_refundable': '0.00',
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Determine refund amount based on input
                if refund_percent_raw is not None:
                    # Calculate percentage of the REMAINING refundable amount
                    percent = Decimal(str(refund_percent_raw))
                    if percent <= 0 or percent > 100:
                        return Response(
                            {'error': 'refund_percent must be greater than 0 and less than or equal to 100'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    # Percentage is of the max_refundable (original listener earnings), not remaining
                    refund_amount = (max_refundable * percent / Decimal('100')).quantize(Decimal('0.01'))
                elif refund_amount_raw is not None:
                    refund_amount = Decimal(str(refund_amount_raw)).quantize(Decimal('0.01'))
                else:
                    # Default: full refund of remaining refundable amount
                    refund_amount = remaining_refundable

                if refund_amount <= 0:
                    return Response(
                        {'error': 'Refund amount must be greater than 0'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if refund_amount > remaining_refundable:
                    return Response(
                        {
                            'error': 'Refund amount exceeds remaining refundable amount for this booking',
                            'max_refundable': str(max_refundable),
                            'already_refunded': str(already_refunded),
                            'remaining_refundable': str(remaining_refundable),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                total_booking_amount = Decimal(str(booking.price))
                listener_amount = Decimal(str(booking.listener_amount))
                listener_share_ratio = (listener_amount / total_booking_amount) if total_booking_amount else Decimal('0')
                listener_refund_amount = (refund_amount * listener_share_ratio).quantize(Decimal('0.01'))
                admin_refund_amount = (refund_amount - listener_refund_amount).quantize(Decimal('0.01'))

                # Process Stripe refund to talker's payment card
                stripe_refund = process_stripe_refund(booking, amount=float(refund_amount))

                if not stripe_refund or not stripe_refund.get('success'):
                    return Response(
                        {
                            'error': 'Stripe refund failed. No balance changes were applied.',
                            'booking_id': str(booking.id),
                            'stripe_error': stripe_refund.get('message') if isinstance(stripe_refund, dict) else 'Unknown Stripe refund error',
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                listener_refund_source = None
                listener_transfer_reversal = None

                is_destination_charge = False
                if booking.transaction_id:
                    try:
                        payment_intent = stripe.PaymentIntent.retrieve(booking.transaction_id)
                        is_destination_charge = payment_intent.get('metadata', {}).get('payout_mode') == 'destination_charge'
                    except stripe.error.StripeError:
                        is_destination_charge = False

                if booking.stripe_transfer_id and listener_refund_amount > 0:
                    transfer_reversal = reverse_booking_listener_transfer(booking, listener_refund_amount)
                    if transfer_reversal and transfer_reversal.get('success'):
                        if transfer_reversal.get('transfer_id'):
                            listener_refund_source = 'stripe_transfer_reversal'
                        else:
                            listener_refund_source = None
                        listener_transfer_reversal = transfer_reversal
                    else:
                        logger.warning(
                            'Stripe transfer reversal failed for booking %s, falling back to listener balance: %s',
                            booking.id,
                            transfer_reversal.get('message') if isinstance(transfer_reversal, dict) else 'unknown error',
                        )

                if listener_refund_source is None and listener_refund_amount > 0 and not is_destination_charge:
                    listener_balance, _ = ListenerBalance.objects.select_for_update().get_or_create(
                        listener=request.user,
                        defaults={'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00')},
                    )

                    if listener_balance.available_balance < listener_refund_amount:
                        return Response(
                            {
                                'error': 'Insufficient listener balance for refund',
                                'available_balance': str(listener_balance.available_balance),
                                'required_amount': str(listener_refund_amount),
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    if not listener_balance.deduct(listener_refund_amount):
                        return Response(
                            {
                                'error': 'Unable to deduct listener balance for refund',
                                'available_balance': str(listener_balance.available_balance),
                                'required_amount': str(listener_refund_amount),
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    listener_refund_source = 'listener_balance'
                elif listener_refund_source is None and listener_refund_amount > 0 and is_destination_charge:
                    listener_refund_source = 'stripe_destination_charge_reversal'

                refund_tracker.total_refunded = (already_refunded + refund_amount).quantize(Decimal('0.01'))
                refund_tracker.save(update_fields=['total_refunded', 'updated_at'])

                channel_layer = get_channel_layer()
                if channel_layer:
                    event_payload = {
                        'type': 'booking_refund_notification',
                        'booking_id': str(booking.id),
                        'refund_amount': str(refund_amount),
                        'listener_refund_amount': str(listener_refund_amount),
                        'admin_refund_amount': str(admin_refund_amount),
                        'listener_refund_source': listener_refund_source,
                        'listener_id': booking.listener.id,
                        'talker_id': booking.talker.id,
                        'timestamp': timezone.now().isoformat(),
                    }

                    # Notify listener who performed the refund
                    async_to_sync(channel_layer.group_send)(
                        f'user_{booking.listener.id}_notifications',
                        {
                            **event_payload,
                            'message': f'Refund processed for booking {booking.id}: ${refund_amount}',
                        },
                    )

                    # Notify talker who receives card refund
                    refund_message = f'You received a refund of ${refund_amount} for booking {booking.id}'
                    if stripe_refund and stripe_refund.get('success'):
                        refund_message += ' (processed to your payment card)'
                    
                    async_to_sync(channel_layer.group_send)(
                        f'user_{booking.talker.id}_notifications',
                        {
                            **event_payload,
                            'message': refund_message,
                        },
                    )

                return Response(
                    {
                        'message': 'Refund processed successfully',
                        'booking_id': str(booking.id),
                        'refund_amount': str(refund_amount),
                        'listener_refund_amount': str(listener_refund_amount),
                        'admin_refund_amount': str(admin_refund_amount),
                        'stripe_refund': stripe_refund if stripe_refund and stripe_refund.get('success') else None,
                        'listener_transfer_reversal': listener_transfer_reversal,
                        'listener_refund_source': listener_refund_source,
                        'already_refunded': str(refund_tracker.total_refunded),
                        'remaining_refundable': str((max_refundable - refund_tracker.total_refunded).quantize(Decimal('0.01'))),
                    },
                    status=status.HTTP_200_OK,
                )

        except (InvalidOperation, ValueError):
            return Response(
                {'error': 'Invalid amount format'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except SessionBooking.DoesNotExist:
            return Response(
                {'error': 'Booking not found for this listener'},
                status=status.HTTP_404_NOT_FOUND,
            )
