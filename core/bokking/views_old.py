from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from datetime import datetime

from .models import ListenerAvailability, TimeSlot
from .serializers import (
    ListenerAvailabilityDetailSerializer,
    ListenerAvailabilityCreateUpdateSerializer,
    BufferTimeUpdateSerializer
)


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
        fresh_availability = ListenerAvailability.objects.select_related(
            'listener'
        ).prefetch_related(
            'time_slots'
        ).get(id=availability_instance.id)

        channel_layer = get_channel_layer()
        serializer = ListenerAvailabilityDetailSerializer(fresh_availability)
        data = serializer.data
        listener = fresh_availability.listener

        message_data = {
            "listener_full_name": listener.full_name or listener.email,
            "listener_email": listener.email,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }

        # Broadcast to all Talkers (availability_updates group)
        async_to_sync(channel_layer.group_send)(
            "availability_updates",
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
        responses={200: ListenerAvailabilityDetailSerializer()}
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
        request_body=ListenerAvailabilityCreateUpdateSerializer(),
        responses={
            201: ListenerAvailabilityDetailSerializer(),
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
        
        WebSocket subscribers will receive real-time updates automatically via signal.
        """
        serializer = ListenerAvailabilityCreateUpdateSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            availability = serializer.save()
            response_serializer = ListenerAvailabilityDetailSerializer(availability)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Update listener availability with new time slots",
        request_body=ListenerAvailabilityCreateUpdateSerializer(),
        responses={
            200: ListenerAvailabilityDetailSerializer(),
            404: openapi.Response("Availability not found"),
            400: openapi.Response("Bad request - Invalid time slots")
        }
    )
    @action(detail=False, methods=['patch'], url_path='update')
    def update_availability(self, request):
        """
        Update listener availability (time slots and/or buffer time).
        This replaces all existing time slots with new ones.
        
        WebSocket subscribers will receive real-time updates automatically.
        """
        try:
            availability = request.user.booking_availability
        except ListenerAvailability.DoesNotExist:
            return Response(
                {"detail": "No availability set yet. Please create availability first."},
                status=status.HTTP_404_NOT_FOUND
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
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Update only the buffer time between sessions",
        request_body=BufferTimeUpdateSerializer(),
        responses={
            200: ListenerAvailabilityDetailSerializer(),
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
        
        WebSocket subscribers will receive real-time updates automatically via signal.
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
            from .serializers import TimeSlotSerializer
            serializer = TimeSlotSerializer(time_slots, many=True)
            return Response(serializer.data)
        except ListenerAvailability.DoesNotExist:
            return Response(
                {"detail": "No availability set yet"},
                status=status.HTTP_404_NOT_FOUND
            )
    """
    ViewSet for managing Listener availability and scheduling.
    Listeners can:
    - Create/Update their full availability with time slots
    - View their own availability
    - Update buffer time between sessions
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get current listener's availability",
        responses={200: ListenerAvailabilityDetailSerializer()}
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
        request_body=ListenerAvailabilityCreateUpdateSerializer(),
        responses={
            201: ListenerAvailabilityDetailSerializer(),
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
        """
        serializer = ListenerAvailabilityCreateUpdateSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            availability = serializer.save()
            response_serializer = ListenerAvailabilityDetailSerializer(availability)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Update listener availability with new time slots",
        request_body=ListenerAvailabilityCreateUpdateSerializer(),
        responses={
            200: ListenerAvailabilityDetailSerializer(),
            404: openapi.Response("Availability not found"),
            400: openapi.Response("Bad request - Invalid time slots")
        }
    )
    @action(detail=False, methods=['patch'], url_path='update')
    def update_availability(self, request):
        """
        Update listener availability (time slots and/or buffer time).
        This replaces all existing time slots with new ones.
        """
        try:
            availability = request.user.booking_availability
        except ListenerAvailability.DoesNotExist:
            return Response(
                {"detail": "No availability set yet. Please create availability first."},
                status=status.HTTP_404_NOT_FOUND
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
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Update only the buffer time between sessions",
        request_body=BufferTimeUpdateSerializer(),
        responses={
            200: ListenerAvailabilityDetailSerializer(),
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
            from .serializers import TimeSlotSerializer
            serializer = TimeSlotSerializer(time_slots, many=True)
            return Response(serializer.data)
        except ListenerAvailability.DoesNotExist:
            return Response(
                {"detail": "No availability set yet"},
                status=status.HTTP_404_NOT_FOUND
            )
