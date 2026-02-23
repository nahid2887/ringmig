"""
Quick fix for pending withdrawals that are stuck due to webhook issues
"""
from django.contrib.auth import get_user_model
from listener.models import ListenerBalance
from chat.call_models import ListenerPayout
from django.utils import timezone
from decimal import Decimal

User = get_user_model()

def fix_stuck_withdrawals():
    """Fix withdrawals that are stuck in pending status."""
    
    print("=== FIXING STUCK WITHDRAWALS ===")
    
    # Get stuck pending payouts (older than 10 minutes)
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(minutes=10)
    
    stuck_payouts = ListenerPayout.objects.filter(
        status='pending',
        payout_requested_at__lt=cutoff
    ).select_related('listener')
    
    print(f"Found {stuck_payouts.count()} stuck withdrawals to fix")
    
    fixed_count = 0
    for payout in stuck_payouts:
        try:
            # Get listener balance
            balance = ListenerBalance.objects.get(listener=payout.listener)
            
            print(f"Fixing payout for {payout.listener.email}: ${payout.amount}")
            print(f"  Current balance: ${balance.available_balance}")
            
            # Check if we should complete this payout
            # For now, let's just mark them as failed so they don't stay pending
            payout.status = 'failed'
            payout.notes = f'Auto-failed due to webhook timeout - please retry withdrawal'
            payout.save()
            
            print(f"  ❌ Marked as failed - user can retry")
            fixed_count += 1
            
        except Exception as e:
            print(f"  Error fixing payout {payout.id}: {str(e)}")
    
    print(f"Fixed {fixed_count} stuck withdrawals")
    print("Users can now retry their withdrawals")

def test_current_balance_api():
    """Test the current balance API."""
    print("\n=== TESTING BALANCE API ===")
    
    listener = User.objects.filter(user_type='listener').first()
    balance = ListenerBalance.objects.get(listener=listener)
    
    print(f"Testing API for: {listener.email}")
    print(f"Available balance: ${balance.available_balance}")
    
    # Check what earned payouts they have
    earned = ListenerPayout.objects.filter(listener=listener, status='earned')
    print(f"Earned payouts ready for withdrawal: {earned.count()}")
    
    total_earned = sum([p.amount for p in earned])
    print(f"Total amount available for withdrawal: ${total_earned}")
    
    if total_earned > 0:
        print("✅ User has funds available for withdrawal")
        print("✅ They can use the API: POST /api/chat/payouts/create-payout-link/")
    else:
        print("❌ No earned payouts available for withdrawal")

if __name__ == "__main__":
    fix_stuck_withdrawals()
    test_current_balance_api()