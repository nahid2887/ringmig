from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from django.db import transaction
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import ListenerAvailability, TimeSlot, UniversalBookingPackage, SessionBooking
from .serializers import (
    ListenerAvailabilityDetailSerializer,
    ListenerAvailabilityCreateUpdateSerializer,
    BufferTimeUpdateSerializer,
    TimeSlotSerializer,
    UniversalBookingPackageSerializer,
    SessionBookingSerializer,
    PurchaseSessionBookingSerializer,
    ConfirmSessionBookingPaymentSerializer,
    RejectSessionBookingSerializer,
)
from .booking_payments import create_session_booking_payment_intent, confirm_session_booking_payment
from talker.models import TalkerBalance

User = get_user_model()


def _flatten_validation_errors(errors, prefix=""):
    """Flatten DRF validation errors into a readable field/message list."""
    items = []

    if isinstance(errors, dict):
        for key, value in errors.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            items.extend(_flatten_validation_errors(value, next_prefix))
        return items

    if isinstance(errors, list):
        # Handle list of nested objects (e.g. time_slots)
        if all(isinstance(entry, dict) for entry in errors):
            for index, entry in enumerate(errors):
                next_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
                items.extend(_flatten_validation_errors(entry, next_prefix))
            return items

        # Handle list of scalar error messages
        for entry in errors:
            if isinstance(entry, (dict, list)):
                items.extend(_flatten_validation_errors(entry, prefix))
            else:
                items.append({
                    'field': prefix or 'non_field_errors',
                    'message': str(entry),
                })
        return items

    items.append({
        'field': prefix or 'non_field_errors',
        'message': str(errors),
    })
    return items


def _availability_update_error_response(serializer):
    """Build a consistent, meaningful validation error payload."""
    return {
        'error': 'Validation failed while updating availability.',
        'message': 'Please review the fields below and submit again.',
        'errors': _flatten_validation_errors(serializer.errors),
        'hint': {
            'buffer_time_minutes': 'Must be 0 or greater.',
            'time_slots': 'Provide at least one slot. Each slot needs day_of_week (0-6), start_time, end_time, and start_time must be before end_time.',
        }
    }


def _build_base_availability_time(listener, days=7):
    """Build raw availability schedule by date (not reduced by bookings)."""
    try:
        availability = ListenerAvailability.objects.prefetch_related('time_slots').get(listener=listener)
    except ListenerAvailability.DoesNotExist:
        return []

    start_date = timezone.localdate()
    slots_by_day = {}
    for slot in availability.time_slots.all():
        slots_by_day.setdefault(slot.day_of_week, []).append(slot)

    rows = []
    for i in range(days):
        day_date = start_date + timedelta(days=i)
        weekday = day_date.weekday()
        day_slots = sorted(slots_by_day.get(weekday, []), key=lambda s: s.start_time)
        rows.append({
            'date': day_date.isoformat(),
            'day_of_week': weekday,
            'slots': [
                {
                    'start_time': slot.start_time.strftime('%H:%M:%S'),
                    'end_time': slot.end_time.strftime('%H:%M:%S'),
                    'duration_minutes': slot.duration_minutes(),
                }
                for slot in day_slots
            ],
        })

    return rows


def _group_by_day_of_week(data_rows):
    """
    Reorganize flat date list into day-of-week groups.
    Input: [{'date': '2026-04-06', 'day_of_week': 0, 'slots': [...]}, ...]
    Output: {'day_of_week': 0, 'dates': [{'date': '2026-04-06', 'slots': [...]}, ...], ...}
    """
    from collections import OrderedDict
    
    grouped = OrderedDict()
    for row in data_rows:
        dow = row['day_of_week']
        if dow not in grouped:
            grouped[dow] = {'day_of_week': dow, 'dates': []}
        
        # Add date entry (copy without day_of_week)
        date_entry = {k: v for k, v in row.items() if k != 'day_of_week'}
        grouped[dow]['dates'].append(date_entry)
    
    return list(grouped.values())


def _group_bookings_by_day_of_week(booking_rows, start_date, days):
    """
    Group booking records by day-of-week with dates underneath.
    Returns same structure as _group_by_day_of_week for consistency.
    """
    from collections import OrderedDict
    
    grouped = OrderedDict()
    for i in range(days):
        day_date = start_date + timedelta(days=i)
        dow = day_date.weekday()
        
        if dow not in grouped:
            grouped[dow] = {'day_of_week': dow, 'dates': []}
        
        # Find bookings for this date
        date_bookings = [b for b in booking_rows if b['booking_date'] == day_date.isoformat()]
        
        if date_bookings:
            grouped[dow]['dates'].append({
                'date': day_date.isoformat(),
                'bookings': date_bookings
            })
    
    return list(grouped.values())


