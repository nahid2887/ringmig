from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Booking, Payment, ListenerPayout


@receiver(post_save, sender=Payment)
def payment_succeeded_handler(sender, instance, created, **kwargs):
    """Handle successful payment."""
    if instance.status == 'succeeded' and instance.booking.status == 'pending':
        # Confirm the booking
        instance.booking.confirm()
        
        # Create payout record for listener
        if not hasattr(instance.booking, 'listener_payout'):
            ListenerPayout.objects.create(
                listener=instance.booking.listener,
                booking=instance.booking,
                amount=instance.booking.listener_amount,
                currency=instance.currency
            )


@receiver(post_save, sender=Booking)
def booking_completed_handler(sender, instance, created, **kwargs):
    """Handle booking completion - mark payout as ready."""
    if instance.status == 'completed' and hasattr(instance, 'listener_payout'):
        payout = instance.listener_payout
        if payout.status == 'pending':
            # Ready to process payout
            # You can trigger automatic payout here or keep it manual
            pass
