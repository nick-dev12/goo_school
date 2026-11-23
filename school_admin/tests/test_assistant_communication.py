"""Assistant direction, lot 3 : rappels programmés, messages ciblés, courriers, notifications, impressions,
suites de sanctions."""
from datetime import datetime, timedelta
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone

from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.notification_directeur_model import NotificationDirecteur
from school_admin.model.notification_enseignant_model import NotificationEnseignant
from school_admin.model.notification_parent_model import NotificationParent
from school_admin.model.personnel_administratif_model import PersonnelAdministratif
from school_admin.model.rappel_model import CourrierEtablissement, NotificationPersonnel, RappelPersonnel
from school_admin.model.sanction_model import Sanction
from school_admin.services.assistant_actions import ACTION_SPECS
from school_admin.services.assistant_communication import parser_quand
from school_admin.services.assistant_tools import build_assistant_context, execute_tool
from school_admin.services.rappels.personnels import envoyer_rappels_personnels
from school_admin.tests.test_assistant_parent_scope import _make_parent
from school_admin.tests_service_cc import Base
from school_admin.utils.permissions_personnel import PERMISSIONS_DISPONIBLES

LUNDI_10H = timezone.make_aware(datetime(2026, 11, 23, 10, 0))  # lundi


class ParserQuandTests(Base):
    def test_expressions_courantes(self):
        cas = {
            'demain à 9h': datetime(2026, 11, 24, 9, 0),
            'après-demain 14h30': datetime(2026, 11, 25, 14, 30),
            'vendredi à 8 h': datetime(2026, 11, 27, 8, 0),
            'lundi': datetime(2026, 11, 30, 8, 0),
            'le 2/12 à 15h': datetime(2026, 12, 2, 15, 0),
            '5 décembre à midi': datetime(2026, 12, 5, 12, 0),
            'ce soir': datetime(2026, 11, 23, 18, 0),
            '16h': datetime(2026, 11, 23, 16, 0),
            '9h': datetime(2026, 11, 24, 9, 0),  # déjà passé aujourd'hui : demain
        }
        for texte, attendu in cas.items():
            obtenu = timezone.localtime(parser_quand(texte, LUNDI_10H)).replace(tzinfo=None)
            self.assertEqual(obtenu, attendu, texte)
        self.assertEqual(parser_quand('dans 2 heures', LUNDI_10H), LUNDI_10H + timedelta(hours=2))
        self.assertIsNone(parser_quand('un jour peut-être', LUNDI_10H))


