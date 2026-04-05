"""Stripe payment helpers for session booking purchases."""
import logging

import stripe
from django.conf import settings

from payment.models import StripeCustomer

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


def create_session_booking_payment_intent(booking, payment_method_id=None):
    """Create Stripe payment intent and checkout session for a booking."""
    try:
        if payment_method_id in ['', None, 'string', 'null']:
            payment_method_id = None

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
            success_url='http://localhost:5174/dashboard/talker/payment-success-booking',
            cancel_url='http://localhost:5174/payment-cancelled',
            metadata={
                'session_booking_id': str(booking.id),
                'payment_intent_id': payment_intent.id,
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
