"""Tests fil d'Ariane professeur (R4)."""
from django.test import RequestFactory, TestCase
from django.urls import resolve

from school_admin.utils.prof_nav_trail import resolve_prof_nav_trail


class ProfNavTrailTests(TestCase):
    def test_dashboard_has_no_trail(self):
        factory = RequestFactory()
        request = factory.get('/enseignant/dashboard/enseignant/')
        from school_admin.model.professeur_model import Professeur

        request.user = Professeur(id=1)
        request.resolver_match = resolve('/dashboard/enseignant/')
        self.assertIsNone(resolve_prof_nav_trail(request))

    def test_liste_presence_maps_to_gestion_presence(self):
        factory = RequestFactory()
        request = factory.get('/enseignant/primaire/presence/5/?classe=12')
        from school_admin.model.professeur_model import Professeur

        request.user = Professeur(id=1)
        request.resolver_match = resolve('/enseignant/primaire/presence/5/')
        trail = resolve_prof_nav_trail(request)
        self.assertIsNotNone(trail)
        self.assertEqual(trail['parent_label'], 'Présence')
        self.assertIn('/enseignant/primaire/presence/', trail['parent_url'])
