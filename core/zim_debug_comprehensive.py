#!/usr/bin/env python3
"""
Comprehensive ZIM Token Debug Script
Tests multiple token versions and formats to debug error 6000107
"""

import jwt
import time
import json
import base64

# Your current credentials
ZIM_APP_ID = 1865295594
ZIM_SERVER_SECRET = "efef8b9e5b13336b686eb207fd05e25b"

def generate_token_with_version(version):
    """Generate ZIM token with specific version number"""
    current_time = int(time.time())
    expire_time = current_time + 7200  # 2 hours
    
    payload = {
        "ver": version,
        "uid": "test123",
        "name": "testuser",
        "exp": expire_time,
        "iat": current_time
    }
    
    token = jwt.encode(
        payload,
        ZIM_SERVER_SECRET,
        algorithm='HS256'
    )
    
    return token, payload

def test_all_versions():
    """Test token versions 1-25 to find the correct one"""
    print("=" * 60)
    print("COMPREHENSIVE ZIM TOKEN VERSION TEST")
    print("=" * 60)
    print(f"App ID: {ZIM_APP_ID}")
    print(f"Server Secret: {ZIM_SERVER_SECRET}")
    print("=" * 60)
    
    versions_to_test = [1, 2, 3, 4, 5, 10, 20, 21, 22, 23, 24, 25]
    
    for version in versions_to_test:
        print(f"\n--- TESTING VERSION {version} ---")
        try:
            token, payload = generate_token_with_version(version)
            
            # Decode to verify
            decoded = jwt.decode(token, ZIM_SERVER_SECRET, algorithms=['HS256'])
            
            print(f"✓ Token generated successfully")
            print(f"  Version in payload: {decoded.get('ver', 'NOT SET')}")
            print(f"  UID: {decoded.get('uid', 'NOT SET')}")
            print(f"  Name: {decoded.get('name', 'NOT SET')}")
            print(f"  Token (first 50 chars): {token[:50]}...")
            
            # Check if token structure looks correct
            parts = token.split('.')
            if len(parts) == 3:
                header = json.loads(base64.b64decode(parts[0] + '=='))
                print(f"  Header algorithm: {header.get('alg', 'NOT SET')}")
                print(f"  Header type: {header.get('typ', 'NOT SET')}")
            
        except Exception as e:
            print(f"✗ Error generating version {version}: {e}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("Try each version in your Zego ZIM client to see which works")
    print("=" * 60)

if __name__ == "__main__":
    test_all_versions()