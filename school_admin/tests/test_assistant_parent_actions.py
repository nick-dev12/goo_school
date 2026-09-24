"""
Par7 — actions confirmées parent (marquer notification, liaison enfant).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from unittest.mock import patch

from django.test import TestCase, TransactionTestCase

from school_admin.model.etablissement_model import Etablissement

from school_admin.model.classe_model import Classe
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.notification_parent_model import NotificationParent
from school_admin.services.assistant_parent_actions import (
    apply_demande_liaison_enfant,
    apply_marquer_notification_lue,
    prepare_demande_liaison_enfant,
    prepare_marquer_notification_lue,
)
from school_admin.services.assistant_parent_tools import execute_parent_tool
from school_admin.services.assistant_tools import build_assistant_context
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
)
from school_admin.tests.test_assistant_parent_scope import _make_parent


class AssistantParentMarquerNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='Par7 Notif',
            niveau='college',
            code_classe=f'P7N-{cls.etab.pk}',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.parent = _make_parent(cls.etab, suffix='p7n')
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Fall', 'Aminata', suffix='p7n')
        LienFamilial.objects.create(
            parent=cls.parent,
            eleve=cls.eleve,
            type_lien='mere',
            statut='valide',
            actif=True,
        )
        cls.notif = NotificationParent.objects.create(
            parent=cls.parent,
            eleve=cls.eleve,
            annee_scolaire=cls.annee,
            titre='Bulletin disponible',
            message='Le bulletin est en ligne.',
            type_notification='bulletin',
            lu=False,
        )
        cls.other_parent = _make_parent(cls.etab, suffix='p7o')

    def _ctx(self):
        return build_assistant_context(
            self.etab,
            {},
            parent=self.parent,
            persona='parent',
        )

    def test_prepare_puis_apply_marquer_lue(self):
        pending = prepare_marquer_notification_lue(
            self._ctx(),
            {'notification_id': self.notif.id},
        )
        self.assertEqual(pending.get('statut'), 'en_attente_confirmation')
        self.assertFalse(self.notif.lu)
        result = apply_marquer_notification_lue(self._ctx(), pending)
        self.assertEqual(result.get('statut'), 'ok')
        self.notif.refresh_from_db()
        self.assertTrue(self.notif.lu)

    def test_apply_sans_confirmation_refuse_autre_parent(self):
        pending = prepare_marquer_notification_lue(
            self._ctx(),
            {'notification_id': self.notif.id},
        )
        ctx_other = build_assistant_context(
            self.etab,
            {},
            parent=self.other_parent,
            persona='parent',
        )
        result = apply_marquer_notification_lue(ctx_other, pending)
        self.assertIn('erreur', result)
        self.notif.refresh_from_db()
        self.assertFalse(self.notif.lu)

    def test_tool_prepare_via_execute(self):
        out = execute_parent_tool(
            self._ctx(),
            'marquer_notification_lue',
            {'notification_id': self.notif.id},
        )
        self.assertEqual(out.get('statut'), 'en_attente_confirmation')
        self.notif.refresh_from_db()
        self.assertFalse(self.notif.lu)

    def test_bloque_paiement_vocal(self):
        out = execute_parent_tool(self._ctx(), 'enregistrer_paiement', {})
        self.assertEqual(out.get('statut'), 'hors_perimetre')


class AssistantParentLiaisonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='Par7 Liaison',
            niveau='college',
            code_classe=f'P7L-{cls.etab.pk}',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.parent = _make_parent(cls.etab, suffix='p7l')
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Ndiaye', 'Omar', suffix='p7l')
        cls.eleve_password = 'Eleve@Test1!'
        cls.eleve.matricule_eleve = f'MAT-P7L-{cls.eleve.pk}'
        with patch.object(Etablissement, 'recalculer_facturation', return_value=None):
            cls.eleve.save(update_fields=['matricule_eleve'])

    def _ctx(self):
        return build_assistant_context(
            self.etab,
            {},
            parent=self.parent,
            persona='parent',
        )

    def _matricule(self):
        return self.eleve.matricule_eleve

    def test_prepare_mauvais_mdp_sans_pending(self):
        out = prepare_demande_liaison_enfant(
            self._ctx(),
            {
                'matricule_eleve': self._matricule(),
                'mot_de_passe_eleve': 'wrong',
            },
        )
        self.assertIn('erreur', out)
        self.assertNotEqual(out.get('statut'), 'en_attente_confirmation')
        self.assertFalse(
            LienFamilial.objects.filter(parent=self.parent, eleve=self.eleve).exists()
        )

    def test_prepare_puis_apply_liaison(self):
        pending = prepare_demande_liaison_enfant(
            self._ctx(),
            {
                'matricule_eleve': self._matricule(),
                'mot_de_passe_eleve': self.eleve_password,
            },
        )
        self.assertEqual(pending.get('statut'), 'en_attente_confirmation')
        result = apply_demande_liaison_enfant(self._ctx(), pending)
        self.assertEqual(result.get('statut'), 'ok')
        lien = LienFamilial.objects.filter(parent=self.parent, eleve=self.eleve, actif=True)
        self.assertTrue(lien.exists())


class AssistantParentActionsConsumerTests(TransactionTestCase):
    def setUp(self):
        self.etab = _make_etablissement()
        self.annee = _make_annee(self.etab)
        self.classe = Classe.objects.create(
            nom='Par7 WS',
            niveau='college',
            code_classe=f'P7W-{self.etab.pk}',
            capacite_max=30,
            etablissement=self.etab,
        )
        self.parent = _make_parent(self.etab, suffix='p7w')
        self.eleve = _make_eleve_simple(self.etab, self.classe, 'Sy', 'Mariama', suffix='p7w')
        LienFamilial.objects.create(
            parent=self.parent,
            eleve=self.eleve,
            type_lien='mere',
            statut='valide',
            actif=True,
        )
        self.notif = NotificationParent.objects.create(
            parent=self.parent,
            eleve=self.eleve,
            annee_scolaire=self.annee,
            titre='Info',
            message='Test',
            type_notification='information',
            lu=False,
        )

    def test_marquer_notification_pose_pending_sans_takeover(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        async def _run():
            consumer = AssistantConsumer()
            consumer.scope = {'user': self.parent, 'session': {}}
            consumer.accept = AsyncMock()
            consumer.close = AsyncMock()
            self.assertTrue(await consumer._resolve_etablissement())
            consumer._reset_turn_stats()
            consumer.pending_action = None
            consumer._persist_pending = AsyncMock()
            consumer._send_json = AsyncMock()

            stop = await consumer._on_live_tool_result(
                'marquer_notification_lue',
                {
                    'statut': 'en_attente_confirmation',
                    'resume': 'marque la notification',
                    'notification_ids': [self.notif.id],
                    'manquants': [],
                },
            )
            self.assertFalse(stop)
            self.assertEqual(consumer._turn_stats['takeover'], 0)
            self.assertEqual(consumer.pending_action.get('name'), 'marquer_notification_lue')

        asyncio.run(_run())
        self.notif.refresh_from_db()
        self.assertFalse(self.notif.lu)
