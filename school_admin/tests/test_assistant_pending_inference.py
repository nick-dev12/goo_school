"""Tests sur les choix de confirmation de l’assistant (sans fausses propositions)."""
from django.test import SimpleTestCase

from school_admin.services.assistant_actions import (
    ACTION_SPECS,
    choices_for_action,
    is_action_ready,
)


class AssistantPendingInferenceTests(SimpleTestCase):
    def test_delete_parametres_exposes_destructive_confirm_choices(self):
        draft = {
            'statut': 'en_attente_confirmation',
            'action': 'supprimer_parametres_comptabilite',
            'resume': 'supprime les paramètres « Tarifs 2nde » (2nde)',
            'parametres_id': 1,
            'nom': 'Tarifs 2nde',
            'destructive': True,
        }
        self.assertTrue(is_action_ready(draft))
        labels = [c['label'] for c in choices_for_action('supprimer_parametres_comptabilite', draft)]
        self.assertIn('Oui, confirmer', labels)
        self.assertIn('Annuler', labels)
        self.assertNotIn('Modifier', labels)

    def test_incomplete_draft_is_not_ready_for_confirm(self):
        draft = {
            'statut': 'incomplet',
            'action': 'supprimer_parametres_comptabilite',
            'manquants': ['query'],
        }
        self.assertFalse(is_action_ready(draft))
        self.assertEqual(choices_for_action('supprimer_parametres_comptabilite', draft), [])