class AssistantCommunicationTests(Base):
    def setUp(self):
        super().setUp()
        self.ctx = build_assistant_context(self.etab)
        self.secretaire = PersonnelAdministratif.objects.create(
            username=f'fatim.{self.etab.pk}', nom='Sow', prenom='Fatim', telephone='770000009',
            fonction='secretaire', etablissement=self.etab, actif=True)

    def _faire(self, nom, args, ctx=None):
        ctx = ctx or self.ctx
        brouillon = execute_tool(ctx, nom, args)
        self.assertEqual(brouillon.get('statut'), 'en_attente_confirmation', brouillon)
        return ACTION_SPECS[nom].apply(ctx, brouillon)

    # ----------------------------------------------------------------- rappels
    def test_rappel_programme_puis_envoye_a_l_heure(self):
        self.assertEqual(execute_tool(self.ctx, 'creer_rappel', {'texte': 'Appeler Senelec'})['manquants'], ['quand'])
        resultat = self._faire('creer_rappel', {'texte': 'Appeler Senelec', 'quand': 'dans 2 heures'})
        self.assertEqual(resultat['statut'], 'ok', resultat)
        rappel = RappelPersonnel.objects.get()
        self.assertIsNone(rappel.personnel)
        self.assertEqual(len(execute_tool(self.ctx, 'get_mes_rappels', {})['rappels']), 1)
        with patch('school_admin.services.push_delivery.enqueue') as push:
            self.assertEqual(envoyer_rappels_personnels(), 0)  # pas encore l'heure
            self.assertEqual(envoyer_rappels_personnels(timezone.now() + timedelta(hours=3)), 1)
            self.assertEqual(envoyer_rappels_personnels(timezone.now() + timedelta(hours=4)), 0)  # une seule fois
            self.assertEqual(push.call_count, 1)
        notif = NotificationDirecteur.objects.get(etablissement=self.etab)
        self.assertEqual(notif.message, 'Appeler Senelec')

    def test_rappel_du_personnel_reste_le_sien(self):
        ctx_perso = build_assistant_context(self.etab, personnel=self.secretaire)
        self._faire('creer_rappel', {'texte': 'Imprimer les reçus', 'quand': 'demain à 8h'}, ctx_perso)
        self.assertEqual(execute_tool(self.ctx, 'get_mes_rappels', {})['nb'], 0)  # pas celui du directeur
        self.assertEqual(execute_tool(ctx_perso, 'get_mes_rappels', {})['nb'], 1)
        self._faire('supprimer_rappel', {'query': 'reçus'}, ctx_perso)
        self.assertFalse(RappelPersonnel.objects.exists())

    # ----------------------------------------------------------------- messages
    def test_message_aux_parents_et_aux_enseignants(self):
        parent = _make_parent(self.etab, suffix='com')
        LienFamilial.objects.create(parent=parent, eleve=self.awa, type_lien='mere', statut='valide', actif=True)
        with patch('school_admin.services.push_delivery.enqueue'):
            r = self._faire('envoyer_message', {'cible': 'parents', 'eleve': 'Awa Ndoye', 'titre': 'Réunion',
                                                'message': 'Merci de passer vendredi à 10 h.'})
            self.assertEqual(r['statut'], 'ok', r)
            self._faire('envoyer_message', {'cible': 'parents', 'classe': 'ECO L1 A', 'message': 'Sortie mardi.'})
            self._faire('envoyer_message', {'cible': 'enseignants', 'classe': 'ECO L1 A', 'message': 'Conseil lundi.'})
            self._faire('envoyer_message', {'cible': 'personnel', 'nom': 'Fatim', 'message': 'Préparer les dossiers.'})
        self.assertEqual(NotificationParent.objects.filter(parent=parent).count(), 2)
        self.assertEqual(NotificationEnseignant.objects.filter(enseignant__in=[self.cm, self.td]).count(), 2)
        self.assertEqual(NotificationPersonnel.objects.filter(personnel=self.secretaire).count(), 1)

    def test_notifications_marquees_lues(self):
        NotificationDirecteur.objects.create(etablissement=self.etab, titre='A', message='a')
        NotificationDirecteur.objects.create(etablissement=self.etab, titre='B', message='b')
        self._faire('marquer_notifications_lues', {})
        self.assertFalse(NotificationDirecteur.objects.filter(etablissement=self.etab, lu=False).exists())
        self.assertIn('erreur', execute_tool(self.ctx, 'marquer_notifications_lues', {}))

    # ----------------------------------------------------------------- courriers et impressions
    def test_courrier_libre_imprimable(self):
        court = execute_tool(self.ctx, 'rediger_courrier', {'objet': 'Réunion'})
        self.assertEqual(court['manquants'], ['contenu'])
        r = self._faire('rediger_courrier', {
            'type': 'note de service', 'objet': 'Réunion pédagogique', 'destinataire': 'Tous les enseignants',
            'contenu': 'Madame, Monsieur,\n\nUne réunion se tiendra vendredi à 16 h en salle des professeurs.\n\n'
                       'Votre présence est indispensable.'})
        courrier = CourrierEtablissement.objects.get()
        self.assertEqual((courrier.type_courrier, r['url']),
                         ('note_service', reverse('directeur:courrier_detail', args=[courrier.id])))
        self.client.force_login(self.etab)
        page = self.client.get(r['url'])
        self.assertContains(page, 'Réunion pédagogique')
        self.assertContains(page, 'NOTE DE SERVICE')
        self.assertContains(self.client.get(reverse('directeur:courriers')), 'Réunion pédagogique')

    def test_imprimer_document(self):
        r = execute_tool(self.ctx, 'imprimer_document', {'document': 'feuille de présence', 'classe': 'ECO L1 A'})
        self.assertTrue(r['ouvrir'])
        self.assertIn(f'/{self.classe.id}/', r['url'])
        self.assertIn('erreur', execute_tool(self.ctx, 'imprimer_document', {'document': 'bulletins'}))
        self.assertIn('impayes', execute_tool(self.ctx, 'imprimer_document', {'document': 'impayés'})['url'])

    # ----------------------------------------------------------------- sanctions
    def test_lever_puis_supprimer_une_sanction(self):
        sanction = Sanction.objects.create(
            eleve=self.awa, classe=self.classe, etablissement=self.etab, annee_scolaire=self.annee,
            type_sanction='avertissement', raison='indiscipline', gravite='legere', attribue_par_type='directeur',
            attribue_par_nom='Directeur')
        self.assertEqual(execute_tool(self.ctx, 'lever_sanction', {'eleve': 'Awa'})['manquants'], ['motif'])
        self._faire('lever_sanction', {'eleve': 'Awa', 'motif': 'Bonne conduite depuis un mois'})
        sanction.refresh_from_db()
        self.assertTrue(sanction.executee)
        self.assertIn('Bonne conduite', sanction.description)
        self._faire('supprimer_sanction', {'eleve': 'Awa'})
        self.assertFalse(Sanction.objects.exists())

    # ----------------------------------------------------------------- permissions
    def test_permissions_du_personnel(self):
        self.secretaire.permissions = {k: False for k in PERMISSIONS_DISPONIBLES}
        self.secretaire.save()
        ctx_perso = build_assistant_context(self.etab, personnel=self.secretaire)
        for outil in ('envoyer_message', 'rediger_courrier', 'get_courriers', 'imprimer_document', 'lever_sanction',
                      'supprimer_sanction'):
            self.assertIn('autorisation', execute_tool(ctx_perso, outil, {}).get('erreur', ''), outil)
        # Ses propres rappels restent possibles sans permission particulière.
        self.assertEqual(execute_tool(ctx_perso, 'creer_rappel', {'texte': 'x', 'quand': 'demain 9h'})['statut'],
                         'en_attente_confirmation')
        self.secretaire.permissions = {'eleves_liste': True}
        self.secretaire.save()
        r = execute_tool(build_assistant_context(self.etab, personnel=self.secretaire), 'imprimer_document',
                         {'document': 'bulletins', 'classe': 'ECO L1 A'})
        self.assertIn('autorisation', r['erreur'])  # liste oui, bulletins non
