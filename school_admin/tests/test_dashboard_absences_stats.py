"""Tests du service dashboard absences (directeur)."""
from datetime import date
from unittest.mock import patch

from django.test import TestCase

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.eleve_model import Eleve
from school_admin.model.inscription_eleve_model import InscriptionEleve
from school_admin.model.matiere_model import Matiere
from school_admin.model.presence_model import Presence
from school_admin.model.professeur_model import Professeur
from school_admin.services.dashboard_absences_stats import build_dashboard_absences_stats


def _make_etab():
    suffix = date.today().strftime('%Y%m%d%H%M%S%f')
    email = f'dbd.abs.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'École Abs Test {suffix}',
        code_etablissement=f'ABS{suffix[-8:]}',
        adresse='Test',
        pays='Sénégal',
        ville='Dakar',
        type_etablissement='lycée',
        directeur_prenom='Test',
        directeur_nom='Directeur',
        directeur_email=email,
        actif=True,
    )
    etab.set_password('Test@1234')
    etab.save()
    return etab


def _make_annee(etab):
    return AnneeScolaire.objects.create(
        etablissement=etab,
        libelle='2026-2027-abs',
        annee_debut=2026,
        annee_fin=2027,
        date_debut=date(2026, 9, 1),
        date_fin=date(2027, 6, 30),
        est_active=True,
        est_ouverte=True,
    )


def _make_eleve(etab, classe, annee, nom, prenom, sexe, suffix):
    with patch.object(Eleve, '_should_regenerate_qr', return_value=False):
        with patch.object(Etablissement, 'recalculer_facturation', return_value=None):
            eleve = Eleve(
                username=f'el-{suffix}-{etab.pk}'[:20],
                numero_eleve=f'N{suffix}{etab.pk}'[:15],
                nom=nom,
                prenom=prenom,
                date_naissance=date(2010, 1, 1),
                lieu_naissance='Dakar',
                sexe=sexe,
                nationalite='Sénégalaise',
                etablissement=etab,
                classe=classe,
                date_inscription=date(2026, 9, 1),
                statut='nouvelle',
                parent_nom=nom,
                parent_prenom='P',
                parent_telephone='770000001',
                parent_lien='pere',
                mot_de_passe_provisoire='123456',
                actif=True,
            )
            eleve.set_password('Eleve@Test1!')
            eleve.save()
    InscriptionEleve.objects.create(
        annee_scolaire=annee,
        eleve=eleve,
        nom=eleve.nom,
        prenom=eleve.prenom,
        date_naissance=eleve.date_naissance,
        lieu_naissance=eleve.lieu_naissance,
        sexe=eleve.sexe,
        nationalite=eleve.nationalite,
        numero_eleve=eleve.numero_eleve,
        matricule_eleve=eleve.matricule_eleve,
        etablissement=etab,
        classe=classe,
        date_inscription=date(2026, 9, 1),
        statut='nouvelle',
        parent_nom=eleve.parent_nom,
        parent_prenom=eleve.parent_prenom,
        parent_telephone=eleve.parent_telephone,
        parent_lien=eleve.parent_lien,
    )
    return eleve


class DashboardAbsencesStatsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etab()
        cls.annee = _make_annee(cls.etab)
        cls.classe_a = Classe.objects.create(
            nom='2nde A',
            niveau='lycee',
            code_classe=f'A-{cls.etab.pk}',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.classe_b = Classe.objects.create(
            nom='2nde B',
            niveau='lycee',
            code_classe=f'B-{cls.etab.pk}',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.matiere = Matiere.objects.create(
            nom='Math',
            code=f'M{cls.etab.pk}'[:8],
            etablissement=cls.etab,
        )
        cls.prof = Professeur.objects.create_user(
            username=f'prof.dbd.{cls.etab.pk}',
            email=f'prof.dbd.{cls.etab.pk}@test.local',
            password='Prof@Test1!',
            nom='Prof',
            prenom='Test',
            telephone='770000002',
            numero_employe=f'PDBD{cls.etab.pk}',
            matiere_principale=cls.matiere,
            etablissement=cls.etab,
            niveau_enseignement='lycee',
            actif=True,
        )
        cls.eleve_f = _make_eleve(cls.etab, cls.classe_a, cls.annee, 'Ba', 'Awa', 'F', 'f1')
        cls.eleve_m = _make_eleve(cls.etab, cls.classe_b, cls.annee, 'Diop', 'Omar', 'M', 'm1')
        cls.eleve_risque = _make_eleve(cls.etab, cls.classe_a, cls.annee, 'Sy', 'Fatou', 'F', 'r1')

    def _presence(self, eleve, classe, d, statut='present'):
        return Presence.objects.create(
            eleve=eleve,
            classe=classe,
            professeur=self.prof,
            etablissement=self.etab,
            date=d,
            statut=statut,
            annee_scolaire=self.annee,
        )

    def _eleves_qs(self):
        return Eleve.objects.filter(
            id__in=[self.eleve_f.id, self.eleve_m.id, self.eleve_risque.id],
            actif=True,
        )

    def test_paliers_et_sexe(self):
        ref = date(2026, 10, 15)
        for i in range(11):
            self._presence(self.eleve_risque, self.classe_a, date(2026, 9, 1 + i), 'absent')
        self._presence(self.eleve_f, self.classe_a, ref, 'absent')
        self._presence(self.eleve_f, self.classe_a, date(2026, 9, 20), 'absent_justifie')
        self._presence(self.eleve_m, self.classe_b, ref, 'absent')
        for i in range(12):
            self._presence(self.eleve_m, self.classe_b, date(2026, 10, 1 + i), 'present')

        data = build_dashboard_absences_stats(
            self.etab, self.annee, self._eleves_qs(), today=ref
        )
        kpis = data['kpis']
        self.assertEqual(kpis['eleves_10_12'], 1)
        self.assertEqual(kpis['eleves_gt_12'], 0)
        self.assertGreaterEqual(kpis['filles_nj'], 12)
        self.assertGreaterEqual(kpis['garcons_nj'], 1)

    def test_top_classe_taux_presence(self):
        ref = date(2026, 11, 1)
        for i in range(15):
            self._presence(self.eleve_m, self.classe_b, date(2026, 10, 1 + i), 'present')
        for i in range(15):
            statut = 'present' if i < 5 else 'absent'
            self._presence(self.eleve_f, self.classe_a, date(2026, 10, 1 + i), statut)

        data = build_dashboard_absences_stats(
            self.etab, self.annee, self._eleves_qs(), today=ref
        )
        top = data['top_classes']
        self.assertTrue(top)
        self.assertEqual(top[0]['nom'], '2nde B')
        self.assertGreater(top[0]['taux_presence'], top[-1]['taux_presence'] if len(top) > 1 else 0)

    def test_sans_donnees_eleves_vides(self):
        empty = Eleve.objects.none()
        data = build_dashboard_absences_stats(self.etab, self.annee, empty)
        self.assertFalse(data['meta']['has_data'])
        self.assertEqual(data['kpis']['taux_presence'], 0.0)
