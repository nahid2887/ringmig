"""
JWT Authentication Middleware for Django Channels WebSocket
"""
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

User = get_user_model()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Custom middleware to authenticate WebSocket connections using JWT tokens.
    Token should be passed as query parameter: ?token=<JWT_TOKEN>
    """

    async def __call__(self, scope, receive, send):
        # Get token from query string
        query_string = parse_qs(scope['query_string'].decode())
        token = query_string.get('token')
        
        if token:
            token = token[0]  # Get first token if multiple provided
            scope['user'] = await self.get_user_from_token(token)
        else:
            scope['user'] = AnonymousUser()
        
        return await super().__call__(scope, receive, send)
    
    @database_sync_to_async
    def get_user_from_token(self, token):
        """Validate JWT token and return user."""
        try:
            # Decode and validate token
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            
            # Get user from database
            user = User.objects.get(id=user_id)
            return user
        
        except (InvalidToken, TokenError, User.DoesNotExist) as e:
            # Invalid token or user not found
            return AnonymousUser()


def JWTAuthMiddlewareStack(inner):
    """
    Helper function to apply JWTAuthMiddleware.
    Usage: JWTAuthMiddlewareStack(URLRouter(...))
    """
    return JWTAuthMiddleware(inner)
