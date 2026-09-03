"""
Consumer WebSocket pour les événements temps réel par établissement.
"""
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class RealtimeConsumer(AsyncWebsocketConsumer):
    """Canal temps réel : un groupe par établissement."""

    async def connect(self):
        self.etablissement_id = await self._resolve_etablissement_id()
        if not self.etablissement_id:
            await self.close(code=4401)
            return

        self.group_name = f'etablissement_{self.etablissement_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connection.established',
            'etablissement_id': self.etablissement_id,
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if payload.get('type') == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))

    async def realtime_event(self, event):
        """Handler pour group_send(type='realtime.event', ...)."""
        await self.send(text_data=json.dumps({
            'type': event.get('event_type', 'update'),
            'payload': event.get('payload', {}),
        }))

    @database_sync_to_async
    def _resolve_etablissement_id(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            return None

        from school_admin.model.etablissement_model import Etablissement
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif
        from school_admin.model.professeur_model import Professeur
        from school_admin.model.eleve_model import Eleve
        from school_admin.model.parent_model import Parent

        if isinstance(user, Etablissement):
            return user.id
        if isinstance(user, PersonnelAdministratif):
            return user.etablissement_id
        if isinstance(user, Professeur):
            return user.etablissement_id
        if isinstance(user, Eleve):
            return user.etablissement_id
        if isinstance(user, Parent):
            return user.etablissement_id

        etablissement_id = getattr(user, 'etablissement_id', None)
        return etablissement_id
