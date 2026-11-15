"""Banc de mesure de performance (désactivé par défaut).

Mesure, pour les pages principales de chaque espace, le temps serveur, le nombre de requêtes SQL, puis le
chargement à froid dans Chromium avec un débit bridé. Tout tourne sur la base de test en mémoire.

    PERF_MESURE=1 PERF_SORTIE=mesures.json python manage.py test school_admin.tests.test_perf_pages \
        --settings=school.test_settings

Variables : PERF_KBPS (400), PERF_LATENCE_MS (400), PERF_GZIP_HTML=1 (compresse le HTML comme le fait Nginx),
PERF_STATIC=whitenoise (sert /static/ par WhiteNoise depuis STATIC_ROOT, après collectstatic),
PERF_PAGES (noms de route), PERF_SANS_NAVIGATEUR=1 (serveur et SQL seulement), PERF_POPUP_TTL (secondes),
PERF_CAPTURES=<dossier> (captures d'écran au lieu des mesures).
"""
import json
import os
import time
import unittest
import uuid
from collections import defaultdict
from unittest.mock import patch
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connection
from django.test import LiveServerTestCase
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import reverse

ACTIF = os.environ.get('PERF_MESURE') == '1'
FILTRE = [n for n in os.environ.get('PERF_PAGES', '').split(',') if n]  # limite la mesure à ces noms de route
SANS_NAVIGATEUR = os.environ.get('PERF_SANS_NAVIGATEUR') == '1'  # temps serveur et SQL seulement
CAPTURES = os.environ.get('PERF_CAPTURES')  # dossier : captures d'écran au lieu des mesures
KBPS = int(os.environ.get('PERF_KBPS', '400'))
LATENCE = int(os.environ.get('PERF_LATENCE_MS', '400'))
WHITENOISE = os.environ.get('PERF_STATIC') == 'whitenoise'
BACKEND = 'school_admin.authentication_backends.MultiUserBackend'

PAGES = {
    'direction': ['directeur:dashboard_directeur', 'directeur:gestion_eleves', 'directeur:notes_et_resultats',
                  'directeur:suivi_presence', 'directeur:liste_comptabilite_eleves_directeur'],
    'personnel': ['directeur:dashboard_directeur', 'directeur:gestion_eleves'],
    'prof_secondaire': ['enseignant:dashboard_enseignant', 'enseignant:gestion_classes', 'enseignant:gestion_eleves'],
    'prof_primaire': ['enseignant_primaire:dashboard', 'enseignant_primaire:gestion_classes',
                      'enseignant_primaire:gestion_eleves'],
    'eleve': ['eleve:dashboard_eleve', 'eleve:devoirs_eleve', 'eleve:emploi_du_temps'],
    'parent': ['school_admin:dashboard_parent', 'school_admin:scolarite_parent'],
}


def _middleware():
    mw = list(settings.MIDDLEWARE)
    if os.environ.get('PERF_GZIP_HTML') == '1' and not any('gzip' in m.lower() or 'compression' in m.lower()
                                                           for m in mw):
        mw.insert(0, 'django.middleware.gzip.GZipMiddleware')
    return mw


class _Base(LiveServerTestCase if WHITENOISE else StaticLiveServerTestCase):
    if WHITENOISE:
        static_handler = staticmethod(lambda app: app)  # /static/ arrive jusqu'au middleware WhiteNoise


@unittest.skipUnless(ACTIF, 'banc de mesure : définir PERF_MESURE=1')
# Durée de cache de production : test_settings hérite du réglage calculé avec DEBUG=True (0 seconde).
@override_settings(MIDDLEWARE=_middleware(), WHITENOISE_MAX_AGE=30 * 24 * 3600,
                   CONTEXT_POPUP_TOTAL_TTL=int(os.environ.get('PERF_POPUP_TTL', '0')))
