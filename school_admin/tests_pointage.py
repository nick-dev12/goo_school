"""Pointage des enseignants : QR tournant, séances, contrôles, validation et paie au réel."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from school_admin.model.classe_model import Classe
from school_admin.model.comptabilite_generale_model import EcritureComptable
from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps, EmploiDuTemps
from school_admin.model.matiere_model import Matiere
from school_admin.model.pointage_model import BornePointage, SeanceCours
from school_admin.model.presence_model import Presence
from school_admin.model.professeur_model import Professeur
from school_admin.services import pointage as pt
from school_admin.tests.test_assistant_directeur_tools import _make_annee, _make_eleve_simple, _make_etablissement

LUNDI = date(2026, 10, 5)


def _aware(jour, h, m=0):
    return timezone.make_aware(datetime.combine(jour, time(h, m)), timezone.get_current_timezone())


class PointageTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement()
        self.annee = _make_annee(self.etab)
        s = str(self.etab.pk)
        self.classe = Classe.objects.create(nom='4e A', niveau='college', code_classe=f'4A-{s}', capacite_max=30,
                                            etablissement=self.etab, actif=True)
        self.matiere = Matiere.objects.create(nom=f'Maths {s}', code=f'M{s}'[:10], etablissement=self.etab, actif=True)
        self.prof = self._prof('Sarr', 'vacataire')
        self.prof.prix_volume_horaire = Decimal('2000')
        self.prof.save()
        edt = EmploiDuTemps.objects.create(classe=self.classe, annee_scolaire=self.annee.libelle,
                                           annee_scolaire_fk=self.annee, est_actif=True, statut_publication='publie')
        self.creneau = CreneauEmploiDuTemps.objects.create(emploi_du_temps=edt, jour='lundi', heure_debut=time(8, 0),
                                                           heure_fin=time(10, 0), matiere=self.matiere,
                                                           professeur=self.prof, type_cours='cours')
        self.borne = BornePointage.objects.create(etablissement=self.etab, libelle='Entrée')
        BornePointage.objects.filter(pk=self.borne.pk).update(date_creation=_aware(date(2026, 9, 1), 7))
        self.borne.refresh_from_db()
        self.eleve = _make_eleve_simple(self.etab, self.classe, 'Diop', 'Awa', suffix='pt')

    def _prof(self, nom, contrat):
        s = f'{self.etab.pk}{nom}'
        return Professeur.objects.create_user(
            username=f'prof.{s}', email=f'prof.{s}@test.local', password='Prof@Test1!', nom=nom, prenom='Ali',
            telephone='770000020', numero_employe=f'PT{s}'[:20], matiere_principale=self.matiere,
            etablissement=self.etab, niveau_enseignement='college', actif=True, type_contrat=contrat,
        )

    def _seance(self, jour=LUNDI):
        pt.generer_seances(self.etab, jour, jour, self.annee)
        return SeanceCours.objects.get(creneau=self.creneau, date=jour)

    def _appel(self, jour, h, m):
        p = Presence.objects.create(eleve=self.eleve, classe=self.classe, professeur=self.prof,
                                    etablissement=self.etab, matiere=self.matiere, date=jour, statut='present',
                                    annee_scolaire=self.annee)
        Presence.objects.filter(pk=p.pk).update(heure_enregistrement=time(h, m))

    def _seance_validee(self, jour=LUNDI):
        s = self._seance(jour)
        pt.commencer(s, self.prof, saisie_qr=pt.contenu_qr(self.borne), maintenant=_aware(jour, 8, 2))
        self._appel(jour, 8, 10)
        return pt.terminer(s, 'Chapitre 3 : fractions', maintenant=_aware(jour, 9, 55))

    def test_qr_tournant(self):
        self.assertEqual(pt.verifier_code(self.etab, pt.contenu_qr(self.borne)), self.borne)
        self.assertEqual(pt.verifier_code(self.etab, pt.code_borne(self.borne)), self.borne)
        ancien = pt.contenu_qr(self.borne, pt._fenetre() - 3)
        self.assertIsNone(pt.verifier_code(self.etab, ancien))
        self.assertIsNone(pt.verifier_code(self.etab, 'ARIA-POINTAGE:999:123456'))

    def test_generation_idempotente(self):
        pt.generer_seances(self.etab, LUNDI, LUNDI + timedelta(days=6), self.annee)
        pt.generer_seances(self.etab, LUNDI, LUNDI + timedelta(days=6), self.annee)
        self.assertEqual(SeanceCours.objects.filter(professeur=self.prof).count(), 1)

    def test_seance_complete_validee_automatiquement(self):
        s = self._seance_validee()
        self.assertEqual(s.statut, 'validee')
        self.assertTrue(s.validation_auto)
        self.assertEqual(s.confiance, 100)

    def test_ouverture_refusee_hors_fenetre_et_sans_preuve(self):
        s = self._seance()
        with self.assertRaises(ValueError):
            pt.commencer(s, self.prof, saisie_qr=pt.contenu_qr(self.borne), maintenant=_aware(LUNDI, 7, 30))
        with self.assertRaises(ValueError):
            pt.commencer(s, self.prof, maintenant=_aware(LUNDI, 8, 0))
        with self.assertRaises(ValueError):
            pt.commencer(s, self.prof, saisie_qr='ARIA-POINTAGE:1:000000', maintenant=_aware(LUNDI, 8, 0))

    def test_sans_qr_et_sans_appel_va_a_verifier_puis_decision(self):
        s = self._seance()
        pt.commencer(s, self.prof, sans_qr_motif='Borne éteinte', maintenant=_aware(LUNDI, 8, 20))
        s = pt.terminer(s, '', maintenant=_aware(LUNDI, 8, 40))
        self.assertEqual(s.statut, 'a_verifier')
        self.assertEqual(set(s.anomalies), {'sans_qr', 'retard', 'sans_appel', 'cahier_vide', 'trop_courte'})
        pt.decider(s, self.etab, 'valider', 'Vu en classe par le surveillant')
        self.assertEqual(s.statut, 'validee')
        self.assertFalse(s.validation_auto)

    def test_non_faite_puis_contestation(self):
        s = self._seance()
        pt.actualiser(self.etab, maintenant=_aware(LUNDI, 11, 0))
        s.refresh_from_db()
        self.assertEqual(s.statut, 'absente')
        with self.assertRaises(ValueError):
            pt.contester(s, self.prof, 'court')
        pt.contester(s, self.prof, 'Le cours a eu lieu en salle 12, la borne était en panne.')
        self.assertEqual(s.statut, 'contestee')

    def test_paie_vacataire_et_ecriture(self):
        self._seance_validee(LUNDI)
        self._seance_validee(LUNDI + timedelta(days=7))
        calc = pt.calculer_paie(self.prof, date(2026, 10, 1), date(2026, 10, 31), self.annee,
                                activation=pt.date_activation(self.etab))
        self.assertEqual(calc.heures_validees, Decimal('4.00'))
        self.assertEqual(calc.brut, Decimal('8000.00'))
        paie = pt.enregistrer_paie(calc, self.etab, self.annee, retenue_pct=Decimal('5'), user=self.etab)
        self.assertEqual(paie.montant_net, Decimal('7600.00'))
        self.assertEqual(SeanceCours.objects.filter(paie=paie).count(), 2)
        e = EcritureComptable.objects.get(source='paie', source_id=paie.id)
        self.assertTrue(e.est_equilibree())
        self.assertEqual({l.compte.numero for l in e.lignes.all()}, {'637', '571', '447'})
        with self.assertRaises(ValueError):
            pt.enregistrer_paie(calc, self.etab, self.annee)

    def test_paiement_bloque_si_seance_a_verifier(self):
        s = self._seance()
        pt.commencer(s, self.prof, sans_qr_motif='Téléphone déchargé', maintenant=_aware(LUNDI, 8, 0))
        pt.terminer(s, 'Cours', maintenant=_aware(LUNDI, 9, 50))
        calc = pt.calculer_paie(self.prof, date(2026, 10, 1), date(2026, 10, 31), self.annee,
                                activation=pt.date_activation(self.etab))
        with self.assertRaises(ValueError):
            pt.enregistrer_paie(calc, self.etab, self.annee)

    def test_permanent_retenue_et_heures_sup(self):
        self.prof.type_contrat = 'permanent'
        self.prof.salaire_mensuel = Decimal('300000')
        self.prof.heures_contrat_semaine = Decimal('2')
        self.prof.save()
        self._seance(LUNDI)
        pt.actualiser(self.etab, maintenant=_aware(LUNDI, 11, 0))
        calc = pt.calculer_paie(self.prof, LUNDI, LUNDI + timedelta(days=6), self.annee,
                                activation=pt.date_activation(self.etab))
        self.assertEqual(calc.minutes_absentes, 120)
        self.assertEqual(calc.retenue_absences, Decimal('4000.00'))
        self.assertEqual(calc.brut, Decimal('296000.00'))

    def test_remplacant_paye_a_la_place(self):
        autre = self._prof('Ndiaye', 'vacataire')
        autre.prix_volume_horaire = Decimal('3000')
        autre.save()
        s = self._seance()
        pt.actualiser(self.etab, maintenant=_aware(LUNDI, 11, 0))
        s.refresh_from_db()
        pt.decider(s, self.etab, 'remplacer', remplacant=autre)
        act = pt.date_activation(self.etab)
        self.assertEqual(pt.calculer_paie(autre, LUNDI, LUNDI, self.annee, act).brut, Decimal('6000.00'))
        self.assertEqual(pt.calculer_paie(self.prof, LUNDI, LUNDI, self.annee, act).brut, Decimal('0.00'))

    def test_avant_mise_en_service_ancienne_methode(self):
        BornePointage.objects.filter(pk=self.borne.pk).update(date_creation=_aware(date(2026, 10, 10), 7))
        act = pt.date_activation(self.etab)
        calc = pt.calculer_paie(self.prof, date(2026, 10, 1), date(2026, 10, 31), self.annee, act)
        # Lundis du 5 octobre (avant la mise en service) : 2 h comptées selon l'EDT.
        self.assertEqual(calc.minutes_avant_pointage, 120)


class PointagePagesTests(PointageTests):
    def test_pages_direction_et_borne_appairee(self):
        from django.test import Client
        from django.urls import reverse

        self.client.force_login(self.etab)
        for url in (reverse('directeur:pointage_controle'), reverse('directeur:liste_volume_horaire'),
                    reverse('directeur:detail_volume_horaire', args=[self.prof.pk])):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        # Un appareil inconnu ne voit pas le QR ; le directeur connecté l'appaire.
        anonyme = Client()
        self.assertEqual(anonyme.get(reverse('directeur:pointage_borne', args=[self.borne.pk])).status_code, 403)
        self.assertEqual(anonyme.get(reverse('directeur:pointage_borne_code', args=[self.borne.pk])).status_code, 403)
        r = self.client.get(reverse('directeur:pointage_borne', args=[self.borne.pk]))
        self.assertEqual(r.status_code, 200)
        cookie = r.cookies[f'aria_borne_{self.borne.pk}']
        anonyme.cookies[cookie.key] = cookie.value
        data = anonyme.get(reverse('directeur:pointage_borne_code', args=[self.borne.pk])).json()
        self.assertTrue(data['contenu'].startswith('ARIA-POINTAGE:'))
        self.assertEqual(pt.verifier_code(self.etab, data['contenu']), self.borne)
        # Désappairer invalide l'appareil.
        self.borne.regenerer_secret()
        self.assertEqual(anonyme.get(reverse('directeur:pointage_borne_code', args=[self.borne.pk])).status_code, 403)

    def test_page_enseignant(self):
        from django.urls import reverse

        self.client.force_login(self.prof)
        self.assertEqual(self.client.get(reverse('enseignant:pointage')).status_code, 200)
