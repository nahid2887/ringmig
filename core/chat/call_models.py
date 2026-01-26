from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

User = get_user_model()

# Import Booking and Payment models
try:
    from payment.models import Booking, Payment
except ImportError:
    Booking = None
    Payment = None


class UniversalCallPackage(models.Model):
    """Admin-created universal call packages (like BookingPackage)."""
    
    PACKAGE_TYPE_CHOICES = [
        ('audio', _('Audio Call')),
        ('video', _('Video Call')),
        ('both', _('Audio/Video Call')),
    ]
    
    name = models.CharField(max_length=100, help_text=_('Package name'))
    package_type = models.CharField(
        max_length=20,
        choices=PACKAGE_TYPE_CHOICES,
        default='audio',
        help_text=_('Type of call package')
    )
    duration_minutes = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text=_('Duration in minutes')
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
    is_active = models.BooleanField(default=True, help_text=_('Package available for purchase'))
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Universal Call Package'
        verbose_name_plural = 'Universal Call Packages'
        ordering = ['duration_minutes', 'price']
    
    def __str__(self):
        return f"{self.name} - {self.duration_minutes} min - ${self.price}"
    
    @property
    def app_fee(self):
        """Calculate app commission amount."""
        if self.price is None or self.app_fee_percentage is None:
            return Decimal('0.00')
        return (self.price * self.app_fee_percentage / 100).quantize(Decimal('0.01'))
    
    @property
    def listener_amount(self):
        """Calculate listener payout amount."""
        if self.price is None:
            return Decimal('0.00')
        return (self.price - self.app_fee).quantize(Decimal('0.01'))


class CallPackage(models.Model):
    """Purchased call package instance (like Booking)."""
    
    STATUS_CHOICES = [
        ('pending', _('Pending Payment')),      # Payment pending
        ('confirmed', _('Confirmed')),          # Payment successful
        ('in_progress', _('In Progress')),      # Call is active
        ('completed', _('Completed')),          # Call finished
        ('cancelled', _('Cancelled')),          # Cancelled
        ('refunded', _('Refunded')),            # Refunded
    ]
    
    talker = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='purchased_call_packages',
        limit_choices_to={'user_type': 'talker'}
    )
    listener = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='listener_call_packages',
        limit_choices_to={'user_type': 'listener'}
    )
    package = models.ForeignKey(
        UniversalCallPackage,
        on_delete=models.PROTECT,
        related_name='purchased_packages'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Pricing snapshot (stored at purchase time)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    app_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    listener_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # Session details
    purchased_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    actual_duration_minutes = models.IntegerField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True, help_text=_('When the package was used/extension was applied'))
    
    # Link to call session
    call_session = models.ForeignKey(
        'CallSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='packages'
    )
    
    # Payment tracking (Stripe)
    stripe_payment_intent_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    stripe_charge_id = models.CharField(max_length=255, blank=True, default='')
    stripe_customer_id = models.CharField(max_length=255, blank=True, default='')
    
    # Additional info
    notes = models.TextField(blank=True, default='')
    cancellation_reason = models.TextField(blank=True, default='')
    is_extension = models.BooleanField(
        default=False,
        help_text=_('Whether this is an extension package for additional minutes')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Call Package Purchase'
        verbose_name_plural = 'Call Package Purchases'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['talker', 'status']),
            models.Index(fields=['listener', 'status']),
            models.Index(fields=['status', '-created_at']),
        ]
    
    def __str__(self):
        return f"Call Package #{self.id}: {self.talker.email} -> {self.listener.email} ({self.status})"
    
    def confirm(self):
        """Mark package as confirmed after successful payment."""
        self.status = 'confirmed'
        self.save(update_fields=['status', 'updated_at'])
    
    def start_call(self):
        """Mark call as started."""
        self.status = 'in_progress'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])
    
    def complete_call(self):
        """Mark call as completed."""
        self.status = 'completed'
        self.ended_at = timezone.now()
        if self.started_at:
            duration = (self.ended_at - self.started_at).total_seconds() / 60
            self.actual_duration_minutes = int(duration)
        self.save(update_fields=['status', 'ended_at', 'actual_duration_minutes', 'updated_at'])
    
    def cancel(self, reason=''):
        """Cancel the call package."""
        self.status = 'cancelled'
        self.cancellation_reason = reason
        self.save(update_fields=['status', 'cancellation_reason', 'updated_at'])
    
    @property
    def payment_status(self):
        """Get payment status from Stripe payment intent."""
        # This would check actual payment status
        if self.status == 'confirmed':
            return 'succeeded'
        elif self.status == 'pending':
            return 'pending'
        return 'unknown'


