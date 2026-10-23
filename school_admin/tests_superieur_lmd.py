"""Supérieur (LMD) — étape 1 de l'audit : relevé cohérent avec le moteur, codes matière,
affectations CM/TD/TP, conflits de salle et cours mutualisés."""
from datetime import date, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from school_admin.model.academic_structure_model import Department
from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.classe_model import Classe
from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps, EmploiDuTemps
from school_admin.model.matiere_model import Matiere
from school_admin.model.module_model import Module, ModuleClasse
from school_admin.model.moyenne_periode_model import MoyennePeriode
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.professeur_model import Professeur
from school_admin.model.salle_model import Salle
from school_admin.personal_views.directeur_view import _group_matieres_par_ue_superieur, _totaux_credits_superieur
from school_admin.services import examens as mx
from school_admin.services.emploi_conflits import conflit_ressources
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement_type,
    _make_inscription,
)

D = Decimal


def ligne(module_id, nom, moyenne, credits, coef=1, module_nom='UE'):
    return {'module_id': module_id, 'module_nom': f'{module_nom}{module_id}', 'module_code': '', 'module_ordre': module_id,
            'module_numero_ue': f'UE{module_id}', 'nom': nom, 'moyenne_eleve': moyenne, 'coefficient': coef,
            'credits': credits, 'moyenne_avec_coefficient': None if moyenne is None else moyenne * coef}


class BaseSup(TestCase):
    def setUp(self):
        self.etab = _make_etablissement_type('superieur', 'lmd')
        self.annee = _make_annee(self.etab)
        s = str(self.etab.pk)
        self.dept = Department.objects.create(nom='Droit', sigle='DRT', etablissement=self.etab)
        self.classe = Classe.objects.create(nom='DRT L1 A', niveau='superieur', niveau_lmd='L1', code_classe=f'L1A-{s}',
                                            capacite_max=60, etablissement=self.etab, department=self.dept)
        self.classe2 = Classe.objects.create(nom='GES L1 A', niveau='superieur', niveau_lmd='L1', code_classe=f'G1A-{s}',
                                             capacite_max=60, etablissement=self.etab)
        self.periode = PeriodeScolaire.objects.create(
            etablissement=self.etab, nom_periode='Semestre 1', type_periode='semestre', niveau_lmd='L1',
            date_debut=date(2026, 9, 1), date_fin=date(2027, 1, 31), annee_scolaire=self.annee.libelle,
            annee_scolaire_fk=self.annee, est_active=True)
        self.regle = mx.regles(self.etab)


