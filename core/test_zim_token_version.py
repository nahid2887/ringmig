#!/usr/bin/env python
"""Test script to verify ZIM token generation with correct version 20"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
sys.path.insert(0, '/c/ringmig2/ringmig/core')

django.setup()

from chat.zim_utils import zim_token_generator

print("=" * 60)
print("ZIM Token Generator Test - Verifying Version 20 Fix")
print("=" * 60)

# Test 1: Generate single token
print("\n1️⃣ Generating single token...")
token = zim_token_generator.generate_token('16', 'talker@example.com')
print("✅ Token generated successfully")

# Test 2: Verify token
print("\n2️⃣ Verifying token structure...")
payload = zim_token_generator.verify_token(token)
print("✅ Token verified successfully")

# Test 3: Check critical fields
print("\n3️⃣ Checking critical fields in payload...")
critical_fields = {
    'app_id': 1247203967,
    'user_id': '16',
    'username': 'talker@example.com',
    'aud': 'zim',
    'iss': 'zego',
    'ver': 20
}

all_correct = True
for field, expected_value in critical_fields.items():
    actual_value = payload.get(field)
    status = "✅" if actual_value == expected_value else "❌"
    print(f"  {status} {field}: {actual_value} (expected: {expected_value})")
    if actual_value != expected_value:
        all_correct = False

# Test 4: Summary
print("\n" + "=" * 60)
if all_correct:
    print("✅ ALL TESTS PASSED!")
    print("Token version 20 is correctly implemented")
    print("Error 6000107 is now fixed!")
else:
    print("❌ Some tests failed")
    print("Please check the implementation")

print("=" * 60)