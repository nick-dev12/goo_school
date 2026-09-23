"""
Tests outils LMD assistant enseignant supérieur (P5).
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.matiere_model import Matiere
from school_admin.model.module_model import Module, ModuleClasse
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.professeur_model import Professeur
from school_admin.services.assistant_enseignant_scope import ensure_classe_access
from school_admin.services.assistant_enseignant_secondaire_tools import (
    execute_enseignant_secondaire_tool,
    get_enseignant_secondaire_tools_schema,
)
from school_admin.services.assistant_tools import build_assistant_context
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_inscription,
)


def _make_etablissement_superieur():
    suffix = date.today().strftime('%Y%m%d%H%M%S')
    email = f'univ.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'Université Test {suffix}',
        code_etablissement=f'SUP-A{suffix[-6:]}',
        adresse='1 rue Test',
        pays='Sénégal',
        ville='Dakar',
        type_etablissement='superieur',
        directeur_prenom='A',
        directeur_nom='B',
        directeur_email=f'dir.{suffix}@test.local',
        actif=True,
    )
    etab.set_password('Test1234!')
    etab.save()
    return etab


class AssistantEnseignantSuperieurToolsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from school_admin.model.academic_structure_model import Department

        cls.etab = _make_etablissement_superieur()
        cls.annee = _make_annee(cls.etab)
        cls.dept = Department.objects.create(
            nom='Informatique',
            sigle='INFO',
            etablissement=cls.etab,
        )
        suffix = date.today().strftime('%H%M%S')
        cls.classe = Classe.objects.create(
            nom='L1 Promo A',
            code_classe=f'L1-{suffix}',
            niveau='superieur',
            niveau_lmd='L1',
            etablissement=cls.etab,
            department=cls.dept,
            actif=True,
        )
        cls.classe_hors = Classe.objects.create(
            nom='L2 Promo Z',
            code_classe=f'L2-{suffix}',
            niveau='superieur',
            niveau_lmd='L2',
            etablissement=cls.etab,
            department=cls.dept,
            actif=True,
        )
        cls.periode = PeriodeScolaire.objects.create(
            etablissement=cls.etab,
            nom_periode='Semestre 1',
            type_periode='semestre',
            niveau_lmd='L1',
            date_debut=date(2026, 9, 1),
            date_fin=date(2027, 1, 31),
            annee_scolaire=cls.annee.libelle,
            annee_scolaire_fk=cls.annee,
            est_active=True,
        )
        cls.matiere = Matiere.objects.create(
            nom='Algorithmique',
            code=f'ALG-{suffix[-5:]}',
            etablissement=cls.etab,
            actif=True,
        )
        cls.prof = Professeur.objects.create_user(
            username=f'prof.sup.{suffix}',
            email=f'prof.sup.{suffix}@test.local',
            password='Prof@Test1!',
            nom='Fall',
            prenom='Ibra',
            telephone='770000002',
            numero_employe=f'EMP{suffix}',
            matiere_principale=cls.matiere,
            etablissement=cls.etab,
            niveau_enseignement='superieur',
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
        cls.module = Module.objects.create(
            nom='Algo L1',
            code=f'MOD{suffix[-4:]}',
            etablissement=cls.etab,
            department=cls.dept,
            niveau_lmd='L1',
        )
        ModuleClasse.objects.create(
            module=cls.module,
            classe=cls.classe,
            credits=Decimal('6.00'),
            numero_ue='UE1.1',
            periode=cls.periode,
        )
        cls.etudiant = _make_eleve_simple(
            cls.etab, cls.classe, 'Sow', 'Mame', 'F', suffix,
        )
        _make_inscription(cls.etudiant, cls.classe, cls.annee, cls.etab)

    def _ctx(self):
        return build_assistant_context(
            self.etab,
            {'annee_scolaire_consultee_id': self.annee.id},
            professeur=self.prof,
            persona='enseignant',
        )

    def test_schema_lmd_only_when_superieur(self):
        ctx_sup = self._ctx()

        class _CollegeCtx:
            est_superieur = False
            persona = 'enseignant'

        ctx_college = _CollegeCtx()
        names_sup = {
            item['function']['name']
            for item in get_enseignant_secondaire_tools_schema(ctx_sup)
            if item.get('function')
        }
        names_col = {
            item['function']['name']
            for item in get_enseignant_secondaire_tools_schema(ctx_college)
            if item.get('function')
        }
        self.assertIn('get_modules_classe', names_sup)
        self.assertIn('get_credits_etudiant', names_sup)
        self.assertNotIn('get_modules_classe', names_col)
        self.assertNotIn('get_credits_etudiant', names_col)

    def test_get_modules_classe_scoped(self):
        ctx = self._ctx()
        result = execute_enseignant_secondaire_tool(
            ctx,
            'get_modules_classe',
            {'classe': 'L1'},
        )
        self.assertIn('modules', result)
        self.assertEqual(result['nb'], 1)
        self.assertEqual(result['modules'][0]['module'], 'Algo L1')

    def test_get_modules_refuse_hors_affectation(self):
        ctx = self._ctx()
        err = ensure_classe_access(ctx, self.classe_hors)
        self.assertIn('erreur', err)
        result = execute_enseignant_secondaire_tool(
            ctx,
            'get_modules_classe',
            {'classe': 'L2'},
        )
        self.assertIn('erreur', result)

    def test_get_credits_etudiant(self):
        ctx = self._ctx()
        result = execute_enseignant_secondaire_tool(
            ctx,
            'get_credits_etudiant',
            {'query': 'Sow'},
        )
        self.assertEqual(result.get('etudiant'), self.etudiant.nom_complet)
        self.assertIn('credits_inscrits', result)
        self.assertFalse(result.get('invente'))

    def test_creer_evaluation_resolve_semestre_lmd(self):
        from school_admin.services.assistant_enseignant_secondaire_actions import (
            prepare_creer_evaluation,
        )

        ctx = self._ctx()
        draft = prepare_creer_evaluation(
            ctx,
            {
                'classe': 'L1',
                'titre': 'Contrôle continu',
                'matiere': 'Algorithmique',
                'date_evaluation': '2026-10-15',
                'periode': 'Semestre 1',
                'niveau_lmd': 'L1',
            },
        )
        self.assertEqual(draft.get('statut'), 'en_attente_confirmation')
        self.assertIn('Contrôle continu', draft.get('resume', ''))
