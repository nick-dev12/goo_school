"""Garde-fous de performance : compression, ressources locales, appel « rappels » allégé."""
import json
import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from school_admin.tests.test_assistant_directeur_tools import _make_annee, _make_etablissement_type

GABARITS = Path(settings.BASE_DIR) / 'school_admin' / 'templates'


class CompressionTests(TestCase):
    def test_page_compressee_si_le_navigateur_l_accepte(self):
        url = reverse('school_admin:connexion_compte_user')
        brute = self.client.get(url)
        compressee = self.client.get(url, HTTP_ACCEPT_ENCODING='gzip')
        self.assertEqual(compressee.status_code, 200)
        self.assertEqual(compressee['Content-Encoding'], 'gzip')
        self.assertIn('Accept-Encoding', compressee['Vary'])
        self.assertLess(len(compressee.content), len(brute.content) / 3)
        self.assertFalse(brute.has_header('Content-Encoding'))

    def test_flux_non_compresses(self):
        from django.http import StreamingHttpResponse

        from school_admin.compression_middleware import CompressionMiddleware

        flux = StreamingHttpResponse(iter([b'data: x\n\n' * 100]), content_type='text/event-stream')
        requete = self.client.request().wsgi_request
        requete.META['HTTP_ACCEPT_ENCODING'] = 'gzip'
        reponse = CompressionMiddleware(lambda r: flux)(requete)
        self.assertFalse(reponse.has_header('Content-Encoding'))


class RessourcesLocalesTests(TestCase):
    def test_polices_et_icones_ne_viennent_plus_de_cdn(self):
        interdits = re.compile(r'fonts\.googleapis\.com/css2\?family=(Inter|Poppins)|fonts\.gstatic\.com|'
                               r'cdnjs\.cloudflare\.com/ajax/libs/font-awesome|unpkg\.com/html5-qrcode|'
                               r'cdn\.jsdelivr\.net/npm/chart\.js@')
        fautifs = [str(p.relative_to(GABARITS)) for p in GABARITS.rglob('*.html')
                   if interdits.search(p.read_text(encoding='utf-8', errors='ignore'))]
        self.assertEqual(fautifs, [])

    def test_fichiers_locaux_presents(self):
        for chemin in ('vendor/fontawesome/css/all.min.css', 'vendor/fontawesome/webfonts/fa-solid-900-aria.woff2',
                       'vendor/fontawesome/webfonts/fa-solid-900.woff2', 'vendor/fonts/inter.css',
                       'vendor/fonts/inter-var-latin.woff2', 'vendor/fonts/poppins.css',
                       'vendor/fonts/poppins-400-latin.woff2', 'vendor/chartjs/chart.umd.min.js',
                       'vendor/html5-qrcode/html5-qrcode.min.js', 'js/shared/qr_scanner_loader.js',
                       'img/aria-assistante-192.webp', 'img/logo_wordmark.webp', 'img/logo-256.webp'):
            self.assertIsNotNone(finders.find(f'school_admin/{chemin}'), chemin)

    def test_feuilles_de_polices_pointent_vers_des_fichiers_existants(self):
        for feuille in ('vendor/fonts/inter.css', 'vendor/fonts/poppins.css', 'vendor/fontawesome/css/all.min.css'):
            chemin = Path(finders.find(f'school_admin/{feuille}'))
            for url in re.findall(r'url\(([^)]+)\)', chemin.read_text(encoding='utf-8')):
                self.assertTrue((chemin.parent / url.strip('\'"')).resolve().is_file(), f'{feuille} -> {url}')


class PastilleRappelsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.etab = _make_etablissement_type('lycée', 'prf')
        _make_annee(self.etab)
        self.client.force_login(self.etab, backend='school_admin.authentication_backends.MultiUserBackend')
        session = self.client.session
        session['_auth_user_type'] = 'etablissement'
        session.save()

    def _claim(self):
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.post(reverse('school_admin:context_popup'), content_type='application/json',
                                 data=json.dumps({'action': 'claim', 'visit_key': 'a' * 32}))
        return r, len(ctx.captured_queries)

    @override_settings(CONTEXT_POPUP_TOTAL_TTL=30)
    def test_page_suivante_reutilise_le_decompte(self):
        premiere, sql_premiere = self._claim()
        suite, sql_suite = self._claim()
        self.assertEqual(premiere.status_code, 200)
        self.assertEqual(suite.status_code, 200)
        self.assertEqual(suite.json()['visit'], premiere.json()['visit'])
        self.assertEqual(suite.json()['total'], premiere.json()['total'])
        self.assertEqual(suite.json()['cards'], [])
        self.assertLess(sql_suite, sql_premiere / 2)

    @override_settings(CONTEXT_POPUP_TOTAL_TTL=0)
    def test_ttl_nul_recalcule_a_chaque_page(self):
        _, sql_premiere = self._claim()
        suite, sql_suite = self._claim()
        self.assertEqual(suite.json()['cards'], [])
        self.assertGreater(sql_suite, sql_premiere / 2)


