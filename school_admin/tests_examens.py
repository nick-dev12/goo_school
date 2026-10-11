"""Système d'examens refondu : moteur de calcul, bulletin, saisie enseignant, planning, LMD."""
from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.classe_model import Classe
from school_admin.model.creneau_examen_model import CreneauExamen
from school_admin.model.matiere_model import Matiere
from school_admin.model.moyenne_model import Moyenne
from school_admin.model.moyenne_periode_model import MoyennePeriode
from school_admin.model.note_examen_model import NoteExamen
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.ponderation_model import Ponderation
from school_admin.model.professeur_model import Professeur
from school_admin.model.salle_model import Salle
from school_admin.model.session_examen_model import ReglesExamen, SessionExamen
from school_admin.services import examens as mx
from school_admin.services.examens_planning import verifier_creneau
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement_type,
    _make_inscription,
)

D = Decimal


class BaseExamens(TestCase):
    type_etab = 'collège'

    def setUp(self):
        self.etab = _make_etablissement_type(self.type_etab, 'exa')
        self.annee = _make_annee(self.etab)
        s = str(self.etab.pk)
        self.classe = Classe.objects.create(nom='3e A', niveau='college', code_classe=f'3A-{s}', capacite_max=40,
                                            etablissement=self.etab, actif=True)
        self.classe_b = Classe.objects.create(nom='3e B', niveau='college', code_classe=f'3B-{s}', capacite_max=40,
                                              etablissement=self.etab, actif=True)
        self.math = Matiere.objects.create(nom=f'Maths {s}', code=f'MA{s}'[:10], etablissement=self.etab, actif=True,
                                           coefficient=4)
        self.fr = Matiere.objects.create(nom=f'Français {s}', code=f'FR{s}'[:10], etablissement=self.etab, actif=True,
                                         coefficient=2)
        self.periode = PeriodeScolaire.objects.create(
            etablissement=self.etab, nom_periode='1er Trimestre', type_periode='trimestre',
            date_debut=date(2026, 9, 1), date_fin=date(2026, 12, 15), annee_scolaire=self.annee.libelle,
            annee_scolaire_fk=self.annee, est_active=True)
        self.prof = Professeur.objects.create_user(
            username=f'prof.exa.{s}', email=f'prof.exa.{s}@test.local', password='Prof@Test1!', nom='Sarr',
            prenom='Ali', telephone='770000090', numero_employe=f'EX{s}', matiere_principale=self.math,
            etablissement=self.etab, niveau_enseignement='college', actif=True)
        AffectationProfesseur.objects.create(professeur=self.prof, classe=self.classe, matiere=self.math,
                                             annee_scolaire=self.annee, statut='classique', actif=True)
        self.prof.matieres_secondaires.add(self.fr)
        AffectationProfesseur.objects.create(professeur=self.prof, classe=self.classe, matiere=self.fr,
                                             annee_scolaire=self.annee, statut='classique', actif=True)
        self.awa = _make_eleve_simple(self.etab, self.classe, 'Diallo', 'Awa', suffix=f'a{s}')
        self.moussa = _make_eleve_simple(self.etab, self.classe, 'Ba', 'Moussa', sexe='M', suffix=f'b{s}')
        for e in (self.awa, self.moussa):
            _make_inscription(e, self.classe, self.annee, self.etab)
        self.compo = self.session('Composition T1', SessionExamen.TYPE_COMPOSITION)
        Ponderation.objects.create(etablissement=self.etab, poids_classe=40, poids_examen=60)

    def session(self, nom, type_session, debut=date(2026, 12, 1), fin=date(2026, 12, 5), matieres=None, **kw):
        sess = SessionExamen.objects.create(nom_examen=nom, etablissement=self.etab, periode=self.periode,
                                            date_debut=debut, date_fin=fin, annee_scolaire=self.annee,
                                            type_session=type_session, **kw)
        sess.classes.set([self.classe])
        sess.matieres.set(matieres or [self.math, self.fr])
        return sess

    def note(self, eleve, session, note=None, matiere=None, bareme=20, absent=False, justifiee=False, soumis=True,
             statut='brouillon'):
        # Des lignes vides sont créées automatiquement pour chaque élève à la création de la session.
        n, _ = NoteExamen.objects.get_or_create(eleve=eleve, session_examen=session, matiere=matiere or self.math,
                                                defaults={'classe': self.classe})
        n.classe, n.professeur, n.bareme, n.note = self.classe, self.prof, bareme, note
        n.absent, n.absence_justifiee, n.soumis, n.statut_publication = absent, justifiee, soumis, statut
        n.save()
        return n

    def res(self, eleve, matiere=None, regle=None):
        return mx.resultat_examen(eleve, self.classe, matiere or self.math, self.periode, self.annee, self.etab,
                                  regle)


