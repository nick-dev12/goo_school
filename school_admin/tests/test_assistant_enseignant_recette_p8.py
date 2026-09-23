"""
P8 — Recette multi-types assistant enseignant (automatisée).

Couvre les parcours primaire, collège/lycée et supérieur sans appeler Gemini :
schéma filtré, lecture + repli oral, écritures en attente de confirmation, UI widget.
"""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.affectation_professeur_primaire_model import (
    AffectationProfesseurPrimaire,
)
from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.matiere_model import Matiere
from school_admin.model.professeur_model import Professeur
from school_admin.services.assistant_enseignant_examens_tools import _examens_allowed
from school_admin.services.assistant_enseignant_primaire_tools import (
    execute_enseignant_primaire_tool,
    get_enseignant_primaire_tools_schema,
    spoken_from_enseignant_tool as spoken_primaire,
)
from school_admin.services.assistant_enseignant_secondaire_tools import (
    execute_enseignant_secondaire_tool,
    get_enseignant_secondaire_tools_schema,
    spoken_from_enseignant_tool as spoken_secondaire,
)
from school_admin.services.assistant_tools import build_assistant_context, suggestions_after_read
from school_admin.tests.test_assistant_enseignant_primaire_tools import (
    _make_etablissement_primaire,
)
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_etablissement,
)


TEMPLATES_ROOT = Path(settings.BASE_DIR) / 'school_admin' / 'templates' / 'school_admin' / 'enseignant'

P7_ACTIONS = (
    'justifier_absence',
    'modifier_evaluation',
    'supprimer_evaluation',
    'marquer_notification_lue',
)
EXAM_TOOLS = (
    'get_examens_prof',
    'get_notes_examen',
    'ouvrir_noter_examen',
    'enregistrer_note_examen',
)
LMD_TOOLS = ('get_modules_classe', 'get_credits_etudiant')


def _schema_names(schema):
    return {
        item['function']['name']
        for item in schema
        if item.get('function')
    }


class EnseignantRecetteP8UiTests(TestCase):
    """Critère audit §11.1 — présence du widget (header ou gate)."""

    def test_headers_include_aria_widget(self):
        for rel in (
            'partials/header_enseignant_new.html',
            'primaire/partials/header_primaire.html',
        ):
            text = (TEMPLATES_ROOT / rel).read_text(encoding='utf-8')
            self.assertIn('assistant_vocal_enseignant', text, msg=rel)

    def test_pages_sans_header_ont_gate(self):
        for rel, needle in (
            ('notifications_enseignant.html', 'assistant_vocal_secondaire_if_not_primary'),
            ('imprimer_releve_notes.html', 'assistant_vocal_secondaire_if_not_primary'),
            ('imprimer_tableau_presence.html', 'assistant_vocal_secondaire_if_not_primary'),
            ('primaire/imprimer_releve_primaire.html', 'assistant_vocal_enseignant_primaire'),
        ):
            text = (TEMPLATES_ROOT / rel).read_text(encoding='utf-8')
            self.assertIn(needle, text, msg=rel)

    def test_dashboard_via_header(self):
        for rel in ('dashboard_enseignant.html', 'primaire/dashboard_primaire.html'):
            text = (TEMPLATES_ROOT / rel).read_text(encoding='utf-8')
            self.assertIn('header', text.lower())
            self.assertTrue(
                'header_enseignant_new' in text or 'header_primaire' in text,
                msg=rel,
            )


