"""Fiches employé côté direction : enseignant (secondaire, primaire, supérieur) et personnel administratif."""
from datetime import time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
from school_admin.model.classe_model import Classe
from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps, EmploiDuTemps
from school_admin.model.employe_dossier_model import DossierEmployeComplementaire
from school_admin.model.matiere_model import Matiere
from school_admin.model.personnel_administratif_model import PersonnelAdministratif
from school_admin.model.professeur_model import Professeur
from school_admin.services import fiche_employe as fe
from school_admin.tests.test_assistant_directeur_tools import _make_annee, _make_etablissement_type

ONGLETS = ('profil', 'enseignement', 'edt', 'presence', 'cahier', 'dossier', 'acces')


class FicheEnseignantTests(TestCase):
    def _etab(self, type_etab, prefix):
        self.etab = _make_etablissement_type(type_etab, prefix)
        self.annee = _make_annee(self.etab)
        s = str(self.etab.pk)
        self.classe = Classe.objects.create(nom='5e B', niveau='college', code_classe=f'5B-{s}', capacite_max=30,
                                            etablissement=self.etab, actif=True)
        self.math = Matiere.objects.create(nom=f'Mathématiques {s}', code=f'MA{s}'[:10], etablissement=self.etab,
                                           actif=True)
        self.svt = Matiere.objects.create(nom=f'SVT {s}', code=f'SV{s}'[:10], etablissement=self.etab, actif=True)
        self.prof = Professeur.objects.create_user(
            username=f'prof.fe.{s}', email=f'prof.fe.{s}@test.local', password='Prof@Test1!', nom='Ba',
            prenom='Aïda', telephone='770000040', numero_employe=f'FE{s}', matiere_principale=self.math,
            etablissement=self.etab, niveau_enseignement='college', actif=True, type_contrat='vacataire',
            prix_volume_horaire=Decimal('5000'), date_embauche=timezone.localdate() - timedelta(days=800))
        self.client.force_login(self.etab)

    def _creneau(self, matiere, debut, fin, jour='lundi'):
        edt, _ = EmploiDuTemps.objects.get_or_create(
            classe=self.classe, annee_scolaire=self.annee.libelle,
            defaults={'annee_scolaire_fk': self.annee, 'est_actif': True, 'statut_publication': 'publie'})
        return CreneauEmploiDuTemps.objects.create(emploi_du_temps=edt, jour=jour, heure_debut=debut, heure_fin=fin,
                                                   matiere=matiere, professeur=self.prof, type_cours='cours')

    def test_secondaire_regroupe_affectations_et_emploi_du_temps(self):
        self._etab('lycée', 'fes')
        AffectationProfesseur.objects.create(professeur=self.prof, classe=self.classe, matiere=self.math,
                                             annee_scolaire=self.annee, statut='classique', actif=True)
        self._creneau(self.math, time(8, 0), time(10, 0))
        self._creneau(self.svt, time(10, 0), time(11, 0), jour='mardi')
        f = fe.profil_enseignant(self.prof, self.annee)
        self.assertEqual(f['nb_classes'], 1)
        self.assertEqual(f['heures_semaine'], 3.0)
        self.assertFalse(f['classes'][0]['hors_edt'])
        self.assertEqual([m.id for m in f['matieres_non_declarees']], [self.svt.id])
        self.assertEqual(len(f['semaine']), 5)

        url = reverse('professeur:detail_professeur', args=[self.prof.id])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        for onglet in ONGLETS:
            self.assertContains(r, f'data-fe-panel="{onglet}"')
        self.assertContains(r, '5e B')
        self.assertContains(r, 'Enseignée(s) mais absente(s) de sa fiche')
        self.assertContains(r, '08:00')
        # Anciens liens d'onglet toujours valides.
        self.assertContains(self.client.get(url + '?onglet=connexion'), 'data-fe-initial="acces"')
        self.assertContains(self.client.get(url + '?onglet=pointage'), 'data-fe-initial="presence"')

    def test_classe_affectee_sans_creneau_signalee(self):
        self._etab('collège', 'fec')
        AffectationProfesseur.objects.create(professeur=self.prof, classe=self.classe, matiere=self.math,
                                             annee_scolaire=self.annee, statut='classique', actif=True)
        f = fe.profil_enseignant(self.prof, self.annee)
        self.assertTrue(f['classes'][0]['hors_edt'])
        self.assertTrue(f['edt_vide'])
        r = self.client.get(reverse('professeur:detail_professeur', args=[self.prof.id]) + '?onglet=enseignement')
        self.assertContains(r, 'aucun créneau publié')

    def test_primaire_polyvalent(self):
        self._etab('primary', 'fep')
        Classe.objects.filter(pk=self.classe.pk).update(niveau='primaire')
        self.classe.refresh_from_db()
        a = AffectationProfesseurPrimaire.objects.create(professeur=self.prof, classe=self.classe,
                                                         annee_scolaire=self.annee, actif=True)
        a.matieres.add(self.math, self.svt)
        f = fe.profil_enseignant(self.prof, self.annee)
        self.assertEqual(len(f['classes'][0]['matieres']), 2)
        self.assertEqual(f['matieres_non_declarees'], [])
        r = self.client.get(reverse('professeur:detail_professeur', args=[self.prof.id]))
        self.assertContains(r, 'Enseignant du primaire')
        self.assertContains(r, 'Enseignant polyvalent')

    def test_superieur(self):
        self._etab('superieur', 'feu')
        r = self.client.get(reverse('professeur:detail_professeur', args=[self.prof.id]))
        self.assertContains(r, 'Enseignant du supérieur')

    def test_completude_et_echeance(self):
        self._etab('lycée', 'fed')
        dossier = DossierEmployeComplementaire.objects.create(professeur=self.prof, nationalite='Sénégalaise',
                                                date_fin_contrat=timezone.localdate() + timedelta(days=20))
        c = fe.completude_dossier(self.prof, dossier, [])
        self.assertIn('Pièces justificatives', c['manquants'])
        self.assertNotIn('Nationalité', c['manquants'])
        self.assertTrue(0 < c['taux'] < 100)
        e = fe.echeance_contrat(dossier)
        self.assertTrue(e['proche'])
        self.assertFalse(e['expire'])
        self.assertEqual(fe.anciennete(timezone.localdate() - timedelta(days=400)), '1 an et 1 mois')


