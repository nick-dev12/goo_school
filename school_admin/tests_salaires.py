"""Salaires et paiements : personnes payées par l'établissement, agents de l'État exclus, versements en caisse."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from school_admin.model.caisse_etablissement_model import DepenseEtablissement, PaiePersonnelMois
from school_admin.model.employe_dossier_model import DossierEmployeComplementaire
from school_admin.model.personnel_administratif_model import PersonnelAdministratif
from school_admin.services import salaires as svc
from school_admin.tests_service_cc import Base

D = Decimal
MOIS = date(2026, 11, 1)


class SalairesTests(Base):
    def setUp(self):
        super().setUp()
        self.secretaire = self._personnel('Diallo', 'Mariama', 'etablissement', D('180000'))
        self.agent = self._personnel('Faye', 'Moussa', 'etat', D('250000'))

    def _personnel(self, nom, prenom, prise, salaire):
        p = PersonnelAdministratif.objects.create(
            username=f'{prenom.lower()}.{self.etab.pk}', nom=nom, prenom=prenom, telephone='770000001',
            fonction='secretaire', etablissement=self.etab, actif=True, prise_en_charge=prise)
        DossierEmployeComplementaire.objects.create(personnel_administratif=p, salaire_base=salaire)
        return p

    def test_qui_est_dans_la_paie(self):
        self.td.prise_en_charge = 'etat'
        self.td.save()
        paie = svc.paie_du_mois(self.etab, self.annee, MOIS)
        noms = {l.nom for l in paie['lignes']}
        self.assertIn(self.secretaire.nom_complet, noms)
        self.assertIn(self.cm.nom_complet, noms)
        self.assertNotIn(self.agent.nom_complet, noms)
        self.assertNotIn(self.td.nom_complet, noms)
        self.assertEqual(paie['agents_etat'], 2)
        ligne = next(l for l in paie['lignes'] if l.personne == self.secretaire)
        self.assertEqual((ligne.statut, ligne.montant), ('a_payer', D('180000')))
        prof = next(l for l in paie['lignes'] if l.personne == self.cm)
        self.assertEqual(prof.statut, 'a_renseigner')  # permanent sans salaire mensuel

    def test_versement_enregistre_en_caisse(self):
        paie = svc.payer_personnel(self.etab, self.secretaire, MOIS, D('175000'), jour=date(2026, 11, 28),
                                   annee_scolaire=self.annee)
        self.assertEqual((paie.montant, paie.depense.motif, paie.depense.montant), (D('175000'), 'salaire', D('175000')))
        self.assertTrue(DepenseEtablissement.objects.filter(pk=paie.depense_id, statut='validee').exists())
        with self.assertRaises(ValueError):
            svc.payer_personnel(self.etab, self.secretaire, MOIS, D('175000'), annee_scolaire=self.annee)
        with self.assertRaises(ValueError):
            svc.payer_personnel(self.etab, self.agent, MOIS, D('250000'), annee_scolaire=self.annee)
        ligne = next(l for l in svc.paie_du_mois(self.etab, self.annee, MOIS)['lignes'] if l.personne == self.secretaire)
        self.assertEqual((ligne.statut, ligne.montant_paye), ('paye', D('175000')))

    def test_page(self):
        self.client.force_login(self.etab)
        url = reverse('directeur:salaires')
        page = self.client.get(url + '?mois=2026-11')
        self.assertContains(page, 'Salaires et paiements')
        self.assertContains(page, 'Mariama')
        self.assertNotContains(page, 'Moussa')
        self.client.post(url, {'action': 'payer', 'type': 'personnel', 'id': self.secretaire.pk, 'mois': '2026-11',
                               'montant': '180 000', 'date': '2026-11-28', 'onglet': 'personnel'})
        self.assertTrue(PaiePersonnelMois.objects.filter(personnel=self.secretaire, mois=MOIS).exists())
        historique = self.client.get(reverse('directeur:historique_salaires', args=['personnel', self.secretaire.pk])).json()
        self.assertEqual((historique['nb'], historique['mois'][0]['mois']), (1, 'novembre 2026'))
        self.assertContains(self.client.get(reverse('directeur:gestion_pedagogique')), 'Salaires et paiements')

    def test_salaire_verse_par_enregistre_depuis_les_formulaires(self):
        from school_admin.utils.employe_dossier_utils import (
            dossier_form_data_from_dossier,
            get_or_create_dossier,
            save_dossier_from_post_if_any,
            update_dossier_from_post,
        )
        save_dossier_from_post_if_any(professeur=self.cm, post_data={'prise_en_charge': 'etat'})
        self.cm.refresh_from_db()
        self.assertEqual(self.cm.prise_en_charge, 'etat')
        dossier = get_or_create_dossier(personnel=self.agent)
        update_dossier_from_post(dossier, {'prise_en_charge': 'etablissement', 'salaire_base': '250000'})
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.prise_en_charge, 'etablissement')
        self.assertEqual(dossier_form_data_from_dossier(dossier)['prise_en_charge'], 'etablissement')

    def test_personnel_paye_a_l_heure(self):
        DossierEmployeComplementaire.objects.filter(personnel_administratif=self.secretaire).update(salaire_base=None)
        self.secretaire.prix_volume_horaire = D('2000')
        self.secretaire.save()
        ligne = next(l for l in svc.paie_du_mois(self.etab, self.annee, MOIS)['lignes'] if l.personne == self.secretaire)
        self.assertEqual((ligne.statut, ligne.mode, ligne.montant), ('a_saisir', 'heure', None))
        paie = svc.payer_personnel(self.etab, self.secretaire, MOIS, heures='12,5', annee_scolaire=self.annee)
        self.assertEqual(paie.montant, D('25000.00'))
        self.assertIn('12,5 h', paie.depense.libelle)

    def test_payer_tout_le_mois(self):
        payes, ignores = svc.payer_tout(self.etab, self.annee, MOIS)
        self.assertEqual([n for n, _m in payes], [self.secretaire.nom_complet])
        ignores_noms = {n for n, _r in ignores}
        self.assertIn(self.cm.nom_complet, ignores_noms)  # salaire mensuel non renseigné
        self.assertNotIn(self.agent.nom_complet, ignores_noms)  # agent de l'État : hors paie
        self.assertEqual(svc.payer_tout(self.etab, self.annee, MOIS)[0], [])  # déjà payé : rien de plus

    def test_enseignant_paye_depuis_la_page(self):
        self.td.type_contrat = 'vacataire'
        self.td.prix_volume_horaire = D('5000')
        self.td.save()
        ligne = next(l for l in svc.paie_du_mois(self.etab, self.annee, MOIS)['lignes'] if l.personne == self.td)
        self.assertEqual(ligne.statut, 'rien')  # aucune séance planifiée
        with self.assertRaises(ValueError):
            svc.payer_enseignant(self.etab, self.td, MOIS, self.annee)