class EnseignantRecetteP8SchemaTests(TestCase):
    """Critère §11.5 — schéma filtré par type d'établissement."""

    @classmethod
    def setUpTestData(cls):
        cls.etab_pri = _make_etablissement_primaire()
        cls.annee_pri = _make_annee(cls.etab_pri)
        cls.etab_col = _make_etablissement()
        cls.annee_col = _make_annee(cls.etab_col)
        sup_suffix = f'{int(time.time() * 1000)}'
        sup_email = f'sup.p8.{sup_suffix}@aria-test.local'
        cls.etab_sup = Etablissement(
            username=sup_email,
            email=sup_email,
            nom=f'Université P8 {sup_suffix}',
            code_etablissement=f'SP8{sup_suffix[-9:]}'[:12],
            adresse='1 rue LMD',
            pays='Sénégal',
            ville='Dakar',
            type_etablissement='superieur',
            directeur_prenom='A',
            directeur_nom='B',
            directeur_email=f'dir.sup.{sup_suffix}@test.local',
            actif=True,
        )
        cls.etab_sup.set_password('Sup@Test1!')
        cls.etab_sup.save()
        cls.annee_sup = _make_annee(cls.etab_sup)

        suffix = str(cls.etab_col.pk)
        cls.matiere_col = Matiere.objects.create(
            nom=f'Hist {suffix}',
            code=f'HI{suffix}'[:10],
            etablissement=cls.etab_col,
            actif=True,
        )
        cls.prof_col = Professeur.objects.create_user(
            username=f'prof.p8.col.{suffix}',
            email=f'prof.p8.col.{suffix}@test.local',
            password='Prof@Test1!',
            nom='Ndiaye',
            prenom='Ibra',
            telephone='770000020',
            numero_employe=f'P8C{suffix}',
            matiere_principale=cls.matiere_col,
            etablissement=cls.etab_col,
            niveau_enseignement='college',
            actif=True,
        )
        cls.classe_col = Classe.objects.create(
            nom='5eme B',
            niveau='college',
            code_classe=f'5B-{suffix}',
            capacite_max=30,
            etablissement=cls.etab_col,
            actif=True,
        )
        AffectationProfesseur.objects.create(
            professeur=cls.prof_col,
            classe=cls.classe_col,
            matiere=cls.matiere_col,
            annee_scolaire=cls.annee_col,
            statut='classique',
            actif=True,
        )

        mat_pri = Matiere.objects.create(
            nom='Français',
            code=f'FR-P8-{suffix}'[:10],
            etablissement=cls.etab_pri,
            actif=True,
        )
        cls.prof_pri = Professeur.objects.create_user(
            username=f'prof.p8.pri.{suffix}',
            email=f'prof.p8.pri.{suffix}@test.local',
            password='Prof@Test1!',
            nom='Fall',
            prenom='Aminata',
            telephone='770000021',
            numero_employe=f'P8P{suffix}',
            matiere_principale=mat_pri,
            etablissement=cls.etab_pri,
            niveau_enseignement='primaire',
            actif=True,
        )
        cls.classe_pri = Classe.objects.create(
            nom='CE2 B',
            code_classe=f'CE2-{suffix}',
            niveau='primaire',
            etablissement=cls.etab_pri,
            actif=True,
        )
        aff_p = AffectationProfesseurPrimaire.objects.create(
            professeur=cls.prof_pri,
            classe=cls.classe_pri,
            annee_scolaire=cls.annee_pri,
            actif=True,
        )
        aff_p.matieres.add(mat_pri)

    def _ctx_pri(self):
        return build_assistant_context(
            self.etab_pri,
            {'annee_scolaire_consultee_id': self.annee_pri.id},
            professeur=self.prof_pri,
            persona='enseignant_primaire',
        )

    def _ctx_col(self):
        return build_assistant_context(
            self.etab_col,
            {'annee_scolaire_consultee_id': self.annee_col.id},
            professeur=self.prof_col,
            persona='enseignant',
        )

    def _ctx_sup(self):
        return build_assistant_context(
            self.etab_sup,
            {'annee_scolaire_consultee_id': self.annee_sup.id},
            professeur=self.prof_col,
            persona='enseignant',
        )

    def test_primaire_sans_examens_ni_lmd(self):
        ctx = self._ctx_pri()
        names = _schema_names(get_enseignant_primaire_tools_schema(ctx))
        for tool in EXAM_TOOLS + LMD_TOOLS:
            self.assertNotIn(tool, names, msg=f'primaire ne doit pas avoir {tool}')
        for action in P7_ACTIONS:
            self.assertIn(action, names)

    def test_college_examens_sans_lmd(self):
        ctx = self._ctx_col()
        self.assertTrue(_examens_allowed(ctx))
        names = _schema_names(get_enseignant_secondaire_tools_schema(ctx))
        for tool in EXAM_TOOLS:
            self.assertIn(tool, names)
        for tool in LMD_TOOLS:
            self.assertNotIn(tool, names)

    def test_superieur_lmd_sans_examens(self):
        ctx = self._ctx_sup()
        self.assertTrue(ctx.est_superieur)
        self.assertFalse(_examens_allowed(ctx))
        names = _schema_names(get_enseignant_secondaire_tools_schema(ctx))
        for tool in LMD_TOOLS:
            self.assertIn(tool, names)
        for tool in EXAM_TOOLS:
            self.assertNotIn(tool, names)


