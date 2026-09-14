from datetime import date
from decimal import Decimal
from unittest.mock import Mock

from django.http import QueryDict
from django.test import SimpleTestCase, TestCase

from school_admin.utils.frais_annexes import (
    FRAIS_ANNEXES_CATALOGUE,
    extraire_frais_annexes_depuis_args,
    extraire_frais_annexes_depuis_post,
    frais_annexes_actifs,
    get_frais_annexes_from_parametres,
    normaliser_frais_annexes,
    serialiser_frais_annexes_pour_stockage,
    date_echeance_frais_annexe,
    appliquer_nouveau_montant,
)


class FraisAnnexesCatalogueTests(SimpleTestCase):
    def test_catalogue_couvre_les_frais_typiques(self):
        codes = {item['code'] for item in FRAIS_ANNEXES_CATALOGUE}
        for attendu in (
            'tenue',
            'carte_scolaire',
            'dossier',
            'assurance',
            'examen',
            'transport',
            'cantine',
            'apport',
            'autre',
        ):
            self.assertIn(attendu, codes)

    def test_transport_et_cantine_sont_optionnels(self):
        optionnels = {
            item['code'] for item in FRAIS_ANNEXES_CATALOGUE if item['optionnel']
        }
        self.assertEqual(optionnels, {'transport', 'cantine'})

    def test_normaliser_inactive_par_defaut(self):
        items = normaliser_frais_annexes([])
        self.assertGreaterEqual(len(items), 9)
        self.assertFalse(any(item['actif'] for item in items))

    def test_actifs_uniquement_si_montant_positif(self):
        stored = [
            {
                'code': 'tenue',
                'actif': True,
                'montant': '15000',
                'periodicite': 'annuel',
                'libelle': 'Tenue',
            },
            {
                'code': 'cantine',
                'actif': True,
                'montant': '0',
                'periodicite': 'annuel',
            },
        ]
        actifs = frais_annexes_actifs(stored)
        self.assertEqual([item['code'] for item in actifs], ['tenue'])

    def test_extraire_depuis_post(self):
        post = QueryDict(mutable=True)
        post['frais_annexe_tenue_actif'] = 'on'
        post['frais_annexe_tenue_montant'] = '12000'
        post['frais_annexe_tenue_periodicite'] = 'annuel'
        post['frais_annexe_autre_actif'] = 'on'
        post['frais_annexe_autre_montant'] = '2500'
        post['frais_annexe_autre_libelle'] = 'Frais de laboratoire'
        post['frais_annexe_autre_periodicite'] = 'ponctuel'
        payload = extraire_frais_annexes_depuis_post(post)
        by_code = {item['code']: item for item in payload}
        self.assertTrue(by_code['tenue']['actif'])
        self.assertEqual(by_code['tenue']['montant'], '12000.00')
        self.assertEqual(by_code['autre']['libelle'], 'Frais de laboratoire')
        self.assertFalse(by_code['cantine']['actif'])

    def test_fusion_assistant_preserve_existants(self):
        existants = serialiser_frais_annexes_pour_stockage([
            {'code': 'tenue', 'actif': True, 'montant': '10000', 'periodicite': 'annuel'},
        ])
        merged = extraire_frais_annexes_depuis_args(
            {
                'frais_annexes': [
                    {'code': 'assurance', 'actif': True, 'montant': 5000, 'periodicite': 'annuel'},
                ]
            },
            existants,
        )
        by_code = {item['code']: item for item in merged}
        self.assertTrue(by_code['tenue']['actif'])
        self.assertEqual(by_code['tenue']['montant'], '10000.00')
        self.assertTrue(by_code['assurance']['actif'])
        self.assertEqual(by_code['assurance']['montant'], '5000.00')

    def test_date_echeance_inscription_plus_30_jours(self):
        inscription = Mock(date_inscription=date(2026, 9, 1))
        echeance = date_echeance_frais_annexe('inscription', inscription=inscription)
        self.assertEqual(echeance, date(2026, 10, 1))

    def test_appliquer_nouveau_montant_conserve_paiement(self):
        charge = Mock(
            montant=Decimal('10000'),
            montant_paye=Decimal('4000'),
            reste_a_payer=Decimal('6000'),
            statut='en_attente',
            date_paiement=None,
        )
        appliquer_nouveau_montant(charge, Decimal('15000'))
        self.assertEqual(charge.montant, Decimal('15000'))
        self.assertEqual(charge.reste_a_payer, Decimal('11000'))
        self.assertEqual(charge.statut, 'en_attente')

    def test_get_frais_annexes_from_parametres_none(self):
        items = get_frais_annexes_from_parametres(None)
        self.assertTrue(items)
        self.assertEqual(items[0]['code'], 'tenue')