def _build_listener_booking_state(listener):
    """
    Build listener booking state for websocket payloads.
    - Filters out expired pending bookings
    - Expands date range to include all bookings
    - Groups results by day-of-week for easier consumption
    """
    # Clean up expired unpaid bookings
    SessionBooking.cleanup_expired_unpaid(listener=listener)

    all_bookings = SessionBooking.objects.filter(
        listener=listener,
    ).order_by('-created_at')[:100]
    
    # Filter out expired pending bookings
    current_time = timezone.now()
    non_expired_bookings = [
        b for b in all_bookings
        if not (b.status in ['pending', 'payment_pending'] and current_time > b.payment_expires_at)
    ]

    booking_rows = [
        {
            'id': str(booking.id),
            'talker_id': booking.talker_id,
            'booking_date': booking.booking_date.isoformat(),
            'start_time': booking.start_time.strftime('%H:%M:%S'),
            'end_time': booking.end_time.strftime('%H:%M:%S'),
            'status': booking.status,
            'created_at': booking.created_at.isoformat(),
            'updated_at': booking.updated_at.isoformat(),
            'payment_completed_at': booking.payment_completed_at.isoformat() if booking.payment_completed_at else None,
            'payment_expires_at': booking.payment_expires_at.isoformat() if booking.status in ['pending', 'payment_pending'] else None,
        }
        for booking in non_expired_bookings
    ]

    booking_time = [
        booking for booking in booking_rows if booking['status'] == 'completed'
    ]
    pending_time = [
        booking for booking in booking_rows if booking['status'] in ['pending', 'payment_pending']
    ]
    
    # Determine date range: today to max booking date (or 7 days if no bookings)
    start_date = timezone.localdate()
    if non_expired_bookings:
        max_booking_date = max(b.booking_date for b in non_expired_bookings)
        # Add 1 day after last booking to show next availability
        end_date = max(max_booking_date, start_date + timedelta(days=6))
    else:
        end_date = start_date + timedelta(days=6)
    
    days_to_show = (end_date - start_date).days + 1

    # Build flat arrays
    availability_flat = _build_base_availability_time(listener=listener, days=days_to_show)
    effective_flat = SessionBooking.get_effective_availability(
        listener=listener,
        days=days_to_show,
    )
    
    # Group by day-of-week
    availability_by_dow = _group_by_day_of_week(availability_flat)
    effective_by_dow = _group_by_day_of_week(effective_flat)
    
    # Group bookings by date then by day_of_week
    booking_time_by_dow = _group_bookings_by_day_of_week(booking_time, start_date, days_to_show)
    pending_time_by_dow = _group_bookings_by_day_of_week(pending_time, start_date, days_to_show)

    return {
        'session_bookings': booking_rows,
        'availability_time': availability_by_dow,
        'booking_time': booking_time_by_dow,
        'pending_time': pending_time_by_dow,
        'effective_availability': effective_by_dow,
    }


