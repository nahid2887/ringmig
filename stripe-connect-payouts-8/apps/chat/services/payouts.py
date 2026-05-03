from django.conf import settings
from stripe_connect.client import stripe_client
from stripe_connect.transfers import create_transfer

def handle_purchase_payout(talker_id, amount):
    # Create a transfer to the talker's account for the purchase
    transfer = create_transfer(talker_id, amount)
    return transfer

def handle_extend_minutes_payout(talker_id, amount):
    # Create a transfer to the talker's account for extending minutes
    transfer = create_transfer(talker_id, amount)
    return transfer

def handle_tip_payout(talker_id, amount):
    # Create a transfer to the talker's account for tips
    transfer = create_transfer(talker_id, amount)
    return transfer

def process_payout(api_endpoint, talker_id, amount):
    if api_endpoint == '/chat/call-packages/purchase/':
        return handle_purchase_payout(talker_id, amount)
    elif api_endpoint == '/chat/call-sessions/extend-minutes/':
        return handle_extend_minutes_payout(talker_id, amount)
    elif api_endpoint == '/payment/tips/create-payment-intent/':
        return handle_tip_payout(talker_id, amount)
    else:
        raise ValueError("Invalid API endpoint")