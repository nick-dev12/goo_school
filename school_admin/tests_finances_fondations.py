"""Fondations Finances : trésorerie, catégories, audit, annulation."""
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from school_admin.model.comptabilite_generale_model import EcritureComptable, LigneEcriture, PeriodeComptable
from school_admin.model.finances_model import CategorieFinanciere, CompteTresorerie, JournalAuditFinancier
from school_admin.services.caisse import bornes_mois, total_depenses
from school_admin.services.comptabilite_generale import ensure_exercice, ensure_plan_comptable
from school_admin.services.finances.categories import assurer_categories
from school_admin.services.finances.operations import annuler_sortie, enregistrer_sortie
from school_admin.services.finances.tresorerie import (
    assurer_comptes_defaut,
    definir_solde_initial,
    ouvrir_compte,
    solde_calcule,
)
from school_admin.tests_comptabilite_generale import _make_annee, _make_etablissement


class FondationsFinancesTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement('fond')
        self.annee = _make_annee(self.etab)
        ensure_plan_comptable(self.etab)
        self.jour = timezone.now().date()

    def test_solde_vient_des_ecritures_pas_de_la_colonne(self):
        depense, _ecriture = enregistrer_sortie(
            self.etab,
            self.jour,
            'fournitures',
            Decimal('10000'),
            libelle='Craies',
            annee_scolaire=self.annee,
            user=self.etab,
        )
        caisse = depense.compte_tresorerie
        caisse.solde_initial = Decimal('999999')
        caisse.save(update_fields=['solde_initial'])
        self.assertEqual(solde_calcule(caisse), Decimal('-10000'))
        with self.assertRaises(ValueError):
            definir_solde_initial(caisse, Decimal('1'))
        self.assertFalse(
            LigneEcriture.objects.filter(
                ecriture__etablissement=self.etab,
                compte__numero='471',
            ).exists()
        )

    def test_annulation_garde_la_ligne_et_sort_du_total(self):
        depense, ecriture = enregistrer_sortie(
            self.etab,
            self.jour,
            'loyer',
            Decimal('8000'),
            annee_scolaire=self.annee,
            user=self.etab,
        )
        annuler_sortie(depense, 'doublon', user=self.etab)
        depense.refresh_from_db()
        self.assertEqual(depense.statut, 'annulee')
        self.assertEqual(depense.annule_object_id, self.etab.pk)
        self.assertEqual(depense.annule_content_type.model, 'etablissement')
        extourne = EcritureComptable.objects.get(source='extourne', source_id=ecriture.id)
        self.assertEqual(extourne.ecriture_origine_id, ecriture.id)
        bornes = bornes_mois(self.jour)
        self.assertEqual(total_depenses(self.etab, bornes.debut, bornes.fin), Decimal('0'))
        audit = JournalAuditFinancier.objects.get(
            etablissement=self.etab,
            action='annulation',
            cible_object_id=depense.id,
        )
        self.assertEqual(audit.acteur_object_id, self.etab.pk)
        self.assertEqual(solde_calcule(depense.compte_tresorerie), Decimal('0'))

    def test_periode_du_jour_verrouillee_bloque_l_annulation(self):
        depense, _ecriture = enregistrer_sortie(
            self.etab,
            self.jour,
            'carburant',
            Decimal('3000'),
            annee_scolaire=self.annee,
            user=self.etab,
        )
        exercice = ensure_exercice(self.etab, self.annee)
        PeriodeComptable.objects.filter(exercice=exercice, type_periode='mois').update(verrouillee=True)
        with self.assertRaises(ValueError):
            annuler_sortie(depense, 'trop tard', user=self.etab)
        depense.refresh_from_db()
        self.assertEqual(depense.statut, 'validee')
        self.assertEqual(EcritureComptable.objects.filter(source='extourne').count(), 0)

    def test_caissier_ne_peut_pas_annuler(self):
        from school_admin.controllers.caisse_controller import CaisseController
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        depense, _ecriture = enregistrer_sortie(
            self.etab,
            self.jour,
            'autre',
            Decimal('1500'),
            annee_scolaire=self.annee,
            user=self.etab,
        )
        caissier = PersonnelAdministratif(
            username=f'caisse{self.etab.pk}@aria-test.local',
            email=f'caisse{self.etab.pk}@aria-test.local',
            nom='Diallo',
            prenom='Caisse',
            telephone='770000222',
            fonction='caissier',
            etablissement=self.etab,
            actif=True,
            permissions={},
        )
        caissier.set_password('Test@Test1!')
        caissier.save()
        request = RequestFactory().post('/', {'motif': 'erreur'})
        request.user = caissier
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        CaisseController.annuler_depense_directeur(request, depense.id)
        depense.refresh_from_db()
        self.assertEqual(depense.statut, 'validee')

    def test_comptes_isoles_par_etablissement(self):
        import uuid

        assurer_comptes_defaut(self.etab)
        autre = _make_etablissement(uuid.uuid4().hex[:8])
        self.assertGreater(CompteTresorerie.objects.filter(etablissement=self.etab).count(), 0)
        self.assertEqual(CompteTresorerie.objects.filter(etablissement=autre).count(), 0)

    def test_deuxieme_banque_recoit_un_sous_compte(self):
        assurer_comptes_defaut(self.etab)
        banque = ouvrir_compte(self.etab, 'banque', 'Banque secondaire', reference='SN001')
        self.assertEqual(banque.compte_comptable.numero, '5211')
        self.assertEqual(banque.solde_initial, Decimal('0'))

    def test_categorie_peut_avoir_un_parent(self):
        assurer_categories(self.etab)
        parent = CategorieFinanciere.objects.get(
            etablissement=self.etab,
            libelle='Fournitures',
        )
        enfant = CategorieFinanciere.objects.create(
            etablissement=self.etab,
            type_categorie='sortie',
            libelle='Papier',
            parent=parent,
            compte_comptable=parent.compte_comptable,
            ordre=41,
        )
        self.assertEqual(enfant.parent_id, parent.id)

    def test_justificatif_pdf_attache_a_la_sortie(self):
        fichier = SimpleUploadedFile('recu.pdf', b'%PDF-1.4', content_type='application/pdf')
        depense, _ecriture = enregistrer_sortie(
            self.etab,
            self.jour,
            'electricite',
            Decimal('4000'),
            annee_scolaire=self.annee,
            user=self.etab,
            fichier=fichier,
        )
        from school_admin.model.finances_model import PieceFinanciere
        from django.contrib.contenttypes.models import ContentType

        pieces = PieceFinanciere.objects.filter(
            content_type=ContentType.objects.get_for_model(depense),
            object_id=depense.id,
        )
        self.assertEqual(pieces.count(), 1)
        self.assertIn('recu', pieces.first().fichier.name)