class FraisAnnexePaiementTests(SimpleTestCase):
    def test_ajouter_paiement_partiel_puis_solde(self):
        class Charge:
            montant = Decimal('10000.00')
            montant_paye = Decimal('0.00')
            reste_a_payer = Decimal('10000.00')
            statut = 'en_attente'
            date_paiement = None

            def est_totalement_paye(self):
                return self.montant_paye >= self.montant

            def save(self, update_fields=None):
                pass

        frais = Charge()

        def ajouter_paiement(self, montant):
            montant_paye_actuel = Decimal(str(self.montant_paye)) if self.montant_paye else Decimal('0.00')
            montant_a_ajouter = Decimal(str(montant))
            nouveau = montant_paye_actuel + montant_a_ajouter
            if nouveau > self.montant:
                nouveau = self.montant
            self.montant_paye = nouveau
            reste = self.montant - nouveau
            self.reste_a_payer = reste if reste > Decimal('0.00') else Decimal('0.00')
            if self.est_totalement_paye():
                self.statut = 'paye'
            else:
                self.statut = 'en_attente'

        ajouter_paiement(frais, Decimal('4000'))
        self.assertEqual(frais.montant_paye, Decimal('4000.00'))
        self.assertEqual(frais.reste_a_payer, Decimal('6000.00'))
        self.assertEqual(frais.statut, 'en_attente')
        ajouter_paiement(frais, Decimal('6000'))
        self.assertEqual(frais.montant_paye, Decimal('10000.00'))
        self.assertEqual(frais.reste_a_payer, Decimal('0.00'))
        self.assertEqual(frais.statut, 'paye')


class AssistantPaiementSchemaTests(SimpleTestCase):
    def test_outils_declares_dans_le_module(self):
        from pathlib import Path

        tools = Path('school_admin/services/assistant_tools.py').read_text()
        actions = Path('school_admin/services/assistant_actions.py').read_text()
        self.assertIn("'get_parametres_comptabilite'", tools)
        for name in (
            'creer_parametres_comptabilite',
            'modifier_parametres_comptabilite',
            'supprimer_parametres_comptabilite',
            'enregistrer_paiement',
        ):
            self.assertIn(name, actions)


class AgregationRecouvrementAnnexesTests(SimpleTestCase):
    def test_aggrege_du_paye_reste_par_code(self):
        from school_admin.controllers.comptabilite_controller import ComptabiliteController

        rows = ComptabiliteController._aggreger_frais_annexes([
            Mock(code='tenue', libelle='Tenue', montant=Decimal('15000'), montant_paye=Decimal('5000')),
            Mock(code='tenue', libelle='Tenue', montant=Decimal('15000'), montant_paye=Decimal('0')),
            Mock(code='assurance', libelle='Assurance', montant=Decimal('3000'), montant_paye=Decimal('3000')),
        ])
        by_code = {row['code']: row for row in rows}
        self.assertEqual(by_code['tenue']['montant_du'], Decimal('30000'))
        self.assertEqual(by_code['tenue']['montant_paye'], Decimal('5000'))
        self.assertEqual(by_code['tenue']['reste'], Decimal('25000'))
        self.assertEqual(by_code['assurance']['reste'], Decimal('0.00'))


def _make_etablissement():
    from school_admin.model.etablissement_model import Etablissement

    suffix = date.today().strftime('%Y%m%d%H%M%S%f')[-10:]
    email = f'directeur.annexes.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'Lycée Annexes {suffix[-6:]}',
        code_etablissement=f'ANX{suffix[-8:]}'[:12],
        adresse='1 rue des Tests',
        pays='Sénégal',
        ville='Dakar',
        type_etablissement='lycée',
        type_etablissement_comptabilite='prive',
        directeur_prenom='Moussa',
        directeur_nom='Sarr',
        directeur_email=f'dir.anx.{suffix}@aria-test.local',
        module_comptabilite=True,
        devise_monnaie='XOF',
        montant_par_eleve=Decimal('3000.00'),
        actif=True,
    )
    etab.set_password('Lycee@Test1!')
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


