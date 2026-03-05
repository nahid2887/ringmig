#!/usr/bin/env python
"""
Example of how to use the new Tip Payment System

This script demonstrates:
1. Creating a tip payment intent via API
2. Processing the payment through Stripe webhook (simulated)
3. Checking listener balance updates
"""

import requests
import json
import os
import sys

# Add Django project to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'core'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
django.setup()

from django.contrib.auth import get_user_model
from payment.models import Tip
from listener.models import ListenerBalance

User = get_user_model()

# Configuration
BASE_URL = "http://10.10.13.27:8005"
API_BASE = f"{BASE_URL}/api"

def demonstrate_tip_system():
    print("🎯 Tip Payment System Demo")
    print("=" * 50)
    
    # Get sample users (assuming they exist)
    try:
        talker = User.objects.filter(user_type='talker').first()
        listener = User.objects.filter(user_type='listener').first()
        
        if not talker or not listener:
            print("❌ Need at least one talker and one listener user")
            return
            
        print(f"👤 Talker: {talker.email}")
        print(f"🎧 Listener: {listener.email}")
        
        # Check initial listener balance
        balance, created = ListenerBalance.objects.get_or_create(
            listener=listener,
            defaults={'available_balance': 0.00, 'total_earned': 0.00}
        )
        initial_balance = balance.available_balance
        print(f"💰 Initial listener balance: ${initial_balance}")
        
        # Create a tip
        tip_amount = "15.00"  # $15 tip
        print(f"\n💡 Creating tip of ${tip_amount}")
        
        tip = Tip.objects.create(
            talker=talker,
            listener=listener,
            amount=tip_amount,
            message="Great conversation! Thanks!",
            status='pending'
        )
        
        print(f"✅ Tip created: ID #{tip.id}")
        print(f"   • Amount: ${tip.amount}")
        print(f"   • Admin fee (10%): ${tip.admin_fee}")
        print(f"   • Listener amount (90%): ${tip.listener_amount}")
        print(f"   • Message: {tip.message}")
        
        # Simulate successful payment
        print(f"\n💳 Simulating successful payment...")
        success = tip.confirm_payment()
        
        if success:
            print("✅ Payment confirmed!")
            
            # Check updated balance
            balance.refresh_from_db()
            final_balance = balance.available_balance
            balance_increase = final_balance - initial_balance
            
            print(f"💰 Updated listener balance: ${final_balance}")
            print(f"📈 Balance increase: +${balance_increase}")
            
            # Verify the split
            expected_listener_amount = float(tip_amount) * 0.9
            print(f"\n📊 Payment Split Verification:")
            print(f"   • Total paid: ${tip_amount}")
            print(f"   • Admin fee (10%): ${float(tip_amount) * 0.1:.2f}")
            print(f"   • Listener gets (90%): ${expected_listener_amount:.2f}")
            print(f"   • Actual balance increase: ${balance_increase}")
            
            if abs(float(balance_increase) - expected_listener_amount) < 0.01:
                print("✅ Split calculation is correct!")
            else:
                print("❌ Split calculation mismatch!")
        else:
            print("❌ Payment confirmation failed")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")

def show_api_endpoints():
    print("\n🔗 Available API Endpoints:")
    print("=" * 40)
    print(f"POST {API_BASE}/payment/tips/create-payment-intent/")
    print("  - Create a new tip payment")
    print("  - Body: {\"listener_id\": 5, \"amount\": \"10.00\", \"message\": \"Thanks!\"}")
    print()
    print(f"GET {API_BASE}/payment/tips/my-sent-tips/")
    print("  - View tips sent by talker")
    print()
    print(f"GET {API_BASE}/payment/tips/my-received-tips/")
    print("  - View tips received by listener")
    print()
    print(f"GET {API_BASE}/listener/balance/my-balance/")
    print("  - View listener current balance")

def show_example_curl_commands():
    print("\n🌐 Example cURL Commands:")
    print("=" * 40)
    
    print("1. Create tip payment:")
    print('curl -X POST \\')
    print(f'  "{API_BASE}/payment/tips/create-payment-intent/" \\')
    print('  -H "Content-Type: application/json" \\')
    print('  -H "Authorization: Bearer YOUR_JWT_TOKEN" \\')
    print('  -d \'{"listener_id": 5, "amount": "25.00", "message": "Amazing session!"}\'')
    
    print("\n2. Check sent tips:")
    print('curl -X GET \\')
    print(f'  "{API_BASE}/payment/tips/my-sent-tips/" \\')
    print('  -H "Authorization: Bearer YOUR_JWT_TOKEN"')
    
    print("\n3. Check received tips:")
    print('curl -X GET \\')
    print(f'  "{API_BASE}/payment/tips/my-received-tips/" \\')
    print('  -H "Authorization: Bearer YOUR_JWT_TOKEN"')
    
    print("\n4. Check listener balance:")
    print('curl -X GET \\')
    print(f'  "{API_BASE}/listener/balance/my-balance/" \\')
    print('  -H "Authorization: Bearer YOUR_JWT_TOKEN"')

if __name__ == "__main__":
    demonstrate_tip_system()
    show_api_endpoints()
    show_example_curl_commands()
    
    print("\n🎉 Tip Payment System Ready!")
    print("The system automatically splits payments:")
    print("• 10% goes to admin")
    print("• 90% goes to listener balance")
    print("• Balance updates happen automatically after successful Stripe payment")