class EnseignantRecetteP8ParcoursTests(TestCase):
    """Critères §11.2–§11.4 — lecture, repli oral, écriture pending."""

    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement_primaire()
        cls.annee = _make_annee(cls.etab)
        suffix = date.today().strftime('%H%M%S')
        cls.matiere = Matiere.objects.create(
            nom='Sciences',
            code=f'SCI-{suffix}',
            etablissement=cls.etab,
            actif=True,
        )
        cls.classe = Classe.objects.create(
            nom='CM1 Parcours',
            code_classe=f'CM1P-{suffix}',
            niveau='primaire',
            etablissement=cls.etab,
            actif=True,
        )
        cls.prof = Professeur.objects.create_user(
            username=f'prof.p8.par.{suffix}',
            email=f'p8.{suffix}@test.local',
            password='Prof@Test1!',
            nom='Ba',
            prenom='Omar',
            telephone='770000022',
            numero_employe=f'P8PAR{suffix}',
            matiere_principale=cls.matiere,
            etablissement=cls.etab,
            niveau_enseignement='primaire',
            actif=True,
        )
        aff = AffectationProfesseurPrimaire.objects.create(
            professeur=cls.prof,
            classe=cls.classe,
            annee_scolaire=cls.annee,
            actif=True,
        )
        aff.matieres.add(cls.matiere)

    def _ctx(self):
        return build_assistant_context(
            self.etab,
            {'annee_scolaire_consultee_id': self.annee.id},
            professeur=self.prof,
            persona='enseignant_primaire',
        )

    def test_lecture_classes_repli_oral_non_vide(self):
        ctx = self._ctx()
        result = execute_enseignant_primaire_tool(ctx, 'get_mes_classes', {})
        spoken = spoken_primaire('get_mes_classes', result)
        self.assertIn('CM1', spoken)
        self.assertGreater(len(spoken.strip()), 8)

    def test_chercher_en_base_trouve_classes(self):
        ctx = self._ctx()
        result = execute_enseignant_primaire_tool(
            ctx,
            'chercher_en_base',
            {'question': 'quelles sont mes classes'},
        )
        self.assertTrue(result.get('trouve'))
        self.assertIn('classes', result)

    def test_suggestions_apres_lecture_sans_caisse(self):
        ctx = self._ctx()
        chips = suggestions_after_read(
            [('get_mes_classes', {'classes': [{'nom': 'CM1 Parcours'}]})],
            {'classe': 'CM1 Parcours'},
            ctx=ctx,
        )
        self.assertGreaterEqual(len(chips), 2)
        blob = ' '.join(c['label'] for c in chips).lower()
        self.assertNotIn('impay', blob)

    def test_ecriture_note_en_attente_confirmation(self):
        from school_admin.services.assistant_enseignant_actions import (
            prepare_enregistrer_note,
        )

        ctx = self._ctx()
        draft = prepare_enregistrer_note(
            ctx,
            {'eleve': 'Ba', 'note': '15', 'classe': 'CM1'},
        )
        self.assertIn(
            draft.get('statut'),
            ('en_attente_confirmation', 'incomplet'),
        )
        if draft.get('statut') == 'en_attente_confirmation':
            self.assertEqual(draft.get('action'), 'enregistrer_note')

    def test_p7_justifier_incomplet_sans_eleve(self):
        from school_admin.services.assistant_enseignant_complements_actions import (
            prepare_justifier_absence,
        )

        ctx = self._ctx()
        out = prepare_justifier_absence(
            ctx,
            {'type_justificatif': 'certificat_medical'},
        )
        self.assertIn(out.get('statut'), ('incomplet', 'en_attente_confirmation'))


