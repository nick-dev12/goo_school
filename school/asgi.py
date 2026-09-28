"""
ASGI config for school project.
HTTP via Django + WebSockets via Django Channels.
"""
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.sessions import SessionMiddlewareStack
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')

django_asgi_app = get_asgi_application()

from school_admin.consumers.websocket_auth_middleware import (  # noqa: E402
    WebSocketMultiUserMiddleware,
)
from school_admin.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        'http': django_asgi_app,
        'websocket': SessionMiddlewareStack(
            AuthMiddlewareStack(
                WebSocketMultiUserMiddleware(URLRouter(websocket_urlpatterns))
            )
        ),
    }
)
