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


# Removed add_listener_earnings_on_call_end - now handled by sync_payout_earnings_to_balance
# when ListenerPayout status changes to 'earned'


@receiver(post_save, sender='chat.ListenerPayout')
def sync_payout_earnings_to_balance(sender, instance, created, update_fields, **kwargs):
    """
    Sync ListenerPayout 'earned' status to ListenerBalance.
    
    When a ListenerPayout transitions to 'earned' status, add the amount to the listener's balance.
    This is the primary synchronization between payout tracking and balance system.
    """
    from listener.models import ListenerBalance
    
    # Skip if this is creation (only handle status updates)
    if created:
        return
        
    # Only process if status field was updated
    if update_fields and 'status' not in update_fields:
        return
        
    # Only when status becomes 'earned'
    if instance.status != 'earned':
        return
        
    # Avoid double-processing (check if this earning was already added)
    if hasattr(instance, '_earnings_synced') and instance._earnings_synced:
        return
        
    try:
        # Get or create balance account
        balance, created = ListenerBalance.objects.get_or_create(
            listener=instance.listener,
            defaults={'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00')}
        )
        
        # Add earnings to balance (only if not an extension for base packages)
        # Extensions are handled separately and added immediately when confirmed
        if not instance.is_extension:
            balance.add_earnings(instance.amount)
            logger.info(f"💰 Synced ${instance.amount} to {instance.listener.email}'s balance (Payout #{instance.id} earned)")
        else:
            logger.info(f"⏱️ Skipping extension payout #{instance.id} - handled separately")
            
        # Mark as processed to avoid double-syncing
        instance._earnings_synced = True
        
    except Exception as e:
        logger.error(f"Error syncing payout #{instance.id} to balance: {str(e)}")


@receiver(post_save, sender='chat.CallPackage')
def add_listener_earnings_on_extension(sender, instance, created, **kwargs):
    """
    Automatically add money to listener's balance when extension payment confirmed.
    
    Triggers when:
    - CallPackage.is_extension = True
    - Status = 'confirmed' or 'used'
    
    Extensions are credited immediately since they don't go through the normal
    'processing' -> 'earned' flow like base packages.
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