class CallSession(models.Model):
    """Represents an active or completed call session."""
    
    STATUS_CHOICES = [
        ('connecting', _('Connecting')),    # WebSocket connecting
        ('active', _('Active')),            # Call in progress
        ('ended', _('Ended')),              # Call ended normally
        ('timeout', _('Timeout')),          # Call ended due to timeout
        ('failed', _('Failed')),            # Call failed to connect
    ]
    
    talker = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='talker_call_sessions',
        limit_choices_to={'user_type': 'talker'}
    )
    listener = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='listener_call_sessions',
        limit_choices_to={'user_type': 'listener'}
    )
    
    # Link to existing booking system
    booking = models.OneToOneField(
        'payment.Booking',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='call_session',
        help_text=_('Related booking if using booking system')
    )
    
    # Link to call package purchase
    call_package = models.OneToOneField(
        CallPackage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='active_call_session',
        help_text=_('Call package used for this session')
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='connecting'
    )
    
    # Time tracking
    total_minutes_purchased = models.IntegerField(
        default=0,
        help_text=_('Total minutes purchased for this call')
    )
    minutes_used = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Minutes actually used')
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    end_reason = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        default='',
        help_text=_('Reason why call ended')
    )
    last_warning_sent = models.BooleanField(
        default=False,
        help_text=_('Whether 3-minute warning was sent')
    )
    
    # Initial package that started the call
    initial_package = models.ForeignKey(
        CallPackage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='initial_sessions'
    )
    
    # Agora-specific fields for real-time communication
    agora_channel_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=_('Agora channel name for the call')
    )
    agora_talker_token = models.TextField(
        blank=True,
        null=True,
        help_text=_('Agora RTC token for talker')
    )
    agora_listener_token = models.TextField(
        blank=True,
        null=True,
        help_text=_('Agora RTC token for listener')
    )
    agora_talker_uid = models.IntegerField(
        blank=True,
        null=True,
        help_text=_('Agora UID for talker')
    )
    agora_listener_uid = models.IntegerField(
        blank=True,
        null=True,
        help_text=_('Agora UID for listener')
    )
    call_type = models.CharField(
        max_length=20,
        choices=[
            ('audio', _('Audio Call')),
            ('video', _('Video Call')),
        ],
        default='audio',
        help_text=_('Type of call based on package')
    )
    agora_tokens_generated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('When Agora tokens were generated')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Call Session'
        verbose_name_plural = 'Call Sessions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['talker', 'status']),
            models.Index(fields=['listener', 'status']),
            models.Index(fields=['status', 'started_at']),
        ]
    
    def __str__(self):
        return f"Call: {self.talker.email} -> {self.listener.email} ({self.status})"
    
    def get_remaining_minutes(self):
        """Calculate remaining minutes in the call."""
        # If call hasn't started yet, return full purchased minutes
        if not self.started_at:
            return self.total_minutes_purchased
        
        # If call is ended or failed, return 0
        if self.status not in ['connecting', 'active']:
            return 0
        
        elapsed_minutes = (timezone.now() - self.started_at).total_seconds() / 60
        remaining = self.total_minutes_purchased - elapsed_minutes
        return max(0, remaining)
    
    def is_listener_busy(self):
        """Check if listener is busy in another call."""
        return CallSession.objects.filter(
            listener=self.listener,
            status__in=['connecting', 'active']
        ).exclude(id=self.id).exists()
    
    @staticmethod
    def is_listener_available(listener):
        """Check if listener is available for a new call."""
        # Check if listener has any active call session
        has_active_call = CallSession.objects.filter(
            listener=listener,
            status__in=['connecting', 'active']
        ).exists()
        
        # Also check if listener has any in-progress booking
        if Booking:
            has_active_booking = Booking.objects.filter(
                listener=listener,
                status='in_progress'
            ).exists()
            return not (has_active_call or has_active_booking)
        
        # Also check call packages in progress
        has_active_package = CallPackage.objects.filter(
            listener=listener,
            status='in_progress'
        ).exists()
        
        return not (has_active_call or has_active_package)
    
    def add_time(self, minutes):
        """Add additional minutes to the call."""
        self.total_minutes_purchased += minutes
        self.save(update_fields=['total_minutes_purchased', 'updated_at'])
    
    def should_send_warning(self):
        """Check if we should send 3-minute warning."""
        if self.last_warning_sent or self.status != 'active':
            return False
        
        remaining = self.get_remaining_minutes()
        return 0 < remaining <= 3
    
    def consume_booking(self):
        """Mark booking as completed after call ends."""
        if self.booking:
            self.booking.complete_session()
        elif self.call_package:
            self.call_package.complete_call()
    
    def can_connect(self):
        """Check if call can be connected based on payment status and session state."""
        # Block connection to timeout or ended calls
        if self.status in ['timeout', 'ended']:
            return False
        
        # Allow reconnection to active or connecting calls (already validated during start)
        if self.status in ['connecting', 'active']:
            return True
        
        # For new connections in other states, validate payment
        if self.booking:
            if hasattr(self.booking, 'payment'):
                return self.booking.payment.status == 'succeeded'
            return self.booking.status == 'confirmed'
        
        if self.call_package:
            return self.call_package.status in ['confirmed', 'in_progress']
        
        if self.initial_package:
            return self.initial_package.status in ['confirmed', 'in_progress']
        
        return False


