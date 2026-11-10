"""
Authentification WebSocket pour les modèles multi-utilisateurs (Professeur, etc.).

AuthMiddlewareStack ne voit pas UserTypeMiddleware (HTTP only). On recharge l'utilisateur
via MultiUserBackend + _auth_user_type de la session Channels.
"""
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.utils.crypto import constant_time_compare


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
    # Comme AuthenticationMiddleware HTTP : une session antérieure au changement
    # de mot de passe ne doit pas rester utilisable en WebSocket.
    session_hash = session.get('_auth_user_hash', '')
    valid_hashes = [user.get_session_auth_hash()]
    if hasattr(user, 'get_session_auth_fallback_hash'):
        valid_hashes.extend(user.get_session_auth_fallback_hash())
    if not session_hash or not any(constant_time_compare(session_hash, value) for value in valid_hashes):
        return AnonymousUser()
    return user


class WebSocketMultiUserMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        if scope.get('type') == 'websocket':
            session = scope.get('session') or {}
            if session.get('_auth_user_id'):
                scope['user'] = await _user_from_session(scope)
        return await super().__call__(scope, receive, send)
