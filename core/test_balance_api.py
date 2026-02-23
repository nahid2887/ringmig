"""
Test script to check listener balance API endpoints
"""
from django.contrib.auth import get_user_model
from listener.models import ListenerBalance
from chat.call_models import ListenerPayout, CallPackage
from django.db.models import Sum
from decimal import Decimal

User = get_user_model()

def test_balance_consistency():
    """Test if balances are consistent between systems"""
    print("=== Testing Balance Consistency ===")
    
    listeners = User.objects.filter(user_type='listener')[:5]
    
    for listener in listeners:
        print(f"\n👤 {listener.email}")
        
        # Get balance from ListenerBalance
        try:
            balance_account = ListenerBalance.objects.get(listener=listener)
            available_balance = balance_account.available_balance
            total_earned = balance_account.total_earned
        except ListenerBalance.DoesNotExist:
            available_balance = Decimal('0.00')
            total_earned = Decimal('0.00')
            
        # Calculate expected balance from payouts
        earned_payouts = ListenerPayout.objects.filter(
            listener=listener,
            status='earned',
            is_extension=False
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        extension_earnings = CallPackage.objects.filter(
            listener=listener,
            is_extension=True,
            status__in=['confirmed', 'used', 'completed']
        ).aggregate(total=Sum('listener_amount'))['total'] or Decimal('0.00')
        
        completed_withdrawals = ListenerPayout.objects.filter(
            listener=listener,
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        expected_balance = earned_payouts + extension_earnings - completed_withdrawals
        
        print(f"  💰 Available Balance: ${available_balance}")
        print(f"  📊 Total Earned: ${total_earned}")
        print(f"  📈 Expected Balance: ${expected_balance}")
        
        if available_balance == expected_balance:
            print("  ✅ Balance is correct!")
        else:
            print(f"  ❌ Balance mismatch! Difference: ${available_balance - expected_balance}")
            
        print(f"  🧮 Breakdown:")
        print(f"    - Earned payouts: ${earned_payouts}")
        print(f"    - Extension earnings: ${extension_earnings}")
        print(f"    - Completed withdrawals: ${completed_withdrawals}")

if __name__ == "__main__":
    test_balance_consistency()