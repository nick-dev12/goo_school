"""Supérieur (LMD) — étape 3 : maquette (volumes, types, options, parcours), inscriptions pédagogiques,
groupes de TD/TP, emploi du temps par semestre et par groupe."""
from datetime import date, time
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from school_admin.model.academic_structure_model import Department
from school_admin.model.classe_model import Classe
from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps, EmploiDuTemps
from school_admin.model.maquette_model import GroupeEnseignement, InscriptionPedagogique, Parcours
from school_admin.model.matiere_model import Matiere
from school_admin.model.module_model import Module, ModuleClasse
from school_admin.model.moyenne_periode_model import MoyennePeriode
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.professeur_model import Professeur
from school_admin.services import deliberations as dlb
from school_admin.services import maquette as mq
from school_admin.services.emploi_conflits import conflit_ressources, creneaux_compatibles
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement_type,
    _make_inscription,
)

D = Decimal


class BaseMaquette(TestCase):
    """S1 : UE1 (12 cr, fondamentale), UE2 (12 cr), options OPT-A / OPT-B (6 cr, 1 à choisir)."""

    def setUp(self):
        self.etab = _make_etablissement_type('superieur', 'mqt')
        self.annee = _make_annee(self.etab)
        s = str(self.etab.pk)
        self.dept = Department.objects.create(nom='Gestion', sigle='GES', etablissement=self.etab)
        self.classe = Classe.objects.create(nom='GES L3 A', niveau='superieur', niveau_lmd='L3', code_classe=f'L3-{s}',
                                            capacite_max=80, etablissement=self.etab, department=self.dept)
        self.s5 = PeriodeScolaire.objects.create(
            etablissement=self.etab, nom_periode='Semestre 5', type_periode='semestre', niveau_lmd='L3',
            date_debut=date(2026, 10, 5), date_fin=date(2027, 1, 24), annee_scolaire=self.annee.libelle,
            annee_scolaire_fk=self.annee, est_active=True)  # 16 semaines
        self.mc, self.ec = {}, {}
        for code, credits, opt in (('UE1', 12, False), ('UE2', 12, False), ('OPTA', 6, True), ('OPTB', 6, True)):
            mod = Module.objects.create(nom=f'Module {code}', code=f'{code}-{s}', etablissement=self.etab,
                                        department=self.dept, niveau_lmd='L3')
            self.mc[code] = ModuleClasse.objects.create(module=mod, classe=self.classe, credits=D(credits), periode=self.s5,
                                                        optionnelle=opt, groupe_options='Option S5' if opt else '')
            m = Matiere.objects.create(nom=f'EC {code}', etablissement=self.etab, department=self.dept, module=mod,
                                       niveau='superieur', coefficient=1, credits=D(credits), volume_cm=20, volume_td=10)
            m.classes.add(self.classe)
            self.ec[code] = m
        self.awa = _make_eleve_simple(self.etab, self.classe, 'Ndoye', 'Awa', 'F', f'a{s}')
        _make_inscription(self.awa, self.classe, self.annee, self.etab)


class SyntheseTests(BaseMaquette):
    def test_credits_options_et_controles(self):
        sem = mq.maquette_classe(self.classe, [self.s5])[0]
        self.assertEqual(sem['totaux']['credits'], D('30'))  # 24 obligatoires + 1 option de 6
        self.assertEqual((sem['totaux']['cm'], sem['totaux']['td'], sem['totaux']['presentiel']), (80, 40, 120))
        self.assertEqual(sem['controles'], [])
        self.ec['UE1'].volume_cm = self.ec['UE1'].volume_td = 0
        self.ec['UE1'].save()
        self.mc['UE2'].credits = D('10')
        self.mc['UE2'].save()
        controles = ' | '.join(mq.maquette_classe(self.classe, [self.s5])[0]['controles'])
        self.assertIn('volume horaire', controles)
        self.assertIn('10 crédits pour l\'UE mais 12', controles)
        self.assertIn('28 crédits par étudiant', controles)

    def test_heures_planifiees_dans_l_emploi_du_temps(self):
        edt = EmploiDuTemps.objects.create(classe=self.classe, annee_scolaire=self.annee.libelle,
                                           annee_scolaire_fk=self.annee, est_actif=True)
        CreneauEmploiDuTemps.objects.create(emploi_du_temps=edt, jour='lundi', heure_debut=time(8), heure_fin=time(10),
                                            matiere=self.ec['UE1'], type_cours='cours', periode_scolaire=self.s5)
        p = mq.heures_planifiees(self.classe, self.s5)[self.ec['UE1'].id]
        self.assertEqual(p['cm'], D('32'))  # 2 h × 16 semaines
        ue1 = next(u for u in mq.maquette_classe(self.classe, [self.s5])[0]['ues'] if u['mc'] == self.mc['UE1'])
        ligne = ue1['ecs'][0]
        self.assertEqual(ligne['ecart'], D('2'))  # 32 h planifiées pour 30 h prévues
        # TD en deux groupes en parallèle : un étudiant n'en suit qu'un (32 h, pas 64 h).
        for nom in ('G1', 'G2'):
            g = GroupeEnseignement.objects.create(classe=self.classe, nom=nom)
            CreneauEmploiDuTemps.objects.create(emploi_du_temps=edt, jour='mardi', heure_debut=time(8), heure_fin=time(10),
                                                matiere=self.ec['UE1'], type_cours='td', groupe=g, periode_scolaire=self.s5)
        self.assertEqual(mq.heures_planifiees(self.classe, self.s5)[self.ec['UE1'].id]['td'], D('32'))


