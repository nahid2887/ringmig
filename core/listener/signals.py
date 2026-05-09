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
        
        # Parse full_name into first_name and last_name
        first_name = ''
        last_name = ''
        if instance.full_name:
            parts = instance.full_name.strip().split(None, 1)
            first_name = parts[0] if parts else ''
            last_name = parts[1] if len(parts) > 1 else ''
        
        ListenerProfile.objects.get_or_create(
            user=instance,
            defaults={
                'first_name': first_name,
                'last_name': last_name
            }
        )
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
            # Parse full_name into first_name and last_name
            first_name = ''
            last_name = ''
            if instance.full_name:
                parts = instance.full_name.strip().split(None, 1)
                first_name = parts[0] if parts else ''
                last_name = parts[1] if len(parts) > 1 else ''
            
            ListenerProfile.objects.get_or_create(
                user=instance,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name
                }
            )
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
        # NOTE: Disabled automatic syncing of ListenerPayout -> ListenerBalance.
        # Earnings should be transferred directly to listeners' Stripe Connect
        # accounts rather than credited to internal balance. Keep the payout
        # record for bookkeeping but do not modify ListenerBalance here.
        logger.info(f"Skipping balance sync for payout #{instance.id} (earned={instance.amount}) - direct Stripe payouts enabled")
        instance._earnings_synced = True

    except Exception as e:
        logger.error(f"Error marking payout #{instance.id} as synced (no balance change): {str(e)}")


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
    
    # Do NOT add extension earnings to ListenerBalance. Extensions are
    # handled via direct Stripe payouts when configured.
    instance._extension_earnings_processed = True
    logger.info(f"Skipping extension earnings credit to balance for package {instance.id} (listener={instance.listener.email})")
