"""Stripe payment helpers for session booking purchases."""
import logging

import stripe
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

from payment.models import StripeCustomer

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


def create_session_booking_payment_intent(booking, payment_method_id=None):
    """Create Stripe payment intent and checkout session for a booking."""
    try:
        if payment_method_id in ['', None, 'string', 'null']:
            payment_method_id = None

        from payment.models import StripeListenerAccount

        try:
            listener_account = StripeListenerAccount.objects.get(
                listener=booking.listener,
                is_enabled=True,
            )
        except StripeListenerAccount.DoesNotExist as exc:
            raise Exception('Listener has not connected an active Stripe account for automatic payout') from exc

        stripe_customer = _get_or_create_customer(booking.talker)
        amount_cents = int(booking.price * 100)

        payment_intent_data = {
            'amount': amount_cents,
            'currency': 'usd',
            'customer': stripe_customer.stripe_customer_id,
            'metadata': {
                'session_booking_id': str(booking.id),
                'talker_id': booking.talker.id,
                'listener_id': booking.listener.id,
                'booking_date': booking.booking_date.isoformat(),
                'start_time': booking.start_time.strftime('%H:%M:%S'),
                'duration_minutes': booking.duration_minutes,
                'payout_mode': 'listener_transfer',
                'listener_stripe_account_id': listener_account.stripe_account_id,
            },
            'description': (
                f"Booking: {booking.duration_minutes} min with {booking.listener.email} "
                f"on {booking.booking_date} at {booking.start_time.strftime('%H:%M')}"
            ),
        }

        if payment_method_id:
            payment_intent_data['payment_method'] = payment_method_id
            payment_intent_data['confirm'] = True

        payment_intent = stripe.PaymentIntent.create(**payment_intent_data)

        # Get the frontend URL from settings for Stripe redirect URLs
        # Format: https://example.com/dashboard/talker
        frontend_url = getattr(settings, 'FRONTEND_URL2', 'https://www.ring-mig.com/dashboard/talker')
        # Build base URL for cancel redirect (remove /dashboard/talker)
        if '/dashboard/talker' in frontend_url:
            base_url = frontend_url.rsplit('/dashboard/talker', 1)[0]
        else:
            base_url = frontend_url.rsplit('/', 1)[0] if '/' in frontend_url else frontend_url
        
        checkout_session = stripe.checkout.Session.create(
            customer=stripe_customer.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': booking.package.name if booking.package else 'Session Booking',
                        'description': (
                            f"{booking.duration_minutes} minutes on {booking.booking_date} "
                            f"at {booking.start_time.strftime('%H:%M')}"
                        ),
                    },
                    'unit_amount': amount_cents,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f'{frontend_url}/payment-success-booking',
            cancel_url=f'{base_url}/payment-cancelled',
            metadata={
                'session_booking_id': str(booking.id),
                'payment_intent_id': payment_intent.id,
                'payout_mode': 'listener_transfer',
                'listener_stripe_account_id': listener_account.stripe_account_id,
            },
        )

        booking.payment_link = checkout_session.url
        booking.transaction_id = payment_intent.id
        booking.save(update_fields=['payment_link', 'transaction_id', 'updated_at'])

        return {
            'payment_intent_id': payment_intent.id,
            'client_secret': payment_intent.client_secret,
            'status': payment_intent.status,
            'amount': float(booking.price),
            'currency': 'usd',
            'payment_link': checkout_session.url,
            'checkout_session_id': checkout_session.id,
        }
    except stripe.error.StripeError as exc:
        logger.error('Stripe error for booking %s: %s', booking.id, str(exc))
        raise Exception(f'Payment processing error: {str(exc)}')


def confirm_session_booking_payment(payment_intent_id):
    """Fetch payment intent and return normalized payment status data."""
    payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
    return {
        'payment_intent_id': payment_intent.id,
        'client_secret': payment_intent.client_secret,
        'status': payment_intent.status,
        'amount': payment_intent.amount / 100,
        'currency': payment_intent.currency,
    }


