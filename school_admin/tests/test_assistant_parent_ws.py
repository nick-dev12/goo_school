"""
Tests WebSocket assistant parent (Par0/Par1).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from django.test import TransactionTestCase

from school_admin.consumers.assistant_consumer import AssistantConsumer
from school_admin.model.classe_model import Classe
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.parent_model import Parent
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
)
from school_admin.tests.test_assistant_parent_scope import _make_parent


def _run(coro):
    return asyncio.run(coro)


async def _consumer_for_parent(parent, session=None):
    consumer = AssistantConsumer()
    consumer.scope = {
        'user': parent,
        'session': session or {},
    }
    consumer.accept = AsyncMock()
    consumer.close = AsyncMock()
    consumer._send_json = AsyncMock()
    consumer._load_pending = AsyncMock()
    consumer._restore_pending_ui = AsyncMock()
    consumer._emit_sentence = AsyncMock()
    allowed = await consumer._resolve_etablissement()
    return consumer, allowed


class AssistantParentWsTests(TransactionTestCase):
    def setUp(self):
        self.etab = _make_etablissement()
        self.annee = _make_annee(self.etab)
        self.classe = Classe.objects.create(
            nom='3eme WS Parent',
            niveau='college',
            code_classe=f'3WP-{self.etab.pk}',
            capacite_max=30,
            etablissement=self.etab,
        )
        self.parent = _make_parent(self.etab, suffix='ws')
        self.eleve = _make_eleve_simple(self.etab, self.classe, 'Ndiaye', 'Fatou', suffix='ws')
        LienFamilial.objects.create(
            parent=self.parent,
            eleve=self.eleve,
            type_lien='mere',
            statut='valide',
            actif=True,
        )
        self.eleve_seul = _make_eleve_simple(
            self.etab, self.classe, 'Ba', 'Moussa', suffix='ws2'
        )

    def test_ws_accepte_parent(self):
        async def _go():
            consumer, allowed = await _consumer_for_parent(self.parent)
            self.assertTrue(allowed)
            self.assertEqual(consumer.persona, 'parent')
            self.assertEqual(consumer.parent.pk, self.parent.pk)

        _run(_go())

    def test_ws_refuse_eleve(self):
        async def _go():
            consumer = AssistantConsumer()
            consumer.scope = {'user': self.eleve_seul, 'session': {}}
            consumer.accept = AsyncMock()
            consumer.close = AsyncMock()
            allowed = await consumer._resolve_etablissement()
            self.assertFalse(allowed)

        _run(_go())

    def test_welcome_parent_apres_connect(self):
        async def _go():
            consumer, allowed = await _consumer_for_parent(
                self.parent,
                session={'eleve_consulte_id': self.eleve.id},
            )
            self.assertTrue(allowed)
            await consumer._send_parent_welcome()
            calls = [c.args[0] for c in consumer._send_json.call_args_list]
            welcome = next(c for c in calls if c.get('type') == 'assistant.welcome')
            self.assertEqual(welcome.get('persona'), 'parent')
            self.assertIn('Wolof', welcome.get('text', ''))
            consumer._emit_sentence.assert_awaited()

        _run(_go())
