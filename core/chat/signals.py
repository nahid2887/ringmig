"""Signals for chat app - handles automatic payout creation when calls complete."""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .call_models import CallPackage, ListenerPayout, CallSession
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=CallPackage)
def create_listener_payout_on_payment_confirmation(sender, instance, created, update_fields, **kwargs):
    """Create payout record for listener when call package payment is confirmed.
    
    This creates a payout entry in ListenerPayout table with status 'processing'
    when a CallPackage has 'confirmed' status (payment succeeded).
    Status will change to 'earned' when call session ends.
    
    Handles both cases:
    1. CallPackage created directly with status='confirmed' (auto-purchase flow)
    2. CallPackage updated from 'pending' to 'confirmed' (normal purchase flow)
    """
    # For updates, check if status field was actually updated
    if not created:
        if update_fields and 'status' not in update_fields:
            return
    
    # Create payout if status is 'confirmed' (either on creation or update)
    if instance.status == 'confirmed':
        try:
            # Check if payout already exists for this call package
            if ListenerPayout.objects.filter(call_package=instance).exists():
                logger.info(f"Payout already exists for call package {instance.id}")
                return
            
            # Calculate listener amount
            listener_amount = instance.listener_amount
            
            if listener_amount > 0:
                # Create payout record with 'processing' status
                # Will be changed to 'earned' when call session ends
                payout = ListenerPayout.objects.create(
                    listener=instance.listener,
                    call_package=instance,
                    amount=listener_amount,
                    status='processing',
                    is_extension=instance.is_extension,  # Exclude from balance if extension
                    notes=f'Waiting for call completion with {instance.talker.email}'
                )
                
                logger.info(f"✓ Payout created (processing) for listener {instance.listener.email}: ${listener_amount} (Call Package #{instance.id}, is_extension={instance.is_extension})")
                return payout
        
        except Exception as e:
            logger.error(f"Error creating payout for call package {instance.id}: {str(e)}")


@receiver(post_save, sender=CallPackage)
def mark_payout_earned_on_call_completion(sender, instance, created, update_fields, **kwargs):
    """Mark payout as earned when call package is completed and update listener balance.
    
    When a CallPackage transitions to 'completed' status,
    update the related payout status from 'processing' to 'earned',
    and add the amount to the listener's available balance.
    """
    # Check if this is an update (not creation) and status field was updated
    if created:
        return
    
    if update_fields and 'status' not in update_fields:
        return
    
    # Only process if status changed to 'completed'
    if instance.status == 'completed':
        try:
            from listener.models import ListenerBalance
            
            # Find and update related payout
            payout = ListenerPayout.objects.filter(
                call_package=instance,
                status='processing'
            ).first()
            
            if payout:
                payout.status = 'earned'
                payout.notes = f'Completed call with {instance.talker.email}'
                payout.save(update_fields=['status', 'notes', 'updated_at'])
                # Do NOT update ListenerBalance here. Payouts are handled by
                # direct Stripe transfers when configured; keep payout record
                # but skip internal balance crediting.
                logger.info(f"Marked payout #{payout.id} as earned for {instance.listener.email} (no balance change)")
        
        except Exception as e:
            logger.error(f"Error marking payout as earned for call package {instance.id}: {str(e)}")



@receiver(post_save, sender=CallSession)
def mark_payout_earned_on_call_session_end(sender, instance, created, update_fields, **kwargs):
    """Mark payouts as earned when call session ends (timeout or ended) and update balance.
    
    When a CallSession transitions to 'timeout' or 'ended' status,
    update all related payouts from 'processing' to 'earned',
    and add amounts to listener's available balance.
    """
    # Check if this is an update (not creation) and status field was updated
    if created:
        return
    
    if update_fields and 'status' not in update_fields:
        return
    
    # Only process if status changed to 'timeout' or 'ended'
    if instance.status in ['timeout', 'ended']:
        try:
            from listener.models import ListenerBalance
            from django.db.models import Sum
            
            all_payouts = []
            
            # Find payouts related to this call session
            # Check initial_package first
            if instance.initial_package:
                payouts = ListenerPayout.objects.filter(
                    call_package=instance.initial_package,
                    status='processing'
                )
                
                if payouts.exists():
                    all_payouts.extend(list(payouts))
                    updated_count = payouts.update(
                        status='earned',
                        notes=f'Call session ended ({instance.status})',
                        updated_at=timezone.now()
                    )
                    logger.info(f"✓ Marked {updated_count} payouts as earned after call session {instance.id} ended")
            
            # Also check call_package if exists
            if instance.call_package:
                payouts = ListenerPayout.objects.filter(
                    call_package=instance.call_package,
                    status='processing'
                )
                
                if payouts.exists():
                    all_payouts.extend(list(payouts))
                    updated_count = payouts.update(
                        status='earned',
                        notes=f'Call session ended ({instance.status})',
                        updated_at=timezone.now()
                    )
                    logger.info(f"✓ Marked {updated_count} payouts as earned after call session {instance.id} ended")
            
            # Also check packages linked to this session
            packages = CallPackage.objects.filter(call_session=instance)
            for package in packages:
                payouts = ListenerPayout.objects.filter(
                    call_package=package,
                    status='processing'
                )
                
                if payouts.exists():
                    all_payouts.extend(list(payouts))
                    updated_count = payouts.update(
                        status='earned',
                        notes=f'Call session ended ({instance.status})',
                        updated_at=timezone.now()
                    )
                    logger.info(f"✓ Marked {updated_count} payouts as earned for package {package.id}")
            
            # Update listener balances for all payouts that were marked as earned
            if all_payouts:
                # Group by listener and sum amounts
                balance_updates = {}
                for payout in all_payouts:
                    if payout.listener.id not in balance_updates:
                        balance_updates[payout.listener.id] = {
                            'listener': payout.listener,
                            'amount': payout.amount
                        }
                    else:
                        balance_updates[payout.listener.id]['amount'] += payout.amount
                
                # Update balance for each listener
                for listener_id, info in balance_updates.items():
                    try:
                        listener = info['listener']
                        amount = info['amount']
                        
                        balance, _ = ListenerBalance.objects.get_or_create(listener=listener)
                        balance.available_balance += amount
                        balance.total_earned += amount
                        balance.save(update_fields=['available_balance', 'total_earned', 'updated_at'])
                        logger.info(f"✓ Updated balance for {listener.email}: +${amount}, New available: ${balance.available_balance}")
                    except Exception as e:
                        logger.error(f"Error updating balance for listener {listener_id}: {str(e)}")
        
        except Exception as e:
            logger.error(f"Error marking payouts as earned for call session {instance.id}: {str(e)}")

