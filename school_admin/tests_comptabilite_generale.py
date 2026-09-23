from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from school_admin.services.comptabilite_generale import (
    COMPTE_BANQUE,
    COMPTE_CAISSE,
    COMPTE_CLIENTS,
    COMPTE_MOBILE,
    PLAN_SYSCOHADA_EDUCATION,
    REGIME_ENGAGEMENT,
    REGIME_TRESORERIE,
    REMAP_PCE,
    backfill_creances_ouvertes,
    dates_exercice_civil,
    enregistrer_regime_comptable,
    ensure_exercice,
    ensure_plan_comptable,
    migrer_plan_syscohada,
    pont_paiement_eleve,
    regime_est_verrouille,
    snapshot_soldes,
)


class PlanPceConstantesTests(SimpleTestCase):
    def test_pce_contient_les_comptes_valides(self):
        numeros = {row[0] for row in PLAN_SYSCOHADA_EDUCATION}
        for attendu in ('571', '521', '585', '7051', '7052', '7061', '411', '637', '6611'):
            self.assertIn(attendu, numeros)
        for interdit in ('531', '512', '701', '702'):
            self.assertNotIn(interdit, numeros)

    def test_remap_couvre_les_anciens_numeros(self):
        remap = dict(REMAP_PCE)
        self.assertEqual(remap['531'], '571')
        self.assertEqual(remap['512'], '521')
        self.assertEqual(remap['701'], '7051')
        self.assertEqual(remap['702'], '7052')
        self.assertEqual(remap['706'], '7061')
        self.assertEqual(remap['622'], '637')
        self.assertEqual(remap['613'], '622')


def _make_etablissement(suffix='pce'):
    from school_admin.model.etablissement_model import Etablissement

    token = date.today().strftime('%Y%m%d%H%M%S%f')[-10:]
    email = f'directeur.{suffix}.{token}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'École {suffix} {token[-6:]}',
        code_etablissement=f'PCE{token[-8:]}'[:12],
        adresse='1 rue des Tests',
        pays='Sénégal',
        ville='Dakar',
        type_etablissement='primaire',
        type_etablissement_comptabilite='prive',
        directeur_prenom='Awa',
        directeur_nom='Ndiaye',
        directeur_email=f'dir.{suffix}.{token}@aria-test.local',
        module_comptabilite=True,
        devise_monnaie='FCFA',
        montant_par_eleve=Decimal('2000.00'),
        actif=True,
    )
    etab.set_password('Pce@Test1!')
    with patch.object(Etablissement, 'recalculer_facturation', return_value=None):
        etab.save()
    return etab


def _make_annee(etab):
    from school_admin.model.annee_scolaire_model import AnneeScolaire

    return AnneeScolaire.objects.create(
        etablissement=etab,
        libelle='2026-2027',
        annee_debut=2026,
        annee_fin=2027,
        date_debut=date(2026, 9, 1),
        date_fin=date(2027, 6, 30),
        est_active=True,
        est_ouverte=True,
    )


class PlanRemapEtExerciceTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement('remap')

    def test_ensure_plan_n_a_plus_les_anciens_numeros(self):
        ensure_plan_comptable(self.etab)
        from school_admin.model.comptabilite_generale_model import CompteComptable

        actifs = set(
            CompteComptable.objects.filter(etablissement=self.etab, actif=True)
            .values_list('numero', flat=True)
        )
        self.assertIn('571', actifs)
        self.assertIn('521', actifs)
        self.assertIn('7051', actifs)
        self.assertNotIn('531', actifs)
        self.assertNotIn('512', actifs)
        self.assertNotIn('701', actifs)

    def test_remap_conserve_les_soldes(self):
        from school_admin.model.comptabilite_generale_model import (
            CompteComptable,
            EcritureComptable,
            JournalComptable,
            LigneEcriture,
        )

        caisse = CompteComptable.objects.create(
            etablissement=self.etab, numero='531', libelle='Caisse', classe='5', nature='actif'
        )
        banque = CompteComptable.objects.create(
            etablissement=self.etab, numero='512', libelle='Banque', classe='5', nature='actif'
        )
        produit = CompteComptable.objects.create(
            etablissement=self.etab, numero='701', libelle='Inscriptions', classe='7', nature='produit'
        )
        vac = CompteComptable.objects.create(
            etablissement=self.etab, numero='622', libelle='Vacations', classe='6', nature='charge'
        )
        loyer = CompteComptable.objects.create(
            etablissement=self.etab, numero='613', libelle='Locations', classe='6', nature='charge'
        )
        jour = JournalComptable.objects.create(
            etablissement=self.etab, code='CAI', libelle='Caisse', compte_contrepartie=caisse
        )
        debut, fin, libelle = dates_exercice_civil()
        from school_admin.model.comptabilite_generale_model import ExerciceComptable

        exercice = ExerciceComptable.objects.create(
            etablissement=self.etab,
            libelle=libelle,
            date_debut=debut,
            date_fin=fin,
            statut='ouvert',
        )
        ecriture = EcritureComptable.objects.create(
            etablissement=self.etab,
            exercice=exercice,
            journal=jour,
            numero='000001',
            date_ecriture=date(2026, 3, 1),
            libelle='Encaissement test',
            source='test_remap',
            source_id=1,
        )
        LigneEcriture.objects.create(ecriture=ecriture, compte=caisse, debit=Decimal('40000'), credit=Decimal('0'))
        LigneEcriture.objects.create(ecriture=ecriture, compte=produit, debit=Decimal('0'), credit=Decimal('40000'))
        ecriture2 = EcritureComptable.objects.create(
            etablissement=self.etab,
            exercice=exercice,
            journal=jour,
            numero='000002',
            date_ecriture=date(2026, 3, 2),
            libelle='Loyer test',
            source='test_remap',
            source_id=2,
        )
        LigneEcriture.objects.create(ecriture=ecriture2, compte=loyer, debit=Decimal('10000'), credit=Decimal('0'))
        LigneEcriture.objects.create(ecriture=ecriture2, compte=caisse, debit=Decimal('0'), credit=Decimal('10000'))
        avant = snapshot_soldes(self.etab)
        self.assertEqual(avant['531'], Decimal('30000'))
        self.assertEqual(avant['701'], Decimal('-40000'))

        resultat = migrer_plan_syscohada(self.etab)
        self.assertTrue(resultat['soldes_identiques'])
        apres = snapshot_soldes(self.etab)
        self.assertEqual(apres.get('571'), Decimal('30000'))
        self.assertEqual(apres.get('7051'), Decimal('-40000'))
        self.assertEqual(apres.get('622'), Decimal('10000'))
        self.assertNotIn('531', {k: v for k, v in apres.items() if v})
        self.assertTrue(CompteComptable.objects.filter(etablissement=self.etab, numero='637').exists())
        self.assertTrue(CompteComptable.objects.filter(etablissement=self.etab, numero=COMPTE_BANQUE).exists())
        self.assertEqual(banque.id, CompteComptable.objects.get(etablissement=self.etab, numero='521').id)
        self.assertEqual(vac.id, CompteComptable.objects.get(etablissement=self.etab, numero='637').id)

    def test_exercice_est_annee_civile(self):
        annee = _make_annee(self.etab)
        exercice = ensure_exercice(self.etab, annee)
        debut, fin, libelle = dates_exercice_civil()
        self.assertEqual(exercice.libelle, libelle)
        self.assertEqual(exercice.date_debut, debut)
        self.assertEqual(exercice.date_fin, fin)
        self.assertEqual(exercice.annee_scolaire_id, annee.id)
        mois = list(exercice.periodes.filter(type_periode='mois'))
        self.assertEqual(len(mois), 12)


class PontsEtBackfillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from school_admin.model.classe_model import Classe
        from school_admin.model.comptabilite_eleve_model import (
            ComptabiliteEleve,
            FraisAnnexe,
            FraisInscription,
            PaiementEleve,
        )
        from school_admin.model.eleve_model import Eleve
        from school_admin.model.etablissement_model import Etablissement
        from school_admin.model.parametres_comptabilite_model import ParametresComptabilite

        cls.etab = _make_etablissement('pont')
        cls.annee = _make_annee(cls.etab)
        ParametresComptabilite.objects.create(
            etablissement=cls.etab,
            regime_comptable=REGIME_ENGAGEMENT,
            montant_frais_inscription=Decimal('25000.00'),
        )
        cls.classe = Classe.objects.create(
            nom='CE1 A',
            niveau='primaire',
            code_classe=f'PCE-{cls.etab.pk}-C1',
            capacite_max=30,
            etablissement=cls.etab,
        )
        with patch.object(Eleve, '_should_regenerate_qr', return_value=False), patch.object(
            Etablissement, 'recalculer_facturation', return_value=None
        ):
            eleve = Eleve(
                username=f'EL{cls.etab.pk:06d}'[:20],
                numero_eleve=f'EL{cls.etab.pk:06d}'[:20],
                nom='Diallo',
                prenom='Fatou',
                date_naissance=date(2016, 4, 2),
                lieu_naissance='Dakar',
                sexe='F',
                nationalite='Sénégalaise',
                etablissement=cls.etab,
                classe=cls.classe,
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
        cls.eleve = eleve
        cls.compta = ComptabiliteEleve.objects.create(
            eleve=cls.eleve,
            etablissement=cls.etab,
            annee_scolaire=cls.annee,
            statut_paiement='en_retard',
        )
        cls.frais = FraisInscription.objects.create(
            eleve=cls.eleve,
            etablissement=cls.etab,
            annee_scolaire=cls.annee,
            comptabilite_eleve=cls.compta,
            montant=Decimal('25000.00'),
            montant_paye=Decimal('10000.00'),
            reste_a_payer=Decimal('15000.00'),
            date_echeance=date(2026, 9, 30),
            statut='en_attente',
            type_frais='inscription',
        )
        FraisAnnexe.objects.create(
            eleve=cls.eleve,
            etablissement=cls.etab,
            annee_scolaire=cls.annee,
            comptabilite_eleve=cls.compta,
            code='tenue',
            libelle='Tenue',
            periodicite='annuel',
            montant=Decimal('8000.00'),
            montant_paye=Decimal('0.00'),
            reste_a_payer=Decimal('8000.00'),
            date_echeance=date(2026, 10, 1),
            statut='en_attente',
        )
        cls.paiement_historique = PaiementEleve.objects.create(
            eleve=cls.eleve,
            etablissement=cls.etab,
            annee_scolaire=cls.annee,
            type_paiement='frais_inscription',
            frais_inscription=cls.frais,
            montant=Decimal('10000.00'),
            mode_paiement='especes',
        )

    def test_pont_engagement_credit_411(self):
        from school_admin.model.comptabilite_eleve_model import PaiementEleve
        from school_admin.model.comptabilite_generale_model import LigneEcriture

        ensure_plan_comptable(self.etab)
        paiement = PaiementEleve.objects.create(
            eleve=self.eleve,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            type_paiement='frais_inscription',
            frais_inscription=self.frais,
            montant=Decimal('5000.00'),
            mode_paiement='especes',
        )
        ecriture = pont_paiement_eleve(paiement, annee_scolaire=self.annee)
        self.assertIsNotNone(ecriture)
        numeros = list(
            LigneEcriture.objects.filter(ecriture=ecriture).values_list('compte__numero', 'debit', 'credit')
        )
        self.assertIn((COMPTE_CAISSE, Decimal('5000.00'), Decimal('0.00')), numeros)
        self.assertIn((COMPTE_CLIENTS, Decimal('0.00'), Decimal('5000.00')), numeros)

    def test_pont_tresorerie_credit_7051(self):
        from school_admin.model.comptabilite_eleve_model import PaiementEleve
        from school_admin.model.comptabilite_generale_model import LigneEcriture
        from school_admin.model.parametres_comptabilite_model import ParametresComptabilite

        ParametresComptabilite.objects.filter(etablissement=self.etab).update(
            regime_comptable=REGIME_TRESORERIE
        )
        paiement = PaiementEleve.objects.create(
            eleve=self.eleve,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            type_paiement='frais_inscription',
            frais_inscription=self.frais,
            montant=Decimal('2000.00'),
            mode_paiement='mobile_money',
        )
        ecriture = pont_paiement_eleve(paiement, annee_scolaire=self.annee)
        self.assertIsNotNone(ecriture)
        numeros = list(
            LigneEcriture.objects.filter(ecriture=ecriture).values_list('compte__numero', 'debit', 'credit')
        )
        self.assertIn((COMPTE_MOBILE, Decimal('2000.00'), Decimal('0.00')), numeros)
        self.assertIn(('7051', Decimal('0.00'), Decimal('2000.00')), numeros)

    def test_backfill_411_sans_doubler_le_deja_encaisse(self):
        from school_admin.model.comptabilite_generale_model import EcritureComptable, LigneEcriture

        ensure_plan_comptable(self.etab)
        # Historique caisse : 10 000 déjà en 7051 (ne doit pas être réémis en 411).
        exercice = ensure_exercice(self.etab, self.annee)
        from school_admin.model.comptabilite_generale_model import JournalComptable
        from school_admin.services.comptabilite_generale import compte, creer_ecriture

        jour = JournalComptable.objects.get(etablissement=self.etab, code='CAI')
        creer_ecriture(
            self.etab,
            exercice,
            jour,
            date(2026, 9, 5),
            'Encaissement historique',
            [
                {
                    'compte': compte(self.etab, COMPTE_CAISSE),
                    'debit': Decimal('10000'),
                    'credit': Decimal('0'),
                },
                {
                    'compte': compte(self.etab, '7051'),
                    'debit': Decimal('0'),
                    'credit': Decimal('10000'),
                },
            ],
            source='paiement_eleve',
            source_id=self.paiement_historique.id,
        )
        resultat = backfill_creances_ouvertes(self.etab, annee_scolaire=self.annee)
        self.assertGreaterEqual(resultat['emises'], 2)
        inscriptions = EcritureComptable.objects.filter(
            etablissement=self.etab, source='creance_inscription', source_id=self.frais.id
        )
        self.assertEqual(inscriptions.count(), 1)
        montant_411 = LigneEcriture.objects.filter(
            ecriture=inscriptions.first(), compte__numero=COMPTE_CLIENTS
        ).values_list('debit', flat=True).first()
        self.assertEqual(montant_411, Decimal('15000.00'))
        credit_7051 = LigneEcriture.objects.filter(
            compte__etablissement=self.etab,
            compte__numero='7051',
            credit__gt=0,
        ).count()
        self.assertEqual(credit_7051, 2)
        replay = backfill_creances_ouvertes(self.etab, annee_scolaire=self.annee)
        self.assertEqual(replay['emises'], 0)

    def test_regime_verrouille_apres_ecriture(self):
        from school_admin.model.parametres_comptabilite_model import ParametresComptabilite

        ensure_plan_comptable(self.etab)
        self.assertFalse(regime_est_verrouille(self.etab))
        pont_paiement_eleve(
            self.paiement_historique, annee_scolaire=self.annee
        )
        self.assertTrue(regime_est_verrouille(self.etab))
        with self.assertRaises(ValueError):
            enregistrer_regime_comptable(self.etab, REGIME_TRESORERIE, annee_scolaire=self.annee)
        self.assertEqual(
            ParametresComptabilite.objects.get(etablissement=self.etab).regime_comptable,
            REGIME_ENGAGEMENT,
        )