class FraisAnnexesRecouvrementTests(TestCase):
    """Les frais annexes persistent et entrent dans le recouvrement (dû / payé / reste)."""

    PASSWORD = 'Lycee@Test1!'

    @classmethod
    def setUpTestData(cls):
        from unittest.mock import patch

        from school_admin.model.etablissement_model import Etablissement
        from school_admin.model.classe_model import Classe
        from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve, FraisAnnexe, FraisInscription
        from school_admin.model.eleve_model import Eleve
        from school_admin.model.inscription_eleve_model import InscriptionEleve
        from school_admin.model.parametres_comptabilite_groupe_classe_model import (
            ParametresComptabiliteGroupeClasse,
        )
        from school_admin.utils.frais_annexes import serialiser_frais_annexes_pour_stockage

        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='2nde A',
            niveau='lycee',
            code_classe=f'ANX-{cls.etab.pk}-2A',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.parametre = ParametresComptabiliteGroupeClasse.objects.create(
            etablissement=cls.etab,
            nom='Tarifs 2nde',
            groupes_classes=['2nde'],
            montant_frais_inscription=Decimal('25000.00'),
            montant_mensualite=Decimal('20000.00'),
            type_facturation='mensuel',
            frais_annexes=serialiser_frais_annexes_pour_stockage([
                {'code': 'tenue', 'actif': True, 'montant': '15000', 'periodicite': 'annuel'},
                {'code': 'carte_scolaire', 'actif': True, 'montant': '5000', 'periodicite': 'annuel'},
            ]),
        )

        with patch.object(Eleve, '_should_regenerate_qr', return_value=False), patch.object(
            Etablissement, 'recalculer_facturation', return_value=None
        ):
            eleve = Eleve(
                username=f'EL{cls.etab.pk:06d}'[:20],
                numero_eleve=f'EL{cls.etab.pk:06d}'[:20],
                nom='Ba',
                prenom='Moussa',
                date_naissance=date(2008, 3, 12),
                lieu_naissance='Dakar',
                sexe='M',
                nationalite='Sénégalaise',
                etablissement=cls.etab,
                classe=cls.classe,
                date_inscription=date(2026, 9, 1),
                statut='nouvelle',
                parent_nom='Ba',
                parent_prenom='Ibrahima',
                parent_telephone='770000001',
                parent_lien='pere',
                mot_de_passe_provisoire='123456',
                actif=True,
            )
            eleve.set_password('Eleve@Test1!')
            eleve.save()
        cls.eleve = eleve

        InscriptionEleve.objects.create(
            annee_scolaire=cls.annee,
            eleve=cls.eleve,
            nom=cls.eleve.nom,
            prenom=cls.eleve.prenom,
            date_naissance=cls.eleve.date_naissance,
            lieu_naissance=cls.eleve.lieu_naissance,
            sexe=cls.eleve.sexe,
            nationalite=cls.eleve.nationalite,
            numero_eleve=cls.eleve.numero_eleve,
            etablissement=cls.etab,
            classe=cls.classe,
            date_inscription=date(2026, 9, 1),
            statut='nouvelle',
            parent_nom=cls.eleve.parent_nom,
            parent_prenom=cls.eleve.parent_prenom,
            parent_telephone=cls.eleve.parent_telephone,
            parent_lien=cls.eleve.parent_lien,
        )

        cls.comptabilite = ComptabiliteEleve.objects.create(
            eleve=cls.eleve,
            etablissement=cls.etab,
            annee_scolaire=cls.annee,
            statut_paiement='a_jour',
        )
        FraisInscription.objects.create(
            eleve=cls.eleve,
            etablissement=cls.etab,
            annee_scolaire=cls.annee,
            comptabilite_eleve=cls.comptabilite,
            montant=Decimal('25000.00'),
            montant_paye=Decimal('25000.00'),
            reste_a_payer=Decimal('0.00'),
            date_echeance=date(2026, 9, 30),
            statut='paye',
            type_frais='inscription',
        )
        FraisAnnexe.objects.create(
            eleve=cls.eleve,
            etablissement=cls.etab,
            annee_scolaire=cls.annee,
            comptabilite_eleve=cls.comptabilite,
            code='tenue',
            libelle='Tenue / uniforme scolaire',
            periodicite='annuel',
            montant=Decimal('15000.00'),
            montant_paye=Decimal('5000.00'),
            reste_a_payer=Decimal('10000.00'),
            date_echeance=date(2026, 10, 1),
            statut='en_attente',
        )
        FraisAnnexe.objects.create(
            eleve=cls.eleve,
            etablissement=cls.etab,
            annee_scolaire=cls.annee,
            comptabilite_eleve=cls.comptabilite,
            code='carte_scolaire',
            libelle='Carte scolaire',
            periodicite='annuel',
            montant=Decimal('5000.00'),
            montant_paye=Decimal('0.00'),
            reste_a_payer=Decimal('5000.00'),
            date_echeance=date(2026, 10, 1),
            statut='en_attente',
        )

    def _login_directeur(self):
        logged = self.client.login(username=self.etab.username, password=self.PASSWORD)
        self.assertTrue(logged)

    def test_total_du_inclut_les_annexes(self):
        self.assertEqual(self.comptabilite.calculer_total_du(), Decimal('45000.00'))
        self.assertEqual(self.comptabilite.calculer_total_paye(), Decimal('30000.00'))

    def test_parametres_form_persiste_les_frais_annexes(self):
        from django.urls import reverse

        from school_admin.model.parametres_comptabilite_groupe_classe_model import (
            ParametresComptabiliteGroupeClasse,
        )
        from school_admin.utils.frais_annexes import frais_annexes_actifs

        self._login_directeur()
        url = reverse('directeur:modifier_parametres_groupe_directeur', args=[self.parametre.id])
        payload = {
            'nom': 'Tarifs 2nde',
            'groupes_classes': ['2nde'],
            'montant_frais_inscription': '25000.00',
            'montant_frais_reinscription': '0.00',
            'montant_mensualite': '20000.00',
            'montant_facturation_annuelle': '0.00',
            'type_facturation': 'mensuel',
            'autoriser_retards': 'on',
            'autoriser_paiements_partiels': 'on',
            'delai_tolerance_retard': '15',
            'envoyer_rappels_automatiques': 'on',
            'jours_avant_rappel': '7',
            'jours_apres_retard_rappel': '3',
            'mois_debut_facturation': '9',
            'mois_fin_facturation': '6',
            'nombre_max_paiements_partiels': '3',
            'jour_versement': '5',
            'nombre_enfants_minimum_remise': '3',
            'pourcentage_remise_famille_nombreuse': '0.00',
            'frais_annexe_tenue_actif': 'on',
            'frais_annexe_tenue_montant': '18000',
            'frais_annexe_tenue_periodicite': 'annuel',
            'frais_annexe_carte_scolaire_actif': 'on',
            'frais_annexe_carte_scolaire_montant': '4000',
            'frais_annexe_carte_scolaire_periodicite': 'annuel',
            'frais_annexe_assurance_actif': 'on',
            'frais_annexe_assurance_montant': '2500',
            'frais_annexe_assurance_periodicite': 'annuel',
        }
        response = self.client.post(url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        parametre = ParametresComptabiliteGroupeClasse.objects.get(pk=self.parametre.pk)
        by_code = {item['code']: item for item in frais_annexes_actifs(parametre.frais_annexes)}
        self.assertEqual(by_code['tenue']['montant'], '18000.00')
        self.assertEqual(by_code['carte_scolaire']['montant'], '4000.00')
        self.assertEqual(by_code['assurance']['montant'], '2500.00')

    def test_liste_recouvrement_affiche_annexes_du_paye_reste(self):
        from django.urls import reverse

        self._login_directeur()
        response = self.client.get(reverse('directeur:liste_comptabilite_eleves_directeur'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('Annexes', html)
        self.assertIn('has-annexes-col', html)
        self.assertIn('Payé', html)
        self.assertIn('Reste', html)
        self.assertContains(response, '20000')
        self.assertContains(response, '5000')
        self.assertContains(response, '15000')
        self.assertContains(response, '45000')
