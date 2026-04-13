from datetime import date, datetime, timedelta
from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

User = get_user_model()


class DayOfWeek(models.IntegerChoices):
    """Choices for days of the week."""
    MONDAY = 0, 'Monday'
    TUESDAY = 1, 'Tuesday'
    WEDNESDAY = 2, 'Wednesday'
    THURSDAY = 3, 'Thursday'
    FRIDAY = 4, 'Friday'
    SATURDAY = 5, 'Saturday'
    SUNDAY = 6, 'Sunday'


class ListenerAvailability(models.Model):
    """
    Represents a Listener's availability settings.
    Manages weekly schedule with buffer time between sessions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listener = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='booking_availability'
    )
    buffer_time_minutes = models.IntegerField(
        default=5,
        help_text="Buffer time in minutes between consecutive sessions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Listener Availability"
        verbose_name_plural = "Listener Availabilities"

    def __str__(self):
        return f"Availability for {self.listener.email} (Buffer: {self.buffer_time_minutes}min)"

    def get_available_slots_for_day(self, day_of_week: int):
        """Get all time slots for a specific day of the week."""
        return self.time_slots.filter(day_of_week=day_of_week).order_by('start_time')


class TimeSlot(models.Model):
    """
    Represents a single time slot on a specific day of the week.
    Multiple time slots can exist for the same day.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    availability = models.ForeignKey(
        ListenerAvailability,
        on_delete=models.CASCADE,
        related_name='time_slots'
    )
    day_of_week = models.IntegerField(
        choices=DayOfWeek.choices,
        help_text="Day of the week (0=Monday, 6=Sunday)"
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['day_of_week', 'start_time']
        unique_together = ('availability', 'day_of_week', 'start_time', 'end_time')
        verbose_name = "Time Slot"
        verbose_name_plural = "Time Slots"

    def clean(self):
        """Validate that start_time is before end_time."""
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        day_name = DayOfWeek(self.day_of_week).label
        return f"{day_name}: {self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"

    def duration_minutes(self) -> int:
        """Calculate duration of this time slot in minutes."""
        from datetime import datetime, date
        start = datetime.combine(date.today(), self.start_time)
        end = datetime.combine(date.today(), self.end_time)
        return int((end - start).total_seconds() / 60)


class UniversalBookingPackage(models.Model):
    """
    Admin-created universal booking packages for listeners.
    """

    PACKAGE_TYPE_CHOICES = [
        ('one_time', _('One-Time')),
        ('recurring', _('Recurring')),
    ]

    MEDIA_TYPE_CHOICES = [
        ('audio', _('Audio')),
        ('video', _('Video')),
    ]

    name = models.CharField(
        max_length=100,
        help_text=_('Package name')
    )
    description = models.TextField(
        blank=True,
        help_text=_('Package description')
    )
    package_type = models.CharField(
        max_length=20,
        choices=PACKAGE_TYPE_CHOICES,
        default='one_time',
        help_text=_('Type of booking package')
    )
    media_type = models.CharField(
        max_length=20,
        choices=MEDIA_TYPE_CHOICES,
        default='audio',
        help_text=_('Meeting media type')
    )
    duration = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text=_('Session duration in minutes')
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_('Price in USD')
    )
    app_fee_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('10.00'),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_('App commission percentage')
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_('Package available for booking')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Universal Booking Package'
        verbose_name_plural = 'Universal Booking Packages'
        ordering = ['duration', 'price']

    def __str__(self):
        return f"{self.name} ({self.duration} min) - ${self.price}"

    @property
    def app_fee(self):
        """Calculate app fee amount."""
        if self.price is None or self.app_fee_percentage is None:
            return Decimal('0.00')
        return (self.price * self.app_fee_percentage) / 100

    @property
    def listener_amount(self):
        """Calculate listener earnings."""
        if self.price is None:
            return Decimal('0.00')
        return self.price - self.app_fee


