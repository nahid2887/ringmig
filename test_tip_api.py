#!/usr/bin/env python
"""
Test script for the Tip Payment System API endpoints

This script tests the API endpoints we created for the tip system.
"""

import requests
import json
import sys
import os

# Add Django project to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'core'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
django.setup()

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

BASE_URL = "http://127.0.0.1:8006"

def get_jwt_token(user):
    """Generate JWT token for a user."""
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token)

def test_tip_api():
    print("🧪 Testing Tip Payment API Endpoints")
    print("=" * 50)
    
    try:
        # Get test users
        talker = User.objects.filter(user_type='talker').first()
        listener = User.objects.filter(user_type='listener').first()
        
        if not talker or not listener:
            print("❌ Need at least one talker and one listener")
            return
        
        print(f"👤 Talker: {talker.email} (ID: {talker.id})")
        print(f"🎧 Listener: {listener.email} (ID: {listener.id})")
        
        # Get JWT token for talker
        talker_token = get_jwt_token(talker)
        listener_token = get_jwt_token(listener)
        
        headers_talker = {
            'Authorization': f'Bearer {talker_token}',
            'Content-Type': 'application/json'
        }
        
        headers_listener = {
            'Authorization': f'Bearer {listener_token}',
            'Content-Type': 'application/json'
        }
        
        # Test 1: Check initial listener balance
        print("\\n1️⃣ Checking initial listener balance...")
        response = requests.get(
            f"{BASE_URL}/api/listener/balance/my-balance/",
            headers=headers_listener
        )
        if response.status_code == 200:
            balance_data = response.json()
            initial_balance = balance_data['available_balance']
            print(f"✅ Initial balance: ${initial_balance}")
        else:
            print(f"❌ Failed to get balance: {response.status_code}")
            return
        
        # Test 2: Create tip payment intent
        print("\\n2️⃣ Creating tip payment intent...")
        tip_data = {
            "listener_id": listener.id,
            "amount": "20.00",
            "message": "API Test Tip - Thanks!"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/payment/tips/create-payment-intent/",
            headers=headers_talker,
            json=tip_data
        )
        
        if response.status_code == 200:
            payment_data = response.json()
            print(f"✅ Payment intent created!")
            print(f"   • Tip ID: {payment_data['tip_id']}")
            print(f"   • Amount: ${payment_data['amount']}")
            print(f"   • Admin fee: ${payment_data['admin_fee']}")
            print(f"   • Listener amount: ${payment_data['listener_amount']}")
            print(f"   • Payment intent ID: {payment_data['stripe_payment_intent_id']}")
        else:
            print(f"❌ Failed to create tip: {response.status_code}")
            print(f"Response: {response.text}")
            return
        
        # Test 3: Check sent tips (talker)
        print("\\n3️⃣ Checking sent tips...")
        response = requests.get(
            f"{BASE_URL}/api/payment/tips/my-sent-tips/",
            headers=headers_talker
        )
        
        if response.status_code == 200:
            sent_tips = response.json()
            print(f"✅ Found {len(sent_tips)} sent tip(s)")
            for tip in sent_tips[-1:]:  # Show last tip
                print(f"   • Tip #{tip['id']}: ${tip['amount']} to {tip['listener_details']['email']}")
                print(f"   • Status: {tip['status']}")
                print(f"   • Message: {tip['message']}")
        else:
            print(f"❌ Failed to get sent tips: {response.status_code}")
        
        # Test 4: Check received tips (listener)
        print("\\n4️⃣ Checking received tips...")
        response = requests.get(
            f"{BASE_URL}/api/payment/tips/my-received-tips/",
            headers=headers_listener
        )
        
        if response.status_code == 200:
            received_tips = response.json()
            print(f"✅ Found {len(received_tips)} received tip(s)")
            for tip in received_tips[-1:]:  # Show last tip
                print(f"   • Tip #{tip['id']}: ${tip['amount']} from {tip['talker_details']['email']}")
                print(f"   • Status: {tip['status']}")
                print(f"   • Message: {tip['message']}")
        else:
            print(f"❌ Failed to get received tips: {response.status_code}")
        
        # Test 5: Test error cases
        print("\\n5️⃣ Testing error cases...")
        
        # Try to create tip as listener (should fail)
        response = requests.post(
            f"{BASE_URL}/api/payment/tips/create-payment-intent/",
            headers=headers_listener,
            json=tip_data
        )
        if response.status_code == 403:
            print("✅ Correctly blocked listener from sending tips")
        else:
            print(f"❌ Unexpected response: {response.status_code}")
        
        # Try to create tip with invalid listener ID
        invalid_tip_data = {
            "listener_id": 999999,
            "amount": "10.00",
            "message": "Invalid listener"
        }
        response = requests.post(
            f"{BASE_URL}/api/payment/tips/create-payment-intent/",
            headers=headers_talker,
            json=invalid_tip_data
        )
        if response.status_code == 400:
            print("✅ Correctly validated invalid listener ID")
        else:
            print(f"❌ Unexpected response for invalid listener: {response.status_code}")
        
        # Try to create tip with invalid amount
        invalid_amount_data = {
            "listener_id": listener.id,
            "amount": "0.00",
            "message": "Zero amount"
        }
        response = requests.post(
            f"{BASE_URL}/api/payment/tips/create-payment-intent/",
            headers=headers_talker,
            json=invalid_amount_data
        )
        if response.status_code == 400:
            print("✅ Correctly validated minimum amount")
        else:
            print(f"❌ Unexpected response for zero amount: {response.status_code}")
        
        print("\\n🎉 All API tests completed!")
        print("\\n📋 Summary of available endpoints:")
        print("   • POST /api/payment/tips/create-payment-intent/ - Create tip payment")
        print("   • GET /api/payment/tips/my-sent-tips/ - View sent tips (talker)")
        print("   • GET /api/payment/tips/my-received-tips/ - View received tips (listener)")
        print("   • GET /api/listener/balance/my-balance/ - View listener balance")
        
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_tip_api()