class PerfPages(_Base):

    def _mesure_serveur(self, url):
        r = self.client.get(url, follow=True)  # échauffement (gabarits, imports) et suivi d'une redirection
        if r.redirect_chain:
            url = r.redirect_chain[-1][0]
        durees = []
        for _ in range(3):
            with CaptureQueriesContext(connection) as ctx:
                t = time.perf_counter()
                r = self.client.get(url)
                durees.append(time.perf_counter() - t)
        # Appel fait par chaque page pour les rappels : première arrivée (synthèse), puis page suivante (pastille).
        popups = []
        for _ in range(2):
            with CaptureQueriesContext(connection) as popup:
                t = time.perf_counter()
                rp = self.client.post(reverse('school_admin:context_popup'), content_type='application/json',
                                      data=json.dumps({'action': 'claim', 'visit_key': self._visite}))
                popups.append((round((time.perf_counter() - t) * 1000), len(popup.captured_queries)))
        sql = [q['sql'] for q in ctx.captured_queries]
        formes = defaultdict(int)
        for s in sql:
            formes[s.split(' WHERE ')[0][:140]] += 1
        doublons = sorted(((n, f) for f, n in formes.items() if n >= 3), reverse=True)[:6]
        return {
            'statut': r.status_code, 'html_ko': round(len(r.content) / 1024, 1),
            'serveur_ms': round(min(durees) * 1000), 'sql': len(sql), 'sql_repetees': doublons,
            'popup_statut': rp.status_code, 'popup_ms': popups[0][0], 'popup_sql': popups[0][1],
            'popup_suite_ms': popups[1][0], 'popup_suite_sql': popups[1][1], 'url_finale': url,
        }

    def _mesure_navigateur(self, browser, cookie, url):
        ctx = browser.new_context(viewport={'width': 390, 'height': 800}, service_workers='block')
        if cookie:
            ctx.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': cookie, 'url': self.live_server_url}])
        page = ctx.new_page()
        cdp = ctx.new_cdp_session(page)
        cdp.send('Network.enable')
        cdp.send('Network.emulateNetworkConditions', {
            'offline': False, 'latency': LATENCE, 'downloadThroughput': KBPS * 125, 'uploadThroughput': KBPS * 125})
        reqs, tailles, echecs, statuts = {}, {}, [], {}
        cdp.on('Network.requestWillBeSent', lambda e: reqs.__setitem__(e['requestId'], e['request']['url']))
        cdp.on('Network.responseReceived', lambda e: statuts.__setitem__(e['requestId'], e['response']['status']))
        cdp.on('Network.loadingFinished', lambda e: tailles.__setitem__(e['requestId'], e['encodedDataLength']))
        cdp.on('Network.loadingFailed', lambda e: echecs.append(reqs.get(e['requestId'], '?')))
        page.add_init_script(
            "window.__lcp=0;new PerformanceObserver(l=>{for(const e of l.getEntries())window.__lcp=e.startTime;})"
            ".observe({type:'largest-contentful-paint',buffered:true});")
        js = """() => { const n = performance.getEntriesByType('navigation')[0];
            const f = performance.getEntriesByType('paint').find(p => p.name === 'first-contentful-paint');
            const bloc = performance.getEntriesByType('resource').filter(e => e.renderBlockingStatus === 'blocking');
            return {ttfb: n.responseStart, dcl: n.domContentLoadedEventEnd, load: n.loadEventEnd,
                    fcp: f ? f.startTime : 0, lcp: window.__lcp, bloquantes: bloc.length}; }"""
        page.goto(self.live_server_url + url, wait_until='load', timeout=300000)
        page.wait_for_timeout(4000)
        m = page.evaluate(js)
        par_hote = defaultdict(lambda: [0, 0])
        lignes = []
        for rid, u in reqs.items():
            if u.startswith(('data:', 'blob:')):
                continue
            hote = urlparse(u).netloc
            hote = 'site' if hote == urlparse(self.live_server_url).netloc else hote
            par_hote[hote][0] += 1
            par_hote[hote][1] += tailles.get(rid, 0)
            lignes.append((tailles.get(rid, 0), u.replace(self.live_server_url, '')[:100]))
        erreurs = [reqs[r].replace(self.live_server_url, '')[:100] for r, s in statuts.items() if s >= 400]
        froid = {
            'requetes': sum(v[0] for v in par_hote.values()),
            'ko': round(sum(v[1] for v in par_hote.values()) / 1024, 1),
            'ko_site': round(par_hote['site'][1] / 1024, 1),
            'ko_cdn': round(sum(v[1] for h, v in par_hote.items() if h != 'site') / 1024, 1),
            'bloquantes': m['bloquantes'],
            'fcp_s': round(m['fcp'] / 1000, 1), 'lcp_s': round(m['lcp'] / 1000, 1),
            'dcl_s': round(m['dcl'] / 1000, 1), 'load_s': round(m['load'] / 1000, 1),
            'par_hote': {h: [v[0], round(v[1] / 1024, 1)] for h, v in par_hote.items()},
            'plus_lourdes': [[round(s / 1024, 1), u] for s, u in sorted(lignes, reverse=True)[:8]],
            'echecs': echecs + erreurs,
        }
        # Deuxième visite de la même page : cache navigateur chaud, même débit.
        reqs.clear(), tailles.clear()
        page.goto(self.live_server_url + url, wait_until='load', timeout=300000)
        page.wait_for_timeout(2500)
        m2 = page.evaluate(js)
        chaud = {
            'requetes_reseau': sum(1 for r in reqs if tailles.get(r, 0) > 0),
            'ko': round(sum(tailles.values()) / 1024, 1),
            'fcp_s': round(m2['fcp'] / 1000, 1), 'load_s': round(m2['load'] / 1000, 1),
        }
        ctx.close()
        return {'froid': froid, 'chaud': chaud}

    def _capture(self, browser, cookie, url, nom):
        """Capture d'écran (mobile et bureau) sans bridage, pour comparer le rendu avant / après."""
        for largeur, suffixe in ((390, 'mobile'), (1366, 'bureau')):
            ctx = browser.new_context(viewport={'width': largeur, 'height': 900}, service_workers='block')
            if cookie:
                ctx.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': cookie, 'url': self.live_server_url}])
            page = ctx.new_page()
            page.goto(self.live_server_url + url, wait_until='networkidle', timeout=120000)
            page.evaluate('document.fonts.ready')
            page.wait_for_timeout(1500)
            page.add_style_tag(content='dialog.arp,.arp-pill{display:none!important}*{animation:none!important;'
                                       'transition:none!important;caret-color:transparent!important}')
            page.screenshot(path=os.path.join(CAPTURES, f'{nom}_{suffixe}.png'), full_page=True)
            ctx.close()

    def test_mesures(self):
        os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
        from playwright.sync_api import sync_playwright

        from school_admin.tests_smoke_primaire_secondaire import SmokePrimaireSecondaire

        # Hors TestCase, on_commit part aussitôt et lance des fils d'envoi : inutiles ici, et ils verrouillent SQLite.
        from school_admin import tests_smoke_primaire_secondaire as smoke
        creer = smoke._make_etablissement_type
        with patch('django.db.transaction.on_commit', lambda *a, **k: None),                 patch.object(smoke, '_make_etablissement_type', lambda t, prefixe: creer(t, 'pri' if t == 'primary' else 'sec')):
            prim = SmokePrimaireSecondaire._peupler(None, 'primary')
            sec = SmokePrimaireSecondaire._peupler(None, 'lycée')
        comptes = {
            'direction': (sec['etab'], 'etablissement'),
            'personnel': (sec['personnel'][0], 'personnel'),
            'prof_secondaire': (next(iter(sec['profs'].values())), 'professeur'),
            'prof_primaire': (next(iter(prim['profs'].values())), 'professeur'),
            'eleve': (sec['eleves'][0], 'eleve'),
            'parent': (sec['parent'], 'parent'),
        }
        resultats = {'reglages': {'kbit_s': KBPS, 'latence_ms': LATENCE,
                                  'gzip_html': os.environ.get('PERF_GZIP_HTML') == '1', 'whitenoise': WHITENOISE}}
        if os.name == 'nt':  # Daphne impose la boucle « selector », incapable de lancer le navigateur
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        with sync_playwright() as p:
            browser = p.chromium.launch()
            url = reverse('school_admin:connexion_compte_user')
            if CAPTURES:
                self._capture(browser, None, url, 'connexion')
            elif not FILTRE:
                resultats['connexion'] = {url: self._mesure_navigateur(browser, None, url)}
            for espace, (user, type_user) in comptes.items():
                self.client.logout()
                self.client.force_login(user, backend=BACKEND)
                session = self.client.session
                session['_auth_user_type'] = type_user
                session.save()
                cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
                resultats[espace] = {}
                for nom in PAGES[espace]:
                    if FILTRE and nom not in FILTRE:
                        continue
                    url = reverse(nom)
                    self._visite = uuid.uuid4().hex
                    if CAPTURES:
                        self._capture(browser, cookie, url, f'{espace}_{nom.replace(":", "_")}')
                        continue
                    ligne = self._mesure_serveur(url)
                    if ligne['statut'] == 200 and not SANS_NAVIGATEUR:
                        ligne.update(self._mesure_navigateur(browser, cookie, ligne['url_finale']))
                    resultats[espace][url] = ligne
                    print(espace, url, json.dumps({k: v for k, v in ligne.items() if k not in ('froid', 'chaud')},
                                                  ensure_ascii=False)[:300], flush=True)
            browser.close()
        sortie = os.environ.get('PERF_SORTIE')
        if sortie:
            with open(sortie, 'w', encoding='utf-8') as f:
                json.dump(resultats, f, ensure_ascii=False, indent=1)