class ParcoursOptionsTests(BaseMaquette):
    def test_exclusions_et_inscriptions(self):
        self.assertEqual(mq.module_ids_exclus(self.awa, self.classe, self.annee),
                         {self.mc['OPTA'].module_id, self.mc['OPTB'].module_id})
        err = mq.enregistrer_inscriptions(self.classe, self.annee,
                                          {self.awa.id: {'options': [self.mc['OPTA'].id, self.mc['OPTB'].id]}})
        self.assertIn('2 UE choisie(s)', err[0])
        self.assertEqual(mq.enregistrer_inscriptions(self.classe, self.annee,
                                                     {self.awa.id: {'options': [self.mc['OPTB'].id]}}), [])
        self.assertEqual(mq.module_ids_exclus(self.awa, self.classe, self.annee), {self.mc['OPTA'].module_id})
        parc = Parcours.objects.create(classe=self.classe, nom='Finance')
        self.mc['UE2'].parcours = parc
        self.mc['UE2'].save()
        self.assertIn(self.mc['UE2'].module_id, mq.module_ids_exclus(self.awa, self.classe, self.annee))
        mq.enregistrer_inscriptions(self.classe, self.annee, {self.awa.id: {'parcours': parc.id,
                                                                            'options': [self.mc['OPTB'].id]}})
        self.assertNotIn(self.mc['UE2'].module_id, mq.module_ids_exclus(self.awa, self.classe, self.annee))

    def test_deliberation_ignore_option_non_choisie(self):
        mq.enregistrer_inscriptions(self.classe, self.annee, {self.awa.id: {'options': [self.mc['OPTA'].id]}})
        for code, note in (('UE1', 12), ('UE2', 11), ('OPTA', 13), ('OPTB', None)):
            MoyennePeriode.objects.create(eleve=self.awa, etablissement=self.etab, periode=self.s5, matiere=self.ec[code],
                                          est_moyenne_generale=False, moyenne_matiere=note, coefficient=1,
                                          credits=self.mc[code].credits, annee_scolaire=self.annee)
        d, _ = dlb.creer(self.etab, self.classe, self.annee, self.s5)
        dj = d.decisions.get()
        self.assertEqual((dj.decision, dj.credits_acquis, dj.credits_total), ('admis', D('30'), D('30')))


