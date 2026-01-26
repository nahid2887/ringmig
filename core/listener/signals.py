from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


@receiver(post_save, sender=User)
def create_listener_profile(sender, instance, created, **kwargs):
    """
    Automatically create a ListenerProfile when a user with user_type='listener' is created.
    """
    if created and instance.user_type == 'listener':
        from .models import ListenerProfile, ListenerBalance
        ListenerProfile.objects.get_or_create(user=instance)
        # Also create balance account
        ListenerBalance.objects.get_or_create(
            listener=instance,
            defaults={'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00')}
        )


@receiver(post_save, sender=User)
def save_listener_profile(sender, instance, **kwargs):
    """
    Ensure listener profile is updated if user changes to listener type.
    """
    if instance.user_type == 'listener':
        from .models import ListenerProfile, ListenerBalance
        if not hasattr(instance, 'listener_profile'):
            ListenerProfile.objects.get_or_create(user=instance)
        if not hasattr(instance, 'balance_account'):
            ListenerBalance.objects.get_or_create(
                listener=instance,
                defaults={'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00')}
            )


@receiver(post_save, sender='chat.CallSession')
def add_listener_earnings_on_call_end(sender, instance, created, **kwargs):
    """
    Automatically add money to listener's balance when call ends.
    
    Triggers when:
    - CallSession status changes to 'ended' or 'timeout'
    - CallPackage is confirmed/used
    """
    from listener.models import ListenerBalance
    
    # Only process when call ends
    if instance.status not in ['ended', 'timeout']:
        return
    
    # Get the initial package
    if not instance.initial_package:
        logger.warning(f"⚠️ CallSession {instance.id} has no initial_package")
        return
    
    package = instance.initial_package
    
    # Only process confirmed/used packages
    if package.status not in ['confirmed', 'used', 'in_progress', 'completed']:
        logger.info(f"📦 Package {package.id} status is '{package.status}', skipping earnings")
        return
    
    # Check if already processed (avoid double-crediting)
    if hasattr(package, '_base_earnings_processed') and package._base_earnings_processed:
        return
    
    # Get or create listener balance
    balance, created = ListenerBalance.objects.get_or_create(
        listener=instance.listener,
        defaults={'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00')}
    )
    
    # Add to balance
    listener_amount = package.listener_amount
    balance.add_earnings(listener_amount)
    
    # Mark as processed
    package._base_earnings_processed = True
    
    logger.info(f"💰 Added ${listener_amount} to {instance.listener.email} for call session {instance.id}")


@receiver(post_save, sender='chat.CallPackage')
def add_listener_earnings_on_extension(sender, instance, created, **kwargs):
    """
    Automatically add money to listener's balance when extension payment confirmed.
    
    Triggers when:
    - CallPackage.is_extension = True
    - Status = 'confirmed' or 'used'
    """
    from listener.models import ListenerBalance
    
    # Only process extensions
    if not instance.is_extension:
        return
    
    # Only when confirmed/used
    if instance.status not in ['confirmed', 'used']:
        return
    
    # Avoid double-processing
    if hasattr(instance, '_extension_earnings_processed') and instance._extension_earnings_processed:
        return
    
    # Get or create balance
    balance, created = ListenerBalance.objects.get_or_create(
        listener=instance.listener,
        defaults={'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00')}
    )
    
    # Add extension earnings
    listener_amount = instance.listener_amount
    balance.add_earnings(listener_amount)
    
    # Mark as processed
    instance._extension_earnings_processed = True
    
    logger.info(f"⏱️ Added ${listener_amount} to {instance.listener.email} for extension package {instance.id}")
