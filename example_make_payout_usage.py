#!/usr/bin/env python
"""
Example usage of the make-payout endpoint
"""

import requests
import json

# Configuration
API_BASE_URL = "http://10.10.13.27:8005/api"
LISTENER_TOKEN = "your-listener-auth-token"  # Replace with actual token

# Headers with authentication
headers = {
    "Authorization": f"Bearer {LISTENER_TOKEN}",
    "Content-Type": "application/json"
}

# Test 1: Create a payout of $100
print("Test 1: Creating $100 payout...")
payload = {
    "amount": "100.00"
}

response = requests.post(
    f"{API_BASE_URL}/chat/payouts/make-payout/",
    json=payload,
    headers=headers
)

print(f"Status Code: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")

if response.status_code == 200:
    data = response.json()
    print(f"\n✓ Payout successful!")
    print(f"  - Transfer ID: {data['transfer_id']}")
    print(f"  - Amount: {data['amount']}")
    print(f"  - New Balance: {data['new_balance']}")
else:
    print(f"\n✗ Payout failed: {response.json()}")

# Test 2: Attempt payout with insufficient balance
print("\n\nTest 2: Attempting payout with insufficient balance...")
payload = {
    "amount": "50000.00"  # Exceeds available balance
}

response = requests.post(
    f"{API_BASE_URL}/chat/payouts/make-payout/",
    json=payload,
    headers=headers
)

if response.status_code == 400:
    data = response.json()
    print(f"✓ Correctly rejected (HTTP 400)")
    print(f"  Error: {data['error']}")
    print(f"  Available: {data['available_balance']}")

# Test 3: Get payout summary
print("\n\nTest 3: Getting payout summary...")
response = requests.get(
    f"{API_BASE_URL}/chat/payouts/summary/",
    headers=headers
)

if response.status_code == 200:
    data = response.json()
    print(f"✓ Summary retrieved")
    print(f"  - Current Balance: {data['balance']}")
    print(f"  - Total Earned: {data['total_earned']}")
    print(f"  - Payouts: {len(data['payouts'])}")
