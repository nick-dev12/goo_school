"""
Page « Justifications de notes » de l'enseignant (collège / lycée) avec une note d'examen.
Régression : le libellé de la note d'examen lisait SessionExamen.nom et CreneauExamen.nom,
qui n'existent pas (erreur 500).
"""
from django.test import TestCase
from django.urls import reverse

from school_admin.tests import test_assistant_enseignant_examens_tools as examens_tests


class JustificationsNotesEnseignantTests(TestCase):
    # Mêmes données que les tests examens : session « BAC blanc », créneau du 02/11/2026, une note d'examen.
    setUpTestData = examens_tests.AssistantEnseignantExamensToolsTests.__dict__['setUpTestData']

    def test_page_avec_note_examen(self):
        self.assertTrue(self.client.login(username=self.prof.username, password='Prof@Test1!'))
        response = self.client.get(reverse('enseignant:justifications_notes'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Examen: BAC blanc')
        self.assertContains(response, '02/11/2026')
