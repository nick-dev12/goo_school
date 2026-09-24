"""
Par8 — Recette multi-types assistant parent (automatisée).

Parent avec enfants primaire + collège/lycée + supérieur ; checklist métier §15
(sans appel Gemini).
"""
from __future__ import annotations

import time
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.notification_parent_model import NotificationParent
from school_admin.services.assistant_parent_actions import (
    apply_marquer_notification_lue,
    prepare_marquer_notification_lue,
)
from school_admin.services.assistant_parent_schema import (
    PARENT_TOOL_NAMES_ALL,
    build_parent_tool_schemas,
)
from school_admin.services.assistant_parent_tools import (
    execute_parent_tool,
    get_parent_tools_schema,
)
from school_admin.services.assistant_parent_language import wolof_marker_score
from school_admin.services.assistant_tools import TOOLS_SCHEMA, build_assistant_context, execute_tool
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
    _make_etablissement_type,
)
from school_admin.tests.test_assistant_parent_scope import _make_parent

TEMPLATES = Path(settings.BASE_DIR) / 'school_admin' / 'templates' / 'school_admin'

DIRECTOR_TOOLS_SAMPLE = frozenset({
    item['function']['name']
    for item in TOOLS_SCHEMA
    if item.get('function', {}).get('name')
})

DIRECTOR_ONLY_PATTERNS = (
    'get_effectifs',
    'get_impayes',
    'get_statistiques_pilotage',
    'get_plan_comptable',
    'creer_classe',
    'get_structure_superieur',
    'get_examens',
    'publier_bulletin',
    'enregistrer_paiement',
    'get_caisse',
    'get_volume_horaire',
)

HUB_PARENT_PAGES = (
    'parent/dashboard_parent.html',
    'parent/scolarite_parent.html',
    'parent/annonces_parent.html',
    'parent/notifications_parent.html',
    'parent/profil_parent.html',
    'parent/convocations_parent.html',
)

ELEVE_NAV_PAGES = (
    'eleve/dashboard_eleve.html',
    'eleve/devoirs_eleve.html',
    'eleve/profil_eleve.html',
    'eleve/sanctions_eleve.html',
    'eleve/emploi_du_temps_eleve.html',
    'eleve/convocations_eleve.html',
    'eleve/notes_evaluations_eleve.html',
    'eleve/annonces_eleve.html',
    'eleve/absences_retards_eleve.html',
)

ELEVE_EXTRA_PAGES = (
    'eleve/bulletin_eleve.html',
    'eleve/bulletin_eleve_superieur.html',
    'eleve/notifications_eleve.html',
    'eleve/historique_annees_eleve.html',
    'eleve/historique_annee_detail_eleve.html',
    'directeur/comptabilite/recu_paiement.html',
)


def _schema_names(ctx=None):
    return {
        item['function']['name']
        for item in get_parent_tools_schema(ctx)
        if item.get('function')
    }


def _desc(ctx, tool_name):
    for item in build_parent_tool_schemas(ctx):
        fn = item.get('function') or {}
        if fn.get('name') == tool_name:
            return (fn.get('description') or '').lower()
    return ''


