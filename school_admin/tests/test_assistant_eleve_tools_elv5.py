"""
Elv5 — notifications + historique années.
"""
from django.test import TestCase

from school_admin.model.classe_model import Classe
from school_admin.model.notification_eleve_model import NotificationEleve
from school_admin.services.assistant_eleve_tools import execute_eleve_tool
from school_admin.services.assistant_tools import build_assistant_context
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
)


class AssistantEleveToolsElv5Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='Elv5',
            niveau='college',
            code_classe=f'E5-{cls.etab.pk}',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Ndiaye', 'Khady', suffix='e5')

    def _ctx(self):
        return build_assistant_context(
            self.eleve.etablissement,
            {},
            eleve=self.eleve,
            persona='eleve',
        )

    def test_get_notifications_liste(self):
        NotificationEleve.objects.create(
            eleve=self.eleve,
            annee_scolaire=self.annee,
            titre='Devoir demain',
            message='Pense à rendre le devoir.',
            type_notification='information',
            lu=False,
        )
        out = execute_eleve_tool(self._ctx(), 'get_notifications', {})
        self.assertGreaterEqual(out.get('nb_non_lues', 0), 1)
        self.assertTrue(out.get('notifications'))

    def test_get_notifications_par_id(self):
        notif = NotificationEleve.objects.create(
            eleve=self.eleve,
            annee_scolaire=self.annee,
            titre='Ciblage',
            message='Detail',
            type_notification='information',
            lu=True,
        )
        out = execute_eleve_tool(
            self._ctx(),
            'get_notifications',
            {'notification_id': notif.id},
        )
        self.assertEqual(out.get('notification_id'), notif.id)

    def test_get_mon_historique(self):
        out = execute_eleve_tool(self._ctx(), 'get_mon_historique', {})
        self.assertIn('annees', out)
        self.assertIn('message', out)