class CallRejection(models.Model):
    """Track call rejections by listener."""
    
    REJECTION_REASON_CHOICES = [
        ('not_available', _('Not Available')),
        ('busy', _('Busy')),
        ('not_interested', _('Not Interested')),
        ('other', _('Other')),
    ]
    
    call_package = models.OneToOneField(
        CallPackage,
        on_delete=models.CASCADE,
        related_name='rejection'
    )
    listener = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='call_rejections',
        limit_choices_to={'user_type': 'listener'}
    )
    talker = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='rejected_calls',
        limit_choices_to={'user_type': 'talker'}
    )
    reason = models.CharField(
        max_length=20,
        choices=REJECTION_REASON_CHOICES,
        default='other'
    )
    notes = models.TextField(blank=True, help_text=_('Optional notes'))
    
    # Refund tracking
    refund_issued = models.BooleanField(default=False, help_text=_('Whether refund was processed'))
    refund_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Amount refunded to talker')
    )
    refund_stripe_id = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Stripe refund ID')
    )
    refund_date = models.DateTimeField(null=True, blank=True)
    
    rejected_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Call Rejection'
        verbose_name_plural = 'Call Rejections'
        ordering = ['-rejected_at']
        indexes = [
            models.Index(fields=['listener', 'rejected_at']),
            models.Index(fields=['talker', 'rejected_at']),
        ]
    
    def __str__(self):
        return f"Call Rejection: {self.talker.email} by {self.listener.email}"


class ListenerPayout(models.Model):
    """Track earnings and payouts for listeners."""
    
    PAYOUT_STATUS_CHOICES = [
        ('earned', _('Earned')),           # Earnings added to balance
        ('pending', _('Pending Payout')),  # Waiting for payout request
        ('processing', _('Processing')),   # Payout in progress
        ('completed', _('Completed')),     # Payout completed
        ('failed', _('Failed')),           # Payout failed
        ('cancelled', _('Cancelled')),     # Payout cancelled (refund for rejection)
    ]
    
    listener = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='listener_payouts',
        limit_choices_to={'user_type': 'listener'}
    )
    
    # Reference to the call that generated this payout
    call_package = models.ForeignKey(
        CallPackage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payouts'
    )
    
    # Payout amount (from CallPackage.listener_amount)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_('Amount to be paid to listener')
    )
    
    status = models.CharField(
        max_length=20,
        choices=PAYOUT_STATUS_CHOICES,
        default='earned'
    )
    
    # Stripe payout tracking
    stripe_payout_id = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Stripe payout ID')
    )
    
    # Dates
    earned_at = models.DateTimeField(auto_now_add=True)
    payout_requested_at = models.DateTimeField(null=True, blank=True)
    payout_completed_at = models.DateTimeField(null=True, blank=True)
    
    # Notes
    notes = models.TextField(blank=True)
    
    # Extension tracking - extensions should NOT be counted in balance
    is_extension = models.BooleanField(
        default=False,
        help_text=_('Extension payouts are not counted in total balance')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Listener Payout'
        verbose_name_plural = 'Listener Payouts'
        ordering = ['-earned_at']
        indexes = [
            models.Index(fields=['listener', 'status']),
            models.Index(fields=['listener', '-earned_at']),
        ]
    
    def __str__(self):
        return f"Payout for {self.listener.email}: ${self.amount} ({self.status})"
    
    @classmethod
    def get_listener_balance(cls, listener):
        """Get total available balance for listener (excludes extension packages)."""
        from django.db.models import Sum
        balance = cls.objects.filter(
            listener=listener,
            status__in=['earned', 'pending'],
            is_extension=False  # Exclude extension packages from balance
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        return balance
    
    @classmethod
    def get_listener_extension_earnings(cls, listener):
        """Get total earnings from extension packages (separate tracking)."""
        from django.db.models import Sum
        return cls.objects.filter(
            listener=listener,
            status__in=['earned', 'pending'],
            is_extension=True
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
