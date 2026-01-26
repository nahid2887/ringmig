from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

User = get_user_model()


class BookingPackage(models.Model):
    """Predefined booking packages with pricing."""
    
    name = models.CharField(max_length=100, help_text=_('Package name'))
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
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Booking Package'
        verbose_name_plural = 'Booking Packages'
        ordering = ['duration_minutes']
    
    def __str__(self):
        return f"{self.name} - {self.duration_minutes} min - ${self.price}"
    
    @property
    def app_fee(self):
        """Calculate app commission amount."""
        return (self.price * self.app_fee_percentage / 100).quantize(Decimal('0.01'))
    
    @property
    def listener_amount(self):
        """Calculate listener payout amount."""
        return (self.price - self.app_fee).quantize(Decimal('0.01'))


class Booking(models.Model):
    """Represents a booking session between talker and listener."""
    
    STATUS_CHOICES = [
        ('pending', _('Pending Payment')),
        ('confirmed', _('Confirmed')),
        ('in_progress', _('In Progress')),
        ('completed', _('Completed')),
        ('cancelled', _('Cancelled')),
        ('refunded', _('Refunded')),
    ]
    
    talker = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bookings_as_talker',
        limit_choices_to={'user_type': 'talker'}
    )
    listener = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bookings_as_listener',
        limit_choices_to={'user_type': 'listener'}
    )
    package = models.ForeignKey(
        BookingPackage,
        on_delete=models.PROTECT,
        related_name='bookings'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Session details
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    actual_duration_minutes = models.IntegerField(null=True, blank=True)
    
    # Pricing snapshot (stored at booking time)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    app_fee = models.DecimalField(max_digits=10, decimal_places=2)
    listener_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Additional info
    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Booking'
        verbose_name_plural = 'Bookings'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['talker', '-created_at']),
            models.Index(fields=['listener', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]
    
    def __str__(self):
        return f"Booking #{self.id}: {self.talker.email} -> {self.listener.email} ({self.status})"
    
    def confirm(self):
        """Mark booking as confirmed after successful payment."""
        self.status = 'confirmed'
        self.save(update_fields=['status', 'updated_at'])
    
    def start_session(self):
        """Mark session as started."""
        from django.utils import timezone
        self.status = 'in_progress'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])
    
    def complete_session(self):
        """Mark session as completed."""
        from django.utils import timezone
        self.status = 'completed'
        self.ended_at = timezone.now()
        if self.started_at:
            duration = (self.ended_at - self.started_at).total_seconds() / 60
            self.actual_duration_minutes = int(duration)
        self.save(update_fields=['status', 'ended_at', 'actual_duration_minutes', 'updated_at'])
    
    def cancel(self, reason=''):
        """Cancel the booking."""
        self.status = 'cancelled'
        self.cancellation_reason = reason
        self.save(update_fields=['status', 'cancellation_reason', 'updated_at'])


class Payment(models.Model):
    """Tracks payment transactions for bookings."""
    
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('processing', _('Processing')),
        ('succeeded', _('Succeeded')),
        ('failed', _('Failed')),
        ('refunded', _('Refunded')),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('card', _('Credit/Debit Card')),
        ('bank', _('Bank Transfer')),
        ('wallet', _('Digital Wallet')),
    ]
    
    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name='payment'
    )
    
    # Stripe information
    stripe_payment_intent_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    stripe_charge_id = models.CharField(max_length=255, blank=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    
    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='card'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Additional info
    failure_reason = models.TextField(blank=True)
    refund_reason = models.TextField(blank=True)
    refund_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['stripe_payment_intent_id']),
            models.Index(fields=['status', '-created_at']),
        ]
    
    def __str__(self):
        return f"Payment #{self.id} - Booking #{self.booking.id} ({self.status})"


class ListenerPayout(models.Model):
    """Tracks payouts to listeners."""
    
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('processing', _('Processing')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
    ]
    
    listener = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='payouts',
        limit_choices_to={'user_type': 'listener'}
    )
    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name='listener_payout'
    )
    
    # Payout details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Stripe Connect information (for automated payouts)
    stripe_account_id = models.CharField(max_length=255, blank=True)
    stripe_transfer_id = models.CharField(max_length=255, blank=True, unique=True)
    
    # Additional info
    notes = models.TextField(blank=True)
    failure_reason = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Listener Payout'
        verbose_name_plural = 'Listener Payouts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['listener', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]
    
    def __str__(self):
        return f"Payout to {self.listener.email} - ${self.amount} ({self.status})"


class StripeCustomer(models.Model):
    """Store Stripe customer IDs for users."""
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='stripe_customer'
    )
    stripe_customer_id = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Stripe Customer'
        verbose_name_plural = 'Stripe Customers'
    
    def __str__(self):
        return f"{self.user.email} - {self.stripe_customer_id}"


class StripeListenerAccount(models.Model):
    """Store Stripe Connect account IDs for listeners."""
    
    listener = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='stripe_listener_account',
        limit_choices_to={'user_type': 'listener'}
    )
    stripe_account_id = models.CharField(max_length=255, unique=True)
    is_verified = models.BooleanField(default=False)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Stripe Listener Account'
        verbose_name_plural = 'Stripe Listener Accounts'
    
    def __str__(self):
        return f"{self.listener.email} - {self.stripe_account_id}"
