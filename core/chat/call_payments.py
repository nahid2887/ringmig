"""
Payment helper functions for call packages.
Integrates with Stripe like the existing payment system.
"""
import stripe
import logging
from django.conf import settings
from decimal import Decimal

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_call_package_payment_intent(call_package, payment_method_id=None):
    """
    Create a Stripe payment intent for a call package.
    Similar to create_booking_with_payment in payment app.
    
    Args:
        call_package: CallPackage instance
        payment_method_id: Stripe payment method ID (optional)
    
    Returns:
        dict: Payment intent response with client_secret and payment link
    """
    try:
        # Get or create Stripe customer (same as payment app)
        from payment.models import StripeCustomer
        
        stripe_customer = None
        try:
            stripe_customer = StripeCustomer.objects.get(user=call_package.talker)
            
            # Verify customer exists in Stripe
            try:
                stripe.Customer.retrieve(stripe_customer.stripe_customer_id)
            except stripe.error.InvalidRequestError:
                # Customer doesn't exist in Stripe, recreate it
                logger.warning(f"Stripe customer {stripe_customer.stripe_customer_id} not found, recreating...")
                customer = stripe.Customer.create(
                    email=call_package.talker.email,
                    metadata={'user_id': call_package.talker.id}
                )
                stripe_customer.stripe_customer_id = customer.id
                stripe_customer.save()
                
        except StripeCustomer.DoesNotExist:
            # Create new Stripe customer
            customer = stripe.Customer.create(
                email=call_package.talker.email,
                metadata={'user_id': call_package.talker.id}
            )
            
            stripe_customer = StripeCustomer.objects.create(
                user=call_package.talker,
                stripe_customer_id=customer.id
            )
        
        # Create payment intent
        amount_cents = int(call_package.total_amount * 100)
        
        payment_intent_data = {
            'amount': amount_cents,
            'currency': 'usd',
            'customer': stripe_customer.stripe_customer_id,
            'metadata': {
                'call_package_id': call_package.id,
                'talker_id': call_package.talker.id,
                'listener_id': call_package.listener.id,
                'duration_minutes': call_package.package.duration_minutes,
                'app_fee': str(call_package.app_fee),
                'listener_amount': str(call_package.listener_amount),
            },
            'description': f'Call Package: {call_package.package.name} ({call_package.package.duration_minutes} min)',
        }
        
        # Add payment method if provided
        if payment_method_id:
            payment_intent_data['payment_method'] = payment_method_id
            payment_intent_data['confirm'] = True
        
        payment_intent = stripe.PaymentIntent.create(**payment_intent_data)
        
        # Create Checkout Session for payment link
        checkout_session = stripe.checkout.Session.create(
            customer=stripe_customer.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': call_package.package.name,
                        'description': f'{call_package.package.duration_minutes} minutes call package',
                    },
                    'unit_amount': amount_cents,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url='http://localhost:5174/dashboard/talker/payment-success-start-call',
            cancel_url='http://localhost:5174/payment-cancelled',
            metadata={
                'call_package_id': call_package.id,
                'payment_intent_id': payment_intent.id,
            },
        )
        
        # Store payment intent ID
        call_package.stripe_payment_intent_id = payment_intent.id
        call_package.stripe_customer_id = stripe_customer.stripe_customer_id
        call_package.save(update_fields=['stripe_payment_intent_id', 'stripe_customer_id'])
        
        logger.info(f"Payment intent created for call package {call_package.id}: {payment_intent.id}")
        
        return {
            'payment_intent_id': payment_intent.id,
            'client_secret': payment_intent.client_secret,
            'status': payment_intent.status,
            'amount': call_package.total_amount,
            'currency': 'usd',
            'payment_link': checkout_session.url,
            'checkout_session_id': checkout_session.id
        }
    
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating payment intent: {str(e)}")
        raise Exception(f"Payment processing error: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error creating payment intent: {str(e)}")
        raise


def confirm_call_package_payment(call_package, payment_intent_id):
    """
    Confirm payment for a call package.
    Updates status when payment succeeds.
    
    Args:
        call_package: CallPackage instance
        payment_intent_id: Stripe payment intent ID
    """
    try:
        # Retrieve payment intent from Stripe
        payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        
        if payment_intent.status == 'succeeded':
            # Update call package
            call_package.status = 'confirmed'
            call_package.stripe_charge_id = payment_intent.charges.data[0].id if payment_intent.charges.data else ''
            call_package.save(update_fields=['status', 'stripe_charge_id'])
            
            logger.info(f"Payment confirmed for call package {call_package.id}")
            return True
        
        return False
    
    except Exception as e:
        logger.error(f"Error confirming payment: {str(e)}")
        return False


