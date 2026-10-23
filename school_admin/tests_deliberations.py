"""Supérieur (LMD) — étape 2 : délibérations, points de jury, passage annuel, dettes, capitalisation, PV."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from school_admin.model.academic_structure_model import Department
from school_admin.model.classe_model import Classe
from school_admin.model.deliberation_model import DecisionJury, Deliberation, UECapitalisee
from school_admin.model.matiere_model import Matiere
from school_admin.model.module_model import Module, ModuleClasse
from school_admin.model.moyenne_periode_model import MoyennePeriode
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.ponderation_model import Ponderation
from school_admin.services import deliberations as svc
from school_admin.services import examens as mx
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement_type,
    _make_inscription,
)

D = Decimal


class BaseDelib(TestCase):
    """L1 : S1 = 3 UE (10 + 10 + 10 crédits), S2 = 3 UE (10 + 10 + 10 crédits)."""

    def setUp(self):
        self.etab = _make_etablissement_type('superieur', 'dlb')
        self.annee = _make_annee(self.etab)
        Ponderation.objects.create(etablissement=self.etab, poids_classe=40, poids_examen=60)
        s = str(self.etab.pk)
        self.dept = Department.objects.create(nom='Droit', sigle='DRT', etablissement=self.etab)
        self.classe = Classe.objects.create(nom='DRT L1 A', niveau='superieur', niveau_lmd='L1', code_classe=f'L1-{s}',
                                            capacite_max=80, etablissement=self.etab, department=self.dept)
        self.s1 = self._periode('Semestre 1', date(2026, 10, 1), date(2027, 2, 28))
        self.s2 = self._periode('Semestre 2', date(2027, 3, 1), date(2027, 7, 31))
        self.ecs = {}
        for per, prefixe in ((self.s1, 'A'), (self.s2, 'B')):
            for i in range(3):
                mod = Module.objects.create(nom=f'UE {prefixe}{i + 1}', code=f'{prefixe}{i}-{s}', etablissement=self.etab,
                                            department=self.dept, niveau_lmd='L1', ordre=i)
                ModuleClasse.objects.create(module=mod, classe=self.classe, credits=D('10'), numero_ue=f'UE{prefixe}{i}',
                                            periode=per)
                m = Matiere.objects.create(nom=f'EC {prefixe}{i + 1}', etablissement=self.etab, department=self.dept,
                                           module=mod, niveau='superieur', coefficient=1, credits=D('10'))
                m.classes.add(self.classe)
                self.ecs[(per.id, i)] = m
        self.awa = self._etudiant('Ndoye', 'Awa', 'a')
        self.regle = mx.regles(self.etab)

    def _periode(self, nom, debut, fin):
        return PeriodeScolaire.objects.create(etablissement=self.etab, nom_periode=nom, type_periode='semestre',
                                              niveau_lmd='L1', date_debut=debut, date_fin=fin,
                                              annee_scolaire=self.annee.libelle, annee_scolaire_fk=self.annee,
                                              est_active=True)

    def _etudiant(self, nom, prenom, suffixe, annee=None):
        e = _make_eleve_simple(self.etab, self.classe, nom, prenom, 'F', f'{suffixe}{self.etab.pk}')
        _make_inscription(e, self.classe, annee or self.annee, self.etab)
        return e

    def notes(self, eleve, periode, valeurs, annee=None):
        for i, v in enumerate(valeurs):
            MoyennePeriode.objects.update_or_create(
                eleve=eleve, etablissement=self.etab, periode=periode, matiere=self.ecs[(periode.id, i)],
                est_moyenne_generale=False,
                defaults={'moyenne_matiere': D(str(v)), 'coefficient': 1, 'credits': D('10'),
                          'annee_scolaire': annee or self.annee})
        MoyennePeriode.objects.update_or_create(
            eleve=eleve, etablissement=self.etab, periode=periode, est_moyenne_generale=True,
            defaults={'moyenne_generale': D('10'), 'annee_scolaire': annee or self.annee})

    def deliberation(self, periode=None, annee=None):
        d, _ = svc.creer(self.etab, self.classe, annee or self.annee, periode)
        return d


class SemestreTests(BaseDelib):
    def test_decisions_et_points_de_jury(self):
        self.notes(self.awa, self.s1, [12, 13, 14])
        moussa = self._etudiant('Diallo', 'Moussa', 'm')
        self.notes(moussa, self.s1, [9, 9.5, 10.3])  # moyenne 9,6 : ajourné
        d = self.deliberation(self.s1)
        dec = {x.eleve_id: x for x in d.decisions.all()}
        self.assertEqual(dec[self.awa.id].decision, DecisionJury.ADMIS)
        self.assertEqual(dec[self.awa.id].mention, 'Assez bien')
        self.assertEqual(dec[moussa.id].decision, DecisionJury.AJOURNE)
        self.assertEqual(len(dec[moussa.id].dettes), 2)
        # motif obligatoire, plafond respecté, rien n'est écrit en cas d'erreur
        self.assertTrue(svc.enregistrer_points(d, {moussa.id: ('0,5', '')}))
        self.assertTrue(svc.enregistrer_points(d, {moussa.id: ('3', 'Assiduité')}))
        self.assertEqual(svc.enregistrer_points(d, {moussa.id: ('0,5', 'Assiduité et progression')}), [])
        m = DecisionJury.objects.get(deliberation=d, eleve=moussa)
        self.assertEqual((m.moyenne_jury, m.decision), (D('10.10'), DecisionJury.ADMIS_COMPENSATION))
        self.assertEqual(m.credits_acquis, D('30'))

    def test_cloture_capitalise_verrouille_et_publie(self):
        self.notes(self.awa, self.s1, [12, 8, 13])
        self.regle.compensation_semestrielle = False
        self.regle.save()
        d = self.deliberation(self.s1)
        d.president = 'Pr. Diop'
        d.save()
        svc.cloturer(d, 'Doyen')
        caps = set(UECapitalisee.objects.filter(eleve=self.awa).values_list('module__nom', flat=True))
        self.assertEqual(caps, {'UE A1', 'UE A3'})
        mp = MoyennePeriode.objects.get(eleve=self.awa, periode=self.s1, est_moyenne_generale=True)
        self.assertIn('Ajourné — 20/30 crédits', mp.decision_conseil)
        self.assertIsNotNone(svc.periode_verrouillee(self.classe, self.s1))
        self.assertIsNone(svc.periode_verrouillee(self.classe, self.s2))
        with self.assertRaises(svc.DeliberationErreur):
            svc.preparer(d)
        svc.rouvrir(d)
        self.assertFalse(UECapitalisee.objects.exists())
        self.assertIsNone(svc.periode_verrouillee(self.classe, self.s1))

    def test_verrou_bloque_calcul_et_saisie_examen(self):
        from school_admin.model.session_examen_model import SessionExamen

        self.notes(self.awa, self.s1, [12, 13, 14])
        d = self.deliberation(self.s1)
        d.president = 'Pr. Diop'
        d.save()
        svc.cloturer(d)
        self.client.force_login(self.etab)
        r = self.client.get(reverse('directeur:calculer_moyenne_eleve', args=[self.classe.id, self.awa.id])
                            + f'?periode={self.s1.id}', follow=True)
        self.assertContains(r, 'verrouillées')
        sess = SessionExamen.objects.create(nom_examen='Partiels S1', etablissement=self.etab, periode=self.s1,
                                            date_debut=date(2027, 2, 1), date_fin=date(2027, 2, 5),
                                            annee_scolaire=self.annee, type_session='examen')
        sess.classes.set([self.classe])
        sess.matieres.set([self.ecs[(self.s1.id, 0)]])
        nb, err = mx.enregistrer_saisie(sess, self.classe, self.ecs[(self.s1.id, 0)], None, [self.awa],
                                        {self.awa.id: {'note': '15'}}, 20)
        self.assertEqual(nb, 0)
        self.assertIn('verrouillées', err[0])


class AnnuelTests(BaseDelib):
    def test_admis_dettes_redouble(self):
        self.notes(self.awa, self.s1, [12, 13, 14])
        self.notes(self.awa, self.s2, [12, 8, 13])           # 50/60 crédits (83 %)
        lamine = self._etudiant('Mbaye', 'Lamine', 'l')
        self.notes(lamine, self.s1, [12, 8, 7])
        self.notes(lamine, self.s2, [8, 7, 12])               # 20/60 crédits
        khady = self._etudiant('Faye', 'Khady', 'k')
        self.notes(khady, self.s1, [12, 13, 14])
        self.notes(khady, self.s2, [11, 12, 13])
        self.regle.compensation_semestrielle = False
        self.regle.save()
        d = self.deliberation()
        dec = {x.eleve_id: x for x in d.decisions.all()}
        self.assertEqual(dec[khady.id].decision, DecisionJury.ADMIS)
        self.assertEqual(dec[self.awa.id].decision, DecisionJury.ADMIS_CONDITIONNEL)
        self.assertEqual([u['titre'] for u in dec[self.awa.id].dettes], ['UE B2'])
        self.assertEqual(dec[lamine.id].decision, DecisionJury.REDOUBLE)

    def test_compensation_annuelle(self):
        self.notes(self.awa, self.s1, [13, 13, 13])
        self.notes(self.awa, self.s2, [8, 8, 9.5])  # S2 sous 10 mais année = 10,75
        self.regle.compensation_semestrielle = False
        self.regle.pourcentage_passage_conditionnel = 100
        self.regle.save()
        self.assertEqual(self.deliberation().decisions.get().decision, DecisionJury.REDOUBLE)
        self.regle.compensation_annuelle = True
        self.regle.save()
        d = Deliberation.objects.get(periode__isnull=True)
        svc.preparer(d)
        dj = d.decisions.get()
        self.assertEqual((dj.decision, dj.credits_acquis), (DecisionJury.ADMIS_COMPENSATION, D('60')))

    def test_ue_capitalisee_acquise_l_annee_suivante(self):
        self.notes(self.awa, self.s1, [12, 7, 14])
        self.regle.compensation_semestrielle = False
        self.regle.save()
        d = self.deliberation(self.s1)
        d.president = 'Pr. Diop'
        d.save()
        svc.cloturer(d)
        # Année suivante : l'étudiante redouble, ne repasse que l'UE A2.
        annee2 = _make_annee(self.etab, libelle='2027-2028', debut=2027, active=False)
        s1b = PeriodeScolaire.objects.create(etablissement=self.etab, nom_periode='Semestre 1', type_periode='semestre',
                                             niveau_lmd='L1', date_debut=date(2027, 10, 1), date_fin=date(2028, 2, 28),
                                             annee_scolaire=annee2.libelle, annee_scolaire_fk=annee2, est_active=True)
        ModuleClasse.objects.filter(classe=self.classe, periode=self.s1).update(periode=s1b)
        mod_a2 = self.ecs[(self.s1.id, 1)]
        MoyennePeriode.objects.create(eleve=self.awa, etablissement=self.etab, periode=s1b, matiere=mod_a2,
                                      est_moyenne_generale=False, moyenne_matiere=D('11'), coefficient=1,
                                      credits=D('10'), annee_scolaire=annee2)
        _make_inscription(self.awa, self.classe, annee2, self.etab)
        d2, _ = svc.creer(self.etab, self.classe, annee2, s1b)
        dj = d2.decisions.get(eleve=self.awa)
        self.assertEqual((dj.decision, dj.credits_acquis), (DecisionJury.ADMIS, D('30')))
        modes = sorted(u['mode'] for u in dj.detail_ues)
        self.assertEqual(modes, ['acquise', 'capitalisee', 'capitalisee'])


class PagesTests(BaseDelib):
    def test_parcours_complet(self):
        self.notes(self.awa, self.s1, [9, 9.6, 10])
        self.client.force_login(self.etab)
        r = self.client.get(reverse('directeur:liste_deliberations'))
        self.assertContains(r, 'Ouvrir une délibération')
        r = self.client.post(reverse('directeur:liste_deliberations'),
                             {'classe_id': self.classe.id, 'portee': 'semestre', 'periode_id': self.s1.id,
                              'session': 'normale'})
        d = Deliberation.objects.get()
        url = reverse('directeur:detail_deliberation', args=[d.id])
        self.assertRedirects(r, url)
        r = self.client.get(url)
        self.assertContains(r, 'Ndoye'.upper())
        self.assertContains(r, 'Ajourné')
        self.client.post(url, {'action': 'points', f'points_{self.awa.id}': '0,5', f'motif_{self.awa.id}': 'Progression'})
        self.assertEqual(DecisionJury.objects.get().decision, DecisionJury.ADMIS_COMPENSATION)
        r = self.client.post(url, {'action': 'cloturer'}, follow=True)
        self.assertContains(r, 'président du jury')
        self.client.post(url, {'action': 'jury', 'president': 'Pr. Pape Diop', 'membres': 'M. Sarr\nMme Fall',
                               'date_deliberation': '2027-03-02'})
        self.client.post(url, {'action': 'cloturer'})
        d.refresh_from_db()
        self.assertTrue(d.est_cloturee)
        r = self.client.get(reverse('directeur:pv_deliberation', args=[d.id]))
        self.assertContains(r, 'Procès-verbal de délibération')
        self.assertContains(r, 'Pr. Pape Diop')
        self.assertContains(r, '+0,5')
        r = self.client.get(reverse('directeur:voir_bulletin_eleve', args=[self.classe.id, self.awa.id])
                            + f'?periode={self.s1.id}')
        self.assertIn('Admis par compensation', r.context['complement_info']['decision_conseil'])
        self.assertIn('jury +0,5', r.context['complement_info']['decision_conseil'])

    def test_regles_jury(self):
        self.client.force_login(self.etab)
        self.client.post(reverse('directeur:regles_examens'), {
            'absence_injustifiee': 'zero', 'regle_rattrapage': 'meilleure', 'seuil_validation': '10',
            'note_eliminatoire': '', 'compensation_semestrielle': 'on', 'compensation_annuelle': 'on',
            'pourcentage_passage_conditionnel': '80', 'points_jury_max': '0,5'})
        r = mx.regles(self.etab)
        r.refresh_from_db()
        self.assertEqual((r.compensation_annuelle, r.pourcentage_passage_conditionnel, r.points_jury_max),
                         (True, 80, D('0.5')))