class ReleveCoherentTests(BaseSup):
    def test_compensation_affichee_comme_le_moteur(self):
        # UE1 = 8/20 (6 cr), UE2 = 13/20 (6 cr) -> semestre 10,5 : UE1 compensée, 12/12 crédits.
        rows = [ligne(1, 'Droit civil', 8.0, 6.0), ligne(2, 'Économie', 13.0, 6.0)]
        blocs = _group_matieres_par_ue_superieur(rows, self.regle)
        self.assertEqual([b['statut_ue'] for b in blocs], ['Compensée', 'Validée'])
        self.assertEqual([b['credits_obtenus'] for b in blocs], [6.0, 6.0])
        att, obt = _totaux_credits_superieur(rows, self.regle)
        self.assertEqual((att, obt), (12.0, 12.0))
        self.assertEqual(mx.validation_lmd_bulletin(rows, self.regle)['decision'], 'Admis par compensation')

    def test_ue_moyenne_des_ec_et_non_ec_par_ec(self):
        # Ancien calcul : EC à 8 non crédité. LMD : UE = (8 + 14) / 2 = 11 -> les 6 crédits de l'UE sont acquis.
        rows = [ligne(1, 'EC a', 8.0, 3.0), ligne(1, 'EC b', 14.0, 3.0)]
        self.assertEqual(_totaux_credits_superieur(rows, self.regle), (6.0, 6.0))

    def test_sans_compensation_et_note_eliminatoire(self):
        rows = [ligne(1, 'A', 8.0, 6.0), ligne(2, 'B', 13.0, 6.0)]
        self.regle.compensation_semestrielle = False
        blocs = _group_matieres_par_ue_superieur(rows, self.regle)
        self.assertEqual(blocs[0]['statut_ue'], 'Non validée')
        self.assertEqual(_totaux_credits_superieur(rows, self.regle)[1], 6.0)
        self.regle.compensation_semestrielle = True
        self.regle.note_eliminatoire = D('9')
        self.assertEqual(_group_matieres_par_ue_superieur(rows, self.regle)[0]['statut_ue'], 'Note éliminatoire')

    def test_page_bulletin_plus_de_sept_ue_et_decision_du_jury(self):
        eleve = _make_eleve_simple(self.etab, self.classe, 'Ndoye', 'Awa', 'F', f'b{self.etab.pk}')
        _make_inscription(eleve, self.classe, self.annee, self.etab)
        total = D('0')
        for i in range(9):  # 9 UE : l'ancien gabarit n'en affichait que 7
            mod = Module.objects.create(nom=f'Unité {i + 1}', code=f'U{i}-{self.etab.pk}', etablissement=self.etab,
                                        department=self.dept, niveau_lmd='L1', ordre=i)
            ModuleClasse.objects.create(module=mod, classe=self.classe, credits=D('3'), numero_ue=f'UE1.{i + 1}',
                                        periode=self.periode)
            m = Matiere.objects.create(nom=f'EC {i + 1}', etablissement=self.etab, department=self.dept, module=mod,
                                       niveau='superieur', niveau_lmd_key='L1', coefficient=1, credits=D('3'))
            m.classes.add(self.classe)
            note = D('8') if i == 0 else D('12')
            MoyennePeriode.objects.create(eleve=eleve, etablissement=self.etab, periode=self.periode, matiere=m,
                                          annee_scolaire=self.annee, est_moyenne_generale=False, moyenne_matiere=note,
                                          coefficient=1, credits=D('3'), moyenne_avec_coefficient=note)
            total += 3
        MoyennePeriode.objects.create(eleve=eleve, etablissement=self.etab, periode=self.periode,
                                      annee_scolaire=self.annee, est_moyenne_generale=True,
                                      moyenne_generale=D('11.56'), decision_conseil='Admis')
        self.client.force_login(self.etab)
        r = self.client.get(reverse('directeur:voir_bulletin_eleve', args=[self.classe.id, eleve.id])
                            + f'?periode={self.periode.id}')
        self.assertEqual(r.status_code, 200)
        ctx = r.context
        self.assertEqual(len(ctx['bulletin_ue_blocs']), 9)
        self.assertEqual(len(ctx['recap_ue_slots']), 9)
        self.assertEqual(ctx['total_credits_obtenus'], 27.0)  # UE 1 compensée
        self.assertIn('Admis par compensation', ctx['complement_info']['decision_conseil'])
        self.assertContains(r, 'Décision du jury')
        self.assertContains(r, 'Compensée')
        self.assertNotContains(r, 'Redouble')


class CodeMatiereTests(BaseSup):
    def test_meme_code_dans_deux_etablissements(self):
        autre = _make_etablissement_type('superieur', 'xyz')
        Matiere.objects.create(nom='Mathématiques', code='MAT101', etablissement=self.etab)
        Matiere.objects.create(nom='Mathématiques', code='MAT101', etablissement=autre)  # plus d'erreur
        a = Matiere.objects.create(nom='Marketing', etablissement=self.etab)
        b = Matiere.objects.create(nom='Marketing digital', etablissement=self.etab)
        self.assertEqual((a.code, b.code), ('MAR', 'MAR1'))