class MoteurExamenTests(BaseExamens):
    def test_note_ramenee_sur_20_et_annee_renseignee(self):
        n = self.note(self.awa, self.compo, D('30'), bareme=40)
        self.assertEqual(n.annee_scolaire_id, self.annee.id)
        self.assertEqual(self.res(self.awa)['valeur'], D('15.00'))

    def test_bareme_controle(self):
        n = NoteExamen(eleve=self.awa, session_examen=self.compo, matiere=self.math, classe=self.classe,
                       bareme=20, note=D('25'))
        with self.assertRaises(ValidationError):
            n.clean()

    def test_brouillon_non_compte(self):
        self.note(self.awa, self.compo, D('14'), soumis=False)
        r = self.res(self.awa)
        self.assertIsNone(r['valeur'])
        self.assertEqual(r['non_publiees'], 1)
        # publiée par l'enseignant : elle compte
        NoteExamen.objects.update(statut_publication='publiee', note_publiee=D('14'))
        self.assertEqual(self.res(self.awa)['valeur'], D('14.00'))

    def test_absence_injustifiee_zero_et_justifiee_neutralisee(self):
        self.note(self.awa, self.compo, absent=True)
        self.note(self.moussa, self.compo, absent=True, justifiee=True)
        r = self.res(self.awa)
        self.assertEqual((r['valeur'], r['statut']), (D('0'), 'absent'))
        r = self.res(self.moussa)
        self.assertEqual((r['valeur'], r['statut']), (None, 'absent_justifie'))
        regle = mx.regles(self.etab)
        regle.absence_injustifiee = 'neutre'
        regle.save()
        self.assertIsNone(self.res(self.awa, regle=regle)['valeur'])

    def test_examen_blanc_exclu_par_defaut(self):
        blanc = self.session('BFEM blanc', SessionExamen.TYPE_BLANC)
        self.assertFalse(blanc.compte_bulletin)
        self.note(self.awa, blanc, D('5'))
        self.note(self.awa, self.compo, D('15'))
        self.assertEqual(self.res(self.awa)['valeur'], D('15.00'))

    def test_plusieurs_compositions_moyennees(self):
        compo2 = self.session('Composition 2', SessionExamen.TYPE_COMPOSITION)
        self.note(self.awa, self.compo, D('12'))
        self.note(self.awa, compo2, D('16'))
        r = self.res(self.awa)
        self.assertEqual((r['valeur'], r['nb_sessions']), (D('14.00'), 2))

    def test_rattrapage_meilleure_ou_remplace(self):
        ratt = self.session('Rattrapage', SessionExamen.TYPE_RATTRAPAGE)
        self.note(self.awa, self.compo, D('12'))
        self.note(self.awa, ratt, D('8'))
        self.assertEqual(self.res(self.awa)['valeur'], D('12.00'))
        regle = mx.regles(self.etab)
        regle.regle_rattrapage = 'remplace'
        regle.save()
        self.assertEqual(self.res(self.awa, regle=regle)['valeur'], D('8.00'))
        # absent au rattrapage : on garde la 1re session
        self.note(self.moussa, self.compo, D('7'))
        self.note(self.moussa, ratt, absent=True)
        self.assertEqual(self.res(self.moussa, regle=regle)['valeur'], D('7.00'))

    def test_session_annulee_ignoree(self):
        self.note(self.awa, self.compo, D('15'))
        self.compo.est_annule = True
        self.compo.save()
        self.assertIsNone(self.res(self.awa)['valeur'])

    def test_moyenne_matiere(self):
        self.assertEqual(mx.moyenne_matiere(D('10'), {'valeur': D('15')}, D('0.4'), D('0.6')), D('13.00'))
        self.assertEqual(mx.moyenne_matiere(D('10'), {'valeur': None}, D('0.4'), D('0.6')), D('10.00'))
        self.assertEqual(mx.moyenne_matiere(None, {'valeur': D('9')}, D('0.4'), D('0.6')), D('9.00'))
        self.assertIsNone(mx.moyenne_matiere(D('12'), {'valeur': None}, D('0.4'), D('0.6'), superieur=True))


