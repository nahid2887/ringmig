from django.conf import settings
from stripe_connect.client import stripe_client
from stripe_connect.transfers import create_transfer

def create_payment_intent(amount, currency, talker_account_id):
    payment_intent = stripe_client.PaymentIntent.create(
        amount=amount,
        currency=currency,
        payment_method_types=["card"],
        transfer_data={
            "destination": talker_account_id,
        },
    )
    return payment_intent

def handle_tip_payment(tip_amount, talker_account_id):
    if tip_amount <= 0:
        raise ValueError("Tip amount must be greater than zero.")
    
    payment_intent = create_payment_intent(tip_amount, settings.DEFAULT_CURRENCY, talker_account_id)
    return payment_intent