"""Fiche élève refondue : direction (tous types) et enseignants (secondaire, primaire)."""
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
from school_admin.model.classe_model import Classe
from school_admin.model.evaluation_model import Evaluation, Note
from school_admin.model.matiere_model import Matiere
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.personnel_administratif_model import PersonnelAdministratif
from school_admin.model.presence_model import Presence
from school_admin.model.professeur_model import Professeur
from school_admin.services import fiche_eleve as fev
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement_type,
    _make_inscription,
)


class FicheEleveTests(TestCase):
    def _monter(self, type_etab, prefix, niveau='college'):
        self.etab = _make_etablissement_type(type_etab, prefix)
        self.annee = _make_annee(self.etab)
        s = str(self.etab.pk)
        self.classe = Classe.objects.create(nom='4e A', niveau=niveau, code_classe=f'4A-{s}', capacite_max=30,
                                            etablissement=self.etab, actif=True)
        self.math = Matiere.objects.create(nom=f'Mathématiques {s}', code=f'MA{s}'[:10], etablissement=self.etab,
                                           actif=True)
        self.svt = Matiere.objects.create(nom=f'SVT {s}', code=f'SV{s}'[:10], etablissement=self.etab, actif=True)
        self.prof = Professeur.objects.create_user(
            username=f'prof.fev.{s}', email=f'prof.fev.{s}@test.local', password='Prof@Test1!', nom='Sy',
            prenom='Ali', telephone='770000060', numero_employe=f'FV{s}', matiere_principale=self.math,
            etablissement=self.etab, niveau_enseignement='college', actif=True)
        self.periode = PeriodeScolaire.objects.create(
            etablissement=self.etab, nom_periode='1er Trimestre', type_periode='trimestre',
            date_debut=date(2026, 9, 1), date_fin=date(2026, 12, 15), annee_scolaire=self.annee.libelle,
            annee_scolaire_fk=self.annee, est_active=True)
        self.eleve = _make_eleve_simple(self.etab, self.classe, 'Diallo', 'Awa', suffix=prefix)
        _make_inscription(self.eleve, self.classe, self.annee, self.etab)

    def _note(self, matiere, valeur, publiee=True, prof=None):
        ev = Evaluation.objects.create(titre=f'Devoir {matiere.nom[:4]} {valeur}', classe=self.classe,
                                       professeur=prof or self.prof, matiere=matiere, date_evaluation=date(2026, 10, 5),
                                       bareme=20, periode_scolaire=self.periode, annee_scolaire=self.annee)
        return Note.objects.create(eleve=self.eleve, evaluation=ev, matiere=matiere, note=valeur,
                                   annee_scolaire=self.annee,
                                   statut_publication=Note.STATUT_PUBLIEE if publiee else Note.STATUT_BROUILLON)

    def test_service_secondaire(self):
        self._monter('lycée', 'fvs')
        self._note(self.math, 8)
        self._note(self.math, 12)
        self._note(self.svt, 15, publiee=False)
        Presence.objects.create(eleve=self.eleve, classe=self.classe, professeur=self.prof, etablissement=self.etab,
                                date=timezone.localdate(), statut='absent', annee_scolaire=self.annee)
        f = fev.construire(self.eleve, self.classe, self.etab, self.annee, vue='direction')
        self.assertEqual(f['nb_notes'], 3)
        self.assertEqual(f['brouillons'], 1)
        mats = {m['nom']: m for m in f['periodes'][0]['matieres']}
        self.assertEqual(mats[self.math.nom]['moyenne'], 10.0)
        self.assertEqual(f['presence']['absences'], 1)
        self.assertIn('completude', f)
        # Vue enseignant : seulement ses matières.
        fp = fev.construire(self.eleve, self.classe, self.etab, self.annee, vue='enseignant', matieres_prof=[self.math])
        self.assertEqual(fp['nb_notes'], 2)
        self.assertNotIn('finances', fp)

    def test_page_direction(self):
        self._monter('collège', 'fvd')
        self._note(self.math, 14)
        self.client.force_login(self.etab)
        url = reverse('secretaire:detail_eleve', args=[self.eleve.id])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        for onglet in ('apercu', 'notes', 'assiduite', 'discipline', 'famille', 'documents', 'acces'):
            self.assertContains(r, f'data-fe-panel="{onglet}"')
        self.assertContains(r, 'Awa')
        self.assertContains(r, 'id="modificationForm"')
        # Le formulaire de modification présélectionne bien la classe actuelle.
        self.assertContains(r, f'<option value="{self.classe.id}" selected>')
        self.assertContains(r, 'fe-transfert')
        self.assertContains(self.client.get(url + '?onglet=login'), 'data-fe-initial="acces"')

    def test_page_direction_primaire_et_superieur(self):
        for t, p, niv in (('primary', 'fvp', 'primaire'), ('superieur', 'fvu', 'licence')):
            self._monter(t, p, niveau=niv)
            self.client.force_login(self.etab)
            r = self.client.get(reverse('secretaire:detail_eleve', args=[self.eleve.id]))
            self.assertEqual(r.status_code, 200, t)
            if t == 'superieur':
                self.assertContains(r, 'Étudiant')

    def test_personnel_sans_comptabilite_ne_voit_pas_les_montants(self):
        self._monter('lycée', 'fvc')
        p = PersonnelAdministratif(username=f'sv.{self.etab.pk}', email=f'sv.{self.etab.pk}@aria-test.local',
                                   nom='Ba', prenom='Mor', telephone='770000061', fonction='surveillant_general',
                                   etablissement=self.etab, actif=True, permissions={'eleves_detail': True})
        p.set_password('Surv@Test1!')
        p.save()
        self.client.force_login(p)
        r = self.client.get(reverse('secretaire:detail_eleve', args=[self.eleve.id]))
        if r.status_code == 200:
            self.assertNotContains(r, 'data-fe-panel="finances"')

    def test_page_enseignant_secondaire(self):
        self._monter('lycée', 'fve')
        AffectationProfesseur.objects.create(professeur=self.prof, classe=self.classe, matiere=self.math,
                                             annee_scolaire=self.annee, statut='classique', actif=True)
        self._note(self.math, 16)
        self._note(self.svt, 4)
        presence = Presence.objects.create(eleve=self.eleve, classe=self.classe, professeur=self.prof,
                                           etablissement=self.etab, date=timezone.localdate() - timedelta(days=1),
                                           statut='absent', annee_scolaire=self.annee)
        self.client.force_login(self.prof)
        r = self.client.get(reverse('enseignant:detail_eleve', args=[self.eleve.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Devoir Math 16')
        self.assertNotContains(r, 'Devoir SVT 4')
        self.assertContains(r, f'data-fe-presence="{presence.id}"')
        self.assertNotContains(r, 'data-fe-panel="finances"')

    def test_page_enseignant_primaire_et_correction_appel(self):
        self._monter('primary', 'fvq', niveau='primaire')
        a = AffectationProfesseurPrimaire.objects.create(professeur=self.prof, classe=self.classe,
                                                         annee_scolaire=self.annee, actif=True)
        a.matieres.add(self.math)
        presence = Presence.objects.create(eleve=self.eleve, classe=self.classe, professeur=self.prof,
                                           etablissement=self.etab, date=timezone.localdate() - timedelta(days=1),
                                           statut='absent', annee_scolaire=self.annee)
        self.client.force_login(self.prof)
        r = self.client.get(reverse('enseignant_primaire:detail_eleve', args=[self.eleve.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-fe-panel="notes"')
        r = self.client.post(reverse('enseignant_primaire:modifier_presence', args=[presence.id]), {'statut': 'present'})
        presence.refresh_from_db()
        self.assertEqual(presence.statut, 'present')
        self.assertIn(reverse('enseignant_primaire:detail_eleve', args=[self.eleve.id]), r['Location'])