class AffectationRolesTests(BaseSup):
    def setUp(self):
        super().setUp()
        s = str(self.etab.pk)
        self.ec = Matiere.objects.create(nom='Droit constitutionnel', etablissement=self.etab, department=self.dept,
                                         niveau='superieur')
        self.profs = []
        for i in range(4):
            p = Professeur.objects.create_user(
                username=f'p{i}.{s}', email=f'p{i}.{s}@t.local', password='Prof@Test1!', nom=f'Prof{i}', prenom='X',
                telephone=f'77000{i:04d}', numero_employe=f'L{i}{s}', matiere_principale=self.ec,
                etablissement=self.etab, niveau_enseignement='superieur', actif=True)
            self.profs.append(p)

    def aff(self, prof, role, groupe=''):
        return AffectationProfesseur.objects.create(professeur=prof, classe=self.classe, matiere=self.ec,
                                                    annee_scolaire=self.annee, role_enseignement=role, groupe=groupe)

    def test_cm_et_groupes_de_td(self):
        self.aff(self.profs[0], 'cm')
        self.aff(self.profs[1], 'td', 'g1')
        self.aff(self.profs[2], 'td', 'G2')
        self.aff(self.profs[0], 'td', 'G3')  # le même enseignant peut aussi avoir un groupe de TD
        self.assertEqual(AffectationProfesseur.objects.filter(classe=self.classe).count(), 4)
        with self.assertRaises(ValidationError):
            self.aff(self.profs[3], 'td', 'G1')
        with self.assertRaises(ValidationError):
            self.aff(self.profs[3], 'complet')

    def test_ec_complet_bloque_les_roles(self):
        self.aff(self.profs[0], 'complet')
        with self.assertRaises(ValidationError):
            self.aff(self.profs[1], 'tp', 'G1')

    def test_secondaire_inchange(self):
        lycee = _make_etablissement_type('lycée', 'lyc')
        c = Classe.objects.create(nom='2nde A', niveau='lycee', code_classe=f'2A-{lycee.pk}', capacite_max=40,
                                  etablissement=lycee)
        m = Matiere.objects.create(nom='Physique', etablissement=lycee)
        ps = [Professeur.objects.create_user(
            username=f's{i}.{lycee.pk}', email=f's{i}.{lycee.pk}@t.local', password='Prof@Test1!', nom='S', prenom='Y',
            telephone=f'78000{i:04d}', numero_employe=f'S{i}{lycee.pk}', matiere_principale=m, etablissement=lycee,
            niveau_enseignement='lycee', actif=True) for i in range(2)]
        AffectationProfesseur.objects.create(professeur=ps[0], classe=c, matiere=m, role_enseignement='td', groupe='G1')
        self.assertEqual(AffectationProfesseur.objects.get(classe=c).role_enseignement, 'complet')
        with self.assertRaises(ValidationError):
            AffectationProfesseur.objects.create(professeur=ps[1], classe=c, matiere=m, role_enseignement='td',
                                                 groupe='G2')

    def test_formulaire_affectation(self):
        self.client.force_login(self.etab)
        self.ec.classes.add(self.classe)
        url = reverse('affectation:affecter_professeur')
        self.client.post(url, {'professeur_id': self.profs[0].id, 'classe_id': self.classe.id, 'matiere_id': self.ec.id,
                               'action': 'add', 'statut': 'classique', 'role_enseignement': 'cm'})
        self.client.post(url, {'professeur_id': self.profs[1].id, 'classe_id': self.classe.id, 'matiere_id': self.ec.id,
                               'action': 'add', 'statut': 'classique', 'role_enseignement': 'td', 'groupe': 'g1'})
        roles = set(AffectationProfesseur.objects.filter(classe=self.classe, actif=True)
                    .values_list('role_enseignement', 'groupe'))
        self.assertEqual(roles, {('cm', ''), ('td', 'G1')})
        r = self.client.get(reverse('affectation:affectation_professeurs'))
        self.assertContains(r, 'Rôle dans la matière')


class EmploiDuTempsConflitsTests(BaseSup):
    def setUp(self):
        super().setUp()
        s = str(self.etab.pk)
        self.m = Matiere.objects.create(nom='Introduction au droit', etablissement=self.etab)
        self.autre_m = Matiere.objects.create(nom='Comptabilité', etablissement=self.etab)
        self.prof = Professeur.objects.create_user(
            username=f'e.{s}', email=f'e.{s}@t.local', password='Prof@Test1!', nom='Diop', prenom='A',
            telephone='770009999', numero_employe=f'E{s}', matiere_principale=self.m, etablissement=self.etab,
            niveau_enseignement='superieur', actif=True)
        self.amphi = Salle.objects.create(nom='Amphi A', numero='A', etablissement=self.etab, capacite_max=300)
        self.edt1 = EmploiDuTemps.objects.create(classe=self.classe, annee_scolaire=self.annee.libelle,
                                                 annee_scolaire_fk=self.annee, est_actif=True)
        self.edt2 = EmploiDuTemps.objects.create(classe=self.classe2, annee_scolaire=self.annee.libelle,
                                                 annee_scolaire_fk=self.annee, est_actif=True)
        CreneauEmploiDuTemps.objects.create(emploi_du_temps=self.edt1, jour='lundi', heure_debut=time(8),
                                            heure_fin=time(10), matiere=self.m, professeur=self.prof, salle=self.amphi)

    def conflit(self, **kw):
        base = dict(etablissement=self.etab, annee_scolaire=self.annee, emploi_du_temps=self.edt2, jour='lundi',
                    debut=time(8), fin=time(10))
        base.update(kw)
        return conflit_ressources(**base)

    def test_cours_mutualise_autorise(self):
        self.assertIsNone(self.conflit(professeur_id=self.prof.id, salle_id=self.amphi.id, matiere_id=self.m.id))

    def test_enseignant_et_salle_occupes(self):
        msg = self.conflit(professeur_id=self.prof.id, matiere_id=self.autre_m.id)
        self.assertIn("L'enseignant a déjà cours", msg)
        msg = self.conflit(salle_id=self.amphi.id, matiere_id=self.autre_m.id, debut=time(9), fin=time(11))
        self.assertIn('« Amphi A » est déjà occupée', msg)
        self.assertIsNone(self.conflit(salle_id=self.amphi.id, debut=time(10), fin=time(12)))

    def test_mutualisation_reservee_au_superieur(self):
        self.etab.type_etablissement = 'lycée'
        self.etab.save()
        self.assertIsNotNone(self.conflit(professeur_id=self.prof.id, matiere_id=self.m.id))