@unittest.skipUnless(os.environ.get('PERF_SQL'), 'détail SQL : définir PERF_SQL=<espace>:<nom de route>')
class PerfSql(LiveServerTestCase):
    """Liste les requêtes SQL répétées d'une page avec la ligne de code qui les lance.

    PERF_SQL=direction:directeur:dashboard_directeur python manage.py test school_admin.tests.test_perf_pages.PerfSql
    """

    def test_detail(self):
        import traceback

        from django.db.backends.utils import CursorWrapper

        from school_admin import tests_smoke_primaire_secondaire as smoke

        espace, _, nom = os.environ['PERF_SQL'].partition(':')
        creer = smoke._make_etablissement_type
        with patch('django.db.transaction.on_commit', lambda *a, **k: None), \
                patch.object(smoke, '_make_etablissement_type', lambda t, prefixe: creer(t, 'pri' if t == 'primary' else 'sec')):
            prim = smoke.SmokePrimaireSecondaire._peupler(None, 'primary')
            sec = smoke.SmokePrimaireSecondaire._peupler(None, 'lycée')
        user, type_user = {
            'direction': (sec['etab'], 'etablissement'), 'personnel': (sec['personnel'][0], 'personnel'),
            'prof_secondaire': (next(iter(sec['profs'].values())), 'professeur'),
            'prof_primaire': (next(iter(prim['profs'].values())), 'professeur'),
            'eleve': (sec['eleves'][0], 'eleve'), 'parent': (sec['parent'], 'parent')}[espace]
        self.client.force_login(user, backend=BACKEND)
        session = self.client.session
        session['_auth_user_type'] = type_user
        session.save()
        url = reverse(nom) if not nom.startswith('/') else nom
        methode = 'post' if nom.endswith('context_popup') else 'get'
        appel = (lambda: self.client.post(url, data='{"action":"claim"}', content_type='application/json')) \
            if methode == 'post' else (lambda: self.client.get(url))
        appel()
        lieux = defaultdict(int)
        origine = CursorWrapper.execute

        def espion(cursor, sql, params=None):
            pile = [f for f in traceback.extract_stack() if 'school_admin' in f.filename and 'tests' not in f.filename]
            lieu = ' < '.join(f'{os.path.basename(f.filename)}:{f.lineno}' for f in reversed(pile[-3:]))
            lieux[(lieu, sql.split(' WHERE ')[0][:90])] += 1
            return origine(cursor, sql, params)

        with patch.object(CursorWrapper, 'execute', espion):
            r = appel()
        print(f'\n{url} -> {r.status_code}, {sum(lieux.values())} requêtes SQL')
        for (lieu, sql), n in sorted(lieux.items(), key=lambda kv: -kv[1])[:int(os.environ.get('PERF_SQL_MAX', '40'))]:
            print(f'{n:4d}  {lieu}\n        {sql}')


