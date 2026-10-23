"""Supérieur (LMD) — étape 5 : admissions et concours, diplômes, nouveaux niveaux."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from school_admin.model.academic_structure_model import Department
from school_admin.model.admission_model import Candidature, Concours, Diplome, EpreuveConcours, NoteConcours
from school_admin.model.classe_model import Classe
from school_admin.model.deliberation_model import DecisionJury, Deliberation, UECapitalisee
from school_admin.model.inscription_eleve_model import InscriptionEleve
from school_admin.model.module_model import Module
from school_admin.services import admissions as adm
from school_admin.services import diplomes as dip
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement_type,
    _make_inscription,
)

D = Decimal


class Base(TestCase):
    def setUp(self):
        self.etab = _make_etablissement_type('superieur', 'adm')
        self.annee = _make_annee(self.etab)
        s = str(self.etab.pk)
        self.dept = Department.objects.create(nom='Sciences juridiques', sigle='DRT', mention='Droit', domaine='Droit',
                                              etablissement=self.etab)
        self.l1 = Classe.objects.create(nom='DRT L1 A', niveau='superieur', niveau_lmd='L1', code_classe=f'L1-{s}',
                                        capacite_max=120, etablissement=self.etab, department=self.dept)
        self.c = Concours.objects.create(etablissement=self.etab, annee_scolaire=self.annee, intitule='Entrée en L1 Droit',
                                         classe_cible=self.l1, mode='dossier', places=2, places_attente=1,
                                         seuil_admission=D('10'))

    def cand(self, nom, moy=None, concours=None, statut='recevable', **kw):
        c = Candidature(concours=concours or self.c, nom=nom, prenom='X', sexe='F', date_naissance=date(2007, 5, 1),
                        lieu_naissance='Dakar', telephone='770000000', moyenne_bac=moy, statut=statut, **kw)
        adm.numeroter(c)
        c.save()
        return c


class ClassementTests(Base):
    def test_dossier_listes_et_ex_aequo(self):
        a, b, c, d, e = (self.cand('A', D('14')), self.cand('B', D('12')), self.cand('C', D('12')),
                         self.cand('D', D('11')), self.cand('E', D('9')))
        st = adm.calculer(self.c)
        for x in (a, b, c, d, e):
            x.refresh_from_db()
        self.assertEqual((a.rang, a.statut), (1, 'admis'))
        self.assertEqual({b.rang, c.rang}, {2})                       # ex æquo
        self.assertEqual(sorted([b.statut, c.statut]), ['admis', 'attente'])
        self.assertEqual((d.statut, e.statut), ('refuse', 'refuse'))
        self.assertIn('seuil', e.motif)
        self.assertEqual((st['admis'], st['attente'], st['barre']), (2, 1, D('12.00')))
        self.assertTrue(a.numero.endswith('-0001'))

    def test_concours_epreuves_eliminatoire_absent(self):
        self.c.mode = 'concours'
        self.c.places = 5
        self.c.save()
        cg = EpreuveConcours.objects.create(concours=self.c, nom='Culture générale', coefficient=2, note_eliminatoire=D('5'))
        fr = EpreuveConcours.objects.create(concours=self.c, nom='Français', coefficient=1)
        a, b, c = self.cand('A'), self.cand('B'), self.cand('C')
        err = adm.enregistrer_notes(self.c, {(a.id, cg.id): '25'})
        self.assertIn('0 à 20', err[0])
        self.assertEqual(adm.enregistrer_notes(self.c, {
            (a.id, cg.id): '14', (a.id, fr.id): '11', (b.id, cg.id): '4', (b.id, fr.id): '18',
            (c.id, cg.id): 'abs', (c.id, fr.id): '15'}), [])
        adm.calculer(self.c)
        a.refresh_from_db(); b.refresh_from_db(); c.refresh_from_db()
        self.assertEqual((a.total, a.statut), (D('13.00'), 'admis'))   # (14×2 + 11) / 3
        self.assertEqual((b.statut, c.statut), ('refuse', 'refuse'))
        self.assertIn('éliminatoire', b.motif)
        self.assertIn('Absent', c.motif)

    def test_mixte_et_desistement(self):
        self.c.mode, self.c.poids_dossier = 'mixte', 40
        self.c.save()
        ep = EpreuveConcours.objects.create(concours=self.c, nom='Oral', coefficient=1)
        a, b, c = self.cand('A', D('15')), self.cand('B', D('12')), self.cand('C', D('11'))
        for x, n in ((a, 12), (b, 14), (c, 13)):
            NoteConcours.objects.create(candidature=x, epreuve=ep, note=D(n))
        adm.calculer(self.c)
        a.refresh_from_db(); b.refresh_from_db(); c.refresh_from_db()
        self.assertEqual(a.total, D('13.20'))   # 15×0,4 + 12×0,6
        self.assertEqual([a.statut, b.statut, c.statut], ['admis', 'admis', 'attente'])
        promu = adm.desister(a)
        c.refresh_from_db()
        self.assertEqual((promu, c.statut), (c, 'admis'))

    def test_inscription_d_un_admis(self):
        a = self.cand('Ndoye', D('15'), contact_nom='Ndoye', contact_prenom='Moussa', contact_telephone='771112233')
        adm.calculer(self.c)
        a.refresh_from_db()
        eleve = adm.inscrire(a)
        a.refresh_from_db()
        self.assertEqual((a.statut, a.eleve, eleve.classe), ('inscrit', eleve, self.l1))
        self.assertTrue(InscriptionEleve.objects.filter(eleve=eleve, classe=self.l1).exists())
        with self.assertRaises(adm.AdmissionErreur):
            adm.inscrire(a)


class PagesAdmissionsTests(Base):
    def test_formulaire_public(self):
        url = reverse('school_admin:candidature_publique', args=[self.c.jeton])
        r = self.client.get(url)
        self.assertContains(r, 'Déposer ma candidature')
        r = self.client.post(url, {'nom': 'Faye', 'prenom': 'Khady', 'sexe': 'F', 'date_naissance': '2007-02-03',
                                   'lieu_naissance': 'Thiès', 'telephone': '770001122', 'serie_bac': 'S2',
                                   'annee_bac': '2026', 'moyenne_bac': '13,5', 'piece_bac': 'on'})
        self.assertContains(r, 'bien été enregistrée')
        c = Candidature.objects.get(nom='Faye')
        self.assertEqual((c.en_ligne, c.moyenne_bac, c.pieces, c.statut), (True, D('13.5'), ['bac'], 'soumise'))
        r = self.client.post(url, {'nom': 'Sans', 'prenom': 'Bac', 'sexe': 'M', 'date_naissance': '2007-02-03',
                                   'lieu_naissance': 'Thiès', 'telephone': '77'})
        self.assertContains(r, 'moyenne du bac est obligatoire')
        self.c.statut = 'clos'
        self.c.save()
        self.assertContains(self.client.get(url), 'closes')

    def test_parcours_administration(self):
        self.client.force_login(self.etab)
        r = self.client.post(reverse('directeur:liste_concours'), {
            'intitule': 'Master Droit des affaires', 'mode': 'concours', 'classe_cible': self.l1.id, 'places': '1',
            'places_attente': '1', 'seuil_admission': '10', 'diplome_requis': 'licence'})
        c = Concours.objects.get(intitule='Master Droit des affaires')
        url = reverse('directeur:detail_concours', args=[c.id])
        self.assertRedirects(r, url)
        self.client.post(url, {'action': 'epreuve_ajouter', 'nom': 'Écrit', 'coefficient': '1', 'onglet': 'notes'})
        r = self.client.post(url, {'action': 'candidature', 'nom': 'Sy', 'prenom': 'Awa', 'sexe': 'F',
                                   'date_naissance': '2003-01-01', 'lieu_naissance': 'Dakar', 'telephone': '77',
                                   'diplome_precedent': 'Licence en Droit', 'moyenne_diplome': '13'}, follow=True)
        self.assertContains(r, 'enregistrée')
        cand = Candidature.objects.get(nom='Sy')
        ep = c.epreuves.get()
        self.client.post(url, {'action': 'notes', f'n_{cand.id}_{ep.id}': '14', 'onglet': 'notes'})
        self.client.post(url, {'action': 'publier', 'onglet': 'resultats'})
        cand.refresh_from_db()
        c.refresh_from_db()
        self.assertEqual((cand.statut, c.statut), ('admis', 'publie'))
        for onglet in ('candidatures', 'notes', 'resultats', 'ajouter'):
            self.assertEqual(self.client.get(url + f'?onglet={onglet}').status_code, 200)
        self.assertContains(self.client.get(reverse('directeur:liste_concours')), 'Master Droit des affaires')


class DiplomesTests(Base):
    def setUp(self):
        super().setUp()
        s = str(self.etab.pk)
        self.l3 = Classe.objects.create(nom='DRT L3 A', niveau='superieur', niveau_lmd='L3', code_classe=f'L3-{s}',
                                        capacite_max=60, etablissement=self.etab, department=self.dept)
        self.e = _make_eleve_simple(self.etab, self.l3, 'Diallo', 'Fatou', 'F', f'd{s}')
        _make_inscription(self.e, self.l3, self.annee, self.etab)
        for i in range(6):
            mod = Module.objects.create(nom=f'UE {i}', code=f'U{i}-{s}', etablissement=self.etab, department=self.dept)
            UECapitalisee.objects.create(eleve=self.e, module=mod, credits=D('30'), moyenne=D('12'))
        d = Deliberation.objects.create(etablissement=self.etab, classe=self.l3, annee_scolaire=self.annee,
                                        statut=Deliberation.STATUT_CLOTUREE)
        DecisionJury.objects.create(deliberation=d, eleve=self.e, decision='admis', moyenne_jury=D('14.20'),
                                    mention='Bien', credits_acquis=D('60'), credits_total=D('60'))

    def test_eligibilite_et_delivrance(self):
        l = dip.situation(self.l3, [self.e])[0]
        self.assertTrue(l['eligible'])
        self.assertEqual((l['credits'], l['mention']), (D('180'), 'Bien'))
        crees = dip.delivrer(self.l3, [self.e], self.annee)
        self.assertEqual(len(crees), 1)
        d = crees[0]
        self.assertEqual(d.intitule, 'Licence en Droit')
        self.assertIn('-L3-00001', d.numero)
        self.assertEqual(dip.delivrer(self.l3, [self.e], self.annee), [])  # pas de doublon
        self.assertIsNone(dip.diplome_de(self.l1))

    def test_non_eligible_si_credits_insuffisants(self):
        UECapitalisee.objects.filter(eleve=self.e).first().delete()
        l = dip.situation(self.l3, [self.e])[0]
        self.assertFalse(l['eligible'])
        self.assertIn('150 crédits capitalisés sur 180', l['motif'])

    def test_pages(self):
        self.client.force_login(self.etab)
        self.assertContains(self.client.get(reverse('directeur:liste_diplomes')), 'DRT L3 A')
        url = reverse('directeur:diplomes_classe', args=[self.l3.id])
        self.assertContains(self.client.get(url), 'Éligible')
        self.client.post(url, {'action': 'delivrer', 'eleves': [self.e.id]})
        d = Diplome.objects.get()
        r = self.client.get(reverse('directeur:imprimer_diplome', args=[d.id]))
        self.assertContains(r, 'ATTESTATION DE DIPLÔME')
        self.assertContains(r, 'Licence en Droit')


class NiveauxTests(TestCase):
    def test_nouveaux_niveaux(self):
        from school_admin.controllers.classe_controller import NIVEAUX_SUPERIEUR_CHOICES
        from school_admin.model.classe_model import NIVEAU_LMD_LIBELLES_COMPLETS
        from school_admin.model.periode_model import SEMESTRES_PAR_NIVEAU_LMD

        codes = {c for c, _ in NIVEAUX_SUPERIEUR_CHOICES}
        self.assertTrue({'CPI1', 'ING3', 'MBA2', 'DU', 'MED7'} <= codes)
        self.assertEqual([n for n, _ in SEMESTRES_PAR_NIVEAU_LMD['ING3']], ['Semestre 9', 'Semestre 10'])
        self.assertEqual([n for n, _ in SEMESTRES_PAR_NIVEAU_LMD['LP']], ['Semestre 5', 'Semestre 6'])
        self.assertIn('Cycle ingénieur', NIVEAU_LMD_LIBELLES_COMPLETS['ING1'])
        self.assertEqual(dip.DIPLOMES['ING3'][0], "Diplôme d'ingénieur")
