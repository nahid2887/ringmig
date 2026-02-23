"""
Debug webhook processing and test balance withdrawal API
"""
from django.contrib.auth import get_user_model
from listener.models import ListenerBalance
from chat.call_models import ListenerPayout
from decimal import Decimal
import requests
import json

User = get_user_model()

def test_payout_api():
    """Test the payout API creation."""
    
    listener = User.objects.filter(user_type='listener').first()
    balance = ListenerBalance.objects.get(listener=listener)
    
    print(f"Testing payout API for {listener.email}")
    print(f"Current balance: ${balance.available_balance}")
    
    # Check if there are any existing pending payouts
    pending = ListenerPayout.objects.filter(listener=listener, status='pending')
    print(f"Existing pending payouts: {pending.count()}")
    
    for p in pending:
        print(f"  - ${p.amount} (ID: {p.id}, Stripe ID: {p.stripe_payout_id})")
    
    return {
        'listener_id': listener.id,
        'balance': str(balance.available_balance),
        'pending_count': pending.count()
    }

def simulate_webhook_processing(listener_id, payout_amount, session_id):
    """Simulate the webhook processing that should happen after Stripe checkout."""
    
    from django.utils import timezone
    
    listener = User.objects.get(id=listener_id)
    payout_amount = Decimal(str(payout_amount))
    
    print(f"Simulating webhook processing:")
    print(f"- Listener: {listener.email}")
    print(f"- Amount: ${payout_amount}")
    print(f"- Session ID: {session_id}")
    
    # Get balance before
    balance = ListenerBalance.objects.get(listener=listener)
    old_balance = balance.available_balance
    
    print(f"- Old balance: ${old_balance}")
    
    # Deduct from balance (what webhook should do)
    if balance.deduct(payout_amount):
        print(f"✅ Deducted ${payout_amount} from balance: ${old_balance} -> ${balance.available_balance}")
        
        # Update pending payouts to completed (what webhook should do)
        pending_payouts = ListenerPayout.objects.filter(
            listener=listener,
            status='pending',
            stripe_payout_id=session_id
        )
        
        updated_count = 0
        for payout in pending_payouts:
            payout.status = 'completed'
            payout.payout_completed_at = timezone.now()
            payout.notes = f'Simulated payout completion'
            payout.save()
            updated_count += 1
        
        print(f"✅ Updated {updated_count} payouts to completed")
        
        return True
    else:
        print(f"❌ Failed to deduct ${payout_amount} from balance")
        return False

if __name__ == "__main__":
    result = test_payout_api()
    print(f"\nResult: {result}")
    
    # You can uncomment this to test webhook simulation
    # simulate_webhook_processing(result['listener_id'], '1.00', 'test_session_123')