class BulletinSansDoubleComptageTests(BaseExamens):
    def test_calcul_bulletin_compte_l_examen_une_seule_fois(self):
        # CC enregistré par l'enseignant : 10 (contrôle continu seul) ; composition : 15/20.
        for eleve, cc, ex in ((self.awa, '10', '15'), (self.moussa, '12', '13')):
            Moyenne.objects.create(eleve=eleve, classe=self.classe, matiere=self.math, professeur=self.prof,
                                   periode=str(self.periode.id), moyenne=D(cc), soumis=True, actif=True,
                                   annee_scolaire=self.annee)
            self.note(eleve, self.compo, D(ex))
        self.client.force_login(self.etab)
        url = reverse('directeur:calculer_moyenne_eleve', args=[self.classe.id, self.awa.id])
        self.client.get(url + f'?periode={self.periode.id}')
        self.client.get(reverse('directeur:calculer_moyenne_eleve', args=[self.classe.id, self.moussa.id])
                        + f'?periode={self.periode.id}')
        mp = MoyennePeriode.objects.get(eleve=self.awa, matiere=self.math, est_moyenne_generale=False)
        self.assertEqual(D(str(mp.moyenne_matiere)), D('13.00'))   # 10×0,4 + 15×0,6
        self.assertEqual(D(str(mp.note_examen)), D('15.00'))
        rangs = dict(MoyennePeriode.objects.filter(est_moyenne_generale=True).values_list('eleve_id', 'rang'))
        # Awa 13,00 ; Moussa 12×0,4 + 13×0,6 = 12,60
        self.assertEqual(rangs, {self.awa.id: 1, self.moussa.id: 2})

    def test_ex_aequo_meme_rang(self):
        for eleve in (self.awa, self.moussa):
            Moyenne.objects.create(eleve=eleve, classe=self.classe, matiere=self.math, professeur=self.prof,
                                   periode=str(self.periode.id), moyenne=D('11'), soumis=True, actif=True,
                                   annee_scolaire=self.annee)
        self.client.force_login(self.etab)
        for eleve in (self.awa, self.moussa):
            self.client.get(reverse('directeur:calculer_moyenne_eleve', args=[self.classe.id, eleve.id])
                            + f'?periode={self.periode.id}')
        rangs = set(MoyennePeriode.objects.filter(est_moyenne_generale=True).values_list('rang', flat=True))
        self.assertEqual(rangs, {1})


