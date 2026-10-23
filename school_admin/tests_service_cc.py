"""Supérieur (LMD) — étape 4 : contrôle continu pondéré, service des enseignants en équivalent TD,
emploi du temps de l'étudiant (groupe, semestre, options)."""
import json
from datetime import date, time
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from school_admin.model.academic_structure_model import Department
from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.classe_model import Classe
from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps, EmploiDuTemps
from school_admin.model.evaluation_model import Evaluation, Note
from school_admin.model.maquette_model import GroupeEnseignement
from school_admin.model.matiere_model import Matiere
from school_admin.model.moyenne_model import Moyenne
from school_admin.model.module_model import Module, ModuleClasse
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.professeur_model import Professeur
from school_admin.model.service_enseignant_model import ReglesService
from school_admin.services import controle_continu as cc
from school_admin.services import examens as mx
from school_admin.services import maquette as mq
from school_admin.services import service_enseignant as srv
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement_type,
    _make_inscription,
)

D = Decimal


class Base(TestCase):
    def setUp(self):
        self.etab = _make_etablissement_type('superieur', 'srv')
        self.annee = _make_annee(self.etab)
        s = str(self.etab.pk)
        self.dept = Department.objects.create(nom='Économie', sigle='ECO', etablissement=self.etab)
        self.classe = Classe.objects.create(nom='ECO L1 A', niveau='superieur', niveau_lmd='L1', code_classe=f'E1-{s}',
                                            capacite_max=100, etablissement=self.etab, department=self.dept)
        self.classe2 = Classe.objects.create(nom='GES L1 A', niveau='superieur', niveau_lmd='L1', code_classe=f'G1-{s}',
                                             capacite_max=100, etablissement=self.etab, department=self.dept)
        self.s1 = PeriodeScolaire.objects.create(
            etablissement=self.etab, nom_periode='Semestre 1', type_periode='semestre', niveau_lmd='L1',
            date_debut=date(2026, 10, 5), date_fin=date(2027, 1, 24), annee_scolaire=self.annee.libelle,
            annee_scolaire_fk=self.annee, est_active=True)  # 16 semaines
        mod = Module.objects.create(nom='Économie générale', code=f'EG-{s}', etablissement=self.etab,
                                    department=self.dept, niveau_lmd='L1')
        ModuleClasse.objects.create(module=mod, classe=self.classe, credits=D(6), periode=self.s1)
        self.ec = Matiere.objects.create(nom='Microéconomie', etablissement=self.etab, department=self.dept, module=mod,
                                         niveau='superieur', coefficient=1, credits=D(6))
        self.ec.classes.add(self.classe, self.classe2)
        self.cm, self.td = (Professeur.objects.create_user(
            username=f'{n}.{s}', email=f'{n}.{s}@t.local', password='Prof@Test1!', nom=n, prenom='X',
            telephone=f'7701{i:05d}', numero_employe=f'{n[:2]}{s}', matiere_principale=self.ec, etablissement=self.etab,
            niveau_enseignement='superieur', actif=True, type_contrat='permanent') for i, n in enumerate(('Diop', 'Sarr')))
        AffectationProfesseur.objects.create(professeur=self.cm, classe=self.classe, matiere=self.ec, annee_scolaire=self.annee,
                                             role_enseignement='cm')
        AffectationProfesseur.objects.create(professeur=self.td, classe=self.classe, matiere=self.ec, annee_scolaire=self.annee,
                                             role_enseignement='td', groupe='G1')
        self.awa = _make_eleve_simple(self.etab, self.classe, 'Ndoye', 'Awa', 'F', f'a{s}')
        _make_inscription(self.awa, self.classe, self.annee, self.etab)

    def evaluation(self, prof, type_eval, note, bareme=20):
        e = Evaluation.objects.create(titre=f'{type_eval} {note}', classe=self.classe, professeur=prof, matiere=self.ec,
                                      date_evaluation=date(2026, 11, 2), bareme=bareme, periode_scolaire=self.s1,
                                      annee_scolaire=self.annee, type_evaluation=type_eval)
        Note.objects.create(eleve=self.awa, evaluation=e, matiere=self.ec, note=D(str(note)), annee_scolaire=self.annee)
        return e