class IconesTests(TestCase):
    def test_icones_des_gabarits_presentes_dans_la_feuille_allegee(self):
        """La feuille d'icônes servie ne contient que les icônes utilisées : une icône ajoutée dans un gabarit
        doit y figurer. En cas d'échec : relancer scripts/build_vendor_assets.py (voir son en-tête)."""
        dossier = Path(finders.find('school_admin/vendor/fontawesome/css/all.min.css')).parent
        motif = re.compile(r'\.fa-([a-z0-9-]+):before')
        toutes = set(motif.findall((dossier / 'all.full.min.css').read_text(encoding='utf-8')))
        servies = set(motif.findall((dossier / 'all.min.css').read_text(encoding='utf-8')))
        utilisees = set()
        for gabarit in GABARITS.rglob('*.html'):
            utilisees.update(re.findall(r'\bfa-([a-z0-9-]+)', gabarit.read_text(encoding='utf-8', errors='ignore')))
        self.assertEqual(sorted((utilisees & toutes) - servies), [])


class LogoImpressionTests(TestCase):
    """Logo de l'établissement dans les en-têtes d'impression : version allégée, jamais d'image cassée."""

    def setUp(self):
        import tempfile

        self.dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self.dossier.cleanup)
        reglage = override_settings(MEDIA_ROOT=self.dossier.name)
        reglage.enable()
        self.addCleanup(reglage.disable)
        self.etab = _make_etablissement_type('lycée', 'lgo')

    def _logo(self, mode, taille, bruit=True):
        import random
        from io import BytesIO

        from django.core.files.base import ContentFile
        from PIL import Image

        canaux = len(mode)
        donnees = random.Random(3).randbytes(taille[0] * taille[1] * canaux) if bruit else bytes(taille[0] * taille[1] * canaux)
        tampon = BytesIO()
        Image.frombytes(mode, taille, donnees).save(tampon, 'PNG')
        self.etab.logo.save('logo.png', ContentFile(tampon.getvalue()), save=True)
        return len(tampon.getvalue())

    def _url(self):
        from school_admin.templatetags.logo_tags import logo_impression

        return logo_impression(self.etab)

    def _poids(self, url):
        return (Path(self.dossier.name) / url.replace(settings.MEDIA_URL, '', 1)).stat().st_size

    def test_sans_logo(self):
        self.assertEqual(self._url(), '')

    def test_logo_lourd_opaque_reduit_en_jpeg(self):
        origine = self._logo('RGB', (1200, 800))
        url = self._url()
        self.assertTrue(url.endswith('.jpg'), url)
        self.assertIn('/impression/', url)
        self.assertLess(self._poids(url), origine / 10)
        self.assertEqual(self._url(), url)  # deuxième appel : même fichier, pas de nouvelle vignette

    def test_logo_transparent_reste_en_png(self):
        from PIL import Image

        origine = self._logo('RGBA', (1200, 800))
        url = self._url()
        self.assertTrue(url.endswith('.png'), url)
        self.assertLess(self._poids(url), origine / 3)
        with Image.open(Path(self.dossier.name) / url.replace(settings.MEDIA_URL, '', 1)) as vignette:
            self.assertEqual(vignette.mode, 'RGBA')
            self.assertEqual(vignette.size, (320, 213))  # proportions conservées

    def test_petit_logo_servi_tel_quel(self):
        self._logo('RGB', (200, 100), bruit=False)
        self.assertEqual(self._url(), self.etab.logo.url)

    def test_fichier_disparu_sans_image_cassee(self):
        self._logo('RGB', (1200, 800))
        Path(self.etab.logo.path).unlink()
        self.assertEqual(self._url(), '')

    def test_entete_sans_logo_ni_champ_vide(self):
        from django.template.loader import render_to_string

        html = render_to_string('school_admin/directeur/partials/_logo_entete_impression.html',
                                {'etablissement': self.etab})
        self.assertNotIn('<img', html)
        self.assertNotIn('entete-logo-etab', html)
