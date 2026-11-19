"""Sécurité, lot 1 : page publique du QR, fichiers déposés servis avec contrôle, filtre des envois."""
import io
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from school_admin.media_views import _normaliser, url_signee
from school_admin.model.classe_model import Classe
from school_admin.model.eleve_model import Eleve
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.tests.test_assistant_directeur_tools import _make_annee, _make_etablissement, _make_etablissement_type
from school_admin.tests.test_assistant_parent_scope import _make_parent
from school_admin.tests.test_dashboard_d1 import _make_eleve
from school_admin.upload_guard import UploadGuardMiddleware, motif_refus

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64
PDF = b'%PDF-1.4\n%fin\n'


class MediaTestCase(TestCase):
    """Établissement, classe, élève avec photo, parent lié, et un dossier media/ temporaire."""

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media, MEDIA_ACCEL_PREFIX='')
        override.enable()
        self.addCleanup(override.disable)

        self.etab = _make_etablissement()
        self.annee = _make_annee(self.etab)
        self.classe = Classe.objects.create(nom='CM2 A', niveau='primaire', code_classe=f'CM2-{self.etab.pk}',
                                            capacite_max=30, etablissement=self.etab, actif=True)
        self.eleve = _make_eleve(self.etab, self.classe, self.annee, 'Diallo', 'Awa', 's1')
        self.photo = 'eleves/photos/awa.png'
        self.ecrire(self.photo, PNG)
        Eleve.objects.filter(pk=self.eleve.pk).update(photo_profil=self.photo, parent_telephone='770001122')
        self.eleve.refresh_from_db()
        self.parent = _make_parent(self.etab, 's1')
        LienFamilial.objects.create(parent=self.parent, eleve=self.eleve, type_lien='mere', statut='valide', actif=True)

    def ecrire(self, chemin, contenu):
        fichier = Path(self.media, *chemin.split('/'))
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_bytes(contenu)


class PageQrPubliqueTests(MediaTestCase):
    def test_sans_connexion_seul_le_necessaire_est_affiche(self):
        reponse = self.client.get(f'/scan-qr/eleve/{self.eleve.qr_code_identifier}/')
        self.assertEqual(reponse.status_code, 200)
        page = reponse.content.decode()
        self.assertIn('Awa D.', page)
        self.assertIn('CM2 A', page)
        self.assertNotIn('Diallo', page)
        self.assertNotIn(self.eleve.matricule_eleve or 'MATRICULE-ABSENT', page)
        self.assertNotIn('770001122', page)
        self.assertIn('noindex', page)
        self.assertEqual(reponse['Cache-Control'], 'no-store')

    def test_la_photo_passe_par_une_adresse_signee(self):
        page = self.client.get(f'/scan-qr/eleve/{self.eleve.qr_code_identifier}/').content.decode()
        self.assertIn('/media/eleves/photos/awa.png?s=', page)
        self.assertEqual(self.client.get(url_signee(self.eleve.photo_profil)).status_code, 200)

    def test_une_signature_ne_vaut_que_pour_son_fichier(self):
        self.ecrire('eleves/photos/autre.png', PNG)
        signature = url_signee(self.eleve.photo_profil).split('?s=')[1]
        reponse = self.client.get(f'/media/eleves/photos/autre.png?s={signature}')
        self.assertEqual(reponse.status_code, 302)

    def test_la_direction_garde_la_page_complete(self):
        self.client.force_login(self.etab)
        reponse = self.client.get(f'/scan-qr/eleve/{self.eleve.qr_code_identifier}/')
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('authenticated', reponse['Location'])


class FichiersDeposesTests(MediaTestCase):
    def get(self, user, chemin):
        self.client.logout()
        if user is not None:
            self.client.force_login(user)
        return self.client.get(f'/media/{chemin}')

    def test_logo_public(self):
        self.ecrire('etablissements/logos/logo.png', PNG)
        reponse = self.get(None, 'etablissements/logos/logo.png')
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('public', reponse['Cache-Control'])

    def test_photo_eleve_selon_le_compte(self):
        autre_etab = _make_etablissement_type('lycée', 'autre')
        _make_annee(autre_etab)
        autre_parent = _make_parent(self.etab, 's2')
        self.assertEqual(self.get(None, self.photo).status_code, 302)
        self.assertEqual(self.get(self.etab, self.photo).status_code, 200)
        self.assertEqual(self.get(self.parent, self.photo).status_code, 200)
        self.assertEqual(self.get(self.eleve, self.photo).status_code, 200)
        self.assertEqual(self.get(autre_etab, self.photo).status_code, 404)
        self.assertEqual(self.get(autre_parent, self.photo).status_code, 404)

    def test_fichier_inconnu_ou_hors_dossier(self):
        self.ecrire('secrets/cle.txt', b'secret')
        self.assertEqual(self.get(self.etab, 'secrets/cle.txt').status_code, 404)
        self.assertEqual(self.get(self.etab, 'eleves/photos/absente.png').status_code, 404)
        for chemin in ('../manage.py', 'eleves/../../manage.py', 'a\\b', 'x\x00.png', ''):
            self.assertIsNone(_normaliser(chemin), chemin)
        self.assertEqual(_normaliser('/etc/passwd'), 'etc/passwd')  # ramené à l'intérieur de media/

    def test_un_fichier_html_ne_s_ouvre_jamais_dans_le_navigateur(self):
        self.ecrire('admin_photos/piege.html', b'<script>alert(1)</script>')
        reponse = self.get(self.etab, 'admin_photos/piege.html')
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse['Content-Disposition'].startswith('attachment'))
        self.assertEqual(reponse['X-Content-Type-Options'], 'nosniff')

    def test_production_delegue_l_envoi_a_nginx(self):
        with override_settings(MEDIA_ACCEL_PREFIX='/protected-media/'):
            reponse = self.get(self.etab, self.photo)
        self.assertEqual(reponse['X-Accel-Redirect'], '/protected-media/eleves/photos/awa.png')
        self.assertTrue(reponse['Content-Disposition'].startswith('inline'))
        self.assertIn('private', reponse['Cache-Control'])


