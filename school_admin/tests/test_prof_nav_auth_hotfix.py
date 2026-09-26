"""Hotfix nav prof — session, bottom-nav, hub_partial, pas de double barre."""
from datetime import date

from django.test import Client, TestCase
from django.urls import reverse

from school_admin.authentication_backends import MultiUserBackend, _user_type_context
from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
from school_admin.model.classe_model import Classe
from school_admin.model.compte_user import CompteUser
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.matiere_model import Matiere
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.professeur_model import Professeur


def _clear_user_type_context():
    if hasattr(_user_type_context, 'user_type'):
        delattr(_user_type_context, 'user_type')


def _make_etab(kind, suffix):
    email = f'{kind}.nav.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'École Nav {kind} {suffix}',
        code_etablissement=f'N{kind[0].upper()}{suffix[-6:]}',
        adresse='1 rue Test',
        pays='Sénégal',
        ville='Dakar',
        type_etablissement=kind,
        directeur_prenom='A',
        directeur_nom='B',
        directeur_email=f'dir.{kind}.{suffix}@test.local',
        actif=True,
    )
    etab.set_password('Test1234!')
    etab.save()
    return etab


class ProfAuthCollisionTests(TestCase):
    """Collision de PK sans _auth_user_type ne doit pas flush la session."""

    @classmethod
    def setUpTestData(cls):
        suffix = date.today().strftime('%Y%m%d%H%M%S')
        cls.etab = _make_etab('college', suffix)
        cls.matiere = Matiere.objects.create(
            nom='Histoire',
            code=f'HN{suffix[-6:]}',
            etablissement=cls.etab,
            actif=True,
        )
        cls.prof = Professeur.objects.create_user(
            username=f'prof.nav.{suffix}',
            email=f'prof.nav.{suffix}@test.local',
            password='Prof@Test1!',
            nom='Bernard',
            prenom='Sophie',
            telephone='770000099',
            numero_employe=f'NAV{suffix}',
            matiere_principale=cls.matiere,
            etablissement=cls.etab,
            niveau_enseignement='college',
            actif=True,
        )
        collide = CompteUser(
            username=f'collide.{suffix}',
            email=f'collide.{suffix}@test.local',
            nom='Collide',
            prenom='Admin',
        )
        collide.pk = cls.prof.pk
        collide.set_password('Admin@Test1!')
        collide.save()

    def setUp(self):
        _clear_user_type_context()

    def tearDown(self):
        _clear_user_type_context()

    def test_get_user_uses_session_type_despite_collision(self):
        backend = MultiUserBackend()
        _user_type_context.user_type = 'professeur'
        user = backend.get_user(self.prof.pk)
        self.assertIsInstance(user, Professeur)
        self.assertEqual(user.pk, self.prof.pk)

    def test_get_user_without_type_does_not_return_wrong_model(self):
        backend = MultiUserBackend()
        _clear_user_type_context()
        user = backend.get_user(self.prof.pk)
        self.assertIsNone(user)

    def test_login_persists_type_and_survives_collision(self):
        client = Client()
        ok = client.login(username=self.prof.username, password='Prof@Test1!')
        self.assertTrue(ok)
        self.assertEqual(client.session.get('_auth_user_type'), 'professeur')

        resp = client.get(reverse('enseignant:dashboard_enseignant'))
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.wsgi_request.user, Professeur)

        classes = client.get(reverse('enseignant:gestion_classes'))
        self.assertNotEqual(classes.status_code, 302)
        self.assertEqual(classes.status_code, 200)
        self.assertNotIn('/connexion/', classes.get('Location', ''))


class ProfBottomNavSessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        suffix = date.today().strftime('%Y%m%d%H%M%S')
        cls.etab = _make_etab('college', suffix)
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
            code=f'HB{suffix[-6:]}',
            etablissement=cls.etab,
            actif=True,
        )
        cls.classe = Classe.objects.create(
            nom='5eme B',
            code_classe=f'5B{suffix[-5:]}',
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
            username=f'prof.bn.{suffix}',
            email=f'prof.bn.{suffix}@test.local',
            password='Prof@Test1!',
            nom='Fall',
            prenom='Moussa',
            telephone='770000088',
            numero_employe=f'BN{suffix}',
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
        self.assertTrue(self.client.login(username=self.prof.username, password='Prof@Test1!'))

    def _assert_stays_on_page(self, url_name, extra=None):
        params = extra or {}
        resp = self.client.get(reverse(url_name), params)
        self.assertEqual(
            resp.status_code,
            200,
            f'{url_name} → {resp.status_code} Location={resp.get("Location")}',
        )
        self.assertNotIn('/connexion/', resp.get('Location', ''))
        return resp

    def test_dashboard_then_each_bottom_item(self):
        self._assert_stays_on_page('enseignant:dashboard_enseignant')
        for name in (
            'enseignant:gestion_classes',
            'enseignant:gestion_eleves',
            'enseignant:gestion_notes',
            'enseignant:exercices_maison',
            'enseignant:gestion_presence',
            'enseignant:justifications_notes',
            'enseignant:parametres_profil',
        ):
            extra = {}
            if 'notes' in name or 'exercices' in name:
                extra = {'classe': str(self.classe.id), 'periode': str(self.periode.id)}
            elif name.endswith('gestion_classes') or name.endswith('gestion_eleves') or name.endswith('gestion_presence'):
                extra = {'classe': str(self.classe.id)}
            self._assert_stays_on_page(name, extra)

    def test_hub_partial_xhr_stays_logged_in(self):
        resp = self.client.get(
            reverse('enseignant:gestion_classes'),
            {'hub_partial': 'hub', 'classe': str(self.classe.id)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('id="prof-hub-chrome"', body)
        self.assertIn('id="prof-hub-panel"', body)
        self.assertIn('prof-hub-nav-link', body)


class ProfPrimaireHubChromeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        suffix = date.today().strftime('%Y%m%d%H%M%S')
        cls.etab = _make_etab('primary', suffix)
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
            code=f'FR{suffix[-6:]}',
            etablissement=cls.etab,
            actif=True,
        )
        cls.classe = Classe.objects.create(
            nom='CE1 A',
            code_classe=f'C1{suffix[-5:]}',
            niveau='primaire',
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
            username=f'prof.pr.{suffix}',
            email=f'prof.pr.{suffix}@test.local',
            password='Prof@Test1!',
            nom='Ndiaye',
            prenom='Awa',
            telephone='770000077',
            numero_employe=f'PR{suffix}',
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

    def setUp(self):
        self.client = Client()
        self.assertTrue(self.client.login(username=self.prof.username, password='Prof@Test1!'))

    def test_primaire_bottom_nav_stays_logged_in(self):
        dash = self.client.get(reverse('enseignant_primaire:dashboard'))
        self.assertEqual(dash.status_code, 200)
        for name in (
            'enseignant_primaire:gestion_classes',
            'enseignant_primaire:gestion_eleves',
            'enseignant_primaire:gestion_notes',
            'enseignant_primaire:exercices_maison',
            'enseignant_primaire:gestion_presence',
        ):
            resp = self.client.get(
                reverse(name),
                {'classe': str(self.classe.id), 'periode': str(self.periode.id)},
            )
            location = resp.get('Location', '')
            self.assertNotIn('/connexion/', location, name)
            if resp.status_code == 302:
                self.assertTrue(
                    location.startswith('/enseignant/'),
                    f'{name} redirect hors espace prof: {location}',
                )
                resp = self.client.get(location)
            self.assertEqual(resp.status_code, 200, name)

    def test_exercices_hub_has_class_pills_and_legacy_hide_css(self):
        resp = self.client.get(
            reverse('enseignant_primaire:exercices_maison'),
            {'periode': str(self.periode.id), 'classe': str(self.classe.id)},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('data-prof-hub-nav-live="1"', body)
        self.assertIn('prof-primaire-classes-bar', body)
        self.assertIn('CE1 A', body)
        self.assertIn('prof_primaire_hub.css', body)


class ProfHubCssHideLegacyTabsTests(TestCase):
    def test_css_hides_category_tab_rows(self):
        from pathlib import Path
        from django.conf import settings

        css = (
            Path(settings.BASE_DIR)
            / 'school_admin'
            / 'static'
            / 'school_admin'
            / 'css'
            / 'enseignant'
            / 'primaire'
            / 'prof_primaire_hub.css'
        )
        text = css.read_text(encoding='utf-8')
        self.assertIn('body[data-prof-hub-nav-live="1"] .tabs-container > .tabs-nav', text)
        self.assertIn('display: none !important', text)
        self.assertIn('.classes-tabs', text)
