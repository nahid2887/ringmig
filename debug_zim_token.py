"""
Debug ZIM Token Generation - Comprehensive Testing
Test all possible token formats to identify the correct one for Zego SDK
"""

import jwt
import time
import json
import base64
import struct
import hashlib
import hmac

# Current credentials
APP_ID = 1865295594
SERVER_SECRET = "efef8b9e5b13336b686eb207fd05e25b"  # Note: This looks incomplete

def decode_jwt_payload(token_str):
    """Decode JWT payload without verification to see what's inside"""
    try:
        parts = token_str.split('.')
        if len(parts) != 3:
            return f"Invalid JWT format - {len(parts)} parts instead of 3"
        
        # Decode payload (second part)
        payload_b64 = parts[1]
        # Add padding if needed
        missing_padding = len(payload_b64) % 4
        if missing_padding:
            payload_b64 += '=' * (4 - missing_padding)
        
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes)
        
        return payload
    except Exception as e:
        return f"Decode error: {str(e)}"

def test_token_format_1():
    """Test format 1: Version first, then everything else"""
    current_time = int(time.time())
    expire_time = current_time + 3600
    
    payload = {
        "ver": 20,                    # Version FIRST
        "app_id": APP_ID,
        "uid": "123",
        "name": "testuser",
        "iat": current_time,
        "exp": expire_time
    }
    
    token = jwt.encode(payload, SERVER_SECRET, algorithm='HS256')
    decoded = decode_jwt_payload(token)
    
    print("=== TOKEN FORMAT 1 (ver first) ===")
    print(f"Token: {token}")
    print(f"Payload: {json.dumps(decoded, indent=2) if isinstance(decoded, dict) else decoded}")
    print()
    
    return token

def test_token_format_2():
    """Test format 2: Standard JWT field order"""
    current_time = int(time.time())
    expire_time = current_time + 3600
    
    payload = {
        "iat": current_time,
        "exp": expire_time,
        "app_id": APP_ID,
        "uid": "123",
        "name": "testuser",
        "ver": 20                     # Version LAST
    }
    
    token = jwt.encode(payload, SERVER_SECRET, algorithm='HS256')
    decoded = decode_jwt_payload(token)
    
    print("=== TOKEN FORMAT 2 (ver last) ===")
    print(f"Token: {token}")
    print(f"Payload: {json.dumps(decoded, indent=2) if isinstance(decoded, dict) else decoded}")
    print()
    
    return token

def test_token_format_3():
    """Test format 3: Minimal required fields only"""
    current_time = int(time.time())
    expire_time = current_time + 3600
    
    payload = {
        "app_id": APP_ID,
        "uid": "123",
        "exp": expire_time,
        "ver": 20
    }
    
    token = jwt.encode(payload, SERVER_SECRET, algorithm='HS256')
    decoded = decode_jwt_payload(token)
    
    print("=== TOKEN FORMAT 3 (minimal) ===")
    print(f"Token: {token}")
    print(f"Payload: {json.dumps(decoded, indent=2) if isinstance(decoded, dict) else decoded}")
    print()
    
    return token

def test_token_format_4():
    """Test format 4: Different version numbers to test"""
    current_time = int(time.time())
    expire_time = current_time + 3600
    
    for version in [1, 2, 3, 4, 5, 20, 21]:
        payload = {
            "ver": version,
            "app_id": APP_ID,
            "uid": "123",
            "name": "testuser",
            "iat": current_time,
            "exp": expire_time
        }
        
        token = jwt.encode(payload, SERVER_SECRET, algorithm='HS256')
        decoded = decode_jwt_payload(token)
        
        print(f"=== TOKEN WITH VERSION {version} ===")
        print(f"Token: {token}")
        print(f"Version in payload: {decoded.get('ver') if isinstance(decoded, dict) else 'decode failed'}")
        print()

def test_zego_native_format():
    """Test Zego native binary token format"""
    current_time = int(time.time())
    expire_time = current_time + 3600
    
    user_id = "123"
    
    # Create payload for native format
    payload_data = {
        'app_id': APP_ID,
        'user_id': user_id,
        'expire_time': expire_time,
        'version': 20
    }
    
    payload_json = json.dumps(payload_data, separators=(',', ':'))
    payload_bytes = payload_json.encode('utf-8')
    
    # Create signature
    signature = hmac.new(
        SERVER_SECRET.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).digest()
    
    # Combine version + payload + signature
    version_bytes = struct.pack('<I', 20)  # 4 bytes little-endian
    token_bytes = version_bytes + payload_bytes + signature
    
    # Encode to base64
    native_token = base64.b64encode(token_bytes).decode('utf-8')
    
    print("=== ZEGO NATIVE TOKEN FORMAT ===")
    print(f"Native Token: {native_token}")
    print(f"Payload JSON: {payload_json}")
    print()
    
    return native_token

def check_server_secret():
    """Check if server secret looks valid"""
    print("=== SERVER SECRET CHECK ===")
    print(f"App ID: {APP_ID}")
    print(f"Server Secret: '{SERVER_SECRET}'")
    print(f"Secret Length: {len(SERVER_SECRET)} characters")
    print(f"Secret looks hex: {all(c in '0123456789abcdefABCDEF' for c in SERVER_SECRET)}")
    
    # Typical Zego server secrets are 32 characters (hex)
    if len(SERVER_SECRET) != 32:
        print("⚠️  WARNING: Server secret should typically be 32 hex characters")
    if not all(c in '0123456789abcdefABCDEF' for c in SERVER_SECRET):
        print("⚠️  WARNING: Server secret should be hexadecimal")
    
    print()

if __name__ == "__main__":
    print("🔍 ZIM Token Debug - Testing All Formats")
    print("=" * 50)
    
    # Check credentials first
    check_server_secret()
    
    # Test different JWT formats
    test_token_format_1()
    test_token_format_2() 
    test_token_format_3()
    
    # Test different version numbers
    print("🔢 Testing Different Version Numbers:")
    test_token_format_4()
    
    # Test native format
    test_zego_native_format()
    
    print("✅ All token formats generated!")
    print("\n📋 NEXT STEPS:")
    print("1. Try each token format in your Zego SDK")
    print("2. Check if server secret is complete")
    print("3. Verify App ID matches your Zego console")
    print("4. Check Zego SDK version compatibility")