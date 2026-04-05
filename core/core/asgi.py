"""
ASGI config for core project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# Import routing and JWT middleware after Django setup
from chat.routing import websocket_urlpatterns as chat_urlpatterns
from bokking.routing import websocket_urlpatterns as bokking_urlpatterns
from chat.jwt_auth_middleware import JWTAuthMiddlewareStack

# Combine all WebSocket URL patterns
all_websocket_urlpatterns = chat_urlpatterns + bokking_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddlewareStack(
            URLRouter(
                all_websocket_urlpatterns
            )
        )
    ),
})