class EmploiSemestreGroupeTests(BaseMaquette):
    def setUp(self):
        super().setUp()
        self.s6 = PeriodeScolaire.objects.create(
            etablissement=self.etab, nom_periode='Semestre 6', type_periode='semestre', niveau_lmd='L3',
            date_debut=date(2027, 2, 1), date_fin=date(2027, 6, 30), annee_scolaire=self.annee.libelle,
            annee_scolaire_fk=self.annee, est_active=True)
        self.g1 = GroupeEnseignement.objects.create(classe=self.classe, nom='G1')
        self.g2 = GroupeEnseignement.objects.create(classe=self.classe, nom='G2')
        self.edt = EmploiDuTemps.objects.create(classe=self.classe, annee_scolaire=self.annee.libelle,
                                                annee_scolaire_fk=self.annee, est_actif=True)
        self.prof = Professeur.objects.create_user(
            username=f'p.{self.etab.pk}', email=f'p.{self.etab.pk}@t.local', password='Prof@Test1!', nom='Sy',
            prenom='A', telephone='770007777', numero_employe=f'M{self.etab.pk}', matiere_principale=self.ec['UE1'],
            etablissement=self.etab, niveau_enseignement='superieur', actif=True)
        self.td1 = CreneauEmploiDuTemps.objects.create(
            emploi_du_temps=self.edt, jour='mardi', heure_debut=time(8), heure_fin=time(10), matiere=self.ec['UE1'],
            type_cours='td', groupe=self.g1, periode_scolaire=self.s5, professeur=self.prof)

    def test_compatibilites(self):
        self.assertTrue(creneaux_compatibles(self.td1, groupe_id=self.g2.id))
        self.assertTrue(creneaux_compatibles(self.td1, periode_id=self.s6.id))
        self.assertFalse(creneaux_compatibles(self.td1, periode_id=self.s5.id, groupe_id=self.g1.id))
        # même enseignant, même heure, mais au semestre 6 : pas de conflit
        self.assertIsNone(conflit_ressources(self.etab, self.annee, None, 'mardi', time(8), time(10),
                                             professeur_id=self.prof.id, periode_id=self.s6.id))
        self.assertIsNotNone(conflit_ressources(self.etab, self.annee, None, 'mardi', time(8), time(10),
                                                professeur_id=self.prof.id, periode_id=self.s5.id))

    def test_ajout_td_g2_en_parallele_par_la_page(self):
        self.client.force_login(self.etab)
        url = reverse('administrateur_etablissement:ajouter_creneau', args=[self.edt.id])
        data = {'jour': 'mardi', 'heure_debut': '08:00', 'heure_fin': '10:00', 'matiere': self.ec['UE2'].id,
                'type_cours': 'td', 'periode_scolaire': self.s5.id, 'groupe': self.g2.id}
        self.client.post(url, data)
        c = CreneauEmploiDuTemps.objects.get(groupe=self.g2)
        self.assertEqual(c.periode_scolaire, self.s5)
        self.client.post(url, dict(data, groupe=self.g1.id, matiere=self.ec['OPTA'].id))  # G1 déjà occupé
        self.assertEqual(CreneauEmploiDuTemps.objects.filter(groupe=self.g1).count(), 1)
        r = self.client.get(reverse('administrateur_etablissement:detail_emploi_du_temps', args=[self.classe.id])
                            + f'?semestre={self.s6.id}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(list(r.context['tous_creneaux']), [])
        r = self.client.get(reverse('administrateur_etablissement:detail_emploi_du_temps', args=[self.classe.id])
                            + f'?semestre={self.s5.id}')
        self.assertEqual(len(r.context['tous_creneaux']), 2)
        self.assertContains(r, 'Semestre 6')


class PagesMaquetteTests(BaseMaquette):
    def test_pages(self):
        self.client.force_login(self.etab)
        r = self.client.get(reverse('directeur:liste_maquettes'))
        self.assertContains(r, 'GES L3 A')
        url = reverse('directeur:maquette_classe', args=[self.classe.id])
        r = self.client.get(url)
        self.assertContains(r, "Unités d'enseignement")
        post = {'action': 'maquette', 'semestre': self.s5.id}
        for code, mc in self.mc.items():
            post.update({f'mc_{mc.id}_credits': str(mc.credits), f'mc_{mc.id}_type': 'transversale' if code == 'UE2' else 'fondamentale'})
            if mc.optionnelle:
                post.update({f'mc_{mc.id}_optionnelle': 'on', f'mc_{mc.id}_groupe': 'Option S5', f'mc_{mc.id}_choix': '1'})
        for code, m in self.ec.items():
            post.update({f'ec_{m.id}_cm': '24', f'ec_{m.id}_td': '12', f'ec_{m.id}_tp': '0', f'ec_{m.id}_tpe': '30'})
        self.client.post(url, post)
        self.ec['UE1'].refresh_from_db()
        self.mc['UE2'].refresh_from_db()
        self.assertEqual((self.ec['UE1'].volume_cm, self.ec['UE1'].volume_tpe), (24, 30))
        self.assertEqual(self.mc['UE2'].type_ue, 'transversale')
        self.client.post(url, {'action': 'groupe_ajouter', 'nom': 'g1', 'type_groupe': 'td', 'capacite': '30'})
        self.client.post(url, {'action': 'groupe_ajouter', 'nom': 'g2', 'type_groupe': 'td', 'capacite': '30'})
        self.client.post(url, {'action': 'groupes_repartir', 'type_groupe': 'td'})
        self.assertEqual(GroupeEnseignement.objects.get(nom='G1').etudiants.count(), 1)
        self.client.post(url, {'action': 'parcours_ajouter', 'nom': 'Audit', 'code': 'AUD'})
        ins = reverse('directeur:inscriptions_pedagogiques', args=[self.classe.id])
        r = self.client.get(ins)
        self.assertContains(r, 'Option S5')
        g2 = GroupeEnseignement.objects.get(nom='G2')
        self.client.post(ins, {f'options_{self.awa.id}': [self.mc['OPTB'].id],
                               f'parcours_{self.awa.id}': Parcours.objects.get().id, f'groupe_td_{self.awa.id}': g2.id})
        i = InscriptionPedagogique.objects.get(eleve=self.awa)
        self.assertEqual(list(i.ues_optionnelles.all()), [self.mc['OPTB']])
        self.assertEqual(list(g2.etudiants.all()), [self.awa])
