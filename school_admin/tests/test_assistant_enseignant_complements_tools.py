"""
Tests P7 — compléments assistant enseignant (justifications, évaluations, notifications).
"""
from datetime import date

from django.test import TestCase
from django.utils import timezone

from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.classe_model import Classe
from school_admin.model.evaluation_model import Evaluation
from school_admin.model.matiere_model import Matiere
from school_admin.model.notification_enseignant_model import NotificationEnseignant
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.presence_model import Presence
from school_admin.model.professeur_model import Professeur
from school_admin.services.assistant_enseignant_complements_actions import (
    apply_marquer_notification_lue,
    apply_supprimer_evaluation,
    prepare_justifier_absence,
    prepare_marquer_notification_lue,
    prepare_supprimer_evaluation,
)
from school_admin.services.assistant_enseignant_secondaire_tools import (
    execute_enseignant_secondaire_tool,
    get_enseignant_secondaire_tools_schema,
)
from school_admin.services.assistant_tools import build_assistant_context
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
    _make_inscription,
)


class AssistantEnseignantComplementsToolsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        suffix = str(cls.etab.pk)
        cls.classe = Classe.objects.create(
            nom='3eme A',
            niveau='college',
            code_classe=f'3A-{suffix}',
            capacite_max=30,
            etablissement=cls.etab,
            actif=True,
        )
        cls.periode = PeriodeScolaire.objects.create(
            etablissement=cls.etab,
            nom_periode='1er Trimestre',
            type_periode='trimestre',
            date_debut=date(2026, 9, 1),
            date_fin=date(2026, 12, 15),
            annee_scolaire=cls.annee.libelle,
            annee_scolaire_fk=cls.annee,
            est_active=True,
        )
        cls.matiere = Matiere.objects.create(
            nom=f'Français {suffix}',
            code=f'FR{suffix}'[:10],
            etablissement=cls.etab,
            actif=True,
        )
        cls.prof = Professeur.objects.create_user(
            username=f'prof.p7.{suffix}',
            email=f'prof.p7.{suffix}@test.local',
            password='Prof@Test1!',
            nom='Camara',
            prenom='Awa',
            telephone='770000010',
            numero_employe=f'P7{suffix}',
            matiere_principale=cls.matiere,
            etablissement=cls.etab,
            niveau_enseignement='college',
            actif=True,
        )
        AffectationProfesseur.objects.create(
            professeur=cls.prof,
            classe=cls.classe,
            matiere=cls.matiere,
            annee_scolaire=cls.annee,
            statut='classique',
            actif=True,
        )
        cls.eleve = _make_eleve_simple(
            cls.etab, cls.classe, 'Diop', 'Mamadou', suffix='p7'
        )
        _make_inscription(cls.eleve, cls.classe, cls.annee, cls.etab)
        cls.evaluation = Evaluation.objects.create(
            titre='Interro surprise',
            classe=cls.classe,
            professeur=cls.prof,
            matiere=cls.matiere,
            periode_scolaire=cls.periode,
            date_evaluation=date(2026, 10, 1),
            bareme=20,
            annee_scolaire=cls.annee,
            actif=True,
        )
        cls.presence = Presence.objects.create(
            eleve=cls.eleve,
            classe=cls.classe,
            professeur=cls.prof,
            etablissement=cls.etab,
            date=date(2026, 10, 5),
            statut='absent',
            annee_scolaire=cls.annee,
        )
        cls.notif = NotificationEnseignant.objects.create(
            enseignant=cls.prof,
            annee_scolaire=cls.annee,
            titre='Rappel conseil',
            message='Réunion pédagogique demain.',
            lu=False,
            statut='non_lu',
        )

    def _ctx(self):
        return build_assistant_context(
            self.etab,
            {'annee_scolaire_consultee_id': self.annee.id},
            professeur=self.prof,
            persona='enseignant',
        )

    def test_schema_includes_p7_actions(self):
        ctx = self._ctx()
        names = {
            item['function']['name']
            for item in get_enseignant_secondaire_tools_schema(ctx)
            if item.get('function')
        }
        for tool in (
            'justifier_absence',
            'modifier_evaluation',
            'supprimer_evaluation',
            'marquer_notification_lue',
            'get_justifications_notes',
        ):
            self.assertIn(tool, names)

    def test_get_notifications_uses_enseignant_fk(self):
        ctx = self._ctx()
        result = execute_enseignant_secondaire_tool(ctx, 'get_notifications', {})
        self.assertEqual(result.get('non_lues'), 1)
        self.assertEqual(result['notifications'][0]['titre'], 'Rappel conseil')

    def test_prepare_justifier_absence_pending(self):
        ctx = self._ctx()
        draft = prepare_justifier_absence(
            ctx,
            {
                'eleve': self.eleve.nom_complet,
                'classe': self.classe.nom,
                'date': '2026-10-05',
                'type_justificatif': 'certificat_medical',
            },
        )
        self.assertEqual(draft.get('statut'), 'en_attente_confirmation')
        self.assertEqual(draft.get('presence_id'), self.presence.id)

    def test_supprimer_evaluation_scope_and_apply(self):
        ctx = self._ctx()
        pending = prepare_supprimer_evaluation(
            ctx,
            {'evaluation': 'Interro', 'classe': self.classe.nom},
        )
        self.assertEqual(pending.get('action'), 'supprimer_evaluation')
        result = apply_supprimer_evaluation(ctx, pending)
        self.assertEqual(result.get('statut'), 'ok')
        self.evaluation.refresh_from_db()
        self.assertFalse(self.evaluation.actif)

    def test_marquer_notification_lue(self):
        ctx = self._ctx()
        pending = prepare_marquer_notification_lue(
            ctx,
            {'notification_id': self.notif.id},
        )
        self.assertEqual(pending.get('statut'), 'en_attente_confirmation')
        result = apply_marquer_notification_lue(ctx, pending)
        self.assertEqual(result.get('statut'), 'ok')
        self.notif.refresh_from_db()
        self.assertTrue(self.notif.lu)
