import json
import asyncio
import math
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken
from .models import ListenerAvailability, SessionBooking
from .serializers import ListenerAvailabilityDetailSerializer
from urllib.parse import parse_qs

User = get_user_model()


class PeriodicRefreshMixin:
    """
    Mixin to periodically refresh and send availability data every 3 minutes.
    This keeps WebSocket connections alive by sending fresh data regularly.
    """
    
    REFRESH_INTERVAL = 180  # 3 minutes
    
    async def start_periodic_refresh(self, callback):
        """Start periodic refresh task."""
        self.refresh_task = asyncio.create_task(self._periodic_refresh_loop(callback))
    
    async def stop_periodic_refresh(self):
        """Stop the periodic refresh task."""
        if hasattr(self, 'refresh_task') and self.refresh_task:
            self.refresh_task.cancel()
            try:
                await self.refresh_task
            except asyncio.CancelledError:
                pass
    
    async def _periodic_refresh_loop(self, callback):
        """
        Periodically call callback to refresh and send data.
        callback should be an async method that sends the availability data.
        """
        try:
            while True:
                await asyncio.sleep(self.REFRESH_INTERVAL)
                # Call the provided callback to send fresh data
                await callback()
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


def _build_base_availability_time(listener, days=7):
    """Build raw availability schedule by date (not reduced by bookings)."""
    try:
        availability = ListenerAvailability.objects.prefetch_related('time_slots').get(listener=listener)
    except ListenerAvailability.DoesNotExist:
        return []

    from django.utils import timezone
    from datetime import timedelta

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


def _serialize_listener_booking_state(listener):
    """
    Build booking + effective availability block for websocket payloads.
    - Filters out expired pending bookings
    - Expands date range to include all bookings
    - Groups results by day-of-week for easier consumption
    """
    from django.utils import timezone
    from datetime import timedelta
    
    # Clean up expired unpaid bookings
    SessionBooking.cleanup_expired_unpaid(listener=listener)
    
    # Get all non-expired bookings
    bookings = SessionBooking.objects.filter(listener=listener).order_by('-created_at')[:100]
    
    # Filter out expired pending bookings
    current_time = timezone.now()
    non_expired_bookings = [
        b for b in bookings 
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
            'price': str(booking.price),
            'app_fee': str(booking.app_fee),
            'listener_amount': str(booking.listener_amount),
            'payment_link': booking.payment_link,
            'transaction_id': booking.transaction_id,
            'created_at': booking.created_at.isoformat(),
            'updated_at': booking.updated_at.isoformat(),
            'payment_completed_at': booking.payment_completed_at.isoformat() if booking.payment_completed_at else None,
            'payment_expires_at': booking.payment_expires_at.isoformat() if booking.status in ['pending', 'payment_pending'] else None,
            'payment': {
                'currency': 'USD',
                'price': str(booking.price),
                'app_fee': str(booking.app_fee),
                'listener_amount': str(booking.listener_amount),
                'payment_link': booking.payment_link,
                'transaction_id': booking.transaction_id,
                'is_paid': booking.payment_completed_at is not None,
                'payment_completed_at': booking.payment_completed_at.isoformat() if booking.payment_completed_at else None,
                'payment_expires_at': booking.payment_expires_at.isoformat() if booking.status in ['pending', 'payment_pending'] else None,
            },
        }
        for booking in non_expired_bookings
    ]
    
    # Determine date range: today to max booking date (or 7 days if no bookings)
    from django.utils import timezone
    start_date = timezone.localdate()
    if non_expired_bookings:
        max_booking_date = max(b.booking_date for b in non_expired_bookings)
        # Add 1 day after last booking to show next availability
        end_date = max(max_booking_date, start_date + timedelta(days=6))
    else:
        end_date = start_date + timedelta(days=6)
    
    days_to_show = (end_date - start_date).days + 1
    
    booking_time = [
        booking for booking in booking_rows if booking['status'] == 'completed'
    ]
    pending_time = [
        booking for booking in booking_rows if booking['status'] in ['pending', 'payment_pending']
    ]
    
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


def _group_bookings_by_day_of_week(booking_rows, start_date, days):
    """
    Group booking records by day-of-week with dates underneath.
    Returns same structure as _group_by_day_of_week for consistency.
    """
    from collections import OrderedDict
    from datetime import timedelta, datetime
    
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


def _enrich_availability_payload(listener, base_payload):
    """Attach booking-aware fields to availability payload."""
    enriched = dict(base_payload)
    booking_state = _serialize_listener_booking_state(listener)
    enriched['session_bookings'] = booking_state['session_bookings']
    enriched['availability_time'] = booking_state['availability_time']
    enriched['booking_time'] = booking_state['booking_time']
    enriched['pending_time'] = booking_state['pending_time']
    enriched['effective_availability'] = booking_state['effective_availability']
    return enriched


class ListenerAvailabilityConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time availability updates.
    Users can subscribe to a listener's availability and receive updates in real-time.
    
    Connect with token parameter:
    ws://localhost:8005/ws/availability/subscribe/?token=eyJ0eXA...
    
    Commands:
    - subscribe: Subscribe to a listener's availability updates
    - get_my_availability: Get own availability
    - unsubscribe: Unsubscribe from updates
    - ping: Send ping to keep connection alive
    """
    
    async def connect(self):
        """Handle WebSocket connection with token from query parameter."""
        self.listener_id = None
        self.listener_username = None
        self.user = None
        
        # Get token from query parameters
        query_string = self.scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        token = query_params.get('token', [None])[0]
        
        if token:
            # Validate token and get user
            self.user = await self.authenticate_user(token)
        
        if self.user and self.user.is_authenticated:
            await self.accept()
        else:
            await self.close(code=4001)  # Unauthorized
    @database_sync_to_async
    def authenticate_user(self, token):
        """Validate JWT token and return user."""
        try:
            decoded_token = AccessToken(token)
            user_id = decoded_token['user_id']
            return User.objects.get(id=user_id)
        except Exception:
            return AnonymousUser()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if self.listener_id:
            await self.channel_layer.group_discard(
                f"listener_availability_{self.listener_id}",
                self.channel_name
            )

    async def receive(self, text_data):
        """
        Handle incoming WebSocket messages.
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'subscribe':
                await self.handle_subscribe(data)
            elif message_type == 'unsubscribe':
                await self.handle_unsubscribe(data)
            else:
                await self.send_error("Unknown message type")
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")
        except Exception as e:
            await self.send_error(f"Error: {str(e)}")

    async def handle_subscribe(self, data):
        """Subscribe to a listener's availability updates."""
        listener_identifier = data.get('listener_id')
        
        if not listener_identifier:
            await self.send_error("listener_id is required")
            return

        # Get listener user
        listener = await self.get_listener_user(listener_identifier)
        if not listener:
            await self.send_error(f"Listener '{listener_identifier}' not found")
            return

        # If already subscribed to different listener, unsubscribe first
        if self.listener_id and self.listener_id != str(listener.id):
            await self.channel_layer.group_discard(
                f"listener_availability_{self.listener_id}",
                self.channel_name
            )

        # Subscribe to this listener's group
        self.listener_id = str(listener.id)
        self.listener_username = listener.full_name or listener.email
        
        await self.channel_layer.group_add(
            f"listener_availability_{self.listener_id}",
            self.channel_name
        )

        # Send current availability
        availability = await self.get_availability(listener)
        if availability:
            await self.send_json({
                "type": "subscription_success",
                "message": f"Subscribed to {(listener.full_name or listener.email)}'s availability",
                "listener_username": listener.full_name or listener.email,
                "data": availability
            })
        else:
            await self.send_json({
                "type": "subscription_success",
                "message": f"Subscribed to {(listener.full_name or listener.email)}'s availability",
                "listener_username": listener.full_name or listener.email,
                "data": None
            })

    async def handle_unsubscribe(self, data):
        """Unsubscribe from listener's availability updates."""
        if self.listener_id:
            await self.channel_layer.group_discard(
                f"listener_availability_{self.listener_id}",
                self.channel_name
            )
            username = self.listener_username
            self.listener_id = None
            self.listener_username = None
            
            await self.send_json({
                "type": "unsubscribe_success",
                "message": f"Unsubscribed from {username}'s availability"
            })
        else:
            await self.send_error("Not subscribed to any listener")

    async def availability_update(self, event):
        """
        Receive availability update from group and send to WebSocket.
        This is called when broadcast_availability_update is triggered.
        """
        await self.send_json({
            "type": "availability_update",
            "listener_username": event.get('listener_username') or event.get('listener_full_name') or event.get('listener_email'),
            "data": event['data'],
            "timestamp": event.get('timestamp')
        })

    async def send_error(self, message):
        """Send error message to client."""
        await self.send_json({
            "type": "error",
            "message": message
        })

    async def send_json(self, data):
        """Send JSON data to WebSocket client."""
        await self.send(text_data=json.dumps(data))

    @database_sync_to_async
    def get_listener_user(self, identifier):
        """Get listener user by ID or email."""
        try:
            # Try to get by ID first
            try:
                return User.objects.get(id=identifier)
            except (User.DoesNotExist, ValueError):
                # Try to get by email
                return User.objects.get(email=identifier)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def get_availability(self, listener):
        """Get listener's availability data."""
        try:
            availability = ListenerAvailability.objects.get(listener=listener)
            serializer = ListenerAvailabilityDetailSerializer(availability)
            return _enrich_availability_payload(listener, serializer.data)
        except ListenerAvailability.DoesNotExist:
            return None


class ListenerAvailabilityNotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for listener's own availability notifications.
    The listener can see their own availability updates and confirmations.
    
    Commands:
    - get_my_availability: Get current listener's availability
    - ping: Send ping to keep connection alive
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        if self.scope["user"].is_authenticated:
            self.user_id = str(self.scope["user"].id)
            self.username = self.scope["user"].full_name or self.scope["user"].email
            
            await self.channel_layer.group_add(
                f"listener_notifications_{self.user_id}",
                self.channel_name
            )
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if self.scope["user"].is_authenticated:
            await self.channel_layer.group_discard(
                f"listener_notifications_{self.user_id}",
                self.channel_name
            )

    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'get_my_availability':
                await self.handle_get_my_availability()
            else:
                await self.send_error("Unknown message type")
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")
        except Exception as e:
            await self.send_error(f"Error: {str(e)}")

    async def handle_get_my_availability(self):
        """Get the current user's availability."""
        user = self.scope["user"]
        availability = await self.get_availability(user)
        
        if availability:
            await self.send_json({
                "type": "my_availability",
                "message": "Your current availability",
                "data": availability
            })
        else:
            await self.send_json({
                "type": "my_availability",
                "message": "No availability set yet",
                "data": None
            })

    async def availability_notification(self, event):
        """
        Receive availability notification from group.
        This is sent when the listener updates their availability.
        """
        await self.send_json({
            "type": "availability_notification",
            "message": event.get('message'),
            "data": event.get('data'),
            "timestamp": event.get('timestamp')
        })

    async def send_error(self, message):
        """Send error message to client."""
        await self.send_json({
            "type": "error",
            "message": message
        })

    async def send_json(self, data):
        """Send JSON data to WebSocket client."""
        await self.send(text_data=json.dumps(data))

    @database_sync_to_async
    def get_availability(self, user):
        """Get user's availability data."""
        try:
            availability = ListenerAvailability.objects.get(listener=user)
            serializer = ListenerAvailabilityDetailSerializer(availability)
            return _enrich_availability_payload(user, serializer.data)
        except ListenerAvailability.DoesNotExist:
            return None