class ParentRecetteP8Fixtures(TestCase):
    """Parent multi-établissements : primaire + lycée + supérieur."""

    @classmethod
    def setUpTestData(cls):
        suffix = str(int(time.time() * 1000))[-8:]
        cls.etab_pri = _make_etablissement_type('primary', f'pp{suffix}')
        cls.etab_col = _make_etablissement()
        cls.annee_col = _make_annee(cls.etab_col)
        cls.annee_pri = _make_annee(cls.etab_pri)

        sup_email = f'sup.p8.{suffix}@aria-test.local'
        cls.etab_sup = Etablissement(
            username=sup_email,
            email=sup_email,
            nom=f'Université P8 {suffix}',
            code_etablissement=f'SP8{suffix}'[:12],
            adresse='1 rue LMD',
            pays='Sénégal',
            ville='Dakar',
            type_etablissement='superieur',
            directeur_prenom='Awa',
            directeur_nom='Test',
            directeur_email=f'dir.{suffix}@aria-test.local',
            module_comptabilite=True,
            actif=True,
        )
        cls.etab_sup.set_password('Vague1@Test1!')
        cls.etab_sup.save()
        cls.annee_sup = _make_annee(cls.etab_sup)

        cls.cl_pri = Classe.objects.create(
            nom='CM1 P8',
            niveau='primaire',
            code_classe=f'CM1-P8-{suffix}',
            capacite_max=30,
            etablissement=cls.etab_pri,
        )
        cls.cl_col = Classe.objects.create(
            nom='2nde P8',
            niveau='lycee',
            code_classe=f'2P8-{cls.etab_col.pk}',
            capacite_max=30,
            etablissement=cls.etab_col,
        )
        cls.cl_sup = Classe.objects.create(
            nom='L1 Info P8',
            niveau='superieur',
            code_classe=f'L1-P8-{suffix}'[:20],
            capacite_max=40,
            etablissement=cls.etab_sup,
        )

        cls.parent = _make_parent(cls.etab_col, suffix=f'm8{suffix}')
        cls.eleve_pri = _make_eleve_simple(
            cls.etab_pri, cls.cl_pri, 'Ba', 'Khady', suffix=f'pri{suffix}'
        )
        cls.eleve_col = _make_eleve_simple(
            cls.etab_col, cls.cl_col, 'Sow', 'Ibra', suffix=f'col{suffix}'
        )
        cls.eleve_sup = _make_eleve_simple(
            cls.etab_sup, cls.cl_sup, 'Ndiaye', 'Moussa', suffix=f'sup{suffix}'
        )
        for eleve, lien in (
            (cls.eleve_pri, 'tuteur'),
            (cls.eleve_col, 'pere'),
            (cls.eleve_sup, 'mere'),
        ):
            LienFamilial.objects.create(
                parent=cls.parent,
                eleve=eleve,
                type_lien=lien,
                statut='valide',
                actif=True,
            )

    def _ctx(self, eleve=None, session=None):
        session = dict(session or {})
        if eleve is not None:
            session['eleve_consulte_id'] = eleve.id
        return build_assistant_context(
            self.parent.etablissement,
            session,
            parent=self.parent,
            persona='parent',
        )

    def test_trois_enfants_lies(self):
        out = execute_parent_tool(self._ctx(), 'get_mes_enfants', {})
        self.assertEqual(out.get('nb'), 3)

    def test_schema_hub_union_sans_tools_directeur(self):
        names = _schema_names(self._ctx())
        self.assertEqual(len(names), 20)
        for forbidden in DIRECTOR_ONLY_PATTERNS:
            self.assertNotIn(forbidden, names)
        self.assertTrue(names <= PARENT_TOOL_NAMES_ALL)
        director_only = names & DIRECTOR_TOOLS_SAMPLE - {'ouvrir_page', 'lister_pages', 'get_annonces', 'get_notifications', 'ouvrir_recu'}
        self.assertFalse(director_only, msg=f'tools directeur dans schéma parent: {director_only}')

    def test_descriptions_adaptees_par_enfant_consulte(self):
        ctx_pri = self._ctx(self.eleve_pri)
        ctx_sup = self._ctx(self.eleve_sup)
        self.assertIn('primaire', _desc(ctx_pri, 'get_notes_enfant'))
        self.assertNotIn('pilotage direction', _desc(ctx_pri, 'get_notes_enfant'))
        self.assertIn('supérieur', _desc(ctx_sup, 'get_notes_enfant'))
        self.assertIn('lmd', _desc(ctx_sup, 'get_notes_enfant'))
        ctx_hub = self._ctx()
        hub_desc = _desc(ctx_hub, 'get_notes_enfant')
        self.assertIn('adapter', hub_desc)

    def test_notes_et_absences_par_type(self):
        for eleve in (self.eleve_pri, self.eleve_col, self.eleve_sup):
            ctx = self._ctx(eleve)
            notes = execute_parent_tool(ctx, 'get_notes_enfant', {})
            self.assertEqual(notes.get('eleve_id'), eleve.id)
            absences = execute_parent_tool(ctx, 'get_absences_enfant', {})
            self.assertEqual(absences.get('eleve_id'), eleve.id)

    def test_refus_eleve_non_lie(self):
        suffix = str(int(time.time() * 1000))[-7:]
        etab = _make_etablissement_type('lycée', f'rf{suffix}')
        cl = Classe.objects.create(
            nom='X',
            niveau='college',
            code_classe=f'X-{etab.pk}-{suffix}',
            capacite_max=20,
            etablissement=etab,
        )
        autre = _make_eleve_simple(etab, cl, 'Z', 'Z', suffix=f'zz{suffix}')
        out = execute_parent_tool(
            self._ctx(self.eleve_col),
            'get_notes_enfant',
            {'eleve_id': autre.id},
        )
        self.assertEqual(out.get('statut'), 'acces_refuse')

    def test_scolarite_chiffres_via_tool(self):
        ctx = self._ctx(self.eleve_col)
        out = execute_parent_tool(
            ctx,
            'get_scolarite_enfant',
            {'nom': self.eleve_col.prenom},
        )
        self.assertEqual(out.get('eleve_id'), self.eleve_col.id)
        self.assertIn('reste', out)
        self.assertIn('message', out)

    def test_scolarite_famille_hub(self):
        out = execute_parent_tool(self._ctx(), 'get_scolarite_famille', {})
        self.assertIn('dette_totale', out)
        self.assertGreaterEqual(out.get('nb_enfants', 0), 1)

    def test_ouvrir_devoirs_navigue(self):
        ctx = self._ctx(self.eleve_col, {'eleve_consulte_id': self.eleve_col.id})
        out = execute_parent_tool(ctx, 'ouvrir_page', {'page_key': 'devoirs'})
        self.assertIn('url', out)
        self.assertIn('devoirs', out['url'])

    def test_bloque_tools_directeur(self):
        ctx = self._ctx(self.eleve_col)
        for name in ('get_effectifs', 'enregistrer_paiement', 'get_plan_comptable'):
            out = execute_tool(ctx, name, {})
            self.assertEqual(out.get('statut'), 'hors_perimetre')

    def test_ecriture_notification_seulement_apres_apply(self):
        notif = NotificationParent.objects.create(
            parent=self.parent,
            eleve=self.eleve_col,
            annee_scolaire=self.annee_col,
            titre='P8 test',
            message='Recette',
            type_notification='information',
            lu=False,
        )
        ctx = self._ctx()
        pending = prepare_marquer_notification_lue(ctx, {'notification_id': notif.id})
        self.assertEqual(pending.get('statut'), 'en_attente_confirmation')
        notif.refresh_from_db()
        self.assertFalse(notif.lu)
        apply_marquer_notification_lue(ctx, pending)
        notif.refresh_from_db()
        self.assertTrue(notif.lu)


