"""Rappels automatiques : seuils, journal anti-doublon, heures calmes, plafond, centre « À faire »."""
import json
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from school_admin.model.context_popup_model import ContextPopupState
from school_admin.model.notification_directeur_model import NotificationDirecteur
from school_admin.model.push_delivery_model import PushDelivery
from school_admin.model.rappel_model import ParametresRappels, RappelEnvoye
from school_admin.services import context_popups as cp
from school_admin.services.rappels import moteur
from school_admin.tests.test_assistant_directeur_tools import _make_annee, _make_etablissement

CANDIDATS = 'school_admin.services.context_popups.candidates'


def midi(jours=0):
    """Un instant hors heures calmes, décalé de quelques jours."""
    return timezone.make_aware(datetime.combine(timezone.localdate() + timedelta(days=jours), time(12)))


class SeuilsTests(TestCase):
    def test_seuils_d_une_echeance(self):
        today = timezone.localdate()
        attendus = {5: 'j-3', 2: 'j-3', 1: 'j-1', 0: 'j', -1: 'retard-0', -3: 'retard-0',
                    -4: 'retard-1', -7: 'retard-2', -60: 'retard-2'}
        for jours, seuil in attendus.items():
            self.assertEqual(cp.stage_for(today + timedelta(days=jours), today), seuil, jours)

    def test_libelles_du_compte_a_rebours(self):
        today = timezone.localdate()
        self.assertEqual(cp.due_label(today, today), "Aujourd'hui")
        self.assertEqual(cp.due_label(today + timedelta(days=1), today), 'Demain')
        self.assertEqual(cp.due_label(today + timedelta(days=3), today), 'Dans 3 jours')
        self.assertEqual(cp.due_label(today - timedelta(days=1), today), "En retard d'un jour")
        self.assertEqual(cp.due_label(today - timedelta(days=2), today), 'En retard de 2 jours')

    def test_carte_groupes_et_push(self):
        today = timezone.localdate()
        proche = cp.card('k1', 'T', 't', '/x/', 'Voir', ['v'], deadline=today)
        loin = cp.card('k2', 'T', 't', '/x/', 'Voir', ['v'], deadline=today + timedelta(days=3))
        info = cp.card('k3', 'T', 't', '/x/', 'Voir', ['v'], group='news')
        self.assertEqual((proche['group'], loin['group'], info['group']), ('now', 'soon', 'news'))
        self.assertTrue(proche['push'])
        self.assertFalse(info['push'])  # une nouveauté a déjà sa notification : pas de rappel
        self.assertIsNone(cp.card('k4', 'T', 't', 'https://ailleurs.example/', 'Voir', ['v']))


class MoteurTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement()

    def carte(self, key='etab:test', deadline=None, evidence=None, **kwargs):
        item = cp.card(key, 'Des dossiers à examiner', 'Deux demandes attendent.', '/dashboard/directeur/',
                       'Examiner', [key, deadline, evidence], deadline=deadline, code='DIR-01',
                       family='inscriptions', **kwargs)
        item['etab'] = self.etab.pk
        if evidence:
            item['evidence'] = evidence
        return item

    def traiter(self, items, maintenant=None):
        with patch(CANDIDATS, return_value=items):
            return moteur.traiter(self.etab, maintenant or midi())

    def test_rappel_cree_notification_et_push_une_seule_fois(self):
        items = [self.carte()]
        self.assertEqual(len(self.traiter(items)), 1)
        self.assertEqual(self.traiter(items), [])
        self.assertEqual(RappelEnvoye.objects.count(), 1)
        notification = NotificationDirecteur.objects.get()
        self.assertEqual(notification.donnees['rappel'], 'DIR-01')
        self.assertEqual(notification.donnees['url'], '/dashboard/directeur/')
        self.assertEqual(PushDelivery.objects.count(), 1)
        self.assertEqual(PushDelivery.objects.get().data['type'], 'rappel')

    def test_simulation_n_ecrit_rien(self):
        with patch(CANDIDATS, return_value=[self.carte()]):
            dus = moteur.traiter(self.etab, midi(), dry_run=True)
        self.assertEqual(len(dus), 1)
        self.assertFalse(RappelEnvoye.objects.exists())
        self.assertFalse(NotificationDirecteur.objects.exists())

    def test_un_rappel_par_seuil_d_echeance(self):
        today = timezone.localdate()
        self.traiter([self.carte(deadline=today + timedelta(days=1))])
        self.traiter([self.carte(deadline=today + timedelta(days=1))])
        self.assertEqual(list(RappelEnvoye.objects.values_list('stage', flat=True)), ['j-1'])
        self.traiter([self.carte(deadline=today)])  # le lendemain, l'échéance est aujourd'hui
        self.assertEqual(set(RappelEnvoye.objects.values_list('stage', flat=True)), {'j-1', 'j'})

    def test_relances_espacees_et_plafonnees(self):
        items = [self.carte()]
        self.traiter(items, midi())
        self.assertEqual(self.traiter(items, midi(1)), [])  # trop tôt
        for n in range(1, 8):
            self.traiter(items, midi(n * moteur.RELANCE_JOURS))
        stages = sorted(RappelEnvoye.objects.values_list('stage', flat=True))
        self.assertEqual(stages, ['initial', 'relance-1', 'relance-2', 'relance-3'])

    def test_nouveaux_dossiers_relancent_mais_pas_une_liste_qui_diminue(self):
        self.traiter([self.carte(evidence={'1': 'pending', '2': 'pending'})])
        self.assertEqual(self.traiter([self.carte(evidence={'1': 'pending'})]), [])
        self.assertEqual(len(self.traiter([self.carte(evidence={'1': 'pending', '3': 'pending'})])), 1)

    def test_heures_calmes(self):
        nuit = timezone.make_aware(datetime.combine(timezone.localdate(), time(23, 0)))
        matin = timezone.make_aware(datetime.combine(timezone.localdate(), time(5, 0)))
        for instant in (nuit, matin):
            self.assertEqual(self.traiter([self.carte()], instant), [])
        self.assertFalse(RappelEnvoye.objects.exists())
        self.assertEqual(len(self.traiter([self.carte()], midi())), 1)

    def test_famille_desactivee_et_rappels_coupes(self):
        params = moteur.parametres(self.etab.pk)
        params.familles_desactivees = ['inscriptions']
        params.save()
        self.assertEqual(self.traiter([self.carte()]), [])
        params.familles_desactivees = []
        params.actif = False
        params.save()
        self.assertEqual(self.traiter([self.carte()]), [])

    def test_plafond_quotidien_regroupe_le_reste(self):
        ParametresRappels.objects.create(etablissement=self.etab, plafond_quotidien=2)
        items = [self.carte(key=f'etab:test:{n}') for n in range(5)]
        self.traiter(items)
        self.assertEqual(RappelEnvoye.objects.exclude(key='synthese').count(), 5)  # tout est journalisé
        self.assertEqual(NotificationDirecteur.objects.count(), 3)  # 2 rappels + 1 synthèse
        synthese = NotificationDirecteur.objects.get(donnees__rappel='SYNTHESE')
        self.assertIn('3 autres actions', synthese.titre)
        self.assertEqual(self.traiter(items), [])

    def test_passage_complet_et_dernier_passage(self):
        with patch(CANDIDATS, return_value=[self.carte()]):
            stats = moteur.generer(etablissement_ids=[self.etab.pk], maintenant=midi())
        self.assertEqual((stats['etablissements'], stats['rappels'], stats['erreurs']), (1, 1, 0))
        self.assertIsNotNone(ParametresRappels.objects.get(etablissement=self.etab).dernier_passage)

    def test_une_erreur_n_arrete_pas_le_passage(self):
        with patch(CANDIDATS, side_effect=RuntimeError('source indisponible')):
            stats = moteur.generer(etablissement_ids=[self.etab.pk], maintenant=midi())
        self.assertEqual(stats['erreurs'], stats['personnes'])


class CentreAFaireTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement()
        _make_annee(self.etab)
        self.client.force_login(self.etab)
        self.item = cp.card('etab:centre', 'Un dossier', 'À examiner.', '/dashboard/directeur/', 'Examiner', ['v1'])

    def post(self, action, **kwargs):
        return self.client.post('/api/context-popup/', data=json.dumps({'action': action, **kwargs}),
                                content_type='application/json')

    def test_centre_liste_sans_marquer_comme_vu(self):
        with patch('school_admin.api_views.context_popup_views.candidates', return_value=[self.item]):
            data = self.client.get('/api/context-popup/?centre=1').json()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['cards'][0]['group'], 'now')
        self.assertIn(data['greeting']['hello'], ('Bonjour', 'Bonsoir'))
        self.assertFalse(ContextPopupState.objects.exists())

    def test_ouvrir_puis_reporter_depuis_le_centre(self):
        with patch('school_admin.api_views.context_popup_views.candidates', return_value=[self.item]):
            self.assertEqual(self.post('go', key='etab:centre').json()['url'], '/dashboard/directeur/')
            self.assertEqual(self.post('later', key='etab:centre').status_code, 200)
            data = self.client.get('/api/context-popup/?centre=1').json()
        self.assertTrue(data['cards'][0]['snoozed'])
        self.assertGreater(ContextPopupState.objects.get(key='etab:centre').snooze_until, timezone.now())

    def test_situation_resolue_refusee(self):
        with patch('school_admin.api_views.context_popup_views.candidates', return_value=[]):
            self.assertEqual(self.post('go', key='etab:centre').status_code, 409)

    def test_synthese_d_arrivee_annonce_le_total(self):
        with patch('school_admin.api_views.context_popup_views.candidates', return_value=[self.item]), \
                patch(CANDIDATS, return_value=[self.item]):
            data = self.post('claim').json()
        self.assertEqual((len(data['cards']), data['total']), (1, 1))

    def test_anonyme_refuse(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/context-popup/?centre=1').status_code, 401)


def _personnel(etab, permissions, suffixe='a'):
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    membre = PersonnelAdministratif(
        username=f'perso.{suffixe}.{etab.pk}', email=f'perso.{suffixe}.{etab.pk}@aria-test.local', nom='Fall',
        prenom='Awa', telephone='770000099', fonction='surveillant', etablissement=etab, actif=True,
        permissions=permissions)
    membre.set_password('Perso@Test1!')
    membre.save()
    return membre


class ReglesEtablissementTests(TestCase):
    """Règles DIR-xx / ADM-xx : chaque source s'exécute et respecte les permissions."""

    def setUp(self):
        self.etab = _make_etablissement()
        self.annee = _make_annee(self.etab)

    def regles(self, user, director):
        from school_admin.services.rappels.etablissement import situations
        return situations(user, self.etab, self.annee, director)

    def test_toutes_les_sources_s_executent_sans_donnee(self):
        self.assertEqual(self.regles(self.etab, True), [])

    def test_depense_en_brouillon_et_session_d_examen(self):
        from school_admin.model.caisse_etablissement_model import DepenseEtablissement
        from school_admin.model.session_examen_model import SessionExamen
        today = timezone.localdate()
        DepenseEtablissement.objects.create(etablissement=self.etab, annee_scolaire=self.annee, date_depense=today,
                                            motif='autre', libelle='Achat', montant=5000, statut='brouillon')
        from school_admin.model.periode_model import PeriodeScolaire
        PeriodeScolaire.objects.bulk_create([PeriodeScolaire(
            etablissement=self.etab, annee_scolaire=self.annee, nom_periode='Trimestre 1',
            type_periode='trimestre', date_debut=today - timedelta(days=60), date_fin=today + timedelta(days=5))])
        periode = PeriodeScolaire.objects.get(etablissement=self.etab)
        SessionExamen.objects.bulk_create([SessionExamen(
            etablissement=self.etab, annee_scolaire=self.annee, nom_examen='Composition 1', periode=periode,
            date_debut=today + timedelta(days=2), date_fin=today + timedelta(days=4))])
        cartes = {item['code']: item for item in self.regles(self.etab, True)}
        self.assertEqual(cartes['DIR-16']['count'], 1)
        self.assertEqual(cartes['DIR-12']['stage'], 'j-3')
        self.assertIn('pas encore publié', cartes['DIR-12']['text'])
        self.assertEqual(cartes['DIR-14']['due'], 'Dans 5 jours')
        self.assertTrue(all(item['url'].startswith('/') for item in cartes.values()))

    def test_personnel_sans_droit_ne_recoit_rien(self):
        from school_admin.model.caisse_etablissement_model import DepenseEtablissement
        DepenseEtablissement.objects.create(etablissement=self.etab, annee_scolaire=self.annee,
                                            date_depense=timezone.localdate(), motif='autre', libelle='Achat',
                                            montant=5000, statut='brouillon')
        sans_droit = _personnel(self.etab, {'comptabilite_bilans': False, 'comptabilite_voir': False}, 'x')
        self.assertEqual(self.regles(sans_droit, False), [])
        comptable = _personnel(self.etab, {'comptabilite_bilans': True}, 'y')
        self.assertEqual([item['code'] for item in self.regles(comptable, False)], ['ADM-06'])

    def test_les_regles_arrivent_dans_les_cartes_du_directeur(self):
        from school_admin.model.caisse_etablissement_model import DepenseEtablissement
        DepenseEtablissement.objects.create(etablissement=self.etab, annee_scolaire=self.annee,
                                            date_depense=timezone.localdate(), motif='autre', libelle='Achat',
                                            montant=5000, statut='brouillon')
        codes = {item['code'] for item in cp.candidates(self.etab)}
        self.assertIn('DIR-16', codes)


class PagesRappelsTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement()
        _make_annee(self.etab)
        self.url = '/directeur/rappels-automatiques/'

    def test_reglages_direction(self):
        from django.urls import reverse
        url = reverse('directeur:rappels_automatiques')
        self.client.force_login(self.etab)
        self.assertEqual(self.client.get(url).status_code, 200)
        reponse = self.client.post(url, {'action': 'enregistrer', 'actif': 'on', 'debut': '20:00', 'fin': '07:00',
                                         'plafond': '99', 'familles': ['devoirs', 'scolarite']})
        self.assertEqual(reponse.status_code, 302)
        params = ParametresRappels.objects.get(etablissement=self.etab)
        self.assertEqual((params.debut_heures_calmes, params.fin_heures_calmes), (time(20, 0), time(7, 0)))
        self.assertEqual(params.plafond_quotidien, 10)  # borné
        self.assertIn('convocations', params.familles_desactivees)
        self.assertNotIn('devoirs', params.familles_desactivees)
        self.assertContains(self.client.post(url, {'action': 'simuler'}), 'Ce qui partirait maintenant')

    def test_reglages_refuses_au_personnel(self):
        from django.urls import reverse
        self.client.force_login(_personnel(self.etab, {}))
        reponse = self.client.get(reverse('directeur:rappels_automatiques'))
        self.assertEqual(reponse.status_code, 302)

    def test_cloche_et_page_du_personnel(self):
        from django.urls import reverse
        from school_admin.model.rappel_model import NotificationPersonnel
        membre = _personnel(self.etab, {})
        autre = _personnel(self.etab, {}, 'b')
        NotificationPersonnel.objects.create(personnel=membre, titre='Des classes sans appel', message='3 classes.',
                                             donnees={'rappel': 'ADM-07', 'url': '/directeur/suivi-presence/'})
        NotificationPersonnel.objects.create(personnel=autre, titre='Pour un collègue', message='Privé.')
        self.client.force_login(membre)
        reponse = self.client.get(reverse('directeur:notifications_directeur'))
        self.assertContains(reponse, 'Des classes sans appel')
        self.assertContains(reponse, '/directeur/suivi-presence/')
        self.assertNotContains(reponse, 'Pour un collègue')
        self.assertTrue(NotificationPersonnel.objects.get(personnel=membre).lu)
        self.assertFalse(NotificationPersonnel.objects.get(personnel=autre).lu)

    def test_rappel_du_personnel_arrive_dans_sa_cloche(self):
        from school_admin.model.rappel_model import NotificationPersonnel
        membre = _personnel(self.etab, {})
        item = cp.card('etab:adm', 'Des classes sans appel', '3 classes.', '/directeur/suivi-presence/', 'Voir',
                       ['v'], code='ADM-07', family='presences')
        item['etab'] = self.etab.pk
        with patch(CANDIDATS, return_value=[item]):
            moteur.traiter(membre, midi())
        notification = NotificationPersonnel.objects.get(personnel=membre)
        self.assertEqual(notification.donnees['rappel'], 'ADM-07')
        self.assertEqual(RappelEnvoye.objects.get().etablissement_id, self.etab.pk)


class ReglesProfesseurTests(TestCase):
    """Règles PROF-xx : appel, cahier de texte, jauge du jour, cours du lendemain."""

    def setUp(self):
        from school_admin.model.affectation_model import AffectationProfesseur
        from school_admin.model.classe_model import Classe
        from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps, EmploiDuTemps
        from school_admin.model.matiere_model import Matiere
        from school_admin.model.professeur_model import Professeur
        from school_admin.services import cahier_texte as ct

        self.etab = _make_etablissement()
        self.annee = _make_annee(self.etab)
        s = str(self.etab.pk)
        self.classe = Classe.objects.create(nom='6e A', niveau='college', code_classe=f'6A-{s}', capacite_max=30,
                                            etablissement=self.etab, actif=True)
        self.matiere = Matiere.objects.create(nom=f'Maths {s}', code=f'MA{s}'[:10], etablissement=self.etab,
                                              actif=True)
        self.prof = Professeur.objects.create_user(
            username=f'prof.rap.{s}', email=f'prof.rap.{s}@test.local', password='Prof@Test1!', nom='Sarr',
            prenom='Ali', telephone='770000031', numero_employe=f'RP{s}', matiere_principale=self.matiere,
            etablissement=self.etab, niveau_enseignement='college', actif=True)
        AffectationProfesseur.objects.create(professeur=self.prof, classe=self.classe, matiere=self.matiere,
                                             annee_scolaire=self.annee, statut='classique', actif=True)
        edt = EmploiDuTemps.objects.create(classe=self.classe, annee_scolaire=self.annee.libelle,
                                           annee_scolaire_fk=self.annee, est_actif=True, statut_publication='publie')
        self.today = timezone.localdate()
        for decalage in (0, 1):
            jour = ct.JOURS[(self.today + timedelta(days=decalage)).weekday()]
            CreneauEmploiDuTemps.objects.create(emploi_du_temps=edt, jour=jour, heure_debut=time(8, 0),
                                                heure_fin=time(9, 0), matiere=self.matiere, professeur=self.prof,
                                                type_cours='cours')
        self.midi = midi()

    def codes(self, maintenant=None):
        from school_admin.services.rappels.professeur import situations
        return {item['code']: item for item in situations(self.prof, self.annee, maintenant or self.midi)}

    def appel(self, jour):
        from school_admin.model.presence_model import SoumissionListePresence
        SoumissionListePresence.objects.create(classe=self.classe, professeur=self.prof, etablissement=self.etab,
                                               date=jour, annee_scolaire=self.annee)

    def test_rien_tant_que_les_outils_ne_sont_pas_utilises(self):
        self.assertEqual(self.codes(), {})

    def test_appel_rappele_puis_retire_une_fois_fait(self):
        self.appel(self.today - timedelta(days=7))  # le professeur utilise l'appel numérique
        carte = self.codes()['PROF-01']
        self.assertEqual((carte['stage'], carte['group'], carte['count']), ('j', 'now', 1))
        self.assertIn('6e A', carte['text'])
        avant_la_fin = timezone.make_aware(datetime.combine(self.today, time(9, 10)))
        self.assertNotIn('PROF-01', self.codes(avant_la_fin))  # 30 minutes de délai après le cours
        self.appel(self.today)
        self.assertNotIn('PROF-01', self.codes())

    def test_cahier_de_texte_a_completer_puis_renseigne(self):
        from school_admin.model.cahier_texte_model import CahierTexte
        CahierTexte.objects.create(etablissement=self.etab, annee_scolaire=self.annee, professeur=self.prof,
                                   classe=self.classe, date=self.today - timedelta(days=30), titre='Ancien',
                                   contenu='Cours', statut='valide')
        avant = self.codes()['PROF-02']['count']  # cours des 7 derniers jours sans séance
        self.assertGreaterEqual(avant, 1)
        CahierTexte.objects.create(etablissement=self.etab, annee_scolaire=self.annee, professeur=self.prof,
                                   classe=self.classe, date=self.today, heure_debut=time(8, 0), titre='Fractions',
                                   contenu='Cours', statut='brouillon')
        cartes = self.codes()
        self.assertEqual(cartes['PROF-02']['count'], avant - 1)  # le cours du jour est renseigné
        self.assertEqual(cartes['PROF-03']['count'], 1)  # la séance reste à valider

    def test_jauge_du_jour(self):
        from school_admin.services.rappels.professeur import progression
        self.assertIsNone(progression(self.prof, self.midi))
        self.appel(self.today - timedelta(days=7))
        self.assertEqual(progression(self.prof, self.midi)['done'], 0)
        self.appel(self.today)
        avancement = progression(self.prof, self.midi)
        self.assertEqual((avancement['done'], avancement['total']), (1, 1))
        self.assertIn('1/1 appel', avancement['label'])

    def test_cours_de_demain_seulement_si_active_et_le_soir(self):
        soir = timezone.make_aware(datetime.combine(self.today, time(18, 0)))
        self.assertNotIn('PROF-10', self.codes(soir))
        params = moteur.parametres(self.etab.pk)
        params.rappel_cours_demain = True
        params.save()
        self.assertNotIn('PROF-10', self.codes(self.midi))
        carte = self.codes(soir)['PROF-10']
        self.assertEqual((carte['stage'], carte['due']), ('j-1', 'Demain'))

    def test_les_regles_arrivent_dans_les_cartes_du_professeur(self):
        self.appel(self.today - timedelta(days=7))
        with patch('school_admin.services.rappels.professeur.timezone.now', return_value=self.midi):
            codes = {item['code'] for item in cp.candidates(self.prof)}
        self.assertIn('PROF-01', codes)



class ReglesFamilleTests(TestCase):
    """Règles ELV-xx / PAR-xx : examens, absences, moratoire, cours du lendemain, liaison, bulletin."""

    def setUp(self):
        from school_admin.model.classe_model import Classe
        from school_admin.model.lien_familial_model import LienFamilial
        from school_admin.model.matiere_model import Matiere
        from school_admin.model.professeur_model import Professeur
        from school_admin.tests.test_assistant_parent_scope import _make_parent
        from school_admin.tests.test_dashboard_d1 import _make_eleve

        self.etab = _make_etablissement()
        self.annee = _make_annee(self.etab)
        s = str(self.etab.pk)
        self.classe = Classe.objects.create(nom='5e B', niveau='college', code_classe=f'5B-{s}', capacite_max=30,
                                            etablissement=self.etab, actif=True)
        self.matiere = Matiere.objects.create(nom=f'Français {s}', code=f'FR{s}'[:10], etablissement=self.etab,
                                              actif=True)
        self.prof = Professeur.objects.create_user(
            username=f'prof.fam.{s}', email=f'prof.fam.{s}@test.local', password='Prof@Test1!', nom='Ba',
            prenom='Omar', telephone='770000032', numero_employe=f'FM{s}', matiere_principale=self.matiere,
            etablissement=self.etab, niveau_enseignement='college', actif=True)
        self.eleve = _make_eleve(self.etab, self.classe, self.annee, 'Diop', 'Awa', 'f1')
        self.parent = _make_parent(self.etab, 'f1')
        LienFamilial.objects.create(parent=self.parent, eleve=self.eleve, type_lien='mere', statut='valide',
                                    actif=True)
        self.today = timezone.localdate()

    def codes(self, parent, maintenant=None):
        from school_admin.services.rappels.famille import situations
        ctx = f'{self.eleve.prenom} · {self.classe.nom}'
        prefix = f'child:{self.eleve.pk}:year:{self.annee.pk}'
        return {item['code']: item for item in
                situations(self.eleve, self.annee, self.classe, parent, ctx, prefix, maintenant or midi())}

    def absence(self, jours, statut='absent', numero=1):
        from school_admin.model.presence_model import Presence
        Presence.objects.bulk_create([Presence(
            eleve=self.eleve, classe=self.classe, professeur=self.prof, etablissement=self.etab,
            matiere=self.matiere, date=self.today - timedelta(days=jours), statut=statut,
            annee_scolaire=self.annee, numero_appel=numero)])

    def test_sans_donnee_aucune_carte(self):
        self.assertEqual(self.codes(False), {})
        self.assertEqual(self.codes(True), {})

    def test_epreuve_d_examen_publiee(self):
        from school_admin.model.creneau_examen_model import CreneauExamen
        from school_admin.model.periode_model import PeriodeScolaire
        from school_admin.model.session_examen_model import SessionExamen
        PeriodeScolaire.objects.bulk_create([PeriodeScolaire(
            etablissement=self.etab, annee_scolaire=self.annee, nom_periode='Trimestre 1', type_periode='trimestre',
            date_debut=self.today - timedelta(days=60), date_fin=self.today + timedelta(days=30))])
        SessionExamen.objects.bulk_create([SessionExamen(
            etablissement=self.etab, annee_scolaire=self.annee, nom_examen='Composition 1',
            periode=PeriodeScolaire.objects.get(etablissement=self.etab), est_publie=False,
            date_debut=self.today + timedelta(days=2), date_fin=self.today + timedelta(days=4))])
        session = SessionExamen.objects.get(etablissement=self.etab)
        session.classes.add(self.classe)
        session.matieres.add(self.matiere)
        CreneauExamen.objects.bulk_create([CreneauExamen(
            session_examen=session, annee_scolaire=self.annee, matiere=self.matiere,
            date_examen=self.today + timedelta(days=2), heure_debut=time(8, 0), heure_fin=time(10, 0))])
        self.assertNotIn('ELV-03', self.codes(False))  # planning non publié : rien n'est annoncé
        SessionExamen.objects.filter(pk=session.pk).update(est_publie=True)
        carte = self.codes(False)['ELV-03']
        self.assertEqual((carte['stage'], carte['due'], carte['count']), ('j-3', 'Dans 2 jours', 1))
        self.assertIn('08:00', carte['text'])
        self.assertEqual(self.codes(True)['PAR-09']['eleve_id'], self.eleve.pk)

    def test_absence_non_justifiee_pour_le_parent_seulement(self):
        self.absence(1)
        self.absence(2, 'absent_justifie', 2)
        carte = self.codes(True)['PAR-05']
        self.assertEqual(carte['count'], 1)  # l'absence justifiée n'est pas rappelée
        self.assertIn('Awa', carte['text'])
        self.assertNotIn('PAR-05', self.codes(False))

    def test_echeance_de_moratoire(self):
        from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve
        from school_admin.model.recouvrement_model import EcheanceMoratoire, Moratoire
        ComptabiliteEleve.objects.bulk_create([ComptabiliteEleve(
            eleve=self.eleve, etablissement=self.etab, annee_scolaire=self.annee)])
        Moratoire.objects.bulk_create([Moratoire(
            eleve=self.eleve, etablissement=self.etab, annee_scolaire=self.annee,
            comptabilite_eleve=ComptabiliteEleve.objects.get(eleve=self.eleve), motif='Accord', montant_total=30000)])
        EcheanceMoratoire.objects.bulk_create([EcheanceMoratoire(
            moratoire=Moratoire.objects.get(eleve=self.eleve), numero=1,
            date_echeance=self.today + timedelta(days=1), montant=15000)])
        carte = self.codes(True)['PAR-02']
        self.assertEqual((carte['stage'], carte['due']), ('j-1', 'Demain'))
        self.assertIn('15,000', carte['text'])
        EcheanceMoratoire.objects.update(statut='paye')
        self.assertNotIn('PAR-02', self.codes(True))

    def test_cours_de_demain_pour_l_eleve(self):
        from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps, EmploiDuTemps
        from school_admin.services.rappels.famille import JOURS
        edt = EmploiDuTemps.objects.create(classe=self.classe, annee_scolaire=self.annee.libelle,
                                           annee_scolaire_fk=self.annee, est_actif=True, statut_publication='publie')
        CreneauEmploiDuTemps.objects.create(
            emploi_du_temps=edt, jour=JOURS[(self.today + timedelta(days=1)).weekday()], heure_debut=time(8, 0),
            heure_fin=time(9, 0), matiere=self.matiere, professeur=self.prof, type_cours='cours')
        soir = timezone.make_aware(datetime.combine(self.today, time(18, 0)))
        self.assertNotIn('ELV-06', self.codes(False, soir))  # option éteinte par défaut
        params = moteur.parametres(self.etab.pk)
        params.rappel_cours_demain = True
        params.save()
        self.assertNotIn('ELV-06', self.codes(False))  # pas avant 17 h
        self.assertEqual(self.codes(False, soir)['ELV-06']['count'], 1)
        self.assertNotIn('ELV-06', self.codes(True, soir))

    def test_liaison_validee_annoncee_une_seule_fois(self):
        from school_admin.model.demande_liaison_model import DemandeLiaisonParent
        from school_admin.services.rappels.famille import parent_situations
        DemandeLiaisonParent.objects.bulk_create([DemandeLiaisonParent(
            parent_demandeur=self.parent, annee_scolaire=self.annee, matricule_eleve='M1', nom_eleve='Diop',
            prenom_eleve='Awa', date_naissance_eleve=self.eleve.date_naissance, type_lien='mere',
            statut='approuvee', date_traitement=timezone.now(), eleve_valide=self.eleve)])
        cartes = parent_situations(self.parent)
        self.assertEqual([(c['code'], c['once'], c['push']) for c in cartes], [('PAR-08', True, True)])
        with patch(CANDIDATS, return_value=cartes):
            self.assertEqual(len(moteur.traiter(self.parent, midi())), 1)
            self.assertEqual(moteur.traiter(self.parent, midi(10)), [])  # jamais relancée

    def test_bulletin_non_consulte_apres_deux_jours(self):
        from school_admin.model.notification_eleve_model import NotificationEleve
        notification = NotificationEleve.objects.create(eleve=self.eleve, titre='Bulletin disponible',
                                                        message='Trimestre 1', type_notification='bulletin')
        def bulletin():
            return next(c for c in cp.recent_notifications(self.eleve, 'eleve')
                        if c['key'] == f'notification:eleve:{notification.pk}')
        self.assertEqual((bulletin()['code'], bulletin()['push']), ('NOTIF', False))  # trop tôt pour rappeler
        NotificationEleve.objects.filter(pk=notification.pk).update(
            date_creation=timezone.now() - timedelta(days=3))
        carte = bulletin()
        self.assertEqual((carte['code'], carte['once'], carte['push'], carte['group']),
                         ('ELV-05', True, True, 'now'))

    def test_les_regles_arrivent_dans_les_cartes(self):
        self.absence(1)
        self.assertIn('PAR-05', {item['code'] for item in cp.candidates(self.parent)})
        self.assertNotIn('PAR-05', {item['code'] for item in cp.candidates(self.eleve)})
