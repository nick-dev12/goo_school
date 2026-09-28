"""
Authentification WebSocket pour les modèles multi-utilisateurs (Professeur, etc.).

AuthMiddlewareStack ne voit pas UserTypeMiddleware (HTTP only). On recharge l'utilisateur
via MultiUserBackend + _auth_user_type de la session Channels.
"""
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _user_from_session(scope):
    from school_admin.authentication_backends import MultiUserBackend, _user_type_context

    session = scope.get('session')
    if session is None:
        return AnonymousUser()

    user_id = session.get('_auth_user_id')
    if not user_id:
        return AnonymousUser()

    user_type = session.get('_auth_user_type')
    if user_type:
        _user_type_context.user_type = user_type
    else:
        if hasattr(_user_type_context, 'user_type'):
            delattr(_user_type_context, 'user_type')

    try:
        user = MultiUserBackend().get_user(int(user_id))
    except (TypeError, ValueError):
        user = None
    finally:
        if hasattr(_user_type_context, 'user_type'):
            delattr(_user_type_context, 'user_type')

    if user is None:
        return AnonymousUser()
    return user


class WebSocketMultiUserMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        if scope.get('type') == 'websocket':
            session = scope.get('session') or {}
            if session.get('_auth_user_id'):
                scope['user'] = await _user_from_session(scope)
        return await super().__call__(scope, receive, send)