def handle_call_package_payment_webhook(payment_intent):
    """
    Handle Stripe webhook for call package payment.
    Called from webhook endpoint.
    
    Args:
        payment_intent: Stripe PaymentIntent object
    """
    try:
        from .call_models import CallPackage
        
        payment_intent_id = payment_intent.id
        
        # Find call package
        call_package = CallPackage.objects.filter(
            stripe_payment_intent_id=payment_intent_id
        ).first()
        
        if not call_package:
            logger.warning(f"Call package not found for payment intent {payment_intent_id}")
            return
        
        if payment_intent.status == 'succeeded':
            call_package.status = 'confirmed'
            call_package.stripe_charge_id = payment_intent.charges.data[0].id if payment_intent.charges.data else ''
            call_package.save(update_fields=['status', 'stripe_charge_id'])
            
            logger.info(f"Webhook: Payment succeeded for call package {call_package.id}")
        
        elif payment_intent.status == 'payment_failed':
            call_package.status = 'cancelled'
            call_package.cancellation_reason = 'Payment failed'
            call_package.save(update_fields=['status', 'cancellation_reason'])
            
            logger.warning(f"Webhook: Payment failed for call package {call_package.id}")
    
    except Exception as e:
        logger.error(f"Error handling webhook for call package: {str(e)}")


def create_listener_payout(call_package):
    """
    Create payout record for listener after call completes.
    
    Args:
        call_package: Completed CallPackage instance
    """
    try:
        from payment.models import ListenerPayout
        
        if call_package.status != 'completed':
            return None
        
        # Check if payout already exists
        existing_payout = ListenerPayout.objects.filter(
            listener=call_package.listener,
            notes__contains=f'call_package_id:{call_package.id}'
        ).first()
        
        if existing_payout:
            return existing_payout
        
        # Create payout
        payout = ListenerPayout.objects.create(
            listener=call_package.listener,
            amount=call_package.listener_amount,
            status='pending',
            related_booking=None,
            notes=f'Call package payout|call_package_id:{call_package.id}|duration:{call_package.actual_duration_minutes}min'
        )
        
        logger.info(f"Payout created for listener {call_package.listener.id}: ${call_package.listener_amount}")
        
        return payout
    
    except Exception as e:
        logger.error(f"Error creating payout: {str(e)}")
        return None


def refund_call_package(call_package, reason=''):
    """
    Process refund for a call package (e.g., when listener rejects).
    Refunds to Stripe and marks call_package as refunded.
    
    Args:
        call_package: CallPackage instance to refund
        reason: Reason for refund
    
    Returns:
        dict: Refund result with status and amount
    """
    try:
        if not call_package.stripe_payment_intent_id:
            return {
                'status': 'error',
                'message': 'No payment intent found for this call package'
            }
        
        # Retrieve the payment intent
        payment_intent = stripe.PaymentIntent.retrieve(call_package.stripe_payment_intent_id)
        
        if not payment_intent.charges.data:
            return {
                'status': 'error',
                'message': 'No charge found to refund'
            }
        
        # Get the charge ID
        charge_id = payment_intent.charges.data[0].id
        
        # Create refund
        refund = stripe.Refund.create(
            charge=charge_id,
            reason='requested_by_customer',
            metadata={
                'call_package_id': call_package.id,
                'reason': reason,
            }
        )
        
        # Update call package status
        call_package.status = 'refunded'
        call_package.cancellation_reason = reason
        call_package.save(update_fields=['status', 'cancellation_reason', 'updated_at'])
        
        logger.info(f"✓ Refund processed for call package {call_package.id}: ${call_package.total_amount} - Refund ID: {refund.id}")
        
        return {
            'status': 'success',
            'message': f'Refund of ${call_package.total_amount} processed',
            'amount': str(call_package.total_amount),
            'refund_id': refund.id
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error processing refund: {str(e)}")
        return {
            'status': 'error',
            'message': f'Stripe error: {str(e)}'
        }
    except Exception as e:
        logger.error(f"Error processing refund: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }
    