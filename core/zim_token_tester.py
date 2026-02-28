#!/usr/bin/env python
"""
ZIM Token Diagnostic Script
Generates tokens in multiple formats to help identify the correct one for Zego SDK
"""

import jwt
import time
import json
import base64
import hmac
import hashlib
import struct

# Zego credentials
ZIM_APP_ID = 1247203967
ZIM_SERVER_SECRET = "39949576ffad57ec6cdad1f1602cf7bc"

def generate_jwt_token_v20(user_id, username, expire_time_seconds=3600):
    """Generate JWT token with version 20"""
    current_time = int(time.time())
    expire_time = current_time + expire_time_seconds
    
    payload = {
        "iss": "zego",
        "app_id": ZIM_APP_ID,
        "user_id": str(user_id),
        "username": str(username),
        "iat": current_time,
        "exp": expire_time,
        "aud": "zim",
        "ver": 20
    }
    
    return jwt.encode(payload, ZIM_SERVER_SECRET, algorithm="HS256")

def generate_minimal_jwt_token(user_id, username, expire_time_seconds=3600):
    """Generate minimal JWT token with only required fields"""
    current_time = int(time.time())
    expire_time = current_time + expire_time_seconds
    
    payload = {
        "app_id": ZIM_APP_ID,
        "user_id": str(user_id),
        "username": str(username),
        "exp": expire_time,
        "ver": 20
    }
    
    return jwt.encode(payload, ZIM_SERVER_SECRET, algorithm="HS256")

def generate_zego_style_token(user_id, username, expire_time_seconds=3600):
    """Generate token following exact Zego documentation format"""
    current_time = int(time.time())
    expire_time = current_time + expire_time_seconds
    
    # Exact format from Zego documentation
    payload = {
        "ver": 20,                    # Version first
        "app_id": ZIM_APP_ID,         # App ID as number
        "uid": str(user_id),          # Use 'uid' instead of 'user_id'
        "name": str(username),        # Use 'name' instead of 'username'
        "iat": current_time,
        "exp": expire_time
    }
    
    return jwt.encode(payload, ZIM_SERVER_SECRET, algorithm="HS256")

def test_token_formats():
    """Test different token formats"""
    user_id = "123"
    username = "testuser"
    
    print("=" * 60)
    print("ZIM Token Format Testing")
    print("=" * 60)
    
    # Test 1: Standard JWT with ver 20
    print("\n1️⃣ JWT Token with version 20:")
    token1 = generate_jwt_token_v20(user_id, username)
    print(f"Token: {token1}")
    
    # Decode to verify
    payload1 = jwt.decode(token1, options={"verify_signature": False})
    print(f"Payload ver: {payload1.get('ver')}")
    print(f"Payload app_id: {payload1.get('app_id')}")
    print()
    
    # Test 2: Minimal JWT 
    print("2️⃣ Minimal JWT Token:")
    token2 = generate_minimal_jwt_token(user_id, username)
    print(f"Token: {token2}")
    
    payload2 = jwt.decode(token2, options={"verify_signature": False})
    print(f"Payload ver: {payload2.get('ver')}")
    print()
    
    # Test 3: Zego-style token
    print("3️⃣ Zego-style Token (uid/name format):")
    token3 = generate_zego_style_token(user_id, username)
    print(f"Token: {token3}")
    
    payload3 = jwt.decode(token3, options={"verify_signature": False})
    print(f"Payload ver: {payload3.get('ver')}")
    print(f"Payload uid: {payload3.get('uid')}")
    print(f"Payload name: {payload3.get('name')}")
    print()
    
    print("=" * 60)
    print("TESTING INSTRUCTIONS:")
    print("1. Try token1 first (standard format)")
    print("2. If that fails, try token3 (Zego uid/name format)")
    print("3. If both fail, the issue might be server secret or app ID")
    print("=" * 60)
    
    return {
        'standard_jwt': token1,
        'minimal_jwt': token2,
        'zego_style': token3
    }

if __name__ == "__main__":
    tokens = test_token_formats()