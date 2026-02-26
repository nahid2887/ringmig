"""
ZIM Token Generator for Zego Cloud
Generates authentication tokens for ZIM (Zego Instant Messaging) service
"""

import jwt
import time
import hashlib
import random
import string
from typing import Dict, Any


class ZIMTokenGenerator:
    """Generate ZIM tokens for Zego Cloud authentication."""
    
    def __init__(self, app_id: int, server_secret: str):
        """
        Initialize ZIM token generator.
        
        Args:
            app_id: Your Zego Cloud App ID
            server_secret: Your Zego Cloud Server Secret
        """
        self.app_id = app_id
        self.server_secret = server_secret
    
    def generate_token(self, user_id: str, username: str, expire_time_in_seconds: int = 3600) -> str:
        """
        Generate ZIM authentication token.
        
        Args:
            user_id: Unique identifier for the user
            username: Display name for the user
            expire_time_in_seconds: Token validity duration (default: 1 hour)
            
        Returns:
            ZIM token string
        """
        # Create payload
        current_time = int(time.time())
        expire_time = current_time + expire_time_in_seconds
        
        payload = {
            "app_id": self.app_id,
            "user_id": user_id,
            "username": username,
            "nonce": self._generate_nonce(),
            "iat": current_time,  # issued at
            "exp": expire_time,   # expires at
            "aud": "zim",         # audience
            "iss": "zego"         # issuer
        }
        
        # Generate token using HS256 algorithm
        token = jwt.encode(payload, self.server_secret, algorithm="HS256")
        
        return token
    
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
            talker_data['username'], 
            expire_time_in_seconds
        )
        
        listener_token = self.generate_token(
            listener_data['user_id'], 
            listener_data['username'], 
            expire_time_in_seconds
        )
        
        return {
            'talker_token': talker_token,
            'listener_token': listener_token,
            'expire_time_seconds': expire_time_in_seconds,
            'expires_at': int(time.time()) + expire_time_in_seconds
        }
    
    def _generate_nonce(self) -> str:
        """Generate a random nonce for the token."""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode a ZIM token.
        
        Args:
            token: ZIM token to verify
            
        Returns:
            Decoded token payload
            
        Raises:
            jwt.InvalidTokenError: If token is invalid
        """
        try:
            payload = jwt.decode(token, self.server_secret, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            raise jwt.InvalidTokenError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise jwt.InvalidTokenError(f"Invalid token: {str(e)}")


# Default ZIM token generator instance using your credentials
ZIM_APP_ID = 1247203967
ZIM_SERVER_SECRET = "39949576ffad57ec6cdad1f1602cf7bc"

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
        'talker': {
            'user_id': talker_data['user_id'],
            'username': talker_data['username'],
            'token': tokens['talker_token']
        },
        'listener': {
            'user_id': listener_data['user_id'],
            'username': listener_data['username'],
            'token': tokens['listener_token']
        },
        'expire_time_seconds': tokens['expire_time_seconds'],
        'expires_at': tokens['expires_at']
    }