class SaisieEnseignantTests(BaseExamens):
    def test_matieres_selon_affectations(self):
        self.assertEqual({m.id for m in mx.matieres_enseignant(self.prof, self.classe, self.annee)},
                         {self.math.id, self.fr.id})
        self.assertEqual(mx.matieres_enseignant(self.prof, self.classe_b, self.annee), [])

    def test_enregistrer_saisie_valide_tout_ou_rien(self):
        eleves = [self.awa, self.moussa]
        nb, err = mx.enregistrer_saisie(self.compo, self.classe, self.math, self.prof, eleves,
                                        {self.awa.id: {'note': '25'}, self.moussa.id: {'note': '12'}}, 20)
        self.assertEqual(nb, 0)
        self.assertTrue(err)
        self.assertFalse(NoteExamen.objects.filter(note__isnull=False).exists())
        nb, err = mx.enregistrer_saisie(self.compo, self.classe, self.math, self.prof, eleves,
                                        {self.awa.id: {'note': '17,5'}, self.moussa.id: {'note': 'ABS'}}, 20)
        self.assertEqual((nb, err), (2, []))
        m = NoteExamen.objects.get(eleve=self.moussa, matiere=self.math)
        self.assertTrue(m.absent)
        self.assertFalse(m.soumis)

    def test_soumission_exige_toutes_les_notes_et_verrouille(self):
        eleves = [self.awa, self.moussa]
        nb, err = mx.enregistrer_saisie(self.compo, self.classe, self.math, self.prof, eleves,
                                        {self.awa.id: {'note': '14'}}, 20, soumettre=True)
        self.assertEqual(nb, 0)
        self.assertIn('Moussa', err[0])
        nb, err = mx.enregistrer_saisie(
            self.compo, self.classe, self.math, self.prof, eleves,
            {self.awa.id: {'note': '14'}, self.moussa.id: {'absent': True, 'justifiee': True}}, 20, soumettre=True)
        self.assertEqual(nb, 2)
        self.assertTrue(NoteExamen.objects.get(eleve=self.moussa, matiere=self.math).absence_justifiee)
        # verrouillée : une nouvelle saisie ne modifie rien
        mx.enregistrer_saisie(self.compo, self.classe, self.math, self.prof, eleves, {self.awa.id: {'note': '2'}}, 20)
        self.assertEqual(NoteExamen.objects.get(eleve=self.awa, matiere=self.math).note, D('14'))

    def test_page_enseignant(self):
        self.client.force_login(self.prof)
        url = reverse('enseignant:noter_examen_session', args=[self.classe.id, self.compo.id])
        r = self.client.get(url + f'?matiere={self.fr.id}')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Composition T1')
        self.assertContains(r, self.fr.nom)
        r = self.client.post(url, {'matiere': self.math.id, 'bareme': '20', 'action': 'enregistrer',
                                   f'note_{self.awa.id}': '16', f'note_{self.moussa.id}': 'abs'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(NoteExamen.objects.get(eleve=self.awa, matiere=self.math).note, D('16'))
        self.assertTrue(NoteExamen.objects.get(eleve=self.moussa, matiere=self.math).absent)
        # classe non affectée : refus
        self.compo.classes.add(self.classe_b)
        r = self.client.get(reverse('enseignant:noter_examen_session', args=[self.classe_b.id, self.compo.id]))
        self.assertEqual(r.status_code, 302)


class PlanningTests(BaseExamens):
    def creneau(self, session=None, matiere=None, jour=date(2026, 12, 2), h1=time(8), h2=time(10), **kw):
        return CreneauExamen(session_examen=session or self.compo, matiere=matiere or self.math, date_examen=jour,
                             heure_debut=h1, heure_fin=h2, annee_scolaire=self.annee, **kw)

    def test_date_hors_session(self):
        err, _ = verifier_creneau(self.creneau(jour=date(2026, 12, 10)))
        self.assertTrue(any('dates de la session' in e for e in err))

    def test_meme_classe_deux_epreuves_simultanees(self):
        self.creneau().save()
        err, _ = verifier_creneau(self.creneau(matiere=self.fr, h1=time(9), h2=time(11)))
        self.assertTrue(any('Conflit' in e for e in err), err)
        err, _ = verifier_creneau(self.creneau(matiere=self.fr, h1=time(10), h2=time(12)))
        self.assertEqual(err, [])

    def test_salle_et_surveillant(self):
        salle = Salle.objects.create(nom='S1', numero='1', etablissement=self.etab, capacite_max=1)
        autre = self.session('Compo 3e B', SessionExamen.TYPE_COMPOSITION, matieres=[self.fr])
        autre.classes.set([self.classe_b])
        self.creneau(salle=salle, surveillant=self.prof).save()
        err, _ = verifier_creneau(self.creneau(session=autre, matiere=self.fr, salle=salle))
        self.assertTrue(err)
        err, _ = verifier_creneau(self.creneau(session=autre, matiere=self.fr, surveillant=self.prof))
        self.assertTrue(err)
        # avertissements : salle trop petite, surveillant qui enseigne la matière
        _, avert = verifier_creneau(self.creneau(matiere=self.fr, jour=date(2026, 12, 3), salle=salle,
                                                 surveillant=self.prof))
        self.assertEqual(len(avert), 2, avert)

    def test_creation_session_depuis_formulaire(self):
        self.client.force_login(self.etab)
        r = self.client.post(reverse('directeur:gestion_examens'), {
            'nom_examen': 'Examen blanc BFEM', 'periode_id': self.periode.id, 'date_debut': '2026-12-08',
            'date_fin': '2026-12-07', 'matieres': [self.math.id], 'groupes_classes': ['3e'],
            'type_session': 'examen_blanc'})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(SessionExamen.objects.filter(nom_examen='Examen blanc BFEM').exists())  # dates inversées

    def test_publication(self):
        self.client.force_login(self.etab)
        self.assertFalse(self.compo.est_publie)
        self.client.post(reverse('directeur:publier_session_examen', args=[self.compo.id]))
        self.compo.refresh_from_db()
        self.assertTrue(self.compo.est_publie)

    def test_regles(self):
        self.client.force_login(self.etab)
        self.client.post(reverse('directeur:regles_examens'), {
            'absence_injustifiee': 'neutre', 'regle_rattrapage': 'remplace', 'seuil_validation': '10',
            'note_eliminatoire': '5', 'compensation_semestrielle': 'on'})
        r = ReglesExamen.objects.get(etablissement=self.etab)
        self.assertEqual((r.absence_injustifiee, r.regle_rattrapage, r.note_eliminatoire), ('neutre', 'remplace', D('5')))


class LMDTests(TestCase):
    def regle(self, **kw):
        base = dict(seuil_validation=D('10'), note_eliminatoire=None, compensation_semestrielle=True)
        base.update(kw)
        return SimpleNamespace(**base)

    def ligne(self, ue, moyenne, credits, coef=1, nom='EC'):
        m = SimpleNamespace(id=id(object()), module_id=ue, module=SimpleNamespace(nom=f'UE{ue}'), nom=nom)
        return {'matiere': m, 'moyenne': None if moyenne is None else D(moyenne), 'coefficient': coef,
                'credits': D(credits)}

    def test_ue_acquise_par_moyenne_des_ec(self):
        # UE1 : 8 et 14 (même coef) -> 11 : acquise malgré l'EC à 8
        v = mx.validation_lmd([self.ligne(1, '8', 3), self.ligne(1, '14', 3), self.ligne(2, '12', 6)], self.regle())
        self.assertEqual(v['decision'], 'Admis')
        self.assertEqual(v['credits_acquis'], D('12'))

    def test_compensation_semestrielle(self):
        v = mx.validation_lmd([self.ligne(1, '8', 6), self.ligne(2, '13', 6)], self.regle())
        self.assertEqual(v['moyenne_semestre'], D('10.50'))
        self.assertEqual(v['decision'], 'Admis par compensation')
        self.assertEqual(v['credits_acquis'], D('12'))
        v = mx.validation_lmd([self.ligne(1, '8', 6), self.ligne(2, '13', 6)],
                              self.regle(compensation_semestrielle=False))
        self.assertEqual((v['decision'], v['credits_acquis']), ('Ajourné', D('6')))

    def test_note_eliminatoire_bloque_la_compensation(self):
        v = mx.validation_lmd([self.ligne(1, '4', 6), self.ligne(2, '17', 6)], self.regle(note_eliminatoire=D('5')))
        self.assertEqual(v['decision'], 'Ajourné')
        self.assertTrue(v['eliminatoire'])

    def test_epreuve_manquante_incomplet(self):
        v = mx.validation_lmd([self.ligne(1, None, 6), self.ligne(2, '15', 6)], self.regle())
        self.assertEqual(v['decision'], 'Incomplet')


class PagesDirectionTests(BaseExamens):
    def test_pages_direction_tous_types(self):
        for type_etab in ('collège', 'primary', 'superieur'):
            self.etab.type_etablissement = type_etab
            self.etab.save()
            self.client.force_login(self.etab)
            r = self.client.get(reverse('directeur:gestion_examens'))
            self.assertEqual(r.status_code, 200, type_etab)
            self.assertContains(r, 'Règles de calcul')
            self.assertContains(r, 'Nature de la session')
            r = self.client.get(reverse('directeur:configurer_creneaux_examen', args=[self.compo.id]))
            self.assertEqual(r.status_code, 200, type_etab)
            self.assertContains(r, 'Planifier une épreuve')
            r = self.client.get(reverse('directeur:emploi_du_temps_examens'))
            self.assertEqual(r.status_code, 200, type_etab)

    def test_planifier_depuis_la_page(self):
        self.client.force_login(self.etab)
        url = reverse('directeur:configurer_creneaux_examen', args=[self.compo.id])
        data = {'matiere_id': self.math.id, 'jour_semaine': '2026-12-02', 'heure_debut': '08:00', 'heure_fin': '10:00'}
        self.client.post(url, data)
        self.assertEqual(CreneauExamen.objects.filter(session_examen=self.compo).count(), 1)
        r = self.client.post(url, dict(data, matiere_id=self.fr.id, heure_debut='09:00', heure_fin='11:00'), follow=True)
        self.assertContains(r, 'Conflit')
        self.assertEqual(CreneauExamen.objects.filter(session_examen=self.compo).count(), 1)
        c = CreneauExamen.objects.get()
        self.client.post(reverse('directeur:supprimer_creneau_examen', args=[c.id]))
        self.assertFalse(CreneauExamen.objects.exists())