class ControleContinuTests(Base):
    def test_ponderation_par_type(self):
        r = cc.calculer({'td': [D(10), D(14)], 'partiel': [D(9)]}, type('R', (), {'poids_cc': {'td': 40, 'partiel': 60}}))
        self.assertEqual(r['moyenne'], D('10.20'))  # 12×0,4 + 9×0,6
        r = cc.calculer({'td': [D(12)], 'partiel': [D(9)]}, type('R', (), {'poids_cc': {}}))
        self.assertEqual(r['moyenne'], D('10.50'))  # à égalité
        r = cc.calculer({'td': [D(12)], 'autre': [D(16)]}, type('R', (), {'poids_cc': {'td': 50, 'tp': 50}}))
        self.assertEqual(r['moyenne'], D('12.00'))  # « autre » sans poids ; TP absent ignoré

    def test_toutes_les_evaluations_de_l_ec(self):
        regle = mx.regles(self.etab)
        regle.poids_cc = {'td': 40, 'partiel': 60}
        regle.save()
        self.evaluation(self.td, 'td', 7, bareme=10)   # 14/20, saisi par l'enseignant de TD
        self.evaluation(self.cm, 'partiel', 10)
        r = cc.moyenne_cc(self.awa, self.classe, self.ec, self.s1, self.annee)
        self.assertEqual(r['moyenne'], D('11.60'))  # 14×0,4 + 10×0,6
        # L'enseignant de CM calcule : la moyenne enregistrée inclut les TD de son collègue.
        self.client.force_login(self.cm)
        r = self.client.post(reverse('enseignant:calculer_moyennes', args=[self.classe.id]),
                             data=json.dumps({'colonnes_selectionnees': [], 'periode': str(self.s1.id),
                                              'nombre_meilleures_notes': 'toutes', 'matiere': self.ec.id}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Moyenne.objects.get(eleve=self.awa, matiere=self.ec).moyenne, D('11.60'))

    def test_type_dans_le_formulaire(self):
        self.client.force_login(self.td)
        r = self.client.get(reverse('enseignant:creer_evaluation', args=[self.classe.id]) + '?partial=1')
        self.assertContains(r, "Type d'évaluation")


class ServiceEnseignantTests(Base):
    def setUp(self):
        super().setUp()
        self.edt = EmploiDuTemps.objects.create(classe=self.classe, annee_scolaire=self.annee.libelle,
                                                annee_scolaire_fk=self.annee, est_actif=True)
        self.edt2 = EmploiDuTemps.objects.create(classe=self.classe2, annee_scolaire=self.annee.libelle,
                                                 annee_scolaire_fk=self.annee, est_actif=True)
        for edt in (self.edt, self.edt2):  # CM mutualisé 2 h / semaine dans deux classes
            CreneauEmploiDuTemps.objects.create(emploi_du_temps=edt, jour='lundi', heure_debut=time(8), heure_fin=time(10),
                                                matiere=self.ec, professeur=self.cm, type_cours='cours',
                                                periode_scolaire=self.s1)
        g1 = GroupeEnseignement.objects.create(classe=self.classe, nom='G1')
        g2 = GroupeEnseignement.objects.create(classe=self.classe, nom='G2')
        for g in (g1, g2):  # 2 groupes de TD de 1 h 30 assurés par le même enseignant
            CreneauEmploiDuTemps.objects.create(emploi_du_temps=self.edt, jour='mardi' if g == g1 else 'mercredi',
                                                heure_debut=time(10), heure_fin=time(11, 30), matiere=self.ec,
                                                professeur=self.cm, type_cours='td', groupe=g, periode_scolaire=self.s1)

    def test_equivalent_td_et_complementaires(self):
        regles = ReglesService.pour(self.etab)
        regles.taux_heure_complementaire = D('5000')
        regles.save()
        self.cm.grade_universitaire = 'maitre_assistant'
        self.cm.service_statutaire = 60
        self.cm.save()
        b = srv.bilan_enseignant(self.cm, self.annee)
        self.assertEqual((b['cm'], b['td']), (D('32.00'), D('48.00')))  # CM compté une fois ; 2 groupes × 1,5 h × 16
        self.assertEqual(b['eqtd'], D('96.00'))                         # 32 × 1,5 + 48
        self.assertEqual((b['du'], b['complementaires'], b['montant']), (D('60.00'), D('36.00'), D('180000.00')))
        self.assertEqual(b['statut'], 'complementaires')

    def test_vacataire_et_sous_service(self):
        self.td.type_contrat = 'vacataire'
        self.td.prix_volume_horaire = D('8000')
        self.td.save()
        CreneauEmploiDuTemps.objects.create(emploi_du_temps=self.edt, jour='jeudi', heure_debut=time(8), heure_fin=time(9),
                                            matiere=self.ec, professeur=self.td, type_cours='tp', periode_scolaire=self.s1)
        b = srv.bilan_enseignant(self.td, self.annee)
        self.assertEqual((b['tp'], b['eqtd'], b['complementaires']), (D('16.00'), D('10.72'), D('10.72')))
        self.assertEqual(b['montant'], D('85760.00'))
        self.cm.grade_universitaire = 'professeur_titulaire'
        self.cm.save()
        self.assertEqual(srv.bilan_enseignant(self.cm, self.annee)['statut'], 'sous_service')  # 96 < 192

    def test_pages(self):
        self.client.force_login(self.etab)
        url = reverse('directeur:service_enseignants')
        r = self.client.get(url)
        self.assertContains(r, 'Service des enseignants')
        self.client.post(url, {'action': 'grades', f'grade_{self.cm.id}': 'maitre_conferences', f'service_{self.cm.id}': '0',
                               f'grade_{self.td.id}': '', f'service_{self.td.id}': '0'})
        self.cm.refresh_from_db()
        self.assertEqual(self.cm.grade_universitaire, 'maitre_conferences')
        post = {'action': 'regles', 'coef_cm': '1,5', 'coef_td': '1', 'coef_tp': '0,75', 'taux': '6000', 'semaines_annee': '28'}
        post.update({f'service_{g}': '200' for g, _ in Professeur.GRADE_CHOICES})
        self.client.post(url, post)
        self.assertEqual(ReglesService.pour(self.etab).coef_tp, D('0.75'))
        r = self.client.get(reverse('directeur:service_enseignant_detail', args=[self.cm.id]))
        self.assertContains(r, 'Cours mutualisé')


class EmploiEtudiantTests(Base):
    def test_filtre_groupe_semestre_options(self):
        s2 = PeriodeScolaire.objects.create(
            etablissement=self.etab, nom_periode='Semestre 2', type_periode='semestre', niveau_lmd='L1',
            date_debut=date(2027, 2, 1), date_fin=date(2027, 6, 30), annee_scolaire=self.annee.libelle,
            annee_scolaire_fk=self.annee, est_active=True)
        edt = EmploiDuTemps.objects.create(classe=self.classe, annee_scolaire=self.annee.libelle,
                                           annee_scolaire_fk=self.annee, est_actif=True)
        g1 = GroupeEnseignement.objects.create(classe=self.classe, nom='G1')
        g2 = GroupeEnseignement.objects.create(classe=self.classe, nom='G2')
        g1.etudiants.add(self.awa)
        cm = CreneauEmploiDuTemps.objects.create(emploi_du_temps=edt, jour='lundi', heure_debut=time(8), heure_fin=time(10),
                                                 matiere=self.ec, type_cours='cours', periode_scolaire=self.s1)
        td1 = CreneauEmploiDuTemps.objects.create(emploi_du_temps=edt, jour='mardi', heure_debut=time(8), heure_fin=time(10),
                                                  matiere=self.ec, type_cours='td', groupe=g1, periode_scolaire=self.s1)
        CreneauEmploiDuTemps.objects.create(emploi_du_temps=edt, jour='mardi', heure_debut=time(8), heure_fin=time(10),
                                            matiere=self.ec, type_cours='td', groupe=g2, periode_scolaire=self.s1)
        CreneauEmploiDuTemps.objects.create(emploi_du_temps=edt, jour='jeudi', heure_debut=time(8), heure_fin=time(10),
                                            matiere=self.ec, type_cours='cours', periode_scolaire=s2)
        res = mq.creneaux_etudiant(list(edt.creneaux.all()), self.awa, self.classe, self.annee, aujourd_hui=date(2026, 11, 10))
        self.assertEqual({c.id for c in res}, {cm.id, td1.id})