class ParentRecetteP8UiTests(TestCase):
    """Critère §15.1 — bulle Aria sur pages hub + enfant + reçu + bulletin."""

    def _assert_widget(self, rel_path):
        text = (TEMPLATES / rel_path).read_text(encoding='utf-8')
        has_widget = 'assistant_vocal_parent' in text
        has_nav = 'bottom_nav_parent.html' in text or 'bottom_nav_eleve.html' in text
        self.assertTrue(
            has_widget or has_nav,
            msg=f'{rel_path} : ni widget ni bottom nav assistant',
        )

    def test_pages_hub_parent(self):
        for rel in HUB_PARENT_PAGES:
            self._assert_widget(rel)

    def test_pages_eleve_avec_nav(self):
        for rel in ELEVE_NAV_PAGES:
            text = (TEMPLATES / rel).read_text(encoding='utf-8')
            self.assertIn('bottom_nav_eleve.html', text, msg=rel)

    def test_pages_eleve_sans_nav_ont_widget(self):
        for rel in ELEVE_EXTRA_PAGES:
            text = (TEMPLATES / rel).read_text(encoding='utf-8')
            self.assertIn('assistant_vocal_parent', text, msg=rel)

    def test_bottom_nav_inclut_widget(self):
        for rel in (
            'parent/partials/bottom_nav_parent.html',
            'eleve/partials/bottom_nav_eleve.html',
        ):
            text = (TEMPLATES / rel).read_text(encoding='utf-8')
            self.assertIn('assistant_vocal_parent', text)


class ParentRecetteP8WolofSmokeTests(TestCase):
    """Critère §15.4 — détection wolof (STT/TTS manuel)."""

    def test_detect_wolof_sample(self):
        self.assertGreater(wolof_marker_score('Na nga def? Wax ma ci sama xale.'), 0)

    def test_french_low_wolof_score(self):
        self.assertEqual(wolof_marker_score('Quelles sont les notes de mon enfant ?'), 0)


class ParentRecetteP8ChecklistMetaTests(TestCase):
    """Résumé checklist §15 pour la doc audit."""

    CHECKLIST_AUTO = (
        '§15.2 scolarité via get_scolarite_*',
        '§15.3 refus acces_refuse',
        '§15.5 ouvrir_page devoirs',
        '§15.6 scan schéma sans tools directeur',
        '§15.7 marquer_notification apply après confirm',
    )
    CHECKLIST_MANUAL = (
        '§15.1 visuel navigateur (bulle sur chaque écran)',
        '§15.4 TTS wolof audible / fallback',
        '§15.2 formulation naturelle « combien je dois pour X »',
    )

    def test_checklist_documented(self):
        self.assertEqual(len(self.CHECKLIST_AUTO), 5)
        self.assertEqual(len(self.CHECKLIST_MANUAL), 3)
