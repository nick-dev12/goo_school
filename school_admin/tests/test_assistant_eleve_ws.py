"""
Tests WebSocket assistant élève (Elv0).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from django.test import TransactionTestCase

from school_admin.consumers.assistant_consumer import AssistantConsumer
from school_admin.model.classe_model import Classe
from school_admin.model.parent_model import Parent
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
)
from school_admin.tests.test_assistant_parent_scope import _make_parent


def _run(coro):
    return asyncio.run(coro)


class AssistantEleveWsTests(TransactionTestCase):
    def setUp(self):
        self.etab = _make_etablissement()
        self.annee = _make_annee(self.etab)
        self.classe = Classe.objects.create(
            nom='WS Elv0',
            niveau='college',
            code_classe=f'WSE-{self.etab.pk}',
            capacite_max=30,
            etablissement=self.etab,
        )
        self.eleve = _make_eleve_simple(self.etab, self.classe, 'Ndiaye', 'Omar', suffix='wse')
        self.parent = _make_parent(self.etab, suffix='wsp')

    def test_ws_accepte_eleve(self):
        async def _go():
            consumer = AssistantConsumer()
            consumer.scope = {'user': self.eleve, 'session': {}}
            consumer.accept = AsyncMock()
            consumer.close = AsyncMock()
            allowed = await consumer._resolve_etablissement()
            self.assertTrue(allowed)
            self.assertEqual(consumer.persona, 'eleve')
            self.assertEqual(consumer.eleve.pk, self.eleve.pk)

        _run(_go())

    def test_ws_refuse_parent_sans_session_enfant(self):
        async def _go():
            consumer = AssistantConsumer()
            consumer.scope = {'user': self.parent, 'session': {}}
            consumer.accept = AsyncMock()
            consumer.close = AsyncMock()
            allowed = await consumer._resolve_etablissement()
            self.assertTrue(allowed)
            self.assertEqual(consumer.persona, 'parent')

        _run(_go())

    def test_welcome_eleve(self):
        async def _go():
            consumer = AssistantConsumer()
            consumer.scope = {'user': self.eleve, 'session': {}}
            consumer.accept = AsyncMock()
            consumer.close = AsyncMock()
            self.assertTrue(await consumer._resolve_etablissement())
            consumer._send_json = AsyncMock()
            consumer._emit_sentence = AsyncMock()
            await consumer._send_eleve_welcome()
            payload = consumer._send_json.call_args[0][0]
            self.assertEqual(payload.get('type'), 'assistant.welcome')
            self.assertEqual(payload.get('persona'), 'eleve')

        _run(_go())
