"""
Tests outils assistant vocal enseignant primaire.
"""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.matiere_model import Matiere
from school_admin.model.professeur_model import Professeur
from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
from school_admin.services.assistant_enseignant_scope import (
    classe_ids_for_prof,
    ensure_classe_access,
    find_classe_prof,
)
from school_admin.services.assistant_enseignant_primaire_tools import (
    ENSEIGNANT_PRIMAIRE_TOOL_HANDLERS,
    execute_enseignant_primaire_tool,
)
from school_admin.services.assistant_pages_enseignant_primaire import find_page, list_pages
from school_admin.services.assistant_tools import build_assistant_context


def _make_etablissement_primaire():
    suffix = date.today().strftime('%Y%m%d%H%M%S')
    email = f'ecole.primaire.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'École Primaire Test {suffix}',
        code_etablissement=f'PRI-A{suffix[-6:]}',
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


class AssistantEnseignantPrimaireToolsTests(TestCase):
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
            nom='Mathématiques',
            code=f'MAT-{suffix[-6:]}',
            etablissement=cls.etab,
            actif=True,
        )
        cls.classe = Classe.objects.create(
            nom='CM1 - A',
            code_classe=f'CM1-{suffix[-5:]}',
            niveau='primaire',
            etablissement=cls.etab,
            actif=True,
        )
        cls.classe_hors = Classe.objects.create(
            nom='CM2 - Z',
            code_classe=f'CM2-{suffix[-5:]}',
            niveau='primaire',
            etablissement=cls.etab,
            actif=True,
        )
        cls.prof = Professeur.objects.create_user(
            username=f'prof.primaire.{date.today().strftime("%H%M%S")}',
            email=f'prof.{date.today().strftime("%H%M%S")}@test.local',
            password='Prof@Test1!',
            nom='Diop',
            prenom='Fatou',
            telephone='770000000',
            numero_employe=f'EMP{date.today().strftime("%H%M%S")}',
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

    def test_classe_ids_scoped(self):
        ctx = self._ctx()
        ids = classe_ids_for_prof(ctx)
        self.assertIn(self.classe.id, ids)
        self.assertNotIn(self.classe_hors.id, ids)

    def test_ensure_classe_access_refuse_hors_affectation(self):
        ctx = self._ctx()
        err = ensure_classe_access(ctx, self.classe_hors)
        self.assertIn('erreur', err)

    def test_get_mes_classes(self):
        ctx = self._ctx()
        result = execute_enseignant_primaire_tool(ctx, 'get_mes_classes', {})
        self.assertIn('classes', result)
        self.assertEqual(len(result['classes']), 1)

    def test_find_classe_prof(self):
        ctx = self._ctx()
        found = find_classe_prof(ctx, 'CM1')
        self.assertIsNotNone(found)
        self.assertEqual(found.id, self.classe.id)

    def test_lister_pages_enseignant(self):
        pages = list_pages()
        keys = {p['key'] for p in pages}
        self.assertIn('dashboard', keys)
        self.assertIn('presence', keys)
        dash = find_page('dashboard')
        self.assertIsNotNone(dash)
        self.assertEqual(dash['url'], reverse('enseignant_primaire:dashboard'))

    def test_tool_handlers_registered(self):
        self.assertIn('get_mes_classes', ENSEIGNANT_PRIMAIRE_TOOL_HANDLERS)
        self.assertIn('proposer_actions', ENSEIGNANT_PRIMAIRE_TOOL_HANDLERS)
        from school_admin.services.assistant_enseignant_actions import ENSEIGNANT_ACTION_SPECS

        self.assertIn('enregistrer_note', ENSEIGNANT_ACTION_SPECS)

    def test_persona_ws_primary_etablissement(self):
        from school_admin.services.assistant_prof_persona import (
            resolve_professeur_assistant_persona,
        )

        self.assertEqual(
            resolve_professeur_assistant_persona(self.prof),
            'enseignant_primaire',
        )

    def test_spoken_liste_classes(self):
        from school_admin.services.assistant_enseignant_primaire_tools import (
            spoken_from_enseignant_tool,
        )

        ctx = self._ctx()
        result = execute_enseignant_primaire_tool(ctx, 'get_mes_classes', {})
        spoken = spoken_from_enseignant_tool('get_mes_classes', result)
        self.assertIn('CM1', spoken)

    def test_suggestions_enseignant_apres_classe(self):
        from school_admin.services.assistant_tools import suggestions_after_read

        ctx = self._ctx()
        chips = suggestions_after_read(
            [('ouvrir_classe', {'nom': 'CM1 - A', 'classe': 'CM1 - A'})],
            {'classe': 'CM1 - A'},
            ctx=ctx,
        )
        self.assertGreaterEqual(len(chips), 2)
        labels = ' '.join(c['label'] for c in chips).lower()
        self.assertNotIn('impay', labels)

    def test_proposer_actions_schema(self):
        from school_admin.services.assistant_enseignant_primaire_tools import (
            get_enseignant_primaire_tools_schema,
        )

        names = {
            item['function']['name']
            for item in get_enseignant_primaire_tools_schema()
            if item.get('function')
        }
        self.assertIn('proposer_actions', names)

    def test_cette_classe_working_refs(self):
        from school_admin.services.gemini_assistant_service import apply_working_refs

        refs = {'classe': 'CM1 - A'}
        args = apply_working_refs(
            'get_effectifs',
            {'classe': 'cette classe'},
            refs,
        )
        self.assertEqual(args['classe'], 'CM1 - A')
