from django.urls import re_path

from .consumers.realtime_consumer import RealtimeConsumer

websocket_urlpatterns = [
    re_path(r'ws/realtime/$', RealtimeConsumer.as_asgi()),
]
