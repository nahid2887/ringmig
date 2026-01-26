import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import timedelta

from .call_models import CallSession, CallPackage

User = get_user_model()


class CallConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for handling voice/video calls between talker and listener.
    
    Connection URL: ws://domain/ws/call/<session_id>/
    
    Events sent to clients:
    - call_started: Call has started
    - time_warning: 3 minutes remaining warning
    - time_extended: Additional time was added
    - call_ending: Call is ending (time expired)
    - call_ended: Call has ended
    - error: Error occurred
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_id = None
        self.call_session = None
        self.user = None
        self.room_group_name = None
        self.time_check_task = None
        self.last_status = None  # Track last known status
    
    async def connect(self):
        """Handle WebSocket connection."""
        # Accept the connection first - MUST be done before any send/close operations
        await self.accept()
        
        self.user = self.scope['user']
        
        # Check if user is authenticated
        if not self.user or not self.user.is_authenticated:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'code': 4001,
                'message': 'Authentication required'
            }))
            await self.close(code=4001)
            return
        
        # Get session ID from URL
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.room_group_name = f'call_{self.session_id}'
        
        # Verify call session exists and user is participant
        self.call_session = await self.get_call_session()
        
        if not self.call_session:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'code': 4004,
                'message': 'Call session not found'
            }))
            await self.close(code=4004)
            return
        
        # Prevent reconnection if call is already ended
        if self.call_session.status in ['ended', 'timeout', 'completed', 'cancelled']:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'code': 4010,
                'message': f'Call session has ended and cannot be reconnected (status: {self.call_session.status})'
            }))
            await self.close(code=4010)
            return
        
        # Check if user is participant in this call
        is_participant = await self.verify_participant()
        if not is_participant:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'code': 4003,
                'message': 'You are not a participant in this call'
            }))
            await self.close(code=4003)
            return
        
        # Validate payment status before connecting
        can_connect = await self.validate_payment_status()
        if not can_connect:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'code': 4402,
                'message': 'Payment validation failed'
            }))
            await self.close(code=4402)
            return
        
        # Add to call group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        # Send welcome message with call details
        await self.send_call_status()
        
        # Store initial status for change detection
        self.last_status = await self.get_session_status()
        
        # DON'T auto-start call - listener must accept via /accept/ API first
        # await self.maybe_start_call()
        
        # Start time monitoring task
        self.time_check_task = asyncio.create_task(self.monitor_call_time())
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Cancel time monitoring
        if self.time_check_task:
            self.time_check_task.cancel()
        
        # Remove from call group
        if self.room_group_name:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
        
        # End call if it was active and consume the booking
        if self.call_session:
            await self.maybe_end_call()
            # Mark booking as consumed/completed
            await self.consume_booking_after_call()
    
    async def receive(self, text_data):
        """Handle messages from WebSocket."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'ping':
                # Heartbeat
                await self.send(text_data=json.dumps({
                    'type': 'pong'
                }))
            
            elif message_type == 'webrtc_signal':
                # Forward WebRTC signaling data to other participant
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'webrtc_signal',
                        'signal': data.get('signal'),
                        'sender_id': self.user.id
                    }
                )
            
            elif message_type == 'get_status':
                # Send current call status
                await self.send_call_status()
        
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
    
    async def webrtc_signal(self, event):
        """Forward WebRTC signal to client (but not to sender)."""
        if event['sender_id'] != self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'webrtc_signal',
                'signal': event['signal']
            }))
    
    async def call_event(self, event):
        """Send call event to client."""
        await self.send(text_data=json.dumps(event['data']))
    
    async def monitor_call_time(self):
        """Background task to monitor call time and status changes."""
        try:
            while True:
                await asyncio.sleep(2)  # Check every 2 seconds for status changes
                
                # Reload session from DB
                self.call_session = await self.get_call_session()
                
                if not self.call_session:
                    break
                
                current_status = self.call_session.status
                
                # Detect status change from "connecting" to "active"
                if self.last_status == 'connecting' and current_status == 'active':
                    # Call was just accepted! Send notification to all participants
                    await self.send_call_accepted_notification()
                
                # Update last status
                self.last_status = current_status
                
                # CRITICAL: Only count down if call has been ACCEPTED (started_at is set)
                # If started_at is None, listener hasn't accepted yet - NO countdown
                if self.call_session.started_at is None:
                    continue  # Keep checking, but don't count down or send updates
                
                # ONLY monitor time if status is 'active'
                if self.call_session.status != 'active':
                    continue
                
                remaining_minutes = await self.get_remaining_minutes()
                
                # End call if time expired (0 minutes)
                if remaining_minutes <= 0:
                    await self.end_call_time_expired()
                    break
                
                # Send 3-minute warning (only once)
                if remaining_minutes <= 3 and remaining_minutes > 0:
                    should_warn = await self.should_send_warning()
                    if should_warn:
                        await self.send_time_warning(remaining_minutes)
                        await self.mark_warning_sent()
        
        except asyncio.CancelledError:
            pass
    
    async def maybe_start_call(self):
        """Start call if both parties are ready."""
        # Check if both talker and listener are in the group
        # For simplicity, we'll start immediately
        # In production, you might wait for both to connect
        
        status = await self.get_session_status()
        
        if status == 'connecting':
            await self.start_call()
    
    async def start_call(self):
        """Mark call as started."""
        await self.update_session_status('active')
        await self.activate_initial_package()
        
        # Get complete call information
        remaining = await self.get_remaining_minutes()
        total = await self.get_total_minutes()
        status = await self.get_session_status()
        package_info = await self.get_package_info()
        started_at = await self.get_started_at()
        
        # Ensure all fields have values
        package_type = package_info.get('package_type') if package_info else 'audio'
        package_name = package_info.get('name') if package_info else 'standard'
        package_duration = package_info.get('duration_minutes') if package_info else total
        
        # Notify all participants with complete information
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'call_event',
                'data': {
                    'type': 'call_started',
                    'message': 'Call has started',
                    'status': status or 'active',
                    'remaining_minutes': round(remaining, 2) if remaining is not None else total,
                    'total_minutes': total or 0,
                    'package_type': package_type,
                    'package_name': package_name,
                    'package_duration': package_duration,
                    'started_at': started_at.isoformat() if started_at else timezone.now().isoformat(),
                    'session_id': str(self.session_id)
                }
            }
        )
    
    async def maybe_end_call(self):
        """End call if no more participants."""
        # In production, you'd check if both disconnected
        # For now, end when either disconnects
        pass
    
    async def end_call_time_expired(self):
        """End call because time expired."""
        await self.update_session_status('timeout')
        await self.consume_booking_after_call()
        
        # Notify all participants
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'call_event',
                'data': {
                    'type': 'call_ending',
                    'message': 'Call time has expired',
                    'reason': 'timeout'
                }
            }
        )
        
        # Wait a moment for message to be sent
        await asyncio.sleep(1)
        
        # Close WebSocket connection for all participants
        await self.close(code=1000)  # Normal closure
    
    async def send_time_warning(self, remaining_minutes):
        """Send warning about remaining time."""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'call_event',
                'data': {
                    'type': 'time_warning',
                    'message': f'{int(remaining_minutes)} minutes remaining',
                    'remaining_minutes': round(remaining_minutes, 2)
                }
            }
        )
    
    async def send_time_update(self, remaining_minutes):
        """Send automatic timer update to all participants."""
        minutes = int(remaining_minutes)
        seconds = int((remaining_minutes - minutes) * 60)
        
        # Format message based on remaining time
        if minutes >= 1:
            message = f'⏱️ {minutes} minute{"s" if minutes != 1 else ""} remaining'
        elif minutes == 0 and seconds > 0:
            message = f'⏱️ {seconds} seconds remaining'
        else:
            message = '⏱️ Call ending soon'
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'call_event',
                'data': {
                    'type': 'time_update',
                    'message': message,
                    'remaining_minutes': round(remaining_minutes, 2),
                    'minutes': minutes,
                    'seconds': seconds
                }
            }
        )
    
    async def send_call_accepted_notification(self):
        """Send notification when call is accepted (status changes from connecting to active)."""
        remaining = await self.get_remaining_minutes()
        total = await self.get_total_minutes()
        package_info = await self.get_package_info()
        started_at = await self.get_started_at()
        
        # Ensure all fields have values
        package_type = package_info.get('package_type') if package_info else 'audio'
        package_name = package_info.get('name') if package_info else 'standard'
        package_duration = package_info.get('duration_minutes') if package_info else total
        
        # Notify all participants that call is now active
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'call_event',
                'data': {
                    'type': 'call_accepted',
                    'message': '✅ Call accepted - timer started',
                    'status': 'active',
                    'status_display': '✅ Call Active',
                    'remaining_minutes': round(remaining, 2) if remaining is not None else total,
                    'total_minutes': total or 0,
                    'package_type': package_type,
                    'package_name': package_name,
                    'package_duration': package_duration,
                    'started_at': started_at.isoformat() if started_at else timezone.now().isoformat(),
                    'session_id': str(self.session_id),
                    'accepted': True,
                    'timer_running': True
                }
            }
        )
    
    async def send_call_status(self):
        """Send current call status to client on connect/reconnect."""
        remaining = await self.get_remaining_minutes()
        total = await self.get_total_minutes()
        status = await self.get_session_status()
        package_info = await self.get_package_info()
        started_at = await self.get_started_at()
        
        # Ensure all fields have values
        package_type = package_info.get('package_type') if package_info else 'audio'
        package_name = package_info.get('name') if package_info else 'standard'
        package_duration = package_info.get('duration_minutes') if package_info else total
        
        # Check if call has been accepted (started_at is set)
        call_accepted = started_at is not None
        
        # Different messages based on acceptance status
        if not call_accepted:
            # Call NOT accepted yet - timer NOT running
            message = '⏳ Waiting for listener to accept call'
            status_display = '⏳ Waiting for acceptance'
            # Show total duration, not remaining (timer not started)
            time_display = total
            timer_running = False
        elif status == 'active':
            # Call accepted - timer IS running
            message = '✅ Call is active - timer counting down'
            status_display = '✅ Call Active'
            # Show actual remaining time
            time_display = round(remaining, 2) if remaining is not None else total
            timer_running = True
        else:
            # Other statuses (ended, declined, etc.)
            message = f'Call status: {status}'
            status_display = status
            time_display = round(remaining, 2) if remaining is not None else 0
            timer_running = False
        
        await self.send(text_data=json.dumps({
            'type': 'call_status',
            'message': message,
            'status': status or 'connecting',
            'status_display': status_display,
            'remaining_minutes': time_display,
            'total_minutes': total or 0,
            'package_type': package_type,
            'package_name': package_name,
            'package_duration': package_duration,
            'started_at': started_at.isoformat() if started_at else None,
            'session_id': str(self.session_id),
            'accepted': call_accepted,
            'timer_running': timer_running,
            'waiting_for_accept': not call_accepted
        }))
    
    # Database operations (must be wrapped with database_sync_to_async)
    
    @database_sync_to_async
    def get_call_session(self):
        """Get call session from database."""
        try:
            return CallSession.objects.select_related('talker', 'listener').get(
                id=self.session_id
            )
        except CallSession.DoesNotExist:
            return None
    
    @database_sync_to_async
    def verify_participant(self):
        """Check if user is participant in the call."""
        return (
            self.call_session.talker_id == self.user.id or
            self.call_session.listener_id == self.user.id
        )
    
    @database_sync_to_async
    def get_session_status(self):
        """Get session status."""
        return self.call_session.status
    
    @database_sync_to_async
    def update_session_status(self, status):
        """Update session status."""
        self.call_session.status = status
        if status == 'active' and not self.call_session.started_at:
            self.call_session.started_at = timezone.now()
        elif status in ['ended', 'timeout']:
            self.call_session.ended_at = timezone.now()
            # Calculate actual minutes used
            if self.call_session.started_at:
                elapsed = (timezone.now() - self.call_session.started_at).total_seconds() / 60
                self.call_session.minutes_used = Decimal(str(round(elapsed, 2)))
        
        self.call_session.save()
    
    @database_sync_to_async
    def activate_initial_package(self):
        """Activate the initial package when call starts."""
        if self.call_session.initial_package:
            package = self.call_session.initial_package
            package.status = 'in_progress'  # Changed from 'active' to match STATUS_CHOICES
            package.activated_at = timezone.now()
            package.call_session = self.call_session
            package.save()
    
    @database_sync_to_async
    def get_remaining_minutes(self):
        """Get remaining minutes."""
        return self.call_session.get_remaining_minutes()
    
    @database_sync_to_async
    def get_total_minutes(self):
        """Get total minutes purchased."""
        return self.call_session.total_minutes_purchased
    
    @database_sync_to_async
    def get_package_info(self):
        """Get package information."""
        package = self.call_session.initial_package or self.call_session.call_package
        if package and package.package:
            return {
                'package_type': package.package.package_type,
                'name': package.package.name,
                'duration_minutes': package.package.duration_minutes
            }
        return None
    
    @database_sync_to_async
    def get_started_at(self):
        """Get call start time."""
        return self.call_session.started_at
    
    @database_sync_to_async
    def should_send_warning(self):
        """Check if warning should be sent."""
        return self.call_session.should_send_warning()
    
    @database_sync_to_async
    def mark_warning_sent(self):
        """Mark that warning was sent."""
        self.call_session.last_warning_sent = True
        self.call_session.save(update_fields=['last_warning_sent'])
    
    @database_sync_to_async
    def validate_payment_status(self):
        """Validate that payment is completed before allowing connection."""
        return self.call_session.can_connect()
    
    @database_sync_to_async
    def consume_booking_after_call(self):
        """Mark booking as consumed/completed after call ends."""
        if self.call_session.status in ['ended', 'timeout', 'active']:
            self.call_session.consume_booking()
    
    # Event Handlers (from group_send)
    
    async def minutes_extended(self, event):
        """
        Handle minutes_extended event from group_send.
        
        Broadcast when talker extends minutes during call.
        Updates both talker and listener in real-time.
        """
        # Send to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'minutes_extended',
            'added_minutes': event['added_minutes'],
            'new_total_minutes': event['new_total_minutes'],
            'remaining_minutes': event['remaining_minutes'],
            'extend_package_id': event.get('extend_package_id'),
            'timestamp': event['timestamp'],
            'message': f"Call extended by {event['added_minutes']} minutes!"
        }))
    
    async def time_extended(self, event):
        """Handle time_extended event for UI updates."""
        await self.send(text_data=json.dumps({
            'type': 'time_extended',
            'added_time': event.get('added_time'),
            'total_minutes': event.get('total_minutes'),
            'remaining_minutes': event.get('remaining_minutes')
        }))
    
    async def call_ending(self, event):
        """Handle call_ending notification."""
        await self.send(text_data=json.dumps({
            'type': 'call_ending',
            'reason': event.get('reason', 'Call time expired'),
            'timestamp': event.get('timestamp')
        }))
    
    async def call_ended(self, event):
        """Handle call_ended notification and close WebSocket connection."""
        await self.send(text_data=json.dumps({
            'type': 'call_ended',
            'message': event.get('data', {}).get('message', 'Call has ended'),
            'reason': event.get('data', {}).get('reason', 'Call ended'),
            'duration_minutes': event.get('data', {}).get('duration_minutes', 0),
            'ended_by': event.get('data', {}).get('ended_by'),
            'ended_by_name': event.get('data', {}).get('ended_by_name'),
            'timestamp': event.get('data', {}).get('timestamp'),
            'session_id': event.get('data', {}).get('session_id'),
            'status': 'ended'
        }))
        
        # Wait a moment for the message to be sent
        await asyncio.sleep(0.5)
        
        # Close the WebSocket connection
        await self.close(code=1000)  # Normal closure
    
    async def error(self, event):
        """Handle error event."""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'code': event.get('code', 500),
            'message': event.get('message', 'An error occurred'),
            'timestamp': event.get('timestamp')
        }))