class SessionBooking(models.Model):
    """Talker-to-listener booking with payment and scheduled slot."""

    PAYMENT_TIMEOUT_MINUTES = 3

    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('payment_pending', _('Payment Pending')),
        ('completed', _('Completed')),
        ('cancelled', _('Cancelled')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    talker = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='session_bookings_as_talker',
        help_text='Talker who is booking the session'
    )
    listener = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='session_bookings_as_listener',
        help_text='Listener providing the session'
    )
    package = models.ForeignKey(
        UniversalBookingPackage,
        on_delete=models.SET_NULL,
        null=True,
        related_name='session_bookings',
        help_text='Booking package selected'
    )

    booking_date = models.DateField(help_text='Date of the booking')
    start_time = models.TimeField(help_text='Start time of the session')
    end_time = models.TimeField(help_text='End time of the session')
    duration_minutes = models.PositiveIntegerField(help_text='Duration in minutes')
    buffer_time_minutes = models.PositiveIntegerField(
        default=5,
        help_text='Buffer time after booking before next slot'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text='Current booking status'
    )

    payment_link = models.URLField(
        null=True,
        blank=True,
        help_text='Payment link for the booking'
    )
    transaction_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='Payment transaction ID'
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Price charged for booking'
    )
    app_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='App commission fee'
    )
    listener_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Amount paid to listener'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    payment_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When payment was completed'
    )
    talker_reminder_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When 20-minute reminder email was sent to talker'
    )
    listener_reminder_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When 20-minute reminder email was sent to listener'
    )
    listener_earnings_released = models.BooleanField(
        default=False,
        help_text='Whether listener earnings were added to available balance after session end'
    )
    listener_earnings_released_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When listener earnings were released to balance'
    )

    class Meta:
        verbose_name = 'Session Booking'
        verbose_name_plural = 'Session Bookings'
        ordering = ['-booking_date', 'start_time']
        indexes = [
            models.Index(fields=['listener', 'booking_date']),
            models.Index(fields=['talker', 'status']),
            models.Index(fields=['status', 'booking_date']),
        ]

    def __str__(self):
        return f"{self.booking_date} {self.start_time}-{self.end_time} ({self.status})"

    @property
    def start_datetime(self):
        return datetime.combine(self.booking_date, self.start_time)

    @property
    def end_datetime(self):
        return datetime.combine(self.booking_date, self.end_time)

    @property
    def next_available_datetime(self):
        return self.end_datetime + timedelta(minutes=self.buffer_time_minutes)

    @property
    def payment_expires_at(self):
        return self.created_at + timedelta(minutes=self.PAYMENT_TIMEOUT_MINUTES)

    @property
    def start_datetime_aware(self):
        start_dt = datetime.combine(self.booking_date, self.start_time)
        if timezone.is_naive(start_dt):
            return timezone.make_aware(start_dt, timezone.get_current_timezone())
        return start_dt

    @property
    def is_payment_expired(self):
        if self.status not in ['pending', 'payment_pending']:
            return False
        if self.payment_completed_at is not None:
            return False
        return timezone.now() > self.payment_expires_at

    def _build_reminder_subject(self):
        return 'Reminder: Your session starts in 20 minutes'

    def release_listener_earnings_if_due(self):
        """
        Release listener earnings to ListenerBalance exactly once after meeting end.
        Returns True if earnings were released in this call, else False.
        """
        from listener.models import ListenerBalance

        now = timezone.now()
        meeting_end = timezone.make_aware(
            datetime.combine(self.booking_date, self.end_time),
            timezone.get_current_timezone(),
        )

        if self.listener_earnings_released:
            return False
        if self.status != 'completed' or not self.payment_completed_at:
            return False
        if now < meeting_end:
            return False

        with transaction.atomic():
            locked_booking = SessionBooking.objects.select_for_update().select_related('listener').get(id=self.id)
            if locked_booking.listener_earnings_released:
                return False

            balance, _ = ListenerBalance.objects.select_for_update().get_or_create(
                listener=locked_booking.listener,
                defaults={'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00')},
            )
            balance.add_earnings(locked_booking.listener_amount)

            locked_booking.listener_earnings_released = True
            locked_booking.listener_earnings_released_at = now
            locked_booking.save(update_fields=['listener_earnings_released', 'listener_earnings_released_at', 'updated_at'])

        return True

    def _build_reminder_message(self, recipient_role):
        listener_name = self.listener.full_name or self.listener.email
        talker_name = self.talker.full_name or self.talker.email
        session_start = self.start_datetime_aware.astimezone(timezone.get_current_timezone())
        session_end = timezone.make_aware(
            datetime.combine(self.booking_date, self.end_time),
            timezone.get_current_timezone()
        ).astimezone(timezone.get_current_timezone())

        if recipient_role == 'talker':
            greeting = f"Hello {talker_name},"
            role_line = f"Your session with listener {listener_name} starts in 20 minutes."
        else:
            greeting = f"Hello {listener_name},"
            role_line = f"Your session with talker {talker_name} starts in 20 minutes."

        return (
            f"{greeting}\n\n"
            f"{role_line}\n"
            f"Date: {self.booking_date.isoformat()}\n"
            f"Start Time: {session_start.strftime('%H:%M %Z')}\n"
            f"End Time: {session_end.strftime('%H:%M %Z')}\n"
            f"Duration: {self.duration_minutes} minutes\n\n"
            "Please be ready before the session starts."
        )

    def _build_reminder_notification(self, recipient_role):
        listener_name = self.listener.full_name or self.listener.email
        talker_name = self.talker.full_name or self.talker.email
        recipient_name = talker_name if recipient_role == 'talker' else listener_name

        return {
            'type': 'booking_reminder_notification',
            'booking_id': str(self.id),
            'session_id': str(self.id),
            'recipient_role': recipient_role,
            'booking_date': self.booking_date.isoformat(),
            'start_time': self.start_time.strftime('%H:%M:%S'),
            'end_time': self.end_time.strftime('%H:%M:%S'),
            'duration_minutes': self.duration_minutes,
            'talker': {
                'id': self.talker_id,
                'email': self.talker.email,
                'full_name': talker_name,
            },
            'listener': {
                'id': self.listener_id,
                'email': self.listener.email,
                'full_name': listener_name,
            },
            'message': f'Your booking starts in 20 minutes, {recipient_name}.',
            'timestamp': timezone.now().isoformat(),
        }

    def _send_booking_websocket_reminder(self, recipient_role):
        notification = self._build_reminder_notification(recipient_role)
        group_name = f"user_{self.talker_id}_notifications" if recipient_role == 'talker' else f"user_{self.listener_id}_notifications"

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return

        async_to_sync(channel_layer.group_send)(
            group_name,
            notification,
        )

    @classmethod
    def send_upcoming_start_reminders(cls, minutes_before=20):
        """
        Send reminder emails for sessions starting within the next N minutes.
        Sends separately to talker/listener and tracks each send time to avoid duplicates.
        """
        now = timezone.now()
        upper_bound = now + timedelta(minutes=minutes_before)

        candidate_dates = {now.date(), upper_bound.date()}
        queryset = cls.objects.select_related('talker', 'listener').filter(
            booking_date__in=candidate_dates,
            status='completed',
        )

        stats = {
            'processed': 0,
            'talker_sent': 0,
            'listener_sent': 0,
            'failed': 0,
        }

        for booking in queryset:
            start_dt = booking.start_datetime_aware
            seconds_until_start = (start_dt - now).total_seconds()

            if seconds_until_start < 0:
                continue
            if seconds_until_start > minutes_before * 60:
                continue

            stats['processed'] += 1

            try:
                if booking.talker_reminder_sent_at is None and booking.talker and booking.talker.email:
                    send_mail(
                        subject=booking._build_reminder_subject(),
                        message=booking._build_reminder_message('talker'),
                        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                        recipient_list=[booking.talker.email],
                        fail_silently=False,
                    )
                    booking.talker_reminder_sent_at = timezone.now()
                    booking._send_booking_websocket_reminder('talker')
                    stats['talker_sent'] += 1

                if booking.listener_reminder_sent_at is None and booking.listener and booking.listener.email:
                    send_mail(
                        subject=booking._build_reminder_subject(),
                        message=booking._build_reminder_message('listener'),
                        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                        recipient_list=[booking.listener.email],
                        fail_silently=False,
                    )
                    booking.listener_reminder_sent_at = timezone.now()
                    booking._send_booking_websocket_reminder('listener')
                    stats['listener_sent'] += 1

                if booking.talker_reminder_sent_at or booking.listener_reminder_sent_at:
                    booking.save(update_fields=['talker_reminder_sent_at', 'listener_reminder_sent_at', 'updated_at'])

            except Exception:
                stats['failed'] += 1

        return stats

    @classmethod
    def release_ended_listener_earnings(cls):
        """Release earnings for completed bookings whose end time has passed."""
        now = timezone.now()
        candidate_bookings = cls.objects.filter(
            status='completed',
            payment_completed_at__isnull=False,
            listener_earnings_released=False,
        ).select_related('listener')

        stats = {
            'processed': 0,
            'released': 0,
            'failed': 0,
        }

        for booking in candidate_bookings:
            meeting_end = timezone.make_aware(
                datetime.combine(booking.booking_date, booking.end_time),
                timezone.get_current_timezone(),
            )
            if now < meeting_end:
                continue

            stats['processed'] += 1
            try:
                if booking.release_listener_earnings_if_due():
                    stats['released'] += 1
            except Exception:
                stats['failed'] += 1

        return stats

    @classmethod
    def cleanup_expired_unpaid(cls, listener=None, booking_date=None):
        """Delete unpaid bookings older than payment timeout window."""
        threshold = timezone.now() - timedelta(minutes=cls.PAYMENT_TIMEOUT_MINUTES)
        queryset = cls.objects.filter(
            status__in=['pending', 'payment_pending'],
            payment_completed_at__isnull=True,
            created_at__lt=threshold,
        )

        if listener is not None:
            queryset = queryset.filter(listener=listener)
        if booking_date is not None:
            queryset = queryset.filter(booking_date=booking_date)

        deleted_count, _ = queryset.delete()
        return deleted_count

    @classmethod
    def check_slot_available(cls, listener, booking_date: date, start_time, duration_minutes: int):
        """
        Validate slot against listener availability and existing bookings with buffer.
        Returns (is_available, end_time, error_message).
        """
        try:
            availability = ListenerAvailability.objects.prefetch_related('time_slots').get(listener=listener)
        except ListenerAvailability.DoesNotExist:
            return False, None, 'Listener has no availability schedule'

        day_of_week = booking_date.weekday()
        day_slots = availability.time_slots.filter(day_of_week=day_of_week).order_by('start_time')
        if not day_slots.exists():
            return False, None, 'Listener is not available on this day'

        requested_start = datetime.combine(booking_date, start_time)
        requested_end = requested_start + timedelta(minutes=duration_minutes)
        requested_end_time = requested_end.time()

        inside_defined_slot = any(
            start_time >= slot.start_time and requested_end_time <= slot.end_time
            for slot in day_slots
        )
        if not inside_defined_slot:
            return False, requested_end_time, 'Selected time is outside listener availability window'

        # Clear stale unpaid bookings (older than payment timeout) so they don't block slots.
        cls.cleanup_expired_unpaid(listener=listener, booking_date=booking_date)

        existing_bookings = cls.objects.filter(
            listener=listener,
            booking_date=booking_date,
            status__in=['pending', 'payment_pending', 'completed']
        ).exclude(status='cancelled')

        for booking in existing_bookings:
            if booking.status in ['pending', 'payment_pending'] and booking.is_payment_expired:
                continue

            existing_start = datetime.combine(booking.booking_date, booking.start_time)
            existing_end_with_buffer = datetime.combine(
                booking.booking_date,
                booking.end_time
            ) + timedelta(minutes=booking.buffer_time_minutes)

            if requested_start < existing_end_with_buffer and requested_end > existing_start:
                return False, requested_end_time, 'Selected time overlaps an existing booking or buffer window'

        return True, requested_end_time, ''

    @classmethod
    def get_effective_availability(cls, listener, days=7, from_date=None, booking_statuses=None):
        """
        Return booking-adjusted availability for the next N days.
        Subtracts booked windows plus buffer time from listener's weekly slots.
        """
        if from_date is None:
            from_date = timezone.localdate()

        try:
            availability = ListenerAvailability.objects.prefetch_related('time_slots').get(listener=listener)
        except ListenerAvailability.DoesNotExist:
            return []

        # Keep payload clean: remove stale unpaid bookings before computing.
        cls.cleanup_expired_unpaid(listener=listener)

        end_date = from_date + timedelta(days=days - 1)
        if booking_statuses is None:
            booking_statuses = ['completed', 'pending', 'payment_pending']

        bookings = cls.objects.filter(
            listener=listener,
            booking_date__gte=from_date,
            booking_date__lte=end_date,
            status__in=booking_statuses,
        ).order_by('booking_date', 'start_time')

        bookings_by_date = {}
        for booking in bookings:
            bookings_by_date.setdefault(booking.booking_date, []).append(booking)

        weekly_slots = {}
        for slot in availability.time_slots.all():
            weekly_slots.setdefault(slot.day_of_week, []).append(slot)

        result = []

        for i in range(days):
            current_date = from_date + timedelta(days=i)
            weekday = current_date.weekday()
            day_slots = weekly_slots.get(weekday, [])
            if not day_slots:
                continue

            free_windows = []
            for slot in sorted(day_slots, key=lambda x: x.start_time):
                free_windows.append([
                    datetime.combine(current_date, slot.start_time),
                    datetime.combine(current_date, slot.end_time),
                ])

            for booking in bookings_by_date.get(current_date, []):
                block_start = datetime.combine(current_date, booking.start_time)
                block_end = datetime.combine(current_date, booking.end_time) + timedelta(
                    minutes=booking.buffer_time_minutes
                )

                updated_windows = []
                for window_start, window_end in free_windows:
                    # No overlap
                    if block_end <= window_start or block_start >= window_end:
                        updated_windows.append([window_start, window_end])
                        continue

                    # Left remainder
                    if block_start > window_start:
                        updated_windows.append([window_start, block_start])

                    # Right remainder
                    if block_end < window_end:
                        updated_windows.append([block_end, window_end])

                free_windows = updated_windows

            formatted_slots = []
            for window_start, window_end in free_windows:
                if window_end <= window_start:
                    continue
                duration_minutes = int((window_end - window_start).total_seconds() / 60)
                if duration_minutes <= 0:
                    continue
                formatted_slots.append({
                    'start_time': window_start.time().strftime('%H:%M:%S'),
                    'end_time': window_end.time().strftime('%H:%M:%S'),
                    'duration_minutes': duration_minutes,
                })

            result.append({
                'date': current_date.isoformat(),
                'day_of_week': weekday,
                'slots': formatted_slots,
            })

        return result
