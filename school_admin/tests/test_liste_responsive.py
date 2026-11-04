"""
Listes d'élèves responsive (js/liste_responsive.js) : le composant est chargé et les listes sont annotées
sur les pages des enseignants (collège / lycée) et de la direction.
"""
from django.test import TestCase
from django.urls import reverse

from school_admin.tests import test_assistant_enseignant_examens_tools as examens_tests


class ListeResponsiveTests(TestCase):
    # Données des tests examens : un professeur, une classe « 2nde C » et un élève inscrit.
    setUpTestData = examens_tests.AssistantEnseignantExamensToolsTests.__dict__['setUpTestData']

    def test_pages_enseignant(self):
        self.assertTrue(self.client.login(username=self.prof.username, password='Prof@Test1!'))
        for url in (reverse('enseignant:gestion_eleves'), reverse('enseignant:detail_classe', args=[self.classe.id])):
            r = self.client.get(url, follow=True)
            self.assertEqual(r.status_code, 200, url)
            self.assertContains(r, 'js/liste_responsive.js', msg_prefix=url)
            self.assertContains(r, 'data-rl data-rl-mobile=', msg_prefix=url)

    def test_liste_eleves_direction(self):
        self.client.force_login(self.etab)
        r = self.client.get(reverse('secretaire:liste_eleves'), follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'js/liste_responsive.js')
        self.assertContains(r, 'data-rl data-rl-mobile="1,2,4" data-rl-actions="6"')
        self.assertContains(r, 'data-rl-titre="')