class TalkerAvailabilityConsumer(PeriodicRefreshMixin, AsyncWebsocketConsumer):
    """
    WebSocket consumer for talkers to view listener availability.
    Talkers can connect with their token and search for listeners' availability.
    
    Connect with token parameter:
    ws://localhost:8005/ws/availability/my-availability/?token=eyJ0eXA...
    
    Commands:
    - get_listeners: Get all available listeners
    - search_listener: Search for a specific listener by ID or username
    - ping: Send ping to keep connection alive
    
    The connection automatically sends a heartbeat every 30 seconds to keep alive.
    """
    
    async def connect(self):
        """Handle WebSocket connection with token from query parameter."""
        self.user = None
        self.is_listener = False
        
        # Get token from query parameters
        query_string = self.scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        token = query_params.get('token', [None])[0]
        
        if token:
            self.user = await self.authenticate_user(token)
        
        if self.user and self.user.is_authenticated:
            # Accept connection first, then join group
            await self.accept()
            print(f"[WebSocket] User {self.user.id} ({self.user.email}) connected (user_type: {self.user.user_type})")
            
            # Check if user is a listener
            if self.user.user_type == 'listener':
                self.is_listener = True
                print(f"[WebSocket] User {self.user.id} is a listener - fetching their availability")
                
                # For listeners: send their own availability and join their notification group
                own_availability = await self.get_user_availability(self.user.id)
                
                if own_availability:
                    print(f"[WebSocket] Sending own availability to listener {self.user.id} with {len(own_availability.get('time_slots', []))} slots")
                    await self.send_json({
                        "type": "my_availability",
                        "message": "Your availability",
                        "data": own_availability
                    })
                else:
                    print(f"[WebSocket] No availability set for listener {self.user.id}")
                    await self.send_json({
                        "type": "no_availability",
                        "message": "No availability set yet. Please create your availability first.",
                        "data": None
                    })
                
                # Join listener's own notification group for real-time updates
                await self.channel_layer.group_add(
                    f"listener_notifications_{self.user.id}",
                    self.channel_name
                )
                print(f"[WebSocket] Listener {self.user.id} joined group: listener_notifications_{self.user.id}")
                
                # Start periodic refresh every 3 minutes to keep connection alive
                await self.start_periodic_refresh(self._send_listener_availability)
            else:
                # For talkers: send all listeners' availability
                listeners = await self.get_all_listeners_availability()
                print(f"[WebSocket] User {self.user.id} is a talker - sending {len(listeners)} listeners")
                await self.send_json({
                    "type": "listeners_list",
                    "message": "Available listeners",
                    "data": listeners,
                    "count": len(listeners)
                })
                # Join the availability updates group to see all listeners' updates
                await self.channel_layer.group_add(
                    "availability_updates",
                    self.channel_name
                )
                print(f"[WebSocket] Talker {self.user.id} joined group: availability_updates")
                
                # Start periodic refresh every 3 minutes to keep connection alive
                await self.start_periodic_refresh(self._send_all_listeners_availability)
        else:
            print(f"[WebSocket] Unauthorized connection attempt with token: {token[:20] if token else 'None'}...")
            await self.close(code=4001)  # Unauthorized
    
    @database_sync_to_async
    def authenticate_user(self, token):
        """Validate JWT token and return user."""
        try:
            decoded_token = AccessToken(token)
            user_id = decoded_token['user_id']
            return User.objects.get(id=user_id)
        except Exception:
            return AnonymousUser()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Stop periodic refresh task
        await self.stop_periodic_refresh()
        
        # Leave the availability updates group (for talkers)
        await self.channel_layer.group_discard(
            "availability_updates",
            self.channel_name
        )
        # Leave listener's own notification group (for listeners)
        if hasattr(self, 'user') and self.user:
            await self.channel_layer.group_discard(
                f"listener_notifications_{self.user.id}",
                self.channel_name
            )
    
    async def availability_update(self, event):
        """
        Receive availability update broadcast from channel layer.
        Sent when a listener updates their availability via REST API.
        """
        print(f"[WebSocket] Sending availability update to user: listener={event.get('listener_email')}")
        await self.send_json({
            "type": "availability_update",
            "message": "Listener availability updated",
            "listener_full_name": event.get('listener_full_name'),
            "listener_email": event.get('listener_email'),
            "data": event.get('data'),
            "timestamp": event.get('timestamp')
        })
    
    async def availability_notification(self, event):
        """
        Receive availability notification for the listener's own availability.
        Sent when the listener updates their own availability via REST API.
        """
        print(f"[WebSocket] Sending own availability update to listener")
        await self.send_json({
            "type": "my_availability_updated",
            "message": event.get('message'),
            "data": event.get('data'),
            "timestamp": event.get('timestamp')
        })
    
    async def _send_listener_availability(self):
        """Periodic callback: Send listener's availability every 3 minutes."""
        if hasattr(self, 'user') and self.user and self.user.user_type == 'listener':
            availability = await self.get_user_availability(self.user.id)
            if availability:
                await self.send_json({
                    "type": "my_availability",
                    "message": "Your availability",
                    "data": availability
                })
    
    async def _send_all_listeners_availability(self):
        """Periodic callback: Send all listeners' availability every 3 minutes."""
        if hasattr(self, 'user') and self.user and self.user.user_type == 'talker':
            listeners = await self.get_all_listeners_availability()
            await self.send_json({
                "type": "listeners_list",
                "message": "Available listeners",
                "data": listeners,
                "count": len(listeners)
            })
    
    async def receive(self, text_data):
        """Handle incoming messages."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'get_listeners':
                await self.handle_get_listeners(data)
            elif message_type == 'search_listener':
                await self.handle_search_listener(data)
            else:
                await self.send_error("Unknown message type")
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")
        except Exception as e:
            await self.send_error(f"Error: {str(e)}")
    
    async def handle_get_listeners(self, data):
        """Get all listeners with availability."""
        listeners = await self.get_all_listeners_availability()
        await self.send_json({
            "type": "listeners_list",
            "message": "Available listeners",
            "data": listeners,
            "count": len(listeners)
        })
    
    async def handle_search_listener(self, data):
        """Search for a specific listener."""
        listener_id = data.get('listener_id')
        
        if not listener_id:
            await self.send_error("listener_id is required")
            return
        
        listener_data = await self.get_listener_availability(listener_id)
        
        if listener_data:
            await self.send_json({
                "type": "listener_found",
                "message": "Listener availability",
                "data": listener_data
            })
        else:
            await self.send_json({
                "type": "listener_not_found",
                "message": f"Listener '{listener_id}' not found or has no availability"
            })
    
    @database_sync_to_async
    def get_all_listeners_availability(self):
        """Get all listeners with availability."""
        try:
            from django.db.models import Prefetch
            
            # Fetch with proper related data
            availabilities = ListenerAvailability.objects.select_related(
                'listener'
            ).prefetch_related(
                'time_slots'
            ).all()
            
            result = []
            for availability in availabilities:
                serializer = ListenerAvailabilityDetailSerializer(availability)
                data = _enrich_availability_payload(availability.listener, serializer.data)
                result.append({
                    "listener_id": availability.listener.id,
                    "listener_full_name": availability.listener.full_name,
                    "listener_email": availability.listener.email,
                    **data
                })
            return result
        except Exception as e:
            print(f"Error in get_all_listeners_availability: {str(e)}")
            return []
    
    @database_sync_to_async
    def get_user_availability(self, user_id):
        """Get the current user's own availability (for listeners)."""
        try:
            availability = ListenerAvailability.objects.select_related(
                'listener'
            ).prefetch_related(
                'time_slots'
            ).get(listener_id=user_id)
            
            serializer = ListenerAvailabilityDetailSerializer(availability)
            return _enrich_availability_payload(availability.listener, serializer.data)
        except ListenerAvailability.DoesNotExist:
            return None
        except Exception as e:
            print(f"Error in get_user_availability: {str(e)}")
            return None
    
    @database_sync_to_async
    def get_listener_availability(self, listener_identifier):
        """Get a specific listener's availability by ID or username."""
        try:
            try:
                # Try by ID first
                listener = User.objects.get(id=listener_identifier)
            except User.DoesNotExist:
                # Try by email
                listener = User.objects.get(email=listener_identifier)
            
            availability = ListenerAvailability.objects.select_related(
                'listener'
            ).prefetch_related(
                'time_slots'
            ).get(listener=listener)
            
            serializer = ListenerAvailabilityDetailSerializer(availability)
            data = _enrich_availability_payload(listener, serializer.data)
            return {
                "listener_id": listener.id,
                "listener_full_name": listener.full_name,
                "listener_email": listener.email,
                **data
            }
        except (ListenerAvailability.DoesNotExist, User.DoesNotExist):
            return None
        except Exception as e:
            print(f"Error in get_listener_availability: {str(e)}")
            return None
    
    async def send_error(self, message):
        """Send error message to client."""
        await self.send_json({
            "type": "error",
            "message": message
        })
    
    async def send_json(self, data):
        """Send JSON data to WebSocket client."""
        await self.send(text_data=json.dumps(data))


