"""Vague 5 — recette automatisée UI prof (hubs, présence binaire)."""
from django.test import SimpleTestCase

from school_admin.services.presence_sync_service import (
    PresenceSyncError,
    _statuts_par_eleve,
)
from school_admin.utils.professeur_ui_tabs import (
    attach_primaire_classe_tab_context,
    enseignant_est_hub_v3_collège_lycée,
    enseignant_est_hub_v4_lmd,
    enrich_eleve_presence_row,
    statut_saisie_presence,
)


class _FakeEtab:
    def __init__(self, type_etablissement):
        self.type_etablissement = type_etablissement


class _FakeProf:
    def __init__(self, type_etablissement):
        self.etablissement = _FakeEtab(type_etablissement)


class _FakeClasse:
    def __init__(self, pk, nom='Classe A'):
        self.id = pk
        self.nom = nom
        self.nombre_eleves = 10


class ProfHubFlagsV5Tests(SimpleTestCase):
    def test_v3_college_not_primary_not_superieur(self):
        for te in ('lycée', 'collège', 'mixte', 'lycee_college'):
            self.assertTrue(
                enseignant_est_hub_v3_collège_lycée(_FakeProf(te)),
                te,
            )

    def test_v3_excludes_primary_and_superieur(self):
        self.assertFalse(enseignant_est_hub_v3_collège_lycée(_FakeProf('primary')))
        self.assertFalse(enseignant_est_hub_v3_collège_lycée(_FakeProf('superieur')))

    def test_v4_lmd_only(self):
        self.assertTrue(enseignant_est_hub_v4_lmd(_FakeProf('superieur')))
        self.assertFalse(enseignant_est_hub_v4_lmd(_FakeProf('lycée')))

    def test_v3_v4_mutually_exclusive_by_etab_type(self):
        for te in ('primary', 'lycée', 'collège', 'mixte', 'superieur'):
            prof = _FakeProf(te)
            v3 = enseignant_est_hub_v3_collège_lycée(prof)
            v4 = enseignant_est_hub_v4_lmd(prof)
            self.assertFalse(v3 and v4, te)


class ProfClasseTabPersistV5Tests(SimpleTestCase):
    def test_attach_classe_from_query(self):
        from django.http import HttpRequest

        req = HttpRequest()
        req.GET = {'classe': '42'}
        ctx = {}
        flat = [{'classe': _FakeClasse(42)}, {'classe': _FakeClasse(99, 'B')}]
        attach_primaire_classe_tab_context(req, ctx, flat)
        self.assertEqual(ctx['initial_classe_id'], '42')

    def test_pick_first_when_missing(self):
        from django.http import HttpRequest

        req = HttpRequest()
        req.GET = {}
        ctx = {}
        flat = [{'classe': _FakeClasse(7)}]
        attach_primaire_classe_tab_context(req, ctx, flat, pick_first_if_missing=True)
        self.assertEqual(ctx['initial_classe_id'], '7')


class PresenceBinaryV5Tests(SimpleTestCase):
    def test_saisie_present_absent_only(self):
        class P:
            statut = 'present'

        self.assertEqual(statut_saisie_presence(P()), 'present')
        P.statut = 'retard'
        self.assertEqual(statut_saisie_presence(P()), '')
        P.statut = 'absent_justifie'
        self.assertEqual(statut_saisie_presence(P()), 'absent')

    def test_enrich_legacy_hint(self):
        class P:
            statut = 'retard'

        row = enrich_eleve_presence_row(P())
        self.assertEqual(row['statut_saisie'], '')
        self.assertIn('historique', row['statut_legacy'].lower())

    def test_post_rejects_retard(self):
        with self.assertRaises(PresenceSyncError) as ctx:
            _statuts_par_eleve([{'eleve_id': 1, 'statut': 'retard'}])
        self.assertEqual(ctx.exception.code, 'invalid_statut')

    def test_post_accepts_binary(self):
        m = _statuts_par_eleve(
            [
                {'eleve_id': 1, 'statut': 'present'},
                {'eleve_id': 2, 'statut': 'absent'},
            ]
        )
        self.assertEqual(m, {1: 'present', 2: 'absent'})


class ProfPrintTemplatesV5Tests(SimpleTestCase):
    """Smoke : partials V5 présents (pas de rendu HTTP)."""

    def test_imprimer_partial_exists(self):
        from django.template.loader import get_template

        get_template('school_admin/enseignant/partials/prof_imprimer_print_assets.html')

    def test_lmd_periodes_partial_exists(self):
        from django.template.loader import get_template

        get_template('school_admin/enseignant/partials/prof_hub_lmd_periodes_tabs.html')

    def test_primaire_ui_assets_includes_matiere_tab_styles(self):
        from django.template.loader import render_to_string

        html = render_to_string(
            'school_admin/enseignant/primaire/partials/prof_primaire_ui_assets.html',
        )
        self.assertIn('prof_matiere_tabs_bar.css', html)
        self.assertIn('tabs_nav_overflow.css', html)
