"""
Complete solution for the withdrawal and Stripe dashboard issues.

This script provides:
1. Manual webhook testing for payout completion
2. Balance verification and fixing
3. Instructions for fixing Stripe webhook configuration
4. Revenue tracking verification
"""

from django.contrib.auth import get_user_model
from listener.models import ListenerBalance
from chat.call_models import ListenerPayout
from payment.models import RevenueTracking
from decimal import Decimal
from django.utils import timezone
import json

User = get_user_model()

def test_webhook_payout_processing():
    """Test the webhook payout processing manually."""
    print("=== Testing Webhook Payout Processing ===")
    
    # Get a listener with pending payouts
    listener = User.objects.filter(user_type='listener').first()
    balance = ListenerBalance.objects.get(listener=listener)
    
    print(f"Listener: {listener.email}")
    print(f"Current balance: ${balance.available_balance}")
    
    # Create a test pending payout
    test_payout = ListenerPayout.objects.create(
        listener=listener,
        amount=Decimal('1.00'),
        status='pending',
        stripe_payout_id='test_session_webhook',
        notes='Test payout for webhook processing'
    )
    
    print(f"Created test payout: ${test_payout.amount} (ID: {test_payout.id})")
    
    # Simulate webhook processing
    old_balance = balance.available_balance
    
    # This is what the webhook should do:
    if balance.deduct(test_payout.amount):
        test_payout.status = 'completed'
        test_payout.payout_completed_at = timezone.now()
        test_payout.notes = 'Webhook processed - TEST'
        test_payout.save()
        
        print(f"✅ Webhook simulation successful:")
        print(f"  - Balance: ${old_balance} -> ${balance.available_balance}")
        print(f"  - Payout status: {test_payout.status}")
        
        # Clean up test data
        test_payout.delete()
        balance.available_balance = old_balance
        balance.save()
        print("✅ Test data cleaned up")
        
        return True
    else:
        print("❌ Webhook simulation failed - insufficient balance")
        test_payout.delete()
        return False

def verify_revenue_tracking():
    """Verify revenue tracking is working correctly."""
    print("\n=== Revenue Tracking Verification ===")
    
    try:
        total_revenue = RevenueTracking.objects.count()
        print(f"Total revenue tracking records: {total_revenue}")
        
        if total_revenue > 0:
            latest = RevenueTracking.objects.first()
            print(f"Latest revenue record:")
            print(f"  - Total: ${latest.total_amount}")
            print(f"  - Admin: ${latest.admin_portion} ({latest.admin_percentage}%)")
            print(f"  - Listener: ${latest.listener_portion} ({latest.listener_percentage}%)")
            print(f"  - Transaction: {latest.transaction_type}")
        else:
            print("No revenue tracking records found")
            print("Revenue tracking will start with new payments")
            
    except Exception as e:
        print(f"Error checking revenue tracking: {str(e)}")

def check_stripe_webhook_status():
    """Check if Stripe webhook is properly configured."""
    print("\n=== Stripe Webhook Configuration Check ===")
    
    from django.conf import settings
    
    # Check webhook secret
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)
    if webhook_secret:
        print("✅ STRIPE_WEBHOOK_SECRET is configured")
    else:
        print("❌ STRIPE_WEBHOOK_SECRET is missing!")
        print("   Add this to your settings.py: STRIPE_WEBHOOK_SECRET = 'whsec_...'")
    
    # Check for recent webhook activity (look for completed payouts)
    recent_completed = ListenerPayout.objects.filter(
        status='completed',
        payout_completed_at__isnull=False
    ).order_by('-payout_completed_at')[:5]
    
    print(f"Recent completed withdrawals: {recent_completed.count()}")
    for payout in recent_completed:
        print(f"  - ${payout.amount} on {payout.payout_completed_at} (Stripe: {payout.stripe_payout_id[:20]}...)")
    
    if recent_completed.count() == 0:
        print("⚠️  No recent completed withdrawals - webhook may not be working")

def fix_pending_payouts():
    """Find and potentially fix stuck pending payouts."""
    print("\n=== Fixing Stuck Pending Payouts ===")
    
    # Find payouts that have been pending for more than 1 hour
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(hours=1)
    
    stuck_payouts = ListenerPayout.objects.filter(
        status='pending',
        payout_requested_at__lt=cutoff
    )
    
    print(f"Found {stuck_payouts.count()} potentially stuck payouts")
    
    for payout in stuck_payouts:
        print(f"  - ${payout.amount} for {payout.listener.email} (requested {payout.payout_requested_at})")
        print(f"    Stripe session: {payout.stripe_payout_id}")
        
        # You could manually complete these here if needed
        # But first check with Stripe dashboard to see if payment was actually completed

def provide_instructions():
    """Provide instructions for fixing the issues."""
    print("\n=== SOLUTION INSTRUCTIONS ===")
    
    print("🔧 To fix the withdrawal balance issue:")
    print("1. Check your Stripe webhook endpoint configuration:")
    print("   - Go to https://dashboard.stripe.com/webhooks")
    print("   - Make sure you have a webhook endpoint pointing to:")
    print("   - http://10.10.13.27:8005/api/payment/stripe/webhook/")
    print("   - Events to listen for: checkout.session.completed")
    print("")
    print("2. Verify STRIPE_WEBHOOK_SECRET in settings:")
    print("   - Copy the webhook signing secret from Stripe dashboard")
    print("   - Add to settings.py: STRIPE_WEBHOOK_SECRET = 'whsec_...'")
    print("")
    print("3. Test webhook delivery:")
    print("   - In Stripe dashboard, go to webhook endpoint")
    print("   - Send test webhook for 'checkout.session.completed'")
    print("   - Check webhook delivery logs")
    print("")
    print("💰 For Stripe dashboard revenue separation:")
    print("1. Revenue tracking has been added to track admin vs listener portions")
    print("2. Check admin dashboard at /api/admin/dashboard/revenue-stats/")
    print("3. Each payment now creates a RevenueTracking record showing the split")
    print("")
    print("🧪 To test manually:")
    print("1. Create a payout request via API")
    print("2. Complete the Stripe checkout")
    print("3. Check if balance decreases and payout status changes to 'completed'")
    print("")
    print("📊 Current system status:")
    check_current_status()

def check_current_status():
    """Show current system status."""
    listeners = User.objects.filter(user_type='listener')
    total_balance = sum([
        ListenerBalance.objects.get_or_create(listener=l, defaults={
            'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00')
        })[0].available_balance for l in listeners
    ])
    
    pending_withdrawals = ListenerPayout.objects.filter(status='pending').count()
    completed_withdrawals = ListenerPayout.objects.filter(status='completed').count()
    
    print(f"  - Total listeners: {listeners.count()}")
    print(f"  - Total available balance: ${total_balance}")
    print(f"  - Pending withdrawals: {pending_withdrawals}")
    print(f"  - Completed withdrawals: {completed_withdrawals}")

if __name__ == "__main__":
    # Run all tests
    test_webhook_payout_processing()
    verify_revenue_tracking()
    check_stripe_webhook_status()
    fix_pending_payouts()
    provide_instructions()