class FichePersonnelTests(TestCase):
    def test_fiche_personnel(self):
        etab = _make_etablissement_type('lycée', 'fpa')
        _make_annee(etab)
        p = PersonnelAdministratif(username=f'sec.{etab.pk}', email=f'sec.{etab.pk}@aria-test.local', nom='Diop',
                                   prenom='Fatou', telephone='770000077', fonction='secretaire', etablissement=etab,
                                   actif=True, permissions={}, mot_de_passe_provisoire='Prov@1234')
        p.set_password('Sec@Test1!')
        p.save()
        self.client.force_login(etab)
        url = reverse('personnel:detail_personnel', args=[p.id])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        for onglet in ('profil', 'autorisations', 'dossier', 'acces'):
            self.assertContains(r, f'data-fe-panel="{onglet}"')
        self.assertContains(r, 'Prov@1234')
        self.assertContains(r, 'Secrétaire')
        self.assertContains(self.client.get(url + '?onglet=connexion'), 'data-fe-initial="acces"')
        # La modification passe par le formulaire de la modale.
        r = self.client.post(reverse('personnel:modifier_personnel', args=[p.id]), {
            'nom': 'Diop', 'prenom': 'Fatou Bintou', 'email': p.email, 'telephone': '770000077',
            'fonction': 'secretaire'})
        p.refresh_from_db()
        self.assertEqual(p.prenom, 'Fatou Bintou')
        # Mise à jour du dossier depuis l'onglet.
        self.client.post(url, {'action': 'update_dossier', 'nationalite': 'Sénégalaise'})
        self.assertEqual(DossierEmployeComplementaire.objects.get(personnel_administratif=p).nationalite, 'Sénégalaise')

    def test_fonction_hors_liste_reste_modifiable(self):
        etab = _make_etablissement_type('lycée', 'fpc')
        _make_annee(etab)
        p = PersonnelAdministratif(username=f'cen.{etab.pk}', email=f'cen.{etab.pk}@aria-test.local', nom='Ndoye',
                                   prenom='Awa', telephone='770000078', fonction='censeur', etablissement=etab,
                                   actif=True, permissions={})
        p.set_password('Cen@Test1!')
        p.save()
        self.client.force_login(etab)
        r = self.client.get(reverse('personnel:detail_personnel', args=[p.id]))
        self.assertContains(r, '<option value="censeur" selected>')
        self.client.post(reverse('personnel:modifier_personnel', args=[p.id]), {
            'nom': 'Ndoye', 'prenom': 'Awa Marie', 'email': p.email, 'telephone': '770000078', 'fonction': 'censeur'})
        p.refresh_from_db()
        self.assertEqual(p.prenom, 'Awa Marie')
