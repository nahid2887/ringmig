from datetime import date, datetime, timedelta
from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

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
    def is_payment_expired(self):
        if self.status not in ['pending', 'payment_pending']:
            return False
        if self.payment_completed_at is not None:
            return False
        return timezone.now() > self.payment_expires_at

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
