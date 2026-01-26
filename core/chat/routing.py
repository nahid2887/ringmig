from django.urls import re_path
from . import consumers
from .call_consumers import CallConsumer

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<conversation_id>\w+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
    re_path(r'ws/conversations/$', consumers.ConversationListConsumer.as_asgi()),
    re_path(r'ws/call/(?P<session_id>\w+)/$', CallConsumer.as_asgi()),
]
