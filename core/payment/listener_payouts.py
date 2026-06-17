"""
Utility functions for automatic listener payouts via Stripe Connect.
Transfers listener's portion of payment to their connected Stripe account.
"""

import stripe
import logging
from django.conf import settings
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


def transfer_to_listener_stripe_account(
    listener,
    amount,
    source_type,
    source_id,
    description="Payout from booking/call",
    source_transaction=None,
):
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
            stripe_account = StripeListenerAccount.objects.get(listener=listener, is_enabled=True)
            
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
            
            transfer_kwargs = {
                'amount': amount_cents,
                'currency': 'usd',
                'destination': stripe_account.stripe_account_id,
                'description': description,
                'metadata': {
                    'source_type': source_type,
                    'source_id': source_id,
                    'listener_id': listener.id,
                    'listener_email': listener.email,
                },
            }

            if source_transaction:
                transfer_kwargs['source_transaction'] = source_transaction

            transfer = stripe.Transfer.create(**transfer_kwargs)
            
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
                f"No enabled Stripe Connect account found for listener {listener.email}. "
                f"Listener must connect or enable a Stripe account to receive payouts."
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


def handle_call_package_payment_succeeded(call_package, source_transaction=None):
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
        
        with transaction.atomic():
            locked_call_package = CallPackage.objects.select_for_update().get(id=call_package.id)

            if locked_call_package.stripe_transfer_id:
                return {
                    'success': True,
                    'transfer_id': locked_call_package.stripe_transfer_id,
                    'error': None,
                    'message': 'Listener payout already transferred for this call package'
                }

            # Update call package status
            locked_call_package.status = 'confirmed'
            locked_call_package.save(update_fields=['status', 'updated_at'])

            # Transfer to listener
            transfer_result = transfer_to_listener_stripe_account(
                listener=locked_call_package.listener,
                amount=locked_call_package.listener_amount,
                source_type='call_package',
                source_id=locked_call_package.id,
                description=f"Payment for call package: {locked_call_package.package.name} ({locked_call_package.package.duration_minutes} min)",
                source_transaction=source_transaction or locked_call_package.stripe_charge_id or None,
            )

            # Update call package with transfer info if successful
            if transfer_result['success']:
                locked_call_package.stripe_transfer_id = transfer_result['transfer_id']
                locked_call_package.save(update_fields=['stripe_transfer_id'])

            return transfer_result
        
    except Exception as e:
        logger.error(f"Error handling call package payment for {call_package.id}: {str(e)}")
        return {
            'success': False,
            'transfer_id': None,
            'error': str(e)
        }


def handle_tip_payment_succeeded(tip, source_transaction=None):
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

        with transaction.atomic():
            locked_tip = Tip.objects.select_for_update().get(id=tip.id)

            if locked_tip.stripe_transfer_id:
                return {
                    'success': True,
                    'transfer_id': locked_tip.stripe_transfer_id,
                    'error': None,
                    'message': 'Listener payout already transferred for this tip'
                }

            # Update tip status
            locked_tip.status = 'succeeded'
            locked_tip.paid_at = timezone.now()
            locked_tip.save(update_fields=['status', 'paid_at', 'updated_at'])

            # Check if this tip was paid via destination charge
            is_destination_charge = False
            if locked_tip.stripe_payment_intent_id:
                try:
                    payment_intent = stripe.PaymentIntent.retrieve(locked_tip.stripe_payment_intent_id)
                    is_destination_charge = payment_intent.get('metadata', {}).get('payout_mode') == 'destination_charge'
                except stripe.error.StripeError:
                    is_destination_charge = False

            if is_destination_charge:
                # For destination charges, Stripe Connect handles the transfer automatically.
                # We just retrieve the transfer ID from the charge and save it.
                transfer_id = None
                charge_id = source_transaction or locked_tip.stripe_charge_id
                if charge_id:
                    try:
                        charge = stripe.Charge.retrieve(charge_id)
                        transfer_id = charge.get('transfer')
                        if transfer_id:
                            locked_tip.stripe_transfer_id = transfer_id
                            locked_tip.save(update_fields=['stripe_transfer_id'])
                    except stripe.error.StripeError as exc:
                        logger.warning(
                            "Could not resolve automatic transfer ID for tip %s: %s",
                            locked_tip.id,
                            str(exc),
                        )
                return {
                    'success': True,
                    'transfer_id': transfer_id,
                    'error': None,
                    'message': f'Destination charge processed automatically by Stripe Connect. Transfer ID: {transfer_id}'
                }

            # Transfer to listener (fallback/legacy mode)
            transfer_result = transfer_to_listener_stripe_account(
                listener=locked_tip.listener,
                amount=locked_tip.listener_amount,
                source_type='tip',
                source_id=locked_tip.id,
                description=f"Tip from {locked_tip.talker.email}",
                source_transaction=source_transaction or locked_tip.stripe_charge_id or None,
            )

            if transfer_result['success']:
                locked_tip.stripe_transfer_id = transfer_result['transfer_id']
                locked_tip.save(update_fields=['stripe_transfer_id'])

            return transfer_result
        
    except Exception as e:
        logger.error(f"Error handling tip payment for {tip.id}: {str(e)}")
        return {
            'success': False,
            'transfer_id': None,
            'error': str(e)
        }


def handle_booking_payment_succeeded(booking, source_transaction=None):
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
            description=f"Payment for booking: {booking.package.name}",
            source_transaction=source_transaction,
        )
        
        return transfer_result
        
    except Exception as e:
        logger.error(f"Error handling booking payment for {booking.id}: {str(e)}")
        return {
            'success': False,
            'transfer_id': None,
            'error': str(e)
        }
