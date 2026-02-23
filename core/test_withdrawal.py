"""
Test withdrawal flow to identify balance issues.
"""
import json
from decimal import Decimal
from django.contrib.auth import get_user_model
from listener.models import ListenerBalance
from chat.call_models import ListenerPayout

User = get_user_model()

def test_withdrawal_flow():
    """Test the withdrawal process to identify issues."""
    
    # Get a listener with balance
    listener = User.objects.filter(user_type='listener').first()
    if not listener:
        print("No listeners found")
        return
    
    print(f"Testing withdrawal for listener: {listener.email}")
    
    # Get their balance
    try:
        balance = ListenerBalance.objects.get(listener=listener)
        print(f"Current balance: ${balance.available_balance}")
        print(f"Total earned: ${balance.total_earned}")
    except ListenerBalance.DoesNotExist:
        print("No balance account found!")
        return
    
    # Check their payouts
    earned_payouts = ListenerPayout.objects.filter(listener=listener, status='earned')
    print(f"Earned payouts: {earned_payouts.count()}")
    
    pending_payouts = ListenerPayout.objects.filter(listener=listener, status='pending')
    print(f"Pending withdrawals: {pending_payouts.count()}")
    
    completed_payouts = ListenerPayout.objects.filter(listener=listener, status='completed')
    print(f"Completed withdrawals: {completed_payouts.count()}")
    
    # Calculate expected balance
    total_earned = sum([p.amount for p in earned_payouts])
    total_completed = sum([p.amount for p in completed_payouts])
    expected_balance = total_earned - total_completed
    
    print(f"\nBalance analysis:")
    print(f"- Total earned from payouts: ${total_earned}")
    print(f"- Total completed withdrawals: ${total_completed}")
    print(f"- Expected balance: ${expected_balance}")
    print(f"- Actual balance: ${balance.available_balance}")
    print(f"- Difference: ${balance.available_balance - expected_balance}")
    
    if balance.available_balance < Decimal('1.00'):
        print("Balance too low for test withdrawal")
        return
    
    # Test the deduct function
    test_amount = min(balance.available_balance, Decimal('0.50'))
    print(f"\nTesting deduction of ${test_amount}...")
    
    old_balance = balance.available_balance
    if balance.deduct(test_amount):
        print(f"✅ Deduction successful: ${old_balance} -> ${balance.available_balance}")
        
        # Add it back for testing
        balance.available_balance += test_amount
        balance.save()
        print(f"✅ Added back for testing: ${balance.available_balance}")
    else:
        print(f"❌ Deduction failed!")

if __name__ == "__main__":
    test_withdrawal_flow()