from django.conf import settings
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY

def create_payment_intent(amount, currency, customer_id, **kwargs):
    return stripe.PaymentIntent.create(
        amount=amount,
        currency=currency,
        customer=customer_id,
        **kwargs
    )

def create_transfer(amount, currency, destination_account_id, **kwargs):
    return stripe.Transfer.create(
        amount=amount,
        currency=currency,
        destination=destination_account_id,
        **kwargs
    )

def retrieve_account(account_id):
    return stripe.Account.retrieve(account_id)

def list_transfers(limit=10, **kwargs):
    return stripe.Transfer.list(limit=limit, **kwargs)