@unittest.skipUnless(os.environ.get('PERF_IMPRESSION'), "captures des pages d'impression : PERF_IMPRESSION=<dossier>")
class PerfImpression(StaticLiveServerTestCase):
    """Compare les pages d'impression avec la police d'icônes (actuel) et avec l'ancienne version JavaScript
    de Font Awesome (réinjectée à la volée) : deux captures par page dans le dossier donné."""

    ROUTES = [('directeur:generer_certificat_scolarite', 'e'), ('directeur:generer_attestation_reussite', 'e'),
              ('directeur:generer_attestation_conduite', 'e'), ('directeur:generer_fiche_inscription', 'e'),
              ('directeur:generer_certificat_radiation', 'e'), ('directeur:imprimer_bulletin_eleve', 'ce'),
              ('directeur:imprimer_bulletins_classe', 'c'), ('directeur:imprimer_liste_nominative', 'c'),
              ('directeur:imprimer_releve_notes', 'c'), ('directeur:imprimer_fiches_classe', 'c')]
    ANCIEN = '<script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/js/all.min.js"></script></body>'

    def test_captures(self):
        os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
        from playwright.sync_api import sync_playwright

        from school_admin import tests_smoke_primaire_secondaire as smoke

        with patch('django.db.transaction.on_commit', lambda *a, **k: None):
            d = smoke.SmokePrimaireSecondaire._peupler(None, 'lycée')
        self.client.force_login(d['etab'], backend=BACKEND)
        session = self.client.session
        session['_auth_user_type'] = 'etablissement'
        session.save()
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        dossier = os.environ['PERF_IMPRESSION']
        if os.name == 'nt':
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for nom, args in self.ROUTES:
                kwargs = {}
                if 'c' in args:
                    kwargs['classe_id'] = d['classes'][0].id
                if 'e' in args:
                    kwargs['eleve_id'] = d['eleves'][0].id
                url = reverse(nom, kwargs=kwargs)
                statut = self.client.get(url).status_code
                for variante in ('police', 'ancien_js'):
                    ctx = browser.new_context(viewport={'width': 1100, 'height': 900}, service_workers='block')
                    ctx.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': cookie, 'url': self.live_server_url}])
                    page = ctx.new_page()
                    if variante == 'ancien_js':
                        def ancien(route):
                            r = route.fetch()
                            route.fulfill(response=r, body=r.text().replace('</body>', self.ANCIEN))
                        page.route(self.live_server_url + url, ancien)
                    erreurs = []
                    page.on('pageerror', lambda e: erreurs.append(str(e)[:120]))
                    page.goto(self.live_server_url + url, wait_until='networkidle', timeout=120000)
                    page.evaluate('document.fonts.ready')
                    page.wait_for_timeout(1500)
                    icones = page.evaluate("document.querySelectorAll('i[class*=fa-], svg.svg-inline--fa').length")
                    vides = page.evaluate("""[...document.querySelectorAll('i[class*=fa-]')].filter(i => {
                        const c = getComputedStyle(i, '::before').content; return !c || c === 'none' || c === 'normal';
                    }).map(i => i.className)""")
                    page.screenshot(path=os.path.join(dossier, f'{nom.split(":")[1]}_{variante}.png'), full_page=True)
                    print(nom, variante, statut, 'icônes :', icones, 'sans glyphe :', vides, 'erreurs JS :', erreurs,
                          flush=True)
                    ctx.close()
            browser.close()

    def test_scanner_qr_direction(self):
        """Le scanner de l'en-tête direction télécharge sa bibliothèque à l'ouverture, puis démarre (caméra simulée)."""
        os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
        from playwright.sync_api import sync_playwright

        from school_admin import tests_smoke_primaire_secondaire as smoke

        with patch('django.db.transaction.on_commit', lambda *a, **k: None):
            d = smoke.SmokePrimaireSecondaire._peupler(None, 'lycée')
        self.client.force_login(d['etab'], backend=BACKEND)
        session = self.client.session
        session['_auth_user_type'] = 'etablissement'
        session.save()
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        if os.name == 'nt':
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        with sync_playwright() as p:
            browser = p.chromium.launch(args=['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'])
            ctx = browser.new_context(service_workers='block')
            ctx.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': cookie, 'url': self.live_server_url}])
            page = ctx.new_page()
            alertes = []
            page.on('dialog', lambda dlg: (alertes.append(dlg.message), dlg.dismiss()))
            page.goto(self.live_server_url + reverse('directeur:dashboard_directeur'), wait_until='load')
            self.assertEqual(page.evaluate('typeof Html5Qrcode'), 'undefined')
            page.evaluate('ouvrirScannerQR()')
            page.wait_for_function("typeof Html5Qrcode === 'function' && !!document.querySelector('#qr-reader video')",
                                   timeout=20000)
            self.assertTrue(page.evaluate('isScanning'))
            page.evaluate('fermerScannerQR()')
            self.assertEqual(alertes, [])
            browser.close()

    def test_assistant_s_ouvre(self):
        """Le bouton de l'assistante ouvre son panneau dans chaque espace (script chargé en différé)."""
        os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
        from playwright.sync_api import sync_playwright

        from school_admin import tests_smoke_primaire_secondaire as smoke

        with patch('django.db.transaction.on_commit', lambda *a, **k: None):
            d = smoke.SmokePrimaireSecondaire._peupler(None, 'lycée')
        comptes = [(d['etab'], 'etablissement', 'directeur:dashboard_directeur'),
                   (next(iter(d['profs'].values())), 'professeur', 'enseignant:dashboard_enseignant'),
                   (d['eleves'][0], 'eleve', 'eleve:dashboard_eleve'),
                   (d['parent'], 'parent', 'school_admin:dashboard_parent')]
        if os.name == 'nt':
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for user, type_user, nom in comptes:
                self.client.logout()
                self.client.force_login(user, backend=BACKEND)
                session = self.client.session
                session['_auth_user_type'] = type_user
                session.save()
                ctx = browser.new_context(service_workers='block')
                ctx.add_cookies([{'name': settings.SESSION_COOKIE_NAME,
                                  'value': self.client.cookies[settings.SESSION_COOKIE_NAME].value,
                                  'url': self.live_server_url}])
                page = ctx.new_page()
                erreurs = []
                page.on('pageerror', lambda e: erreurs.append(str(e)[:200]))
                page.goto(self.live_server_url + reverse(nom), wait_until='load')
                page.add_style_tag(content='dialog.arp,.arp-pill{display:none!important}')
                page.evaluate("document.querySelectorAll('dialog[open]').forEach(d => d.close())")
                page.click('#assistant-vocal-fab')
                page.wait_for_function("document.getElementById('assistant-vocal-root').classList.contains('is-open')",
                                       timeout=10000)
                print(nom, 'assistante ouverte, erreurs JS :', erreurs, flush=True)
                ctx.close()
            browser.close()


