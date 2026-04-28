"""
ZIM Token Generator for Zego Cloud
Generates authentication tokens for ZIM (Zego Instant Messaging) service

Uses Token04 format required by Zego ZIM SDK 2.x
Token format: "04" + base64(expire_time + iv + AES-CBC encrypted payload)
"""

import time
import hashlib
import hmac
import json
import base64
import struct
import secrets
import os
from typing import Dict, Any

# Try to import cryptography for AES encryption
try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    CRYPTO_AVAILABLE = True
except ImportError:
    try:
        from Cryptodome.Cipher import AES
        from Cryptodome.Util.Padding import pad
        CRYPTO_AVAILABLE = True
    except ImportError:
        CRYPTO_AVAILABLE = False


def _aes_pkcs5_encrypt(plain_text: bytes, key: bytes, iv: bytes) -> bytes:
    """
    AES-CBC encryption with PKCS5/PKCS7 padding.
    
    Args:
        plain_text: Text to encrypt
        key: 32-byte key (will be truncated/padded if necessary)
        iv: 16-byte initialization vector
        
    Returns:
        Encrypted bytes
    """
    if not CRYPTO_AVAILABLE:
        raise ImportError("pycryptodome is required. Install with: pip install pycryptodome")
    
    # Ensure key is exactly 32 bytes for AES-256
    key = key[:32].ljust(32, b'\x00')
    
    # PKCS7 padding (same as PKCS5 for 16-byte blocks)
    padded = pad(plain_text, AES.block_size)
    
    # Encrypt
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return cipher.encrypt(padded)


def generate_token04(app_id: int, user_id: str, server_secret: str, 
                     effective_time_in_seconds: int = 3600, payload: str = '') -> str:
    """
    Generate Zego Token04 - the correct format for ZIM SDK 2.x.
    
    This is the official Zego token generation algorithm.
    Token starts with "04" and contains encrypted payload.
    
    Args:
        app_id: Zego App ID (numeric)
        user_id: User identifier (string)
        server_secret: 32-character server secret
        effective_time_in_seconds: Token validity in seconds (default: 1 hour)
        payload: Optional custom payload string
        
    Returns:
        Token string starting with "04"
        
    Raises:
        ValueError: If parameters are invalid
        ImportError: If pycryptodome is not installed
    """
    if not app_id:
        raise ValueError("app_id is required")
    
    if not user_id:
        raise ValueError("user_id is required") 
    
    if not server_secret or len(server_secret) != 32:
        raise ValueError("server_secret must be exactly 32 characters")
    
    if effective_time_in_seconds <= 0:
        raise ValueError("effective_time_in_seconds must be positive")
    
    # Current timestamp
    create_time = int(time.time())
    expire_time = create_time + effective_time_in_seconds
    
    # Random nonce (32-bit integer)
    nonce = secrets.randbits(31)  # Use 31 bits to ensure positive number
    
    # Create token info JSON - exact format Zego expects
    token_info = {
        "app_id": int(app_id),
        "user_id": str(user_id),
        "nonce": nonce,
        "ctime": create_time,
        "expire": expire_time,
        "payload": payload
    }
    
    # JSON encode with compact format (no spaces)
    plain_text = json.dumps(token_info, separators=(',', ':'), ensure_ascii=True)
    plain_bytes = plain_text.encode('utf-8')
    
    # Generate random IV (16 bytes)
    iv = secrets.token_bytes(16)
    
    # Encrypt using AES-CBC with server secret as key
    key = server_secret.encode('utf-8')
    encrypted = _aes_pkcs5_encrypt(plain_bytes, key, iv)
    
    # Build final binary data:
    # - expire_time: 8 bytes (big-endian unsigned long long)
    # - iv_length: 2 bytes (big-endian unsigned short) 
    # - iv: 16 bytes
    # - encrypted_length: 2 bytes (big-endian unsigned short)
    # - encrypted: variable bytes
    
    output = bytearray()
    output.extend(struct.pack('>Q', expire_time))  # 8 bytes expire time
    output.extend(struct.pack('>H', len(iv)))       # 2 bytes IV length
    output.extend(iv)                                # 16 bytes IV
    output.extend(struct.pack('>H', len(encrypted))) # 2 bytes encrypted length
    output.extend(encrypted)                         # encrypted payload
    
    # Base64 encode and prepend version "04"
    token = '04' + base64.b64encode(bytes(output)).decode('utf-8')
    
    return token