class TalkerListenerAvailabilityConsumer(PeriodicRefreshMixin, AsyncWebsocketConsumer):
    """
    WebSocket consumer for a talker watching one specific listener's availability.

    Route: ws://localhost:8005/ws/availability/listener/<listener_id>/?token=<jwt>
    """

    async def connect(self):
        self.user = None
        self.listener_id = self.scope.get('url_route', {}).get('kwargs', {}).get('listener_id')

        # Authenticate via query token
        query_string = self.scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        token = query_params.get('token', [None])[0]

        if token:
            self.user = await self.authenticate_user(token)

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        if not self.listener_id:
            await self.close(code=4000)
            return

        self.group_name = f"listener_availability_{self.listener_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        
        # Start periodic refresh every 3 minutes to keep connection alive
        await self.start_periodic_refresh(self._send_listener_availability_refresh)

        # Send initial snapshot for selected listener
        listener_data = await self.get_listener_availability(self.listener_id)
        if listener_data:
            await self.send_json({
                "type": "listener_availability",
                "message": "Listener availability",
                "data": listener_data,
            })
        else:
            await self.send_json({
                "type": "listener_not_found",
                "message": f"Listener '{self.listener_id}' not found or has no availability",
            })

    async def disconnect(self, close_code):
        # Stop periodic refresh task
        await self.stop_periodic_refresh()
        
        if hasattr(self, 'group_name') and self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
    
    async def _send_listener_availability_refresh(self):
        """Periodic callback: Send listener's availability every 3 minutes."""
        if hasattr(self, 'listener_id') and self.listener_id:
            listener_data = await self.get_listener_availability(self.listener_id)
            if listener_data:
                await self.send_json({
                    "type": "listener_availability",
                    "message": "Listener availability",
                    "data": listener_data,
                })

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'get_listener':
                listener_data = await self.get_listener_availability(self.listener_id)
                await self.send_json({
                    "type": "listener_availability",
                    "message": "Listener availability",
                    "data": listener_data,
                })
            elif message_type == 'ping':
                await self.send_json({"type": "pong"})
            else:
                await self.send_error("Unknown message type")
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")
        except Exception as e:
            await self.send_error(f"Error: {str(e)}")

    async def availability_update(self, event):
        await self.send_json({
            "type": "availability_update",
            "listener_username": event.get('listener_username'),
            "listener_full_name": event.get('listener_full_name'),
            "listener_email": event.get('listener_email'),
            "data": event.get('data'),
            "timestamp": event.get('timestamp'),
        })

    async def send_error(self, message):
        await self.send_json({
            "type": "error",
            "message": message
        })

    async def send_json(self, data):
        await self.send(text_data=json.dumps(data))

    @database_sync_to_async
    def authenticate_user(self, token):
        try:
            decoded_token = AccessToken(token)
            user_id = decoded_token['user_id']
            return User.objects.get(id=user_id)
        except Exception:
            return AnonymousUser()

    @database_sync_to_async
    def get_listener_availability(self, listener_identifier):
        try:
            listener = User.objects.get(id=listener_identifier)
            availability = ListenerAvailability.objects.select_related('listener').prefetch_related('time_slots').get(listener=listener)
            serializer = ListenerAvailabilityDetailSerializer(availability)
            data = _enrich_availability_payload(listener, serializer.data)
            return {
                "listener_id": listener.id,
                "listener_full_name": listener.full_name,
                "listener_email": listener.email,
                **data,
            }
        except (ListenerAvailability.DoesNotExist, User.DoesNotExist, ValueError):
            return None


class UserBookingListConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for users (talker/listener) to view their own booking list and details.
    Unified payload with all bookings (running, upcoming, completed) in a single message.

    Route: ws://localhost:8005/ws/bookings/my-bookings/?token=<jwt>
    """

    def _get_absolute_media_url(self, url_path):
        """Return absolute media URL for websocket payloads."""
        if not url_path:
            return None
        if url_path.startswith('http'):
            return url_path

        configured = getattr(settings, 'BACKEND_URL', '').strip().rstrip('/')
        if configured:
            return f"{configured}{url_path}"

        host = ''
        forwarded_proto = ''
        for header_name, header_value in self.scope.get('headers', []):
            if header_name == b'host':
                host = header_value.decode('utf-8').strip()
            elif header_name == b'x-forwarded-proto':
                forwarded_proto = header_value.decode('utf-8').split(',')[0].strip().lower()

        if not host:
            host = 'localhost:8000'

        is_local = host.startswith('localhost') or host.startswith('127.0.0.1')
        scheme = 'https' if forwarded_proto == 'https' or not is_local else 'http'

        return f"{scheme}://{host}{url_path}"

    async def connect(self):
        self.user = None
        self.start_tasks = []
        self.end_tasks = []
        self.change_monitor_task = None
        self.running_booking_id = None
        self.upcoming_signature = ''
        # Add user to booking updates group for real-time broadcasts
        self.booking_group_name = None

        query_string = self.scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        token = query_params.get('token', [None])[0]

        if token:
            self.user = await self.authenticate_user(token)

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        await self.accept()
        
        # Join user-specific group for booking updates
        self.booking_group_name = f"booking_updates_{self.user.id}"
        await self.channel_layer.group_add(self.booking_group_name, self.channel_name)
        
        await self._schedule_upcoming_booking_events(emit_on_running_change=False)
        await self._send_full_bookings_payload()
        self.upcoming_signature = await self.get_upcoming_bookings_signature()
        self.change_monitor_task = asyncio.create_task(self._monitor_upcoming_booking_changes())

    async def disconnect(self, close_code):
        if self.booking_group_name:
            await self.channel_layer.group_discard(self.booking_group_name, self.channel_name)
        
        for task in self.start_tasks:
            task.cancel()
        self.start_tasks = []
        for task in self.end_tasks:
            task.cancel()
        self.end_tasks = []
        if self.change_monitor_task:
            self.change_monitor_task.cancel()

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type in ['get_my_bookings', 'get_upcoming_bookings']:
                await self._schedule_upcoming_booking_events(emit_on_running_change=False)
                await self._send_full_bookings_payload()
                self.upcoming_signature = await self.get_upcoming_bookings_signature()
            elif message_type == 'get_booking_detail':
                booking_id = data.get('booking_id')
                if not booking_id:
                    await self.send_error('booking_id is required')
                    return
                booking_detail = await self.get_booking_detail_for_user(booking_id)
                if booking_detail is None:
                    await self.send_error('Booking not found for this user')
                    return
                await self.send_json({
                    'type': 'my_booking_detail',
                    'message': 'Booking detail',
                    'data': booking_detail,
                })
            else:
                await self.send_error('Unknown message type')
        except json.JSONDecodeError:
            await self.send_error('Invalid JSON')
        except Exception as e:
            await self.send_error(f'Error: {str(e)}')

    async def booking_update(self, event):
        """Receive booking update broadcast from channel layer."""
        await self.send_json(event.get('payload', {}))

    async def _send_full_bookings_payload(self):
        """
        Send unified bookings payload with all bookings sorted: running → upcoming → completed.
        Includes meeting and zim details embedded in running booking.
        """
        payload = await self.build_full_bookings_payload(self.running_booking_id)
        await self.send_json(payload)

    async def _schedule_upcoming_booking_events(self, emit_on_running_change=True):
        """Schedule asyncio tasks for booking start and end times."""
        for task in self.start_tasks:
            task.cancel()
        self.start_tasks = []
        for task in self.end_tasks:
            task.cancel()
        self.end_tasks = []

        schedule_items = await self.get_upcoming_booking_schedule_data()
        now = timezone.now()
        previous_running_booking_id = self.running_booking_id
        detected_running_booking_id = None

        for item in schedule_items:
            booking_id = item['booking_id']
            start_at = item['start_datetime']
            end_at = item['end_datetime']

            # Detect exactly one currently running booking for this user.
            if start_at <= now < end_at and detected_running_booking_id is None:
                detected_running_booking_id = booking_id

            # Schedule future start events only.
            start_delay_seconds = (start_at - now).total_seconds()
            if start_delay_seconds > 0:
                task = asyncio.create_task(self._send_at_start(booking_id, start_delay_seconds))
                self.start_tasks.append(task)

            # Schedule future end events only.
            end_delay_seconds = (end_at - now).total_seconds()
            if end_delay_seconds > 0:
                task = asyncio.create_task(self._send_at_end(booking_id, end_delay_seconds))
                self.end_tasks.append(task)

        self.running_booking_id = detected_running_booking_id

        # Refresh immediately if running booking changed due to rescheduling.
        if emit_on_running_change and previous_running_booking_id != self.running_booking_id:
            await self._send_full_bookings_payload()

    async def _send_at_start(self, booking_id, delay_seconds):
        try:
            await asyncio.sleep(delay_seconds)
            self.running_booking_id = booking_id
            await self._send_full_bookings_payload()
        except asyncio.CancelledError:
            return

    async def _send_at_end(self, booking_id, delay_seconds):
        try:
            await asyncio.sleep(delay_seconds)
            await self.release_booking_listener_earnings(booking_id)
            if self.running_booking_id == booking_id:
                self.running_booking_id = None
            await self._send_full_bookings_payload()
        except asyncio.CancelledError:
            return

    @database_sync_to_async
    def release_booking_listener_earnings(self, booking_id):
        booking = SessionBooking.objects.filter(id=booking_id).first()
        if not booking:
            return False
        return booking.release_listener_earnings_if_due()

    async def _monitor_upcoming_booking_changes(self):
        try:
            while True:
                await asyncio.sleep(10)
                latest_signature = await self.get_upcoming_bookings_signature()
                if latest_signature != self.upcoming_signature:
                    self.upcoming_signature = latest_signature
                    await self._schedule_upcoming_booking_events(emit_on_running_change=False)
                    await self._send_full_bookings_payload()
        except asyncio.CancelledError:
            return

    async def send_error(self, message):
        await self.send_json({
            'type': 'error',
            'message': message,
        })

    async def send_json(self, data):
        await self.send(text_data=json.dumps(data))

    @database_sync_to_async
    def authenticate_user(self, token):
        try:
            decoded_token = AccessToken(token)
            user_id = decoded_token['user_id']
            return User.objects.get(id=user_id)
        except Exception:
            return AnonymousUser()

    @database_sync_to_async
    def get_upcoming_bookings_for_user(self):
        now = timezone.now()
        bookings = SessionBooking.objects.select_related('talker', 'listener', 'package').filter(
            Q(talker=self.user) | Q(listener=self.user),
            status='completed',
            booking_date__gte=now.date(),
        ).order_by('booking_date', 'start_time')[:200]

        upcoming_bookings = []
        for booking in bookings:
            if booking.start_datetime_aware >= now:
                upcoming_bookings.append(self._serialize_booking(booking))

        return upcoming_bookings

    @database_sync_to_async
    def get_upcoming_booking_schedule_data(self):
        now = timezone.now()
        bookings = SessionBooking.objects.filter(
            Q(talker=self.user) | Q(listener=self.user),
            status='completed',
            booking_date__gte=now.date(),
        ).only('id', 'booking_date', 'start_time', 'end_time').order_by('booking_date', 'start_time')[:200]

        schedule_items = []
        for booking in bookings:
            start_dt = booking.start_datetime_aware
            end_dt = timezone.make_aware(
                datetime.combine(booking.booking_date, booking.end_time),
                timezone.get_current_timezone(),
            )
            if end_dt >= now:
                schedule_items.append({
                    'booking_id': str(booking.id),
                    'start_datetime': start_dt,
                    'end_datetime': end_dt,
                })

        return schedule_items

    @database_sync_to_async
    def get_upcoming_bookings_signature(self):
        now = timezone.now()
        bookings = SessionBooking.objects.filter(
            Q(talker=self.user) | Q(listener=self.user),
            status='completed',
            booking_date__gte=now.date(),
        ).only('id', 'updated_at', 'booking_date', 'start_time').order_by('booking_date', 'start_time')[:300]

        parts = []
        for booking in bookings:
            if booking.start_datetime_aware >= now:
                parts.append(f"{booking.id}:{booking.updated_at.isoformat()}")

        return '|'.join(parts)

    @database_sync_to_async
    def build_full_bookings_payload(self, running_booking_id=None):
        """
        Build unified bookings payload with all bookings (running, upcoming, completed).
        Sorted: running → upcoming → completed.
        Includes meeting and zim details embedded in running booking.
        """
        now = timezone.now()
        bookings_qs = SessionBooking.objects.select_related('talker', 'listener', 'package').filter(
            Q(talker=self.user) | Q(listener=self.user),
            status='completed',
            booking_date__gte=now.date(),
        ).order_by('booking_date', 'start_time')[:500]

        running_bookings = []
        upcoming_bookings = []
        completed_bookings = []

        # Resolve exactly one running booking id for this payload.
        running_booking_resolved = None
        if running_booking_id:
            for booking in bookings_qs:
                if str(booking.id) != str(running_booking_id):
                    continue
                meeting_end = timezone.make_aware(
                    datetime.combine(booking.booking_date, booking.end_time),
                    timezone.get_current_timezone(),
                )
                if booking.start_datetime_aware <= now < meeting_end:
                    running_booking_resolved = str(booking.id)
                    break

        # Fallback: detect first active booking by time window if no valid running id.
        if running_booking_resolved is None:
            for booking in bookings_qs:
                meeting_end = timezone.make_aware(
                    datetime.combine(booking.booking_date, booking.end_time),
                    timezone.get_current_timezone(),
                )
                if booking.start_datetime_aware <= now < meeting_end:
                    running_booking_resolved = str(booking.id)
                    break

        for booking in bookings_qs:
            serialized = self._serialize_booking(booking)
            meeting_end = timezone.make_aware(
                datetime.combine(booking.booking_date, booking.end_time),
                timezone.get_current_timezone(),
            )

            # Check if this is the single running booking
            if running_booking_resolved and str(booking.id) == running_booking_resolved:
                if now >= booking.start_datetime_aware and now < meeting_end:
                    serialized['meeting_status'] = 'running'
                    serialized['state'] = 'running'
                    serialized['meeting_started_at'] = now.isoformat()

                    # Fetch meeting and zim info for running booking
                    from chat.call_models import CallSession
                    from chat.call_serializers import CallSessionSerializer
                    from chat.zim_utils import generate_zim_tokens_for_call

                    session = CallSession.objects.filter(
                        talker=booking.talker,
                        listener=booking.listener,
                        status__in=['connecting', 'active'],
                    ).order_by('-created_at').first()

                    if not session:
                        session = CallSession.objects.create(
                            talker=booking.talker,
                            listener=booking.listener,
                            total_minutes_purchased=booking.duration_minutes,
                            status='connecting',
                            call_type='audio',
                        )

                    if session:
                        meeting_data = CallSessionSerializer(session).data
                        meeting_data['call_type'] = session.call_type
                        serialized['meeting'] = meeting_data

                    if session:
                        zim_tokens = generate_zim_tokens_for_call(
                            talker_user=booking.talker,
                            listener_user=booking.listener,
                            expire_time_in_seconds=7200,
                        )
                        serialized['zim'] = {
                            'app_id': zim_tokens['app_id'],
                            'talker': {
                                'user_id': zim_tokens['talker']['user_id'],
                                'username': zim_tokens['talker']['username'],
                                'token': zim_tokens['talker']['token'],
                            },
                            'listener': {
                                'user_id': zim_tokens['listener']['user_id'],
                                'username': zim_tokens['listener']['username'],
                                'token': zim_tokens['listener']['token'],
                            },
                            'expires_at': zim_tokens['expires_at'],
                            'expire_time_seconds': zim_tokens['expire_time_seconds'],
                        }

                    running_bookings.append(serialized)
                else:
                    serialized['meeting_status'] = 'completed'
                    completed_bookings.append(serialized)
            # Categorize by time
            elif booking.start_datetime_aware > now:
                serialized['meeting_status'] = 'upcoming'
                upcoming_bookings.append(serialized)
            elif now >= booking.start_datetime_aware and now < meeting_end:
                # Overlapping active slots are downgraded so only one booking is marked running.
                serialized['meeting_status'] = 'upcoming'
                upcoming_bookings.append(serialized)
            else:
                serialized['meeting_status'] = 'completed'
                completed_bookings.append(serialized)

        # Combine: running first, then upcoming, then completed
        all_bookings = running_bookings + upcoming_bookings + completed_bookings

        return {
            'type': 'upcoming_bookings',
            'message': 'Your bookings',
            'count': len(all_bookings),
            'running_count': len(running_bookings),
            'upcoming_count': len(upcoming_bookings),
            'completed_count': len(completed_bookings),
            'data': all_bookings,
        }

    @database_sync_to_async
    def get_booking_detail_for_user(self, booking_id):
        booking = SessionBooking.objects.select_related('talker', 'listener', 'package').filter(
            id=booking_id,
        ).filter(
            Q(talker=self.user) | Q(listener=self.user)
        ).first()

        if not booking:
            return None

        return self._serialize_booking(booking)

    def _serialize_booking(self, booking):
        role_in_booking = 'talker' if booking.talker_id == self.user.id else 'listener'
        now = timezone.now()
        seconds_left = (booking.start_datetime_aware - now).total_seconds()
        minutes_left_to_start = max(0, int(math.ceil(seconds_left / 60)))

        talker_profile = getattr(booking.talker, 'talker_profile', None)
        listener_profile = getattr(booking.listener, 'listener_profile', None)
        talker_image = None
        listener_image = None
        if talker_profile and getattr(talker_profile, 'profile_image', None):
            talker_image = self._get_absolute_media_url(talker_profile.profile_image.url)
        if listener_profile and getattr(listener_profile, 'profile_image', None):
            listener_image = self._get_absolute_media_url(listener_profile.profile_image.url)

        return {
            'id': str(booking.id),
            'role_in_booking': role_in_booking,
            'status': booking.status,
            'booking_date': booking.booking_date.isoformat(),
            'start_time': booking.start_time.strftime('%H:%M:%S'),
            'end_time': booking.end_time.strftime('%H:%M:%S'),
            'minutes_left_to_start': minutes_left_to_start,
            'duration_minutes': booking.duration_minutes,
            'buffer_time_minutes': booking.buffer_time_minutes,
            'talker': {
                'id': booking.talker_id,
                'email': booking.talker.email,
                'full_name': booking.talker.full_name,
                'profile_image_url': talker_image,
            },
            'listener': {
                'id': booking.listener_id,
                'email': booking.listener.email,
                'full_name': booking.listener.full_name,
                'profile_image_url': listener_image,
            },
            'package': {
                'id': booking.package_id,
                'name': booking.package.name if booking.package else None,
                'description': booking.package.description if booking.package else None,
                'media_type': booking.package.media_type if booking.package else None,
                'duration': booking.package.duration if booking.package else None,
            },
            'created_at': booking.created_at.isoformat(),
            'updated_at': booking.updated_at.isoformat(),
            'price': str(booking.price),
            'app_fee': str(booking.app_fee),
            'listener_amount': str(booking.listener_amount),
            'payment_link': booking.payment_link,
            'transaction_id': booking.transaction_id,
            'payment_completed_at': booking.payment_completed_at.isoformat() if booking.payment_completed_at else None,
            'payment_expires_at': booking.payment_expires_at.isoformat() if booking.status in ['pending', 'payment_pending'] else None,
            'payment': {
                'currency': 'USD',
                'price': str(booking.price),
                'app_fee': str(booking.app_fee),
                'listener_amount': str(booking.listener_amount),
                'payment_link': booking.payment_link,
                'transaction_id': booking.transaction_id,
                'is_paid': booking.payment_completed_at is not None,
                'payment_completed_at': booking.payment_completed_at.isoformat() if booking.payment_completed_at else None,
                'payment_expires_at': booking.payment_expires_at.isoformat() if booking.status in ['pending', 'payment_pending'] else None,
            },
        }