class EnseignantRecetteP8ConsumerRoutingTests(TestCase):
    """Persona WS cohérent avec le type d'établissement."""

    def test_resolve_persona_primary_vs_secondaire(self):
        from school_admin.services.assistant_prof_persona import (
            resolve_professeur_assistant_persona,
        )

        etab_pri = _make_etablissement_primaire()
        mat = Matiere.objects.create(
            nom='Lecture',
            code='LEC-P8',
            etablissement=etab_pri,
            actif=True,
        )
        prof_pri = Professeur.objects.create_user(
            username='prof.p8.ws.pri',
            email='prof.p8.ws.pri@test.local',
            password='Prof@Test1!',
            nom='X',
            prenom='Y',
            telephone='770000023',
            numero_employe='P8WSP',
            matiere_principale=mat,
            etablissement=etab_pri,
            niveau_enseignement='primaire',
            actif=True,
        )
        etab_col = _make_etablissement()
        mat2 = Matiere.objects.create(
            nom='Physique',
            code='PHY-P8',
            etablissement=etab_col,
            actif=True,
        )
        prof_col = Professeur.objects.create_user(
            username='prof.p8.ws.col',
            email='prof.p8.ws.col@test.local',
            password='Prof@Test1!',
            nom='Z',
            prenom='W',
            telephone='770000024',
            numero_employe='P8WSC',
            matiere_principale=mat2,
            etablissement=etab_col,
            niveau_enseignement='lycee',
            actif=True,
        )
        self.assertEqual(
            resolve_professeur_assistant_persona(prof_pri),
            'enseignant_primaire',
        )
        self.assertEqual(
            resolve_professeur_assistant_persona(prof_col),
            'enseignant',
        )

    def test_secondaire_spoken_effectifs_non_vide(self):
        etab = _make_etablissement()
        suffix = str(etab.pk)
        annee = _make_annee(etab)
        matiere = Matiere.objects.create(
            nom=f'Ang {suffix}',
            code=f'EN{suffix}'[:10],
            etablissement=etab,
            actif=True,
        )
        classe = Classe.objects.create(
            nom='4eme A',
            niveau='college',
            code_classe=f'4A-{suffix}',
            capacite_max=30,
            etablissement=etab,
            actif=True,
        )
        prof = Professeur.objects.create_user(
            username=f'prof.p8.sp.{suffix}',
            email=f'prof.p8.sp.{suffix}@test.local',
            password='Prof@Test1!',
            nom='Col',
            prenom='Leg',
            telephone='770000025',
            numero_employe=f'P8SP{suffix}',
            matiere_principale=matiere,
            etablissement=etab,
            niveau_enseignement='college',
            actif=True,
        )
        AffectationProfesseur.objects.create(
            professeur=prof,
            classe=classe,
            matiere=matiere,
            annee_scolaire=annee,
            statut='classique',
            actif=True,
        )
        ctx = build_assistant_context(
            etab,
            {'annee_scolaire_consultee_id': annee.id},
            professeur=prof,
            persona='enseignant',
        )
        result = execute_enseignant_secondaire_tool(
            ctx,
            'get_effectifs',
            {'classe': '4eme'},
        )
        spoken = spoken_secondaire('get_effectifs', result)
        self.assertGreater(len((spoken or result.get('message') or '').strip()), 3)
