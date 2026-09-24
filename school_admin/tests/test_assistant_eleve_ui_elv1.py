"""
Elv1 — présence du widget assistant sur les 14 écrans élève (compte élève seul).
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import TestCase

TEMPLATES = Path(settings.BASE_DIR) / 'school_admin' / 'templates' / 'school_admin'

ELEVE_NAV_PAGES = (
    'eleve/dashboard_eleve.html',
    'eleve/devoirs_eleve.html',
    'eleve/profil_eleve.html',
    'eleve/sanctions_eleve.html',
    'eleve/emploi_du_temps_eleve.html',
    'eleve/convocations_eleve.html',
    'eleve/notes_evaluations_eleve.html',
    'eleve/annonces_eleve.html',
    'eleve/absences_retards_eleve.html',
)

ELEVE_EXTRA_PAGES = (
    'eleve/bulletin_eleve.html',
    'eleve/bulletin_eleve_superieur.html',
    'eleve/notifications_eleve.html',
    'eleve/historique_annees_eleve.html',
    'eleve/historique_annee_detail_eleve.html',
)


class AssistantEleveUiElv1Tests(TestCase):
    def test_nav_pages_incluent_bottom_nav(self):
        for rel in ELEVE_NAV_PAGES:
            text = (TEMPLATES / rel).read_text(encoding='utf-8')
            self.assertIn('bottom_nav_eleve.html', text, msg=rel)

    def test_bottom_nav_widget_eleve_et_parent(self):
        text = (TEMPLATES / 'eleve/partials/bottom_nav_eleve.html').read_text(encoding='utf-8')
        self.assertIn('assistant_vocal_parent.html', text)
        self.assertIn('assistant_vocal_eleve.html', text)
        self.assertIn('{% if est_parent %}', text)
        self.assertIn('{% else %}', text)

    def test_pages_sans_nav_incluent_widget_eleve(self):
        for rel in ELEVE_EXTRA_PAGES:
            text = (TEMPLATES / rel).read_text(encoding='utf-8')
            self.assertIn('assistant_vocal_eleve.html', text, msg=rel)
            self.assertIn('{% if est_parent %}', text, msg=rel)

    def test_partial_eleve_data_persona(self):
        text = (TEMPLATES / 'eleve/partials/assistant_vocal_eleve.html').read_text(encoding='utf-8')
        self.assertIn('data-persona="eleve"', text)
        self.assertIn('assistant_vocal.js', text)
