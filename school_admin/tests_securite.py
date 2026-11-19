"""Sécurité, lot 1 : page publique du QR, fichiers déposés servis avec contrôle, filtre des envois."""
import io
import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings

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
