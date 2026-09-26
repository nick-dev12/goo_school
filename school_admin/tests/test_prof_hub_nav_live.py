"""Smoke tests — contrat hub_partial navigation hub prof primaire (R0/R1)."""
from datetime import date

from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.matiere_model import Matiere
from school_admin.model.professeur_model import Professeur
from school_admin.utils.prof_hub_partial import wants_prof_hub_partial


def _make_etablissement_primaire():
    suffix = date.today().strftime('%Y%m%d%H%M%S%f')
    email = f'ecole.hub.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'École Hub Test {suffix}',
        code_etablissement=f'HUB{suffix[-6:]}',
        adresse='1 rue Test',
        pays='Sénégal',
        ville='Dakar',
        type_etablissement='primary',
        directeur_prenom='A',
        directeur_nom='B',
        directeur_email=f'dir.{suffix}@test.local',
        actif=True,
    )
    etab.set_password('Test1234!')
    etab.save()
    return etab


class ProfHubPartialContractTests(TestCase):
    def test_wants_partial_requires_xhr_and_valid_value(self):
        factory = RequestFactory()
        req = factory.get('/enseignant/primaire/eleves/', {'hub_partial': 'hub'})
        self.assertIsNone(wants_prof_hub_partial(req))

        req = factory.get(
            '/enseignant/primaire/eleves/',
            {'hub_partial': 'hub'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(wants_prof_hub_partial(req), 'hub')

        req = factory.get(
            '/enseignant/primaire/eleves/',
            {'hub_partial': 'invalid'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertIsNone(wants_prof_hub_partial(req))


class ProfHubPartialIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement_primaire()
        suffix = date.today().strftime('%Y%m%d%H%M%S')
        cls.annee = AnneeScolaire.objects.create(
            etablissement=cls.etab,
            libelle='2026-2027',
            annee_debut=2026,
            annee_fin=2027,
            date_debut=date(2026, 9, 1),
            date_fin=date(2027, 6, 30),
            est_active=True,
            est_ouverte=True,
        )
        cls.matiere = Matiere.objects.create(
            nom='Français',
            code=f'FR-{suffix[-6:]}',
            etablissement=cls.etab,
            actif=True,
        )
        cls.classe = Classe.objects.create(
            nom='CE2 - A',
            code_classe=f'CE2-{suffix[-5:]}',
            niveau='primaire',
            etablissement=cls.etab,
            actif=True,
        )
        cls.prof = Professeur.objects.create_user(
            username=f'prof.hub.{suffix}',
            email=f'prof.hub.{suffix}@test.local',
            password='Prof@Test1!',
            nom='Ndiaye',
            prenom='Amadou',
            telephone='770000001',
            numero_employe=f'EMP{suffix}',
            matiere_principale=cls.matiere,
            etablissement=cls.etab,
            niveau_enseignement='primaire',
            actif=True,
        )
        aff = AffectationProfesseurPrimaire.objects.create(
            professeur=cls.prof,
            classe=cls.classe,
            annee_scolaire=cls.annee,
            statut='principal',
            actif=True,
        )
        aff.matieres.add(cls.matiere)
        cls.periode = PeriodeScolaire.objects.create(
            etablissement=cls.etab,
            nom_periode='Trimestre 1',
            date_debut=date(2026, 9, 1),
            date_fin=date(2026, 12, 20),
            est_active=True,
            annee_scolaire_fk=cls.annee,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.prof)

    def _assert_hub_swap(self, url_name):
        url = reverse(url_name)
        resp = self.client.get(
            url,
            {'hub_partial': 'hub', 'classe': str(self.classe.id)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('id="prof-hub-chrome"', body)
        self.assertIn('id="prof-hub-panel"', body)

    def test_eleves_hub_partial_swap(self):
        self._assert_hub_swap('enseignant_primaire:gestion_eleves')

    def test_presence_hub_partial_swap(self):
        self._assert_hub_swap('enseignant_primaire:gestion_presence')

    def test_exercices_full_page_periode_classe(self):
        resp = self.client.get(
            reverse('enseignant_primaire:exercices_maison'),
            {'periode': str(self.periode.id), 'classe': str(self.classe.id)},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('prof-hub-chrome', body)
        self.assertIn('prof-primaire-periodes-bar', body)

    def test_exercices_hub_partial_swap_periode_classe(self):
        resp = self.client.get(
            reverse('enseignant_primaire:exercices_maison'),
            {
                'hub_partial': 'hub',
                'periode': str(self.periode.id),
                'classe': str(self.classe.id),
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('id="prof-hub-chrome"', body)
        self.assertIn('id="prof-hub-panel"', body)
        self.assertIn('prof-primaire-periodes-bar', body)

    def test_classes_hub_partial_swap(self):
        self._assert_hub_swap('enseignant_primaire:gestion_classes')

    def test_justifications_hub_partial_swap(self):
        resp = self.client.get(
            reverse('enseignant_primaire:justifications_notes'),
            {
                'hub_partial': 'hub',
                'periode': str(self.periode.id),
                'classe': str(self.classe.id),
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('id="prof-hub-chrome"', body)
        self.assertIn('id="prof-hub-panel"', body)

    def test_eleves_difficulte_hub_partial_swap(self):
        resp = self.client.get(
            reverse('enseignant_primaire:eleves_en_difficulte'),
            {
                'hub_partial': 'hub',
                'periode': str(self.periode.id),
                'classe': str(self.classe.id),
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('id="prof-hub-chrome"', body)
        self.assertIn('id="prof-hub-panel"', body)


def _make_etablissement_college():
    suffix = date.today().strftime('%Y%m%d%H%M%S%f')
    email = f'college.hub.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'Collège Hub {suffix}',
        code_etablissement=f'CH{suffix[-6:]}',
        adresse='2 rue Test',
        pays='Sénégal',
        ville='Dakar',
        type_etablissement='college',
        directeur_prenom='A',
        directeur_nom='B',
        directeur_email=f'dir.{suffix}@test.local',
        actif=True,
    )
    etab.set_password('Test1234!')
    etab.save()
    return etab


class ProfHubSecondaryIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement_college()
        suffix = date.today().strftime('%Y%m%d%H%M%S')
        cls.annee = AnneeScolaire.objects.create(
            etablissement=cls.etab,
            libelle='2026-2027',
            annee_debut=2026,
            annee_fin=2027,
            date_debut=date(2026, 9, 1),
            date_fin=date(2027, 6, 30),
            est_active=True,
            est_ouverte=True,
        )
        cls.matiere = Matiere.objects.create(
            nom='Histoire',
            code=f'HI-{suffix[-6:]}',
            etablissement=cls.etab,
            actif=True,
        )
        cls.classe = Classe.objects.create(
            nom='5eme B',
            code_classe=f'5B-{suffix[-5:]}',
            niveau='college',
            etablissement=cls.etab,
            actif=True,
        )
        cls.periode = PeriodeScolaire.objects.create(
            etablissement=cls.etab,
            nom_periode='Trimestre 1',
            date_debut=date(2026, 9, 1),
            date_fin=date(2026, 12, 20),
            est_active=True,
            annee_scolaire_fk=cls.annee,
        )
        cls.prof = Professeur.objects.create_user(
            username=f'prof.col.hub.{suffix}',
            email=f'prof.col.{suffix}@test.local',
            password='Prof@Test1!',
            nom='Fall',
            prenom='Moussa',
            telephone='770000002',
            numero_employe=f'EMC{suffix}',
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

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.prof)

    def test_college_notes_hub_partial_swap(self):
        resp = self.client.get(
            reverse('enseignant:gestion_notes'),
            {
                'hub_partial': 'hub',
                'classe': str(self.classe.id),
                'periode': str(self.periode.id),
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('id="prof-hub-chrome"', body)
        self.assertIn('id="gestion-notes-live-root"', body)

    def test_college_notes_hub_partial_panel(self):
        resp = self.client.get(
            reverse('enseignant:gestion_notes'),
            {
                'hub_partial': 'panel',
                'classe': str(self.classe.id),
                'periode': str(self.periode.id),
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('id="prof-hub-panel"', body)
        self.assertIn('id="gestion-notes-live-root"', body)

    def test_college_presence_hub_partial_swap(self):
        resp = self.client.get(
            reverse('enseignant:gestion_presence'),
            {'hub_partial': 'hub', 'classe': str(self.classe.id)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('id="prof-hub-chrome"', body)
        self.assertIn('id="gestion-presence-live-root"', body)
