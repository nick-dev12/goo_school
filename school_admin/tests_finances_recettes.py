"""Recettes complémentaires : activité, subvention, divers, remboursement. Pas de scolarité recopiée."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from school_admin.model.comptabilite_eleve_model import PaiementEleve
from school_admin.model.comptabilite_generale_model import LigneEcriture, PeriodeComptable
from school_admin.model.finances_model import CategorieFinanciere, PieceFinanciere, RecetteEtablissement
from school_admin.services.comptabilite_generale import compte, ensure_exercice, synthese_bilan
from school_admin.services.finances.categories import assurer_categories
from school_admin.services.finances.recettes import (
    annuler_recette,
    annuler_remboursement,
    enregistrer_recette,
    enregistrer_remboursement,
    paiements_scolarite,
)
from school_admin.services.finances.tresorerie import assurer_comptes_defaut, compte_principal, solde_calcule
from school_admin.tests_comptabilite_generale import _make_annee, _make_etablissement


class RecettesComplementairesTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement('rct')
        self.annee = _make_annee(self.etab)
        assurer_categories(self.etab)
        assurer_comptes_defaut(self.etab)
        self.jour = timezone.now().date()
        self.caisse = compte_principal(self.etab, 'caisse')

    def _categorie(self, libelle):
        return CategorieFinanciere.objects.get(
            etablissement=self.etab, type_categorie='recette', libelle=libelle,
        )

    def _lignes(self, ecriture):
        return {
            ligne.compte.numero: (ligne.debit, ligne.credit)
            for ligne in ecriture.lignes.select_related('compte')
        }

    def test_activite_debite_caisse_et_credite_la_classe_7(self):
        avant = synthese_bilan(self.etab, ensure_exercice(self.etab, self.annee))['produits']
        recette, ecriture = enregistrer_recette(
            self.etab, 'activite', self._categorie('Activité'), self.caisse,
            self.jour, Decimal('600'), libelle='Sortie', annee_scolaire=self.annee, user=self.etab,
        )
        lignes = self._lignes(ecriture)
        self.assertEqual(lignes['571'], (Decimal('600'), Decimal('0')))
        self.assertEqual(lignes['7068'], (Decimal('0'), Decimal('600')))
        self.assertFalse(LigneEcriture.objects.filter(ecriture=ecriture, compte__classe='6').exists())
        self.assertTrue(recette.dans_le_resultat())
        self.assertEqual(recette.destination, '')
        apres = synthese_bilan(self.etab, ensure_exercice(self.etab, self.annee))['produits']
        self.assertEqual(apres - avant, Decimal('600'))
        self.assertEqual(PaiementEleve.objects.filter(etablissement=self.etab).count(), 0)

    def test_subvention_equipement_reste_en_classe_7(self):
        recette, ecriture = enregistrer_recette(
            self.etab, 'subvention', self._categorie('Subvention'), self.caisse,
            self.jour, Decimal('2000'), destination='equipement',
            annee_scolaire=self.annee, user=self.etab,
        )
        lignes = self._lignes(ecriture)
        self.assertEqual(lignes['711'], (Decimal('0'), Decimal('2000')))
        self.assertTrue(recette.dans_le_resultat())
        self.assertEqual(recette.destination, 'equipement')

    def test_compte_hors_classe_7_sort_du_resultat_sans_regarder_la_destination(self):
        cat = self._categorie('Subvention')
        cat.compte_comptable = compte(self.etab, '2184')
        cat.save(update_fields=['compte_comptable'])
        avant = synthese_bilan(self.etab, ensure_exercice(self.etab, self.annee))['produits']
        recette, ecriture = enregistrer_recette(
            self.etab, 'subvention', cat, self.caisse, self.jour, Decimal('900'),
            destination='equipement', annee_scolaire=self.annee, user=self.etab,
        )
        lignes = self._lignes(ecriture)
        self.assertEqual(lignes['2184'], (Decimal('0'), Decimal('900')))
        self.assertNotIn('711', lignes)
        self.assertFalse(LigneEcriture.objects.filter(ecriture=ecriture, compte__classe='7').exists())
        self.assertFalse(recette.dans_le_resultat())
        apres = synthese_bilan(self.etab, ensure_exercice(self.etab, self.annee))['produits']
        self.assertEqual(apres, avant)

    def test_subvention_sans_destination_est_refusee(self):
        with self.assertRaises(ValueError):
            enregistrer_recette(
                self.etab, 'subvention', self._categorie('Subvention'), self.caisse,
                self.jour, Decimal('10'), annee_scolaire=self.annee, user=self.etab,
            )
        self.assertEqual(RecetteEtablissement.objects.filter(etablissement=self.etab).count(), 0)

    def test_remboursement_garde_lorigine_et_calcule_le_net(self):
        recette, _ecriture = enregistrer_recette(
            self.etab, 'divers', self._categorie('Recette diverse'), self.caisse,
            self.jour, Decimal('300'), annee_scolaire=self.annee, user=self.etab,
        )
        remboursement, ecriture = enregistrer_remboursement(
            recette, self.jour, Decimal('50'), 'Trop perçu', user=self.etab,
        )
        recette.refresh_from_db()
        self.assertEqual(recette.montant, Decimal('300'))
        self.assertEqual(recette.statut, 'validee')
        self.assertEqual(recette.net(), Decimal('250'))
        lignes = self._lignes(ecriture)
        self.assertEqual(lignes['758'], (Decimal('50'), Decimal('0')))
        self.assertEqual(lignes['571'], (Decimal('0'), Decimal('50')))
        self.assertEqual(solde_calcule(self.caisse), Decimal('250'))
        with self.assertRaises(ValueError):
            enregistrer_remboursement(recette, self.jour, Decimal('300'), 'Trop', user=self.etab)
        self.assertEqual(remboursement.statut, 'validee')
        with self.assertRaises(ValueError):
            annuler_recette(recette, 'Trop tôt', user=self.etab)
        annuler_remboursement(remboursement, 'Erreur de saisie', user=self.etab)
        recette.refresh_from_db()
        self.assertEqual(recette.net(), Decimal('300'))
        self.assertEqual(recette.montant, Decimal('300'))
        annuler_recette(recette, 'Vérification', user=self.etab)
        recette.refresh_from_db()
        self.assertEqual(recette.statut, 'annulee')
        self.assertEqual(recette.net(), Decimal('0'))
        self.assertEqual(solde_calcule(self.caisse), Decimal('0'))

    def test_paiement_eleve_ne_cree_pas_de_recette(self):
        from school_admin.model.classe_model import Classe
        from school_admin.model.eleve_model import Eleve
        from school_admin.model.etablissement_model import Etablissement

        classe = Classe.objects.create(
            nom='CE1 A',
            niveau='primaire',
            code_classe=f'RC{self.etab.pk}'[:20],
            capacite_max=30,
            etablissement=self.etab,
        )
        with patch.object(Eleve, '_should_regenerate_qr', return_value=False), patch.object(
            Etablissement, 'recalculer_facturation', return_value=None
        ):
            eleve = Eleve(
                username=f'EL{self.etab.pk:06d}'[:20],
                numero_eleve=f'EL{self.etab.pk:06d}'[:20],
                nom='Diallo',
                prenom='Fatou',
                date_naissance=date(2016, 4, 2),
                lieu_naissance='Dakar',
                sexe='F',
                nationalite='Sénégalaise',
                etablissement=self.etab,
                classe=classe,
                date_inscription=date(2026, 9, 1),
                statut='nouvelle',
                parent_nom='Diallo',
                parent_prenom='Mamadou',
                parent_telephone='770000002',
                parent_lien='pere',
                mot_de_passe_provisoire='123456',
                actif=True,
            )
            eleve.set_password('Eleve@Test1!')
            eleve.save()
        paiement = PaiementEleve.objects.create(
            eleve=eleve,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            type_paiement='autre',
            montant=Decimal('1500.00'),
            mode_paiement='especes',
        )
        self.assertEqual(RecetteEtablissement.objects.filter(etablissement=self.etab).count(), 0)
        lus = paiements_scolarite(self.etab, self.annee)
        self.assertEqual([ligne.pk for ligne in lus], [paiement.pk])
        self.assertEqual(RecetteEtablissement.objects.filter(etablissement=self.etab).count(), 0)
        with self.assertRaises(ValueError):
            enregistrer_remboursement(paiement, self.jour, Decimal('10'), 'Interdit', user=self.etab)

    def test_periode_verrouillee_et_autre_ecole(self):
        exercice = ensure_exercice(self.etab, self.annee)
        PeriodeComptable.objects.filter(exercice=exercice, type_periode='mois').update(verrouillee=True)
        with self.assertRaises(ValueError):
            enregistrer_recette(
                self.etab, 'divers', self._categorie('Recette diverse'), self.caisse,
                self.jour, Decimal('20'), annee_scolaire=self.annee, user=self.etab,
            )
        self.assertEqual(RecetteEtablissement.objects.filter(etablissement=self.etab).count(), 0)

        autre = _make_etablissement('rc2')
        assurer_categories(autre)
        assurer_comptes_defaut(autre)
        with self.assertRaises(ValueError):
            enregistrer_recette(
                self.etab, 'divers', self._categorie('Recette diverse'),
                compte_principal(autre, 'caisse'), self.jour, Decimal('15'),
                annee_scolaire=self.annee, user=self.etab,
            )

    def test_justificatif_pdf(self):
        fichier = SimpleUploadedFile('recu_activite.pdf', b'%PDF-1.4 test', content_type='application/pdf')
        recette, _ecriture = enregistrer_recette(
            self.etab, 'activite', self._categorie('Activité'), self.caisse,
            self.jour, Decimal('12'), fichier=fichier, annee_scolaire=self.annee, user=self.etab,
        )
        piece = PieceFinanciere.objects.get(etablissement=self.etab, object_id=recette.pk)
        self.assertIn('recu_activite', piece.fichier.name)
