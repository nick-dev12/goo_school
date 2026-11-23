import time
from importlib import import_module
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.test import TestCase

from school_admin.consumers.assistant_consumer import AssistantConsumer
from school_admin.model.annonce_model import Annonce
from school_admin.model.personnel_administratif_model import PersonnelAdministratif
from school_admin.tests.test_assistant_directeur_tools import _make_annee, _make_etablissement_type


class AssistantDirectionConfirmationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etablissement = _make_etablissement_type('superieur', 'aria-ecriture')
        cls.annee = _make_annee(cls.etablissement)
        cls.historique = _make_annee(cls.etablissement, '2025-2026', debut=2025, active=False)
        cls.personnel = PersonnelAdministratif.objects.create(
            username='aria.annonce', email='aria-annonce@example.test',
            nom='Sarr', prenom='Ousmane', telephone='770000012',
            fonction='secretaire', etablissement=cls.etablissement,
            permissions={'annonces_voir': True},
        )

    def setUp(self):
        session_class = import_module(settings.SESSION_ENGINE).SessionStore
        self.session = session_class()
        self.brouillon = {
            'name': 'creer_publier_annonce',
            'draft': {'titre': 'Message de test', 'contenu': 'Texte fictif', 'destinataires': ['tous']},
            'confirmation': {
                'id': uuid4().hex, 'expire': time.time() + 60,
                'etablissement': self.etablissement.pk, 'personnel': self.personnel.pk,
                'annee': self.annee.pk,
            },
        }
        self.session['aria_pending'] = self.brouillon
        self.session[SESSION_KEY] = str(self.personnel.pk)
        self.session['_auth_user_type'] = 'personnel'
        self.session.save()

    def consumer(self):
        consumer = AssistantConsumer()
        consumer.scope = {'session': self.session}
        consumer.etablissement = self.etablissement
        consumer.personnel = self.personnel
        return consumer

    def autoriser(self):
        return async_to_sync(self.consumer()._authorize_direction_confirmation)(self.brouillon)

    def test_droit_revoque_apres_preparation(self):
        PersonnelAdministratif.objects.filter(pk=self.personnel.pk).update(permissions={'annonces_voir': False})
        ctx, erreur = self.autoriser()
        self.assertIsNone(ctx)
        self.assertIn('autorisation', erreur)

    def test_annee_changee_sur_une_autre_page(self):
        session_class = import_module(settings.SESSION_ENGINE).SessionStore
        autre_page = session_class(self.session.session_key)
        autre_page['annee_scolaire_consultee_id'] = self.historique.pk
        autre_page.save()
        ctx, erreur = self.autoriser()
        self.assertIsNone(ctx)
        self.assertIn('année scolaire consultée a changé', erreur)

    def test_deux_connexions_ne_peuvent_reutiliser_le_meme_brouillon(self):
        ctx, erreur = self.autoriser()
        self.assertIsNone(erreur)
        self.assertEqual(ctx.annee_scolaire.pk, self.annee.pk)
        ctx, erreur = self.autoriser()
        self.assertIsNone(ctx)
        self.assertIn('déjà été confirmée', erreur)

    def test_brouillon_annule_depuis_une_autre_connexion(self):
        session_class = import_module(settings.SESSION_ENGINE).SessionStore
        autre_page = session_class(self.session.session_key)
        autre_page.pop('aria_pending')
        autre_page.save()
        ctx, erreur = self.autoriser()
        self.assertIsNone(ctx)
        self.assertIn('plus valable', erreur)

    def test_enregistrement_du_brouillon_conserve_l_annee_choisie_sur_une_autre_page(self):
        session_class = import_module(settings.SESSION_ENGINE).SessionStore
        autre_page = session_class(self.session.session_key)
        autre_page['annee_scolaire_consultee_id'] = self.historique.pk
        autre_page.save()
        async_to_sync(self.consumer()._save_direction_pending)(self.brouillon)
        actualisee = session_class(self.session.session_key)
        self.assertEqual(actualisee['annee_scolaire_consultee_id'], self.historique.pk)

    def test_confirmation_websocket_enregistre_une_fois_le_brouillon_affiche(self):
        self.brouillon['draft']['publier'] = False
        self.session['aria_pending'] = self.brouillon
        self.session.save()
        consumer = self.consumer()
        consumer.pending_action = self.brouillon
        consumer._send_json = AsyncMock()
        consumer._send_action_result = AsyncMock()
        consumer._speak_and_finish = AsyncMock()
        annonces = Annonce.objects.filter(etablissement=self.etablissement)
        self.assertFalse(annonces.exists())
        with patch('school_admin.services.realtime_helpers.emit_live'):
            async_to_sync(consumer._confirm_pending)(confirmation_id='ancien-brouillon')
            self.assertFalse(annonces.exists())
            identifiant = self.brouillon['confirmation']['id']
            async_to_sync(consumer._confirm_pending)(confirmation_id=identifiant)
            async_to_sync(consumer._confirm_pending)(confirmation_id=identifiant)
        self.assertEqual(annonces.get().statut, 'brouillon')
