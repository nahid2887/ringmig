"""
Utility functions for automatic listener payouts via Stripe Connect.
Transfers listener's portion of payment to their connected Stripe account.
"""

import stripe
import logging
from django.conf import settings
from decimal import Decimal
from django.utils import timezone

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


def transfer_to_listener_stripe_account(listener, amount, source_type, source_id, description="Payout from booking/call"):
    """
    Automatically transfer listener's earned amount to their connected Stripe account.
    
    Args:
        listener: User instance (listener)
        amount: Amount to transfer (Decimal)
        source_type: 'call_package', 'tip', 'booking', etc.
        source_id: ID of the source object (call_package_id, tip_id, etc.)
        description: Description for the transfer
    
    Returns:
        dict: {
            'success': bool,
            'transfer_id': str or None,
            'error': str or None,
            'message': str
        }
    """
    try:
        # Check if listener has a verified Stripe Connect account
        from payment.models import StripeListenerAccount
        
        try:
            stripe_account = StripeListenerAccount.objects.get(listener=listener)
            
            # Verify account is enabled and ideally verified
            if not stripe_account.is_enabled:
                return {
                    'success': False,
                    'transfer_id': None,
                    'error': 'Listener Stripe account is disabled',
                    'message': f'Cannot transfer to {listener.email} - account disabled'
                }
            
            # Check account status from Stripe
            account = stripe.Account.retrieve(stripe_account.stripe_account_id)
            
            if not account.payouts_enabled:
                logger.warning(
                    f"Listener {listener.email} account {stripe_account.stripe_account_id} "
                    f"does not have payouts enabled. Cannot transfer."
                )
                return {
                    'success': False,
                    'transfer_id': None,
                    'error': 'Listener account payouts not enabled',
                    'message': f'Listener {listener.email} has not completed Stripe verification'
                }
            
            # Create transfer
            amount_cents = int(amount * 100)  # Convert to cents
            
            transfer = stripe.Transfer.create(
                amount=amount_cents,
                currency='usd',
                destination=stripe_account.stripe_account_id,
                description=description,
                metadata={
                    'source_type': source_type,
                    'source_id': source_id,
                    'listener_id': listener.id,
                    'listener_email': listener.email
                }
            )
            
            logger.info(
                f"Successfully transferred ${amount} to listener {listener.email} "
                f"(account: {stripe_account.stripe_account_id}, transfer: {transfer.id})"
            )
            
            return {
                'success': True,
                'transfer_id': transfer.id,
                'error': None,
                'message': f'Transferred ${amount} to listener {listener.email}'
            }
            
        except StripeListenerAccount.DoesNotExist:
            logger.warning(
                f"No Stripe Connect account found for listener {listener.email}. "
                f"Listener must connect Stripe account to receive payouts."
            )
            return {
                'success': False,
                'transfer_id': None,
                'error': 'No Stripe Connect account',
                'message': f'Listener {listener.email} has not connected Stripe account'
            }
    
    except stripe.error.StripeError as e:
        logger.error(f"Stripe transfer error for listener {listener.email}: {str(e)}")
        return {
            'success': False,
            'transfer_id': None,
            'error': str(e),
            'message': f'Stripe error: {str(e)}'
        }
    
    except Exception as e:
        logger.error(f"Unexpected error transferring to listener {listener.email}: {str(e)}")
        return {
            'success': False,
            'transfer_id': None,
            'error': str(e),
            'message': f'Unexpected error: {str(e)}'
        }


def handle_call_package_payment_succeeded(call_package):
    """
    Handle successful payment for a call package.
    Updates status and transfers listener amount to their Stripe account.
    
    Args:
        call_package: CallPackage instance
    
    Returns:
        dict: Success status and transfer info
    """
    try:
        from chat.models import CallPackage
        
        # Update call package status
        call_package.status = 'confirmed'
        call_package.save(update_fields=['status', 'updated_at'])
        
        # Transfer to listener
        transfer_result = transfer_to_listener_stripe_account(
            listener=call_package.listener,
            amount=call_package.listener_amount,
            source_type='call_package',
            source_id=call_package.id,
            description=f"Payment for call package: {call_package.package.name} ({call_package.package.duration_minutes} min)"
        )
        
        # Update call package with transfer info if successful
        if transfer_result['success']:
            call_package.stripe_transfer_id = transfer_result['transfer_id']
            call_package.save(update_fields=['stripe_transfer_id'])
        
        return transfer_result
        
    except Exception as e:
        logger.error(f"Error handling call package payment for {call_package.id}: {str(e)}")
        return {
            'success': False,
            'transfer_id': None,
            'error': str(e)
        }


def handle_tip_payment_succeeded(tip):
    """
    Handle successful payment for a tip.
    Updates status and transfers listener amount to their Stripe account.
    
    Args:
        tip: Tip instance
    
    Returns:
        dict: Success status and transfer info
    """
    try:
        from payment.models import Tip
        
        # Update tip status
        tip.status = 'succeeded'
        tip.paid_at = timezone.now()
        tip.save(update_fields=['status', 'paid_at', 'updated_at'])
        
        # Transfer to listener
        transfer_result = transfer_to_listener_stripe_account(
            listener=tip.listener,
            amount=tip.listener_amount,
            source_type='tip',
            source_id=tip.id,
            description=f"Tip from {tip.talker.email}"
        )
        
        return transfer_result
        
    except Exception as e:
        logger.error(f"Error handling tip payment for {tip.id}: {str(e)}")
        return {
            'success': False,
            'transfer_id': None,
            'error': str(e)
        }


def handle_booking_payment_succeeded(booking):
    """
    Handle successful payment for a booking.
    Transfers listener amount to their Stripe account.
    
    Args:
        booking: Booking instance
    
    Returns:
        dict: Success status and transfer info
    """
    try:
        from payment.models import Booking
        
        # Update booking status if needed
        if booking.status == 'pending':
            booking.status = 'confirmed'
            booking.save(update_fields=['status', 'updated_at'])
        
        # Transfer to listener
        transfer_result = transfer_to_listener_stripe_account(
            listener=booking.listener,
            amount=booking.listener_amount,
            source_type='booking',
            source_id=booking.id,
            description=f"Payment for booking: {booking.package.name}"
        )
        
        return transfer_result
        
    except Exception as e:
        logger.error(f"Error handling booking payment for {booking.id}: {str(e)}")
        return {
            'success': False,
            'transfer_id': None,
            'error': str(e)
        }
