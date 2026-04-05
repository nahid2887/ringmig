from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/availability/subscribe/$", consumers.ListenerAvailabilityConsumer.as_asgi()),
    re_path(r"ws/availability/notifications/$", consumers.ListenerAvailabilityNotificationConsumer.as_asgi()),
    re_path(r"ws/availability/my-availability/$", consumers.TalkerAvailabilityConsumer.as_asgi()),
    re_path(r"ws/availability/listener/(?P<listener_id>\d+)/$", consumers.TalkerListenerAvailabilityConsumer.as_asgi()),
]