class FiltreEnvoisTests(TestCase):
    def fichier(self, nom, contenu):
        return SimpleUploadedFile(nom, contenu)

    def test_formats_acceptes(self):
        for nom, contenu in (('releve.pdf', PDF), ('photo.png', PNG), ('photo.jpg', b'\xff\xd8\xff\xe0' + b'0' * 20),
                             ('liste.csv', b'nom;prenom\nDiop;Awa\n'), ('eleves.xlsx', b'PK\x03\x04' + b'0' * 20),
                             ('note.doc', b'\xd0\xcf\x11\xe0' + b'0' * 20)):
            self.assertIsNone(motif_refus(self.fichier(nom, contenu)), nom)

    def test_formats_refuses(self):
        for nom, contenu in (('page.html', b'<html>'), ('dessin.svg', b'<svg onload=alert(1)>'),
                             ('script.js', b'alert(1)'), ('outil.exe', b'MZ'), ('sans_extension', b'data'),
                             ('faux.pdf', b'<html><script>'), ('faux.png', PDF),
                             ('liste.csv', b'<script>alert(1)</script>')):
            self.assertIsNotNone(motif_refus(self.fichier(nom, contenu)), nom)

    def test_taille_maximale(self):
        gros = self.fichier('gros.pdf', PDF)
        gros.size = 25 * 1024 * 1024
        self.assertIn('dépasse', motif_refus(gros))

    def test_le_middleware_bloque_avant_la_vue(self):
        appels = []

        def vue(request):
            appels.append(request)
            return None

        middleware = UploadGuardMiddleware(vue)
        factory = RequestFactory()
        mauvais = factory.post('/annonces/creer/', {'fichier_joint': self.fichier('piege.html', b'<html>')},
                               HTTP_ACCEPT='application/json')
        reponse = middleware(mauvais)
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(appels, [])
        bon = factory.post('/annonces/creer/', {'fichier_joint': self.fichier('note.pdf', PDF)})
        middleware(bon)
        self.assertEqual(len(appels), 1)
        self.assertEqual(appels[0].FILES['fichier_joint'].read(), PDF)  # le fichier reste lisible par la vue


# --------------------------------------------------------------------------- lot 2
from unittest.mock import patch  # noqa: E402

from django.core.cache import cache  # noqa: E402
from django.urls import reverse  # noqa: E402

from school_admin.model.demande_liaison_model import DemandeLiaisonParent  # noqa: E402
from school_admin.utils import login_throttle  # noqa: E402


