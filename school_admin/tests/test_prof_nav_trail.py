"""Tests fil d'Ariane professeur (P3)."""
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve

from school_admin.model.professeur_model import Professeur
from school_admin.utils.prof_nav_trail import (
    resolve_prof_nav_trail,
    set_prof_breadcrumb_current_label,
)


def _request(path, user=None):
    factory = RequestFactory()
    request = factory.get(path)
    request.user = user if user is not None else Professeur(id=1)
    request.resolver_match = resolve(path.split('?', 1)[0])
    return request


class ProfNavTrailTests(SimpleTestCase):
    def test_dashboard_has_no_trail(self):
        request = _request('/dashboard/enseignant/')
        self.assertIsNone(resolve_prof_nav_trail(request))

    def test_dashboard_primaire_has_no_trail(self):
        request = _request('/enseignant/primaire/dashboard/')
        self.assertIsNone(resolve_prof_nav_trail(request))

    def test_hubs_have_no_trail(self):
        for path in (
            '/enseignant/primaire/notes/',
            '/enseignant/primaire/presence/',
            '/enseignant/primaire/eleves/',
            '/enseignant/primaire/classes/',
            '/enseignant/primaire/justifications-notes/',
            '/enseignant/primaire/exercices/',
            '/enseignant/primaire/eleves-difficulte/',
            '/enseignant/notes/',
            '/enseignant/presence/',
        ):
            self.assertIsNone(resolve_prof_nav_trail(_request(path)), path)

    def test_non_professeur_has_no_trail(self):
        request = _request('/enseignant/primaire/presence/5/')
        request.user = object()
        self.assertIsNone(resolve_prof_nav_trail(request))

    def test_liste_presence_primaire_maps_to_presence(self):
        trail = resolve_prof_nav_trail(_request('/enseignant/primaire/presence/5/?classe=12'))
        self.assertIsNotNone(trail)
        self.assertEqual(str(trail['parent_label']), 'Présence')
        self.assertEqual(str(trail['current_label']), 'Appel')
        self.assertIn('/enseignant/primaire/presence/', trail['parent_url'])
        self.assertIn('classe=12', trail['parent_url'])

    def test_liste_presence_infers_classe_from_path(self):
        trail = resolve_prof_nav_trail(_request('/enseignant/primaire/presence/5/'))
        self.assertIn('classe=5', trail['parent_url'])

    def test_liste_presence_secondaire_maps_to_presence(self):
        request = _request('/enseignant/presence/8/')
        self.assertEqual(request.resolver_match.namespace, 'school_admin')
        trail = resolve_prof_nav_trail(request)
        self.assertEqual(str(trail['parent_label']), 'Présence')
        self.assertIn('/enseignant/presence/', trail['parent_url'])
        self.assertIn('classe=8', trail['parent_url'])

    def test_noter_eleves_maps_to_notes_and_keeps_query(self):
        trail = resolve_prof_nav_trail(
            _request('/enseignant/primaire/noter/15/?periode=2&matiere=4&vue=saisie')
        )
        self.assertEqual(str(trail['parent_label']), 'Notes')
        self.assertEqual(str(trail['current_label']), 'Saisie des notes')
        self.assertIn('/enseignant/primaire/notes/', trail['parent_url'])
        self.assertIn('periode=2', trail['parent_url'])
        self.assertIn('classe=15', trail['parent_url'])
        self.assertIn('matiere=4', trail['parent_url'])
        self.assertIn('vue=saisie', trail['parent_url'])

    def test_voir_releve_and_creer_evaluation_map_to_notes(self):
        releve = resolve_prof_nav_trail(_request('/enseignant/releve/3/?periode=1'))
        self.assertEqual(str(releve['parent_label']), 'Notes')
        self.assertEqual(str(releve['current_label']), 'Relevé')
        self.assertIn('/enseignant/notes/', releve['parent_url'])

        creer = resolve_prof_nav_trail(_request('/enseignant/primaire/evaluation/creer/9/'))
        self.assertEqual(str(creer['parent_label']), 'Notes')
        self.assertEqual(str(creer['current_label']), 'Nouvelle évaluation')
        self.assertIn('classe=9', creer['parent_url'])

    def test_detail_eleve_and_classe_map_to_hubs(self):
        eleve = resolve_prof_nav_trail(_request('/enseignant/primaire/eleve/4/?classe=11'))
        self.assertEqual(str(eleve['parent_label']), 'Élèves')
        self.assertIn('/enseignant/primaire/eleves/', eleve['parent_url'])
        self.assertIn('classe=11', eleve['parent_url'])

        classe = resolve_prof_nav_trail(_request('/enseignant/classe/7/'))
        self.assertEqual(str(classe['parent_label']), 'Classes')
        self.assertIn('/enseignant/classes/', classe['parent_url'])
        self.assertIn('classe=7', classe['parent_url'])

    def test_historique_presence_maps_to_eleve(self):
        trail = resolve_prof_nav_trail(_request('/enseignant/historique-presence/4/'))
        self.assertEqual(str(trail['parent_label']), 'Élève')
        self.assertIn('/enseignant/eleve/4/', trail['parent_url'])

    def test_historique_annee_detail_maps_to_historique(self):
        trail = resolve_prof_nav_trail(_request('/enseignant/primaire/historique-annees/3/'))
        self.assertEqual(str(trail['parent_label']), 'Années scolaires')
        self.assertIn('/enseignant/primaire/historique-annees/', trail['parent_url'])
        self.assertNotIn('/3/', trail['parent_url'])

    def test_historique_annees_maps_to_profil(self):
        trail = resolve_prof_nav_trail(_request('/enseignant/historique-annees/'))
        self.assertEqual(str(trail['parent_label']), 'Profil')
        self.assertIn('/enseignant/parametres-profil/', trail['parent_url'])

    def test_noter_examen_maps_to_notes(self):
        trail = resolve_prof_nav_trail(_request('/enseignant/noter-examen/6/'))
        self.assertEqual(str(trail['parent_label']), 'Notes')
        self.assertEqual(str(trail['current_label']), "Notes d'examen")
        self.assertIn('classe=6', trail['parent_url'])

    def test_liste_evaluations_maps_to_notes(self):
        trail = resolve_prof_nav_trail(_request('/enseignant/evaluations/'))
        self.assertEqual(str(trail['parent_label']), 'Notes')
        self.assertEqual(str(trail['current_label']), 'Évaluations')
        self.assertIn('/enseignant/notes/', trail['parent_url'])

    def test_modifier_evaluation_maps_to_liste(self):
        trail = resolve_prof_nav_trail(_request('/enseignant/modifier-evaluation/2/'))
        self.assertEqual(str(trail['parent_label']), 'Évaluations')
        self.assertIn('/enseignant/evaluations/', trail['parent_url'])

    def test_view_can_override_current_label(self):
        request = _request('/enseignant/primaire/eleve/4/')
        set_prof_breadcrumb_current_label(request, 'Aminata Diop')
        trail = resolve_prof_nav_trail(request)
        self.assertEqual(trail['current_label'], 'Aminata Diop')
        self.assertEqual(str(trail['parent_label']), 'Élèves')