class ZIMTokenGenerator:
    """Generate ZIM tokens for Zego Cloud authentication using Token04 format."""
    
    # Token version 04 is required for ZIM SDK 2.x
    TOKEN_VERSION = "04"
    
    def __init__(self, app_id: int, server_secret: str):
        """
        Initialize ZIM token generator.
        
        Args:
            app_id: Your Zego Cloud App ID (numeric)
            server_secret: Your Zego Cloud Server Secret (32 characters)
        """
        self.app_id = int(app_id)
        self.server_secret = server_secret
        
        # Validate server secret
        if len(server_secret) != 32:
            raise ValueError(f"server_secret must be 32 characters, got {len(server_secret)}")
    
    def generate_token(self, user_id: str, username: str = None, expire_time_in_seconds: int = 3600) -> str:
        """
        Generate ZIM Token04 authentication token for Zego Cloud.
        
        This generates a token compatible with Zego ZIM SDK 2.x
        Token starts with "04" (Token04 format)
        
        Args:
            user_id: Unique identifier for the user (string or number)
            username: Display name for the user (optional, not used in Token04)
            expire_time_in_seconds: Token validity duration (default: 1 hour)
            
        Returns:
            ZIM token string starting with "04"
        """
        return generate_token04(
            app_id=self.app_id,
            user_id=str(user_id),
            server_secret=self.server_secret,
            effective_time_in_seconds=expire_time_in_seconds,
            payload=''
        )
    
    def generate_zego_native_token(self, user_id: str, username: str = None, expire_time_in_seconds: int = 3600) -> str:
        """
        Generate token using Token04 format (same as generate_token).
        
        Kept for backwards compatibility.
        """
        return self.generate_token(user_id, username, expire_time_in_seconds)
    
    def generate_user_tokens(self, talker_data: Dict[str, Any], listener_data: Dict[str, Any], 
                           expire_time_in_seconds: int = 3600) -> Dict[str, str]:
        """
        Generate ZIM tokens for both talker and listener.
        
        Args:
            talker_data: Dict with talker info {'user_id': str, 'username': str}
            listener_data: Dict with listener info {'user_id': str, 'username': str}
            expire_time_in_seconds: Token validity duration
            
        Returns:
            Dict containing tokens for both users
        """
        talker_token = self.generate_token(
            talker_data['user_id'], 
            talker_data.get('username'), 
            expire_time_in_seconds
        )
        
        listener_token = self.generate_token(
            listener_data['user_id'], 
            listener_data.get('username'), 
            expire_time_in_seconds
        )
        
        return {
            'talker_token': talker_token,
            'listener_token': listener_token,
            'expire_time_seconds': expire_time_in_seconds,
            'expires_at': int(time.time()) + expire_time_in_seconds,
            'token_version': self.TOKEN_VERSION
        }
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify Token04 format - just checks the prefix and structure.
        
        Note: Full verification requires decryption which should be done server-side.
        
        Args:
            token: ZIM token to verify
            
        Returns:
            Dict with validation info
            
        Raises:
            ValueError: If token format is invalid
        """
        if not token.startswith('04'):
            raise ValueError(f"Invalid token version. Expected '04' prefix, got '{token[:2]}'")
        
        try:
            # Decode base64 part
            token_data = base64.b64decode(token[2:])
            
            # Extract expire time (first 8 bytes)
            expire_time = struct.unpack('>Q', token_data[:8])[0]
            
            return {
                'version': '04',
                'expire_time': expire_time,
                'is_expired': expire_time < int(time.time()),
                'valid_format': True
            }
        except Exception as e:
            raise ValueError(f"Invalid token format: {str(e)}")


# Default ZIM token generator instance using your credentials
ZIM_APP_ID = 1582778301
ZIM_SERVER_SECRET = "140681a600d91db15eddb05ba75bb0b3"

zim_token_generator = ZIMTokenGenerator(ZIM_APP_ID, ZIM_SERVER_SECRET)


def generate_zim_tokens_for_call(talker_user, listener_user, expire_time_in_seconds: int = 3600) -> Dict[str, Any]:
    """
    Convenience function to generate ZIM tokens for a call session.
    
    Args:
        talker_user: Talker User model instance
        listener_user: Listener User model instance
        expire_time_in_seconds: Token validity duration
        
    Returns:
        Dict containing ZIM tokens and metadata
    """
    talker_data = {
        'user_id': str(talker_user.id),
        'username': talker_user.get_full_name() or talker_user.email
    }
    
    listener_data = {
        'user_id': str(listener_user.id), 
        'username': listener_user.get_full_name() or listener_user.email
    }
    
    tokens = zim_token_generator.generate_user_tokens(
        talker_data, 
        listener_data, 
        expire_time_in_seconds
    )
    
    return {
        'app_id': ZIM_APP_ID,
        'token_version': zim_token_generator.TOKEN_VERSION,
        'talker': {
            'user_id': talker_data['user_id'],
            'username': talker_data['username'],
            'token': tokens['talker_token'],  # Token04 format (starts with "04")
        },
        'listener': {
            'user_id': listener_data['user_id'],
            'username': listener_data['username'],
            'token': tokens['listener_token'],  # Token04 format (starts with "04")
        },
        'expire_time_seconds': tokens['expire_time_seconds'],
        'expires_at': tokens['expires_at'],
        'usage_instructions': {
            'format': 'Token04 - correct format for ZIM SDK 2.x',
            'prefix': 'Token starts with "04"',
            'encryption': 'AES-CBC encrypted payload'
        }
    }


def test_token04_generation():
    """Test Token04 generation."""
    print("=" * 60)
    print("Testing ZIM Token04 Generation")
    print("=" * 60)
    
    test_user_id = "test_user_123"
    
    try:
        # Generate token
        token = zim_token_generator.generate_token(test_user_id, expire_time_in_seconds=3600)
        
        print(f"✅ App ID: {ZIM_APP_ID}")
        print(f"✅ User ID: {test_user_id}")
        print(f"✅ Token version: {zim_token_generator.TOKEN_VERSION}")
        print(f"✅ Token prefix: {token[:2]}")
        print(f"✅ Token length: {len(token)} chars")
        print(f"✅ Token (first 80 chars): {token[:80]}...")
        
        # Verify format
        if token.startswith('04'):
            print("\n✅ SUCCESS: Token starts with '04' (correct Token04 format)")
        else:
            print(f"\n❌ ERROR: Token should start with '04', got '{token[:2]}'")
        
        # Verify structure
        info = zim_token_generator.verify_token(token)
        print(f"✅ Token expires at: {info['expire_time']}")
        print(f"✅ Token is expired: {info['is_expired']}")
        
        return token
        
    except ImportError as e:
        print(f"\n❌ Missing dependency: {str(e)}")
        print("Install with: pip install pycryptodome")
        raise
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        raise


if __name__ == '__main__':
    test_token04_generation()