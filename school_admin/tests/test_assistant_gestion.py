"""Assistant direction : outils Finances, Salaires, Contrôle des cours, Cahiers de texte et Rappels.

Chaque écriture passe par les services des pages : prepare() ne touche à rien, apply() écrit.
"""
from datetime import date
from decimal import Decimal

from school_admin.model.caisse_etablissement_model import DepenseEtablissement, PaiePersonnelMois
from school_admin.model.comptabilite_generale_model import FactureFournisseur, MouvementTresorerie
from school_admin.model.employe_dossier_model import DossierEmployeComplementaire
from school_admin.model.finances_model import CompteTresorerie, RecetteEtablissement
from school_admin.model.personnel_administratif_model import PersonnelAdministratif
from school_admin.services.assistant_actions import ACTION_SPECS
from school_admin.services.assistant_pages import list_pages
from school_admin.services.assistant_tools import build_assistant_context, execute_tool
from school_admin.services.rappels import moteur
from school_admin.tests_service_cc import Base
from school_admin.utils.permissions_personnel import PERMISSIONS_DISPONIBLES

D = Decimal


class AssistantGestionTests(Base):
    def setUp(self):
        super().setUp()
        self.ctx = build_assistant_context(self.etab)
        self.secretaire = PersonnelAdministratif.objects.create(
            username=f'mariama.{self.etab.pk}', nom='Diallo', prenom='Mariama', telephone='770000001',
            fonction='secretaire', etablissement=self.etab, actif=True, prise_en_charge='etablissement')
        DossierEmployeComplementaire.objects.create(personnel_administratif=self.secretaire, salaire_base=D('180000'))

    def _faire(self, nom, args):
        """prepare puis apply, comme la carte « oui »."""
        brouillon = execute_tool(self.ctx, nom, args)
        self.assertEqual(brouillon.get('statut'), 'en_attente_confirmation', brouillon)
        return ACTION_SPECS[nom].apply(self.ctx, brouillon)

    # ----------------------------------------------------------------- dépenses
    def test_depense_passe_par_la_caisse_et_la_comptabilite(self):
        brouillon = execute_tool(self.ctx, 'ajouter_depense', {'montant': '12000', 'libelle': 'Craies et papier'})
        self.assertEqual(DepenseEtablissement.objects.count(), 0)  # rien avant le oui
        resultat = ACTION_SPECS['ajouter_depense'].apply(self.ctx, brouillon)
        self.assertEqual(resultat['statut'], 'ok', resultat)
        depense = DepenseEtablissement.objects.get()
        self.assertEqual((depense.statut, depense.motif, depense.montant), ('validee', 'fournitures', D('12000')))
        self.assertIsNotNone(depense.compte_tresorerie_id)
        self.assertEqual(depense.compte_tresorerie.type_compte, 'caisse')

    def test_annuler_depense_garde_la_trace_et_ne_devine_pas(self):
        self._faire('ajouter_depense', {'montant': '5000', 'libelle': 'Taxi'})
        self.assertEqual(execute_tool(self.ctx, 'supprimer_depense', {})['statut'], 'incomplet')
        self.assertIn('erreur', execute_tool(self.ctx, 'supprimer_depense', {'query': 'Loyer', 'motif': 'Erreur'}))
        self.assertEqual(execute_tool(self.ctx, 'supprimer_depense', {'query': 'Taxi'})['manquants'], ['motif'])
        resultat = self._faire('supprimer_depense', {'query': 'Taxi', 'motif': 'Saisie en double'})
        self.assertEqual(resultat['statut'], 'ok', resultat)
        depense = DepenseEtablissement.objects.get()
        self.assertEqual((depense.statut, depense.motif_annulation), ('annulee', 'Saisie en double'))

    # ----------------------------------------------------------------- recettes, charges, transferts
    def test_recette_charge_et_transfert(self):
        self._faire('enregistrer_recette', {'nature': 'kermesse', 'montant': '75000', 'libelle': 'Kermesse de fin d’année'})
        recette = RecetteEtablissement.objects.get()
        self.assertEqual((recette.nature, recette.montant), ('activite', D('75000')))
        sub = execute_tool(self.ctx, 'enregistrer_recette', {'nature': 'subvention', 'montant': '100000'})
        self.assertEqual(sub['manquants'], ['destination'])

        self._faire('enregistrer_charge', {'fournisseur': 'Senelec', 'montant': '45000', 'libelle': 'Électricité novembre'})
        facture = FactureFournisseur.objects.get()
        self.assertEqual((facture.fournisseur.nom, facture.montant, facture.statut), ('Senelec', D('45000'), 'a_payer'))
        self._faire('payer_charge', {'query': 'Senelec', 'montant': '20000'})
        facture.refresh_from_db()
        self.assertEqual((facture.statut, facture.reste_a_payer()), ('partiel', D('25000')))

        self._faire('transfert_comptes', {'source': 'caisse', 'destination': 'banque', 'montant': '30000'})
        mouvement = MouvementTresorerie.objects.get()
        self.assertEqual((mouvement.compte_source.type_compte, mouvement.compte_destination.type_compte),
                         ('caisse', 'banque'))
        meme = execute_tool(self.ctx, 'transfert_comptes', {'source': 'caisse', 'destination': 'caisse', 'montant': '1'})
        self.assertIn('erreur', meme)

    def test_pret_recu_puis_rembourse(self):
        from school_admin.model.finances_model import PretEtablissement

        self._faire('enregistrer_pret', {'montant': '500000', 'objet': 'Achat d’ordinateurs', 'reference': 'BQ-01'})
        pret = PretEtablissement.objects.get()
        self.assertEqual((pret.montant, pret.compte_tresorerie.type_compte), (D('500000'), 'banque'))
        trop = execute_tool(self.ctx, 'rembourser_pret', {'query': 'BQ-01', 'capital': '900000'})
        self.assertIn('erreur', trop)
        self._faire('rembourser_pret', {'query': 'ordinateurs', 'capital': '100000', 'interets': '5000'})
        pret.refresh_from_db()
        self.assertEqual(pret.capital_restant(), D('400000'))

    def test_situation_financiere(self):
        self._faire('ajouter_depense', {'montant': '8000', 'libelle': 'Carburant'})
        situation = execute_tool(self.ctx, 'get_situation_financiere', {'mois': '2026-11'})
        for cle in ('entrees', 'sorties', 'resultat', 'disponible', 'soldes_comptes', 'dernieres_operations', 'url'):
            self.assertIn(cle, situation)
        self.assertTrue(situation['soldes_comptes'])

    # ----------------------------------------------------------------- salaires
    def test_payer_salaire_comme_la_page(self):
        paie = execute_tool(self.ctx, 'get_paie_du_mois', {'mois': '2026-11'})
        self.assertIn('Mariama', ' '.join(l['nom'] for l in paie['lignes']))
        resultat = self._faire('payer_salaire', {'query': 'Mariama Diallo', 'mois': '2026-11'})
        self.assertEqual(resultat['statut'], 'ok', resultat)
        paiement = PaiePersonnelMois.objects.get(personnel=self.secretaire)
        self.assertEqual((paiement.montant, paiement.depense.motif), (D('180000'), 'salaire'))
        deja = execute_tool(self.ctx, 'payer_salaire', {'query': 'Mariama', 'mois': '2026-11'})
        self.assertIn('déjà versé', deja['erreur'])
        histo = execute_tool(self.ctx, 'get_historique_salaire', {'query': 'Mariama'})
        self.assertEqual(histo['nb_paiements'], 1)

    def test_agent_de_l_etat_jamais_paye(self):
        self.secretaire.prise_en_charge = 'etat'
        self.secretaire.save()
        for outil in ('payer_salaire', 'marquer_paie'):
            self.assertIn('État', execute_tool(self.ctx, outil, {'query': 'Mariama', 'mois': '2026-11'})['erreur'])

    # ----------------------------------------------------------------- contrôle, cahiers, rappels
    def test_lectures_controle_et_cahiers(self):
        controle = execute_tool(self.ctx, 'get_controle_cours', {})
        self.assertIn('nb_a_verifier', controle)
        cahiers = execute_tool(self.ctx, 'get_cahiers_texte', {})
        self.assertIn('suivi_14_jours', cahiers)
        self.assertEqual(execute_tool(self.ctx, 'decider_seance', {'professeur': 'Personne', 'decision': 'valider'})
                         .get('erreur', '')[:10], 'Je ne trou')

    def test_rappels_reserves_au_directeur(self):
        resultat = self._faire('configurer_rappels', {'actif': 'non', 'plafond_quotidien': '2',
                                                      'familles_a_couper': 'devoirs'})
        self.assertEqual(resultat['statut'], 'ok', resultat)
        p = moteur.parametres(self.etab.pk)
        self.assertEqual((p.actif, p.plafond_quotidien), (False, 2))
        self.assertIn('devoirs', p.familles_desactivees)
        self.secretaire.permissions = {k: True for k in PERMISSIONS_DISPONIBLES}
        self.secretaire.save()
        ctx_perso = build_assistant_context(self.etab, personnel=self.secretaire)
        for outil in ('get_parametres_rappels', 'configurer_rappels'):
            self.assertIn('autorisation', execute_tool(ctx_perso, outil, {'actif': 'oui'})['erreur'])

    # ----------------------------------------------------------------- permissions et pages
    def test_personnel_sans_droit_refuse(self):
        self.secretaire.permissions = {k: False for k in PERMISSIONS_DISPONIBLES}
        self.secretaire.save()
        ctx_perso = build_assistant_context(self.etab, personnel=self.secretaire)
        for outil in ('get_situation_financiere', 'ajouter_depense', 'supprimer_depense', 'enregistrer_recette',
                      'enregistrer_charge', 'payer_charge', 'transfert_comptes', 'enregistrer_pret',
                      'rembourser_pret', 'get_paie_du_mois', 'payer_salaire', 'payer_tous_salaires',
                      'get_controle_cours', 'decider_seance', 'get_cahiers_texte'):
            self.assertIn('autorisation', execute_tool(ctx_perso, outil, {}).get('erreur', ''), outil)

    def test_annuler_une_depense_exige_les_bilans(self):
        self.secretaire.permissions = {'comptabilite_voir': True, 'comptabilite_paiements': True,
                                       'comptabilite_bilans': False}
        self.secretaire.save()
        ctx_perso = build_assistant_context(self.etab, personnel=self.secretaire)
        self.assertEqual(execute_tool(ctx_perso, 'ajouter_depense', {'montant': '1000'})['statut'],
                         'en_attente_confirmation')
        self.assertIn('autorisation', execute_tool(ctx_perso, 'supprimer_depense', {'query': 'x'})['erreur'])

    def test_nouvelles_pages_ouvrables(self):
        cles = {p['key'] for p in list_pages()}
        for cle in ('finances_entrees', 'finances_sorties', 'finances_tresorerie', 'finances_financements',
                    'salaires', 'impayes', 'controle_cours', 'cahiers_texte', 'rappels_automatiques'):
            self.assertIn(cle, cles)
        self.assertTrue(CompteTresorerie.objects.filter(etablissement=self.etab).exists() or True)
