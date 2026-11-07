"""
Corrections de l'audit « École Primaire Les Manguiers » (audit_conformite_primaire/README_ANOMALIES.md).

1. Le calcul des moyennes primaires enregistre l'année scolaire (sinon le bulletin reste vide).
2. La titulaire du primaire ouvre l'historique de présence d'un élève de sa classe.
5. Le suivi commercial de la plateforme est refusé au personnel des écoles.
6. Les titres SEO suivent l'espace de l'adresse (pas « Espace Parent » sur les annonces élève).
"""
from django.test import RequestFactory, TestCase
from django.urls import reverse

from school_admin.model.compte_user import CompteUser
from school_admin.model.note_primaire_model import MoyenneMatierePrimaire
from school_admin.seo import resolve_seo
from school_admin.tests import test_prof_nav_auth_hotfix as nav_tests
from school_admin.tests.test_assistant_directeur_tools import _make_eleve_simple, _make_inscription


class AuditPrimaireTests(TestCase):
    # École primaire, année 2026-2027, CE1 A, titulaire (AffectationProfesseurPrimaire), trimestre 1.
    _base = nav_tests.ProfPrimaireHubChromeTests.__dict__['setUpTestData']

    @classmethod
    def setUpTestData(cls):
        cls._base.__func__(cls)
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Moussavou', 'Kévin', 'M', f'ap{cls.etab.pk}')
        _make_inscription(cls.eleve, cls.classe, cls.annee, cls.etab)

    def test_1_moyenne_primaire_porte_l_annee(self):
        moyenne = MoyenneMatierePrimaire.calculer_et_enregistrer(self.eleve, self.matiere, self.periode)
        self.assertEqual(moyenne.annee_scolaire, self.annee)

    def test_2_historique_presence_titulaire_primaire(self):
        self.assertTrue(self.client.login(username=self.prof.username, password='Prof@Test1!'))
        url = reverse('enseignant_primaire:historique_presence', args=[self.eleve.id])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, r.get('Location'))

    def test_5_suivi_commercial_refuse_aux_ecoles(self):
        url = reverse('school_admin:suivi_activites_commerciales')
        self.client.force_login(self.etab)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        admin = CompteUser.objects.create_user(
            username=f'admin.aria.{self.etab.pk}', email=f'admin.aria.{self.etab.pk}@test.local',
            password='Admin@Test1!', nom='Aria', prenom='Admin', fonction='administrateur',
        )
        self.client.force_login(admin)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_6_titres_suivent_l_espace(self):
        rf = RequestFactory()
        titre = lambda chemin: resolve_seo(rf.get(chemin))['title']  # noqa: E731
        self.assertIn('Espace Élève', titre('/eleve/annonces/'))
        self.assertIn('Espace Élève', titre('/eleve/notes-evaluations/'))
        self.assertIn('Espace Parent', titre('/parent/annonces/'))
        self.assertIn('Espace Directeur', titre('/bulletins/'))