class AdresseVisiteurTests(TestCase):
    def requete(self, remote, **meta):
        return RequestFactory().get('/', REMOTE_ADDR=remote, **meta)

    def test_adresse_reelle_transmise_par_nginx(self):
        self.assertEqual(login_throttle.get_client_ip(self.requete('127.0.0.1', HTTP_X_REAL_IP='41.82.10.5')),
                         '41.82.10.5')

    def test_en_tete_falsifie_ignore_hors_mandataire(self):
        # Un visiteur qui joindrait l'application directement ne peut pas choisir son adresse.
        self.assertEqual(login_throttle.get_client_ip(self.requete('41.82.10.5', HTTP_X_REAL_IP='1.2.3.4')),
                         '41.82.10.5')

    def test_plafond_par_adresse_tous_comptes_confondus(self):
        cache.clear()
        with patch.object(login_throttle, 'IP_FAILURE_LIMIT', 3):
            requete = self.requete('127.0.0.1', HTTP_X_REAL_IP='41.82.10.9')
            self.assertEqual(login_throttle.register_auth_failure(requete, 'a@x.sn'), 0)
            self.assertEqual(login_throttle.register_auth_failure(requete, 'b@x.sn'), 0)
            self.assertGreater(login_throttle.register_auth_failure(requete, 'c@x.sn'), 0)
            # Un autre compte, depuis la même adresse, est aussi en pause…
            self.assertGreater(login_throttle.get_seconds_remaining(requete, 'd@x.sn'), 0)
            # …mais pas un visiteur d'une autre adresse.
            autre = self.requete('127.0.0.1', HTTP_X_REAL_IP='41.82.10.10')
            self.assertEqual(login_throttle.get_seconds_remaining(autre, 'd@x.sn'), 0)

    def test_verrou_par_compte_lie_a_l_adresse(self):
        cache.clear()
        attaquant = self.requete('127.0.0.1', HTTP_X_REAL_IP='5.5.5.5')
        for _ in range(login_throttle.ATTEMPT_LIMIT):
            login_throttle.register_auth_failure(attaquant, 'directeur@ecole.sn')
        self.assertGreater(login_throttle.get_seconds_remaining(attaquant, 'directeur@ecole.sn'), 0)
        # Le vrai directeur, depuis son école, n'est pas bloqué par l'attaquant.
        ecole = self.requete('127.0.0.1', HTTP_X_REAL_IP='41.82.10.20')
        self.assertEqual(login_throttle.get_seconds_remaining(ecole, 'directeur@ecole.sn'), 0)


class LiaisonParentTests(MediaTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        Eleve.objects.filter(pk=self.eleve.pk).update(matricule_eleve=f'MAT-{self.eleve.pk}-TEST')
        self.eleve.refresh_from_db()
        self.eleve.set_password('Eleve@Test1!')
        self.eleve.save()
        LienFamilial.objects.filter(eleve=self.eleve).delete()
        self.url = reverse('school_admin:demande_liaison_enfant')

    def essayer(self, parent, matricule, mot_de_passe='mauvais'):
        self.client.force_login(parent)
        reponse = self.client.post(self.url, {'matricule_eleve': matricule, 'mot_de_passe_eleve': mot_de_passe},
                                   follow=True)
        return ' '.join(str(m) for m in reponse.context['messages']) if reponse.context else ''

    def test_matricule_inexistant_et_mauvais_mot_de_passe_meme_message(self):
        self.assertIn('Matricule ou mot de passe incorrect', self.essayer(self.parent, 'INCONNU-000'))
        self.assertIn('Matricule ou mot de passe incorrect', self.essayer(self.parent, self.eleve.matricule_eleve))

    def test_un_parent_malveillant_ne_bloque_pas_les_autres(self):
        for _ in range(5):
            self.essayer(self.parent, self.eleve.matricule_eleve)
        self.assertIn('Trop de tentatives', self.essayer(self.parent, self.eleve.matricule_eleve, 'Eleve@Test1!'))
        vrai_parent = _make_parent(self.etab, 's9')
        self.assertIn('lié avec succès', self.essayer(vrai_parent, self.eleve.matricule_eleve, 'Eleve@Test1!'))

    def test_plafond_global_du_parent(self):
        for numero in range(10):
            self.essayer(self.parent, f'INCONNU-{numero}')
        self.assertIn('Trop de tentatives', self.essayer(self.parent, self.eleve.matricule_eleve, 'Eleve@Test1!'))
        self.assertFalse(LienFamilial.objects.filter(parent=self.parent, eleve=self.eleve).exists())

    def test_les_anciens_echecs_ne_bloquent_plus(self):
        for _ in range(5):
            self.essayer(self.parent, self.eleve.matricule_eleve)
        DemandeLiaisonParent.objects.update(date_demande=timezone.now() - timedelta(days=2))
        cache.clear()
        self.assertIn('lié avec succès', self.essayer(self.parent, self.eleve.matricule_eleve, 'Eleve@Test1!'))


class RythmeParCompteTests(MediaTestCase):
    def test_au_dela_du_seuil_la_reponse_est_429(self):
        cache.clear()
        self.client.force_login(self.etab)
        with override_settings(ACCOUNT_RATE_LIMIT=3, ACCOUNT_RATE_WINDOW=300):
            codes = [self.client.get('/notifications/').status_code for _ in range(4)]
            self.assertEqual(codes[3], 429)
            self.assertNotIn(429, codes[:3])
            # Les images ne comptent pas : la photo reste accessible.
            self.assertEqual(self.client.get(f'/media/{self.photo}').status_code, 200)
            api = self.client.get('/api/sync/pull/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertNotEqual(api.status_code, 429)

    def test_robots_et_sitemap_publics(self):
        self.assertEqual(self.client.get('/robots.txt').status_code, 200)
        self.assertIn('Disallow: /parent/', self.client.get('/robots.txt').content.decode())
        self.assertEqual(self.client.get('/sitemap.xml').status_code, 200)
