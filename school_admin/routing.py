from django.urls import re_path

from .consumers.assistant_consumer import AssistantConsumer
from .consumers.realtime_consumer import RealtimeConsumer

websocket_urlpatterns = [
    re_path(r'ws/realtime/$', RealtimeConsumer.as_asgi()),
    re_path(r'ws/assistant/$', AssistantConsumer.as_asgi()),
]