def broadcast_availability_update(availability_instance):
    """
    Broadcast availability update to all WebSocket subscribers.
    This broadcasts to:
    1. All Talkers watching listeners (availability_updates group)
    2. The listener's own notification channel
    
    Args:
        availability_instance: ListenerAvailability model instance
    """
    try:
        # Force fresh read from DB with all relations loaded
        availability_instance.refresh_from_db()
        
        fresh_availability = ListenerAvailability.objects.select_related(
            'listener'
        ).prefetch_related(
            'time_slots'
        ).get(id=availability_instance.id)

        channel_layer = get_channel_layer()
        serializer = ListenerAvailabilityDetailSerializer(fresh_availability)
        data = serializer.data
        listener = fresh_availability.listener
        booking_state = _build_listener_booking_state(listener)
        data['session_bookings'] = booking_state['session_bookings']
        data['availability_time'] = booking_state['availability_time']
        data['booking_time'] = booking_state['booking_time']
        data['pending_time'] = booking_state['pending_time']
        data['effective_availability'] = booking_state['effective_availability']

        message_data = {
            "listener_username": listener.full_name or listener.email,
            "listener_full_name": listener.full_name or listener.email,
            "listener_email": listener.email,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }

        print(f"[Broadcast] Availability update for {listener.email}: {fresh_availability.time_slots.count()} time slots")

        # Broadcast to all Talkers (availability_updates group)
        async_to_sync(channel_layer.group_send)(
            "availability_updates",
            {
                "type": "availability_update",
                **message_data
            }
        )

        # Broadcast to subscribers watching this specific listener
        async_to_sync(channel_layer.group_send)(
            f"listener_availability_{listener.id}",
            {
                "type": "availability_update",
                **message_data
            }
        )

        # Send notification to the Listener themselves
        async_to_sync(channel_layer.group_send)(
            f"listener_notifications_{listener.id}",
            {
                "type": "availability_notification",
                "message": "Your availability has been updated",
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
        )

    except Exception as e:
        import traceback
        print(f"[Broadcast Error] {str(e)}")
        traceback.print_exc()


class ListenerAvailabilityViewSet(viewsets.ViewSet):
    """
    ViewSet for managing Listener availability and scheduling.
    Listeners can:
    - Create/Update their full availability with time slots
    - View their own availability
    - Update buffer time between sessions
    
    WebSocket Updates:
    - All updates are broadcast to subscribed users via WebSocket
    - Connect to ws://localhost:8000/ws/availability/subscribe/ to subscribe
    - Connect to ws://localhost:8000/ws/availability/notifications/ for own notifications
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get current listener's availability",
        responses={200: ListenerAvailabilityDetailSerializer}
    )
    def list(self, request):
        """Get the current user's availability."""
        try:
            availability = request.user.booking_availability
            serializer = ListenerAvailabilityDetailSerializer(availability)
            return Response(serializer.data)
        except ListenerAvailability.DoesNotExist:
            return Response(
                {"detail": "No availability set yet"},
                status=status.HTTP_404_NOT_FOUND
            )

    @swagger_auto_schema(
        operation_description="Create or update listener availability with multiple time slots",
        request_body=ListenerAvailabilityCreateUpdateSerializer,
        responses={
            201: ListenerAvailabilityDetailSerializer,
            400: openapi.Response("Bad request - Invalid time slots")
        },
        examples={
            'application/json': {
                'buffer_time_minutes': 5,
                'time_slots': [
                    {
                        'day_of_week': 0,
                        'start_time': '09:00',
                        'end_time': '12:00'
                    },
                    {
                        'day_of_week': 0,
                        'start_time': '14:00',
                        'end_time': '18:00'
                    },
                    {
                        'day_of_week': 1,
                        'start_time': '10:00',
                        'end_time': '17:00'
                    }
                ]
            }
        }
    )
    def create(self, request):
        """
        Create or update availability with time slots.
        
        You can set multiple time slots for the same day or different days.
        Example: Monday 9:00-12:00 and 14:00-18:00, Tuesday 10:00-17:00
        
        WebSocket subscribers will receive real-time updates.
        """
        serializer = ListenerAvailabilityCreateUpdateSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            availability = serializer.save()
            response_serializer = ListenerAvailabilityDetailSerializer(availability)
            
            # Broadcast update to WebSocket subscribers AFTER full save
            broadcast_availability_update(availability)
            
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Update listener availability with new time slots",
        request_body=ListenerAvailabilityCreateUpdateSerializer,
        responses={
            200: ListenerAvailabilityDetailSerializer,
            404: openapi.Response("Availability not found"),
            400: openapi.Response("Bad request - Invalid time slots")
        }
    )
    @action(detail=False, methods=['patch'], url_path='update')
    def update_availability(self, request):
        """
        Update listener availability (time slots and/or buffer time).
        This replaces all existing time slots with new ones.
        
        WebSocket subscribers will receive real-time updates.
        """
        try:
            availability = request.user.booking_availability
        except ListenerAvailability.DoesNotExist:
            return Response(
                {"detail": "No availability set yet. Please create availability first."},
                status=status.HTTP_404_NOT_FOUND
            )

        if not request.data:
            return Response(
                {
                    'error': 'Request body is empty.',
                    'message': 'Send at least one field to update: buffer_time_minutes and/or time_slots.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ListenerAvailabilityCreateUpdateSerializer(
            availability,
            data=request.data,
            context={'request': request},
            partial=True
        )
        if serializer.is_valid():
            availability = serializer.save()
            response_serializer = ListenerAvailabilityDetailSerializer(availability)
            
            # Broadcast update to WebSocket subscribers AFTER full save
            broadcast_availability_update(availability)
            
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        return Response(
            _availability_update_error_response(serializer),
            status=status.HTTP_400_BAD_REQUEST
        )

    @swagger_auto_schema(
        operation_description="Update only the buffer time between sessions",
        request_body=BufferTimeUpdateSerializer,
        responses={
            200: ListenerAvailabilityDetailSerializer,
            404: openapi.Response("Availability not found")
        },
        examples={
            'application/json': {
                'buffer_time_minutes': 10
            }
        }
    )
    @action(detail=False, methods=['patch'], url_path='buffer-time')
    def update_buffer_time(self, request):
        """
        Update only the buffer time between sessions.
        This allows updating buffer time without changing time slots.
        
        WebSocket subscribers will receive real-time updates.
        """
        try:
            availability = request.user.booking_availability
        except ListenerAvailability.DoesNotExist:
            return Response(
                {"detail": "No availability set yet. Please create availability first."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = BufferTimeUpdateSerializer(
            availability,
            data=request.data,
            partial=True
        )
        if serializer.is_valid():
            availability = serializer.save()
            response_serializer = ListenerAvailabilityDetailSerializer(availability)
            
            # Broadcast update to WebSocket subscribers AFTER full save
            broadcast_availability_update(availability)
            
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Get available time slots for a specific day",
        manual_parameters=[
            openapi.Parameter(
                'day_of_week',
                openapi.IN_QUERY,
                description='Day of week (0=Monday, 6=Sunday)',
                type=openapi.TYPE_INTEGER,
                required=True
            )
        ],
        responses={
            200: openapi.Response(
                description="List of time slots",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'id': openapi.Schema(type=openapi.TYPE_STRING),
                            'day_of_week': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'day_of_week_display': openapi.Schema(type=openapi.TYPE_STRING),
                            'start_time': openapi.Schema(type=openapi.TYPE_STRING),
                            'end_time': openapi.Schema(type=openapi.TYPE_STRING),
                            'duration_minutes': openapi.Schema(type=openapi.TYPE_INTEGER),
                        }
                    )
                )
            ),
            404: openapi.Response("Availability not found")
        }
    )
    @action(detail=False, methods=['get'], url_path='slots')
    def get_slots_for_day(self, request):
        """
        Get all time slots for a specific day of the week.
        Query parameter: day_of_week (0=Monday, 6=Sunday)
        """
        day_of_week = request.query_params.get('day_of_week')
        
        if day_of_week is None:
            return Response(
                {"detail": "day_of_week query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            day_of_week = int(day_of_week)
            if not (0 <= day_of_week <= 6):
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {"detail": "day_of_week must be an integer between 0 and 6"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            availability = request.user.booking_availability
            time_slots = availability.get_available_slots_for_day(day_of_week)
            serializer = TimeSlotSerializer(time_slots, many=True)
            return Response(serializer.data)
        except ListenerAvailability.DoesNotExist:
            return Response(
                {"detail": "No availability set yet"},
                status=status.HTTP_404_NOT_FOUND
            )


class UniversalBookingPackageViewSet(viewsets.ReadOnlyModelViewSet):
    """List active booking packages for talker purchase flow."""

    queryset = UniversalBookingPackage.objects.filter(is_active=True)
    serializer_class = UniversalBookingPackageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or self.request is None:
            return UniversalBookingPackage.objects.filter(is_active=True).order_by('duration', 'price')

        queryset = UniversalBookingPackage.objects.filter(is_active=True)
        package_type = self.request.query_params.get('package_type')
        if package_type:
            queryset = queryset.filter(package_type=package_type)
        return queryset.order_by('duration', 'price')


class SessionBookingViewSet(viewsets.ModelViewSet):
    """Create and manage paid session bookings with availability + buffer checks."""

    serializer_class = SessionBookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or self.request is None:
            return SessionBooking.objects.none()

        user = self.request.user
        if user.user_type == 'talker':
            return SessionBooking.objects.filter(talker=user).select_related('listener', 'package')
        if user.user_type == 'listener':
            return SessionBooking.objects.filter(listener=user).select_related('talker', 'package')
        return SessionBooking.objects.none()

    @swagger_auto_schema(
        operation_description='Purchase a booking slot with Stripe payment link',
        request_body=PurchaseSessionBookingSerializer,
        responses={201: SessionBookingSerializer, 400: 'Bad request'},
        tags=['Booking Purchase']
    )
    @action(detail=False, methods=['post'], url_path='purchase')
    def purchase(self, request):
        if request.user.user_type != 'talker':
            return Response({'error': 'Only talkers can purchase bookings'}, status=status.HTTP_403_FORBIDDEN)

        # Clean stale unpaid holds first and broadcast removal if any were deleted.
        listener_id_raw = request.data.get('listener_id')
        booking_date_raw = request.data.get('booking_date')
        if listener_id_raw and booking_date_raw:
            try:
                listener_for_cleanup = User.objects.get(id=listener_id_raw, user_type='listener')
                booking_date_for_cleanup = datetime.strptime(booking_date_raw, '%Y-%m-%d').date()
                deleted = SessionBooking.cleanup_expired_unpaid(
                    listener=listener_for_cleanup,
                    booking_date=booking_date_for_cleanup,
                )
                if deleted > 0 and hasattr(listener_for_cleanup, 'booking_availability'):
                    broadcast_availability_update(listener_for_cleanup.booking_availability)
            except (User.DoesNotExist, ValueError):
                pass

        serializer = PurchaseSessionBookingSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        listener = payload['listener']
        package = payload['package']

        booking = SessionBooking.objects.create(
            talker=request.user,
            listener=listener,
            package=package,
            booking_date=payload['booking_date'],
            start_time=payload['start_time'],
            end_time=payload['end_time'],
            duration_minutes=package.duration,
            buffer_time_minutes=getattr(listener.booking_availability, 'buffer_time_minutes', 5),
            status='payment_pending',
            price=package.price,
            app_fee=package.app_fee,
            listener_amount=package.listener_amount,
        )

        payment_data = create_session_booking_payment_intent(
            booking,
            payment_method_id=payload.get('payment_method_id')
        )

        if payment_data.get('status') == 'succeeded':
            booking.status = 'completed'
            booking.transaction_id = payment_data.get('payment_intent_id')
            booking.payment_completed_at = timezone.now()
            booking.save(update_fields=['status', 'transaction_id', 'payment_completed_at', 'updated_at'])

        if hasattr(listener, 'booking_availability'):
            broadcast_availability_update(listener.booking_availability)

        response_status = status.HTTP_201_CREATED
        return Response(
            {
                'message': 'Booking created. Complete payment to finalize booking.' if booking.status != 'completed' else 'Booking payment completed successfully.',
                'booking': SessionBookingSerializer(booking).data,
                'payment': payment_data,
            },
            status=response_status,
        )

    @swagger_auto_schema(
        operation_description='Confirm booking payment and mark booking completed',
        request_body=ConfirmSessionBookingPaymentSerializer,
        responses={200: SessionBookingSerializer, 400: 'Bad request'},
        tags=['Booking Purchase']
    )
    @action(detail=False, methods=['post'], url_path='confirm-payment')
    def confirm_payment(self, request):
        serializer = ConfirmSessionBookingPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        booking_id = serializer.validated_data['booking_id']
        payment_intent_id = serializer.validated_data['payment_intent_id']

        try:
            booking = SessionBooking.objects.select_related('listener').get(id=booking_id)
        except SessionBooking.DoesNotExist:
            return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)

        if request.user not in [booking.talker, booking.listener]:
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        if booking.is_payment_expired:
            booking_id_str = str(booking.id)
            listener = booking.listener
            booking.delete()

            if hasattr(listener, 'booking_availability'):
                broadcast_availability_update(listener.booking_availability)

            return Response(
                {
                    'error': 'Booking payment window expired after 10 minutes. Booking has been deleted.',
                    'booking_id': booking_id_str,
                },
                status=status.HTTP_410_GONE,
            )

        payment_data = confirm_session_booking_payment(payment_intent_id)

        if payment_data['status'] == 'succeeded':
            booking.status = 'completed'
            booking.transaction_id = payment_intent_id
            booking.payment_completed_at = timezone.now()
            booking.save(update_fields=['status', 'transaction_id', 'payment_completed_at', 'updated_at'])

            if hasattr(booking.listener, 'booking_availability'):
                broadcast_availability_update(booking.listener.booking_availability)

            return Response(
                {
                    'message': 'Payment successful. Booking completed.',
                    'booking': SessionBookingSerializer(booking).data,
                    'payment': payment_data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                'message': 'Payment not completed yet.',
                'booking': SessionBookingSerializer(booking).data,
                'payment': payment_data,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    @swagger_auto_schema(
        operation_description='Reject a paid booking before it starts and refund the listener amount to the talker balance',
        request_body=RejectSessionBookingSerializer,
        responses={200: SessionBookingSerializer, 400: 'Bad request', 403: 'Forbidden', 404: 'Not found'},
        tags=['Booking Purchase']
    )
    @action(detail=False, methods=['post'], url_path='reject')
    def reject_booking(self, request):
        if request.user.user_type != 'listener':
            return Response({'error': 'Only listeners can reject bookings'}, status=status.HTTP_403_FORBIDDEN)

        serializer = RejectSessionBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        booking_id = serializer.validated_data['booking_id']
        reason = serializer.validated_data['reason']
        notes = serializer.validated_data.get('notes', '') or ''

        try:
            with transaction.atomic():
                booking = SessionBooking.objects.select_for_update().select_related('talker', 'listener', 'package').get(
                    id=booking_id,
                    listener=request.user,
                )

                if booking.status != 'completed' or booking.payment_completed_at is None:
                    return Response(
                        {'error': 'Only paid bookings can be rejected'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if booking.start_datetime_aware <= timezone.now():
                    return Response(
                        {'error': 'You can only reject a booking before it starts'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if booking.status == 'cancelled':
                    return Response(
                        {'error': 'This booking has already been rejected or cancelled'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                talker_balance, _ = TalkerBalance.objects.select_for_update().get_or_create(
                    talker=booking.talker,
                    defaults={'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00')},
                )

                refund_amount = booking.listener_amount
                talker_balance.add_earnings(refund_amount)

                booking.status = 'cancelled'
                booking.cancellation_reason = f'Rejected by listener: {reason}. {notes}'.strip()
                booking.save(update_fields=['status', 'cancellation_reason', 'updated_at'])

                return Response(
                    {
                        'message': 'Booking rejected successfully and refunded to talker balance.',
                        'booking': SessionBookingSerializer(booking).data,
                        'refund': {
                            'amount': str(refund_amount),
                            'credited_to': booking.talker.email,
                            'talker_balance': {
                                'available_balance': str(talker_balance.available_balance),
                                'total_earned': str(talker_balance.total_earned),
                            },
                        },
                    },
                    status=status.HTTP_200_OK,
                )

        except SessionBooking.DoesNotExist:
            return Response(
                {'error': 'Booking not found for this listener'},
                status=status.HTTP_404_NOT_FOUND,
            )

    @swagger_auto_schema(
        operation_description='Check if a listener slot is available for selected date/time/package',
        manual_parameters=[
            openapi.Parameter('listener_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=True),
            openapi.Parameter('booking_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE, required=True),
            openapi.Parameter('start_time', openapi.IN_QUERY, type=openapi.TYPE_STRING, required=True),
            openapi.Parameter('booking_package_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=True),
        ],
        responses={200: openapi.Response('Availability check result')},
        tags=['Booking Purchase']
    )
    @action(detail=False, methods=['get'], url_path='check-slot')
    def check_slot(self, request):
        listener_id = request.query_params.get('listener_id')
        booking_date = request.query_params.get('booking_date')
        start_time = request.query_params.get('start_time')
        package_id = request.query_params.get('booking_package_id')

        if not all([listener_id, booking_date, start_time, package_id]):
            return Response(
                {'error': 'listener_id, booking_date, start_time and booking_package_id are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            listener = User.objects.get(id=listener_id, user_type='listener')
            package = UniversalBookingPackage.objects.get(id=package_id, is_active=True)
            booking_date_value = datetime.strptime(booking_date, '%Y-%m-%d').date()
            start_time_value = datetime.strptime(start_time, '%H:%M').time()
        except (User.DoesNotExist, UniversalBookingPackage.DoesNotExist, ValueError):
            return Response({'error': 'Invalid listener/package/date/time'}, status=status.HTTP_400_BAD_REQUEST)

        # Remove stale unpaid holds before checking and broadcast if list changed.
        deleted = SessionBooking.cleanup_expired_unpaid(listener=listener, booking_date=booking_date_value)
        if deleted > 0 and hasattr(listener, 'booking_availability'):
            broadcast_availability_update(listener.booking_availability)

        is_available, end_time_value, message = SessionBooking.check_slot_available(
            listener=listener,
            booking_date=booking_date_value,
            start_time=start_time_value,
            duration_minutes=package.duration,
        )

        return Response(
            {
                'listener_id': listener.id,
                'booking_date': booking_date_value,
                'start_time': start_time_value,
                'end_time': end_time_value,
                'duration_minutes': package.duration,
                'is_available': is_available,
                'message': message or 'Slot is available',
            },
            status=status.HTTP_200_OK,
        )