def process_stripe_refund(booking, amount=None):
    """
    Process Stripe refund for a booking.
    Refunds to the original payment card.
    
    Args:
        booking: SessionBooking instance with transaction_id (payment_intent_id)
        amount: Optional partial refund amount in dollars (None for full refund)
    
    Returns:
        dict with success status, refund_id, and amount
    """
    payment_intent_id = booking.transaction_id
    
    if not payment_intent_id:
        logger.error('No PaymentIntent found for booking %s', booking.id)
        return {
            "success": False,
            "message": "No PaymentIntent found for this booking"
        }
    
    try:
        # Determine refund amount
        if amount:
            refund_amount = int(float(amount) * 100)  # dollars → cents
        else:
            refund_amount = None  # full refund

        # Create refund using payment_intent (requested flow)
        refund_data = {
            "payment_intent": payment_intent_id,
        }

        if refund_amount:
            refund_data["amount"] = refund_amount

        refund = stripe.Refund.create(**refund_data)

        logger.info(
            'Stripe refund created for booking %s: refund_id=%s, payment_intent=%s, amount=%s',
            booking.id,
            refund.id,
            payment_intent_id,
            amount or 'full',
        )

        # Store refund details in booking
        booking.stripe_refund_id = refund.id
        booking.refund_amount = amount if amount else booking.price
        booking.refunded_at = timezone.now()
        booking.save(update_fields=['stripe_refund_id', 'refund_amount', 'refunded_at'])

        return {
            "success": True,
            "refund_id": refund.id,
            "amount": amount if amount else float(booking.price),
            "currency": "usd",
            "status": getattr(refund, 'status', None),
        }
    
    except stripe.error.InvalidRequestError as e:
        logger.error('Stripe refund error for booking %s: %s', booking.id, str(e))
        return {
            "success": False,
            "message": f"Stripe error: {str(e)}"
        }
    
    except Exception as e:
        logger.error('Unexpected error processing refund for booking %s: %s', booking.id, str(e))
        return {
            "success": False,
            "message": str(e)
        }


def reverse_booking_listener_transfer(booking, amount):
    """Reverse the listener-side Stripe transfer for a booking refund.

    This reverses only the listener share. The admin share is kept in local
    bookkeeping and reflected in the refund split returned to the caller.
    """
    transfer_id = getattr(booking, 'stripe_transfer_id', '')

    if not transfer_id:
        return {
            'success': True,
            'reversal_id': None,
            'transfer_id': None,
            'amount': str(amount),
            'message': 'No listener transfer recorded for this booking',
        }

    try:
        amount_decimal = Decimal(str(amount)).quantize(Decimal('0.01'))
        if amount_decimal <= 0:
            return {
                'success': True,
                'reversal_id': None,
                'transfer_id': transfer_id,
                'amount': '0.00',
                'message': 'No listener transfer reversal required',
            }

        amount_cents = int(amount_decimal * Decimal('100'))

        reversal = stripe.Transfer.create_reversal(
            transfer_id,
            amount=amount_cents,
            metadata={
                'source_type': 'session_booking',
                'booking_id': str(booking.id),
                'listener_id': booking.listener.id,
                'refund_amount': str(amount_decimal),
            },
        )

        logger.info(
            'Stripe transfer reversal created for booking %s: reversal_id=%s, transfer_id=%s, amount=%s',
            booking.id,
            reversal.id,
            transfer_id,
            amount_decimal,
        )

        return {
            'success': True,
            'reversal_id': reversal.id,
            'transfer_id': transfer_id,
            'amount': str(amount_decimal),
            'message': 'Listener transfer reversed successfully',
        }

    except stripe.error.StripeError as exc:
        logger.error('Stripe transfer reversal error for booking %s: %s', booking.id, str(exc))
        return {
            'success': False,
            'reversal_id': None,
            'transfer_id': transfer_id,
            'amount': str(amount),
            'message': f'Stripe transfer reversal failed: {str(exc)}',
        }


def _get_or_create_customer(user):
    """Get or create Stripe customer mapping for a user."""
    try:
        customer = StripeCustomer.objects.get(user=user)
        try:
            stripe.Customer.retrieve(customer.stripe_customer_id)
        except stripe.error.InvalidRequestError:
            stripe_customer = stripe.Customer.create(
                email=user.email,
                metadata={'user_id': user.id},
            )
            customer.stripe_customer_id = stripe_customer.id
            customer.save(update_fields=['stripe_customer_id'])
        return customer
    except StripeCustomer.DoesNotExist:
        stripe_customer = stripe.Customer.create(
            email=user.email,
            metadata={'user_id': user.id},
        )
        return StripeCustomer.objects.create(
            user=user,
            stripe_customer_id=stripe_customer.id,
        )
