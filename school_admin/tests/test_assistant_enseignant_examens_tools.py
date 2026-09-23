"""
Tests outils examens assistant enseignant (P6 — college / lycee).
"""
from datetime import date, time as datetime_time
from decimal import Decimal

from django.test import TestCase

from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.classe_model import Classe
from school_admin.model.creneau_examen_model import CreneauExamen
from school_admin.model.matiere_model import Matiere
from school_admin.model.note_examen_model import NoteExamen
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.professeur_model import Professeur
from school_admin.model.salle_model import Salle
from school_admin.model.session_examen_model import SessionExamen
from school_admin.services.assistant_enseignant_examens_actions import (
    prepare_enregistrer_note_examen,
)
from school_admin.services.assistant_enseignant_examens_tools import _examens_allowed
from school_admin.services.assistant_enseignant_secondaire_tools import (
    execute_enseignant_secondaire_tool,
    get_enseignant_secondaire_tools_schema,
)
from school_admin.services.assistant_tools import build_assistant_context
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
    _make_inscription,
)


class AssistantEnseignantExamensToolsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        suffix = str(cls.etab.pk)
        cls.classe = Classe.objects.create(
            nom='2nde C',
            niveau='lycee',
            code_classe=f'2ND-{suffix}',
            capacite_max=35,
            etablissement=cls.etab,
            actif=True,
        )
        cls.classe_hors = Classe.objects.create(
            nom='1ere D',
            niveau='lycee',
            code_classe=f'1D-{suffix}',
            capacite_max=35,
            etablissement=cls.etab,
            actif=True,
        )
        cls.periode = PeriodeScolaire.objects.create(
            etablissement=cls.etab,
            nom_periode='1er Trimestre',
            type_periode='trimestre',
            date_debut=date(2026, 9, 1),
            date_fin=date(2026, 12, 15),
            annee_scolaire=cls.annee.libelle,
            annee_scolaire_fk=cls.annee,
            est_active=True,
        )
        cls.matiere = Matiere.objects.create(
            nom=f'Physique {suffix}',
            code=f'PH{suffix}'[:10],
            etablissement=cls.etab,
            actif=True,
        )
        cls.prof = Professeur.objects.create_user(
            username=f'prof.exam.{suffix}',
            email=f'prof.exam.{suffix}@test.local',
            password='Prof@Test1!',
            nom='Ba',
            prenom='Moussa',
            telephone='770000003',
            numero_employe=f'EX{suffix}',
            matiere_principale=cls.matiere,
            etablissement=cls.etab,
            niveau_enseignement='lycee',
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
        cls.session = SessionExamen.objects.create(
            nom_examen='BAC blanc',
            etablissement=cls.etab,
            periode=cls.periode,
            date_debut=date(2026, 11, 1),
            date_fin=date(2026, 11, 5),
            annee_scolaire=cls.annee,
        )
        cls.session.classes.add(cls.classe)
        cls.session.matieres.add(cls.matiere)
        cls.salle = Salle.objects.create(
            nom='S1',
            numero=f'S{suffix}'[:8],
            etablissement=cls.etab,
            type_salle='classe',
            actif=True,
        )
        cls.creneau = CreneauExamen.objects.create(
            session_examen=cls.session,
            matiere=cls.matiere,
            date_examen=date(2026, 11, 2),
            heure_debut=datetime_time(8, 0),
            heure_fin=datetime_time(10, 0),
            surveillant=cls.prof,
            salle=cls.salle,
            annee_scolaire=cls.annee,
        )
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Kane', 'Lamine', 'M', suffix)
        _make_inscription(cls.eleve, cls.classe, cls.annee, cls.etab)
        NoteExamen.objects.create(
            eleve=cls.eleve,
            session_examen=cls.session,
            creneau_examen=cls.creneau,
            matiere=cls.matiere,
            professeur=cls.prof,
            classe=cls.classe,
            note=Decimal('12.00'),
            bareme=Decimal('20.00'),
            annee_scolaire=cls.annee,
        )

    def _ctx(self):
        return build_assistant_context(
            self.etab,
            {'annee_scolaire_consultee_id': self.annee.id},
            professeur=self.prof,
            persona='enseignant',
        )

    def test_examens_allowed_lycee_not_primaire(self):
        ctx = self._ctx()
        self.assertTrue(_examens_allowed(ctx))
        self.assertFalse(ctx.est_superieur)

    def test_schema_examens_secondaire_only(self):
        ctx = self._ctx()
        names = {
            item['function']['name']
            for item in get_enseignant_secondaire_tools_schema(ctx)
            if item.get('function')
        }
        for tool in (
            'get_examens_prof',
            'get_notes_examen',
            'ouvrir_noter_examen',
            'enregistrer_note_examen',
        ):
            self.assertIn(tool, names)

        class _Sup:
            est_superieur = True
            est_primaire = False
            persona = 'enseignant'

        names_sup = {
            item['function']['name']
            for item in get_enseignant_secondaire_tools_schema(_Sup())
            if item.get('function')
        }
        self.assertNotIn('get_examens_prof', names_sup)

    def test_get_examens_prof(self):
        ctx = self._ctx()
        result = execute_enseignant_secondaire_tool(ctx, 'get_examens_prof', {})
        self.assertGreaterEqual(result.get('nb', 0), 1)
        self.assertTrue(any('BAC' in (s.get('nom') or '') for s in result.get('sessions', [])))

    def test_get_notes_examen(self):
        ctx = self._ctx()
        result = execute_enseignant_secondaire_tool(
            ctx,
            'get_notes_examen',
            {'classe': '2nde', 'session': 'BAC'},
        )
        self.assertGreaterEqual(result.get('nb', 0), 1)
        self.assertEqual(result['notes'][0]['eleve'], self.eleve.nom_complet)

    def test_hors_affectation_refusee(self):
        ctx = self._ctx()
        result = execute_enseignant_secondaire_tool(
            ctx,
            'get_notes_examen',
            {'classe': '1ere D'},
        )
        self.assertIn('erreur', result)

    def test_prepare_enregistrer_note_examen(self):
        ctx = self._ctx()
        draft = prepare_enregistrer_note_examen(
            ctx,
            {
                'classe': '2nde',
                'session': 'BAC blanc',
                'eleve': 'Kane',
                'matiere': 'Physique',
                'note': '15',
            },
        )
        self.assertEqual(draft.get('statut'), 'en_attente_confirmation')
        self.assertIn('KANE', draft.get('resume', '').upper())