@unittest.skipUnless(os.environ.get('PERF_LOGO'), "captures des en-têtes avec / sans logo : PERF_LOGO=<dossier>")
@override_settings(MEDIA_ROOT=os.path.join(os.environ.get('PERF_LOGO', '.'), 'media'))
class PerfLogoImpression(StaticLiveServerTestCase):
    """Les 10 pages d'impression avec un établissement qui a un logo (lourd, 1600 × 900) puis sans logo :
    captures à l'écran et en rendu d'impression, taille affichée, proportions et poids du logo servi."""

    def test_logo(self):
        os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
        import random
        from io import BytesIO

        from django.core.files.base import ContentFile
        from PIL import Image, ImageDraw
        from playwright.sync_api import sync_playwright

        from school_admin import tests_smoke_primaire_secondaire as smoke

        with patch('django.db.transaction.on_commit', lambda *a, **k: None):
            d = smoke.SmokePrimaireSecondaire._peupler(None, 'lycée')
        etab = d['etab']
        rnd = random.Random(1)
        image = Image.frombytes('RGB', (1600, 900), rnd.randbytes(1600 * 900 * 3))  # bruit : fichier très lourd
        dessin = ImageDraw.Draw(image)
        dessin.ellipse([500, 150, 1100, 750], fill=(20, 90, 200))
        dessin.rectangle([0, 0, 1599, 899], outline=(200, 30, 30), width=24)
        tampon = BytesIO()
        image.save(tampon, 'PNG')
        poids_origine = len(tampon.getvalue())
        dossier = os.environ['PERF_LOGO']
        if os.name == 'nt':
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for variante in ('avec_logo', 'sans_logo'):
                if variante == 'avec_logo':
                    etab.logo.save('logo_test.png', ContentFile(tampon.getvalue()), save=True)
                else:
                    etab.logo.delete(save=True)
                self.client.logout()
                self.client.force_login(etab, backend=BACKEND)
                session = self.client.session
                session['_auth_user_type'] = 'etablissement'
                session.save()
                cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
                for nom, args in PerfImpression.ROUTES:
                    kwargs = {}
                    if 'c' in args:
                        kwargs['classe_id'] = d['classes'][0].id
                    if 'e' in args:
                        kwargs['eleve_id'] = d['eleves'][0].id
                    url = reverse(nom, kwargs=kwargs)
                    ctx = browser.new_context(viewport={'width': 1100, 'height': 900}, service_workers='block')
                    ctx.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': cookie, 'url': self.live_server_url}])
                    page = ctx.new_page()
                    recus = {}
                    page.on('response', lambda r: recus.__setitem__(r.url, r.status) if '/media/' in r.url else None)
                    page.goto(self.live_server_url + url, wait_until='networkidle', timeout=120000)
                    court = nom.split(':')[1]
                    page.screenshot(path=os.path.join(dossier, f'{court}_{variante}_ecran.png'),
                                    clip={'x': 0, 'y': 0, 'width': 1100, 'height': 420})
                    mesure = """() => [...document.querySelectorAll('.entete-logo-etab img, img.logo-img')].map(i => {
                        const r = i.getBoundingClientRect();
                        return {l: Math.round(r.width), h: Math.round(r.height), nl: i.naturalWidth, nh: i.naturalHeight,
                                ok: i.complete && i.naturalWidth > 0, fit: getComputedStyle(i).objectFit, src: i.src}; })"""
                    ecran = page.evaluate(mesure)
                    casses = page.evaluate("[...document.images].filter(i => !(i.complete && i.naturalWidth > 0)).map(i => i.src)")
                    vides = page.evaluate("[...document.querySelectorAll('.entete-logo-etab')].length")
                    page.emulate_media(media='print')
                    page.screenshot(path=os.path.join(dossier, f'{court}_{variante}_impression.png'),
                                    clip={'x': 0, 'y': 0, 'width': 1100, 'height': 420})
                    impression = page.evaluate(mesure)
                    poids = None
                    if ecran:
                        poids = len(page.request.get(ecran[0]['src']).body())
                    print(f"{variante} {court:32} logos {len(ecran)} blocs {vides} écran "
                          f"{[(e['l'], e['h'], e['fit']) for e in ecran[:1]]} impression {[(e['l'], e['h']) for e in impression[:1]]}"
                          f" source {[(e['nl'], e['nh']) for e in ecran[:1]]} poids {poids} (origine {poids_origine})"
                          f" images cassées {len(casses)} médias {sorted(set(recus.values()))}", flush=True)
                    if variante == 'avec_logo':
                        self.assertTrue(ecran and all(e['ok'] for e in ecran), court)
                        self.assertLess(poids, poids_origine / 3, court)
                    else:
                        self.assertEqual((len(ecran), vides), (0, 0), court)
                    self.assertEqual(casses, [], court)
                    # Texte visible : ni balise de gabarit en clair, ni « None » à la place d'un champ vide.
                    texte = page.evaluate("document.body.innerText")
                    suspects = [l.strip()[:90] for l in texte.splitlines()
                                if '{%' in l or '%}' in l or '{{' in l or 'None' in l.split() or 'undefined' in l.split()]
                    print('   texte suspect :', suspects, flush=True)
                    page.screenshot(path=os.path.join(dossier, f'{court}_{variante}_page.png'), full_page=True)
                    ctx.close()
            browser.close()
