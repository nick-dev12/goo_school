"""
Tests outils assistant vocal enseignant secondaire / collège-lycée.
"""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.matiere_model import Matiere
from school_admin.model.professeur_model import Professeur
from school_admin.services.assistant_enseignant_scope import (
    classe_ids_for_prof,
    ensure_classe_access,
    find_classe_prof,
)
from school_admin.services.assistant_enseignant_secondaire_tools import (
    ENSEIGNANT_SECONDAIRE_TOOL_HANDLERS,
    execute_enseignant_secondaire_tool,
)
from school_admin.services.assistant_pages_enseignant import find_page, list_pages
from school_admin.services.assistant_tools import build_assistant_context


def _make_etablissement_college():
    suffix = date.today().strftime('%Y%m%d%H%M%S')
    email = f'ecole.college.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'Collège Test {suffix}',
        code_etablissement=f'COL-A{suffix[-6:]}',
        adresse='1 rue Test',
        pays='Sénégal',
        ville='Dakar',
        type_etablissement='collège',
        directeur_prenom='A',
        directeur_nom='B',
        directeur_email=f'dir.{suffix}@test.local',
        actif=True,
    )
    etab.set_password('Test1234!')
    etab.save()
    return etab


class AssistantEnseignantSecondaireToolsTests(TestCase):
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
            nom='Mathématiques',
            code=f'MAT-{suffix[-6:]}',
            etablissement=cls.etab,
            actif=True,
        )
        cls.classe = Classe.objects.create(
            nom='6ème - A',
            code_classe=f'6A-{suffix[-5:]}',
            niveau='college',
            etablissement=cls.etab,
            actif=True,
        )
        cls.classe_hors = Classe.objects.create(
            nom='5ème - Z',
            code_classe=f'5Z-{suffix[-5:]}',
            niveau='college',
            etablissement=cls.etab,
            actif=True,
        )
        cls.prof = Professeur.objects.create_user(
            username=f'prof.college.{date.today().strftime("%H%M%S")}',
            email=f'prof.col.{date.today().strftime("%H%M%S")}@test.local',
            password='Prof@Test1!',
            nom='Ndiaye',
            prenom='Amadou',
            telephone='770000001',
            numero_employe=f'EMP{date.today().strftime("%H%M%S")}',
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

    def _ctx(self):
        return build_assistant_context(
            self.etab,
            {'annee_scolaire_consultee_id': self.annee.id},
            professeur=self.prof,
            persona='enseignant',
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
        result = execute_enseignant_secondaire_tool(ctx, 'get_mes_classes', {})
        self.assertIn('classes', result)
        self.assertEqual(len(result['classes']), 1)

    def test_find_classe_prof(self):
        ctx = self._ctx()
        found = find_classe_prof(ctx, '6ème')
        self.assertIsNotNone(found)
        self.assertEqual(found.id, self.classe.id)

    def test_lister_pages_enseignant(self):
        pages = list_pages()
        keys = {p['key'] for p in pages}
        self.assertIn('dashboard', keys)
        self.assertIn('presence', keys)
        dash = find_page('dashboard')
        self.assertIsNotNone(dash)
        self.assertEqual(dash['url'], reverse('enseignant:dashboard_enseignant'))

    def test_tool_handlers_registered(self):
        self.assertIn('get_mes_classes', ENSEIGNANT_SECONDAIRE_TOOL_HANDLERS)
        self.assertIn('proposer_actions', ENSEIGNANT_SECONDAIRE_TOOL_HANDLERS)
        from school_admin.services.assistant_enseignant_secondaire_actions import (
            ENSEIGNANT_SECONDAIRE_ACTION_SPECS,
        )

        self.assertIn('enregistrer_note', ENSEIGNANT_SECONDAIRE_ACTION_SPECS)

    def test_persona_ws_non_primary_etablissement(self):
        from school_admin.services.assistant_prof_persona import (
            resolve_professeur_assistant_persona,
        )

        self.assertEqual(
            resolve_professeur_assistant_persona(self.prof),
            'enseignant',
        )

    def test_spoken_liste_classes(self):
        from school_admin.services.assistant_enseignant_secondaire_tools import (
            spoken_from_enseignant_tool,
        )

        ctx = self._ctx()
        result = execute_enseignant_secondaire_tool(ctx, 'get_mes_classes', {})
        spoken = spoken_from_enseignant_tool('get_mes_classes', result)
        self.assertIn('6ème', spoken)

    def test_proposer_actions_schema(self):
        from school_admin.services.assistant_enseignant_secondaire_tools import (
            get_enseignant_secondaire_tools_schema,
        )

        ctx = self._ctx()
        names = {
            item['function']['name']
            for item in get_enseignant_secondaire_tools_schema(ctx)
            if item.get('function')
        }
        self.assertIn('proposer_actions', names)
        self.assertNotIn('get_modules_classe', names)
        self.assertNotIn('get_credits_etudiant', names)
