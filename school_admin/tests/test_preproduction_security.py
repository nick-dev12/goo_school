import re
from datetime import date
from io import StringIO
from unittest.mock import Mock, patch

from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase, SimpleTestCase
from django.urls import reverse, resolve, Resolver404

from school_admin.model.compte_user import CompteUser
from school_admin.model.fcm_token_model import FCMToken
from school_admin.api_views.fcm_views import save_fcm_token, delete_fcm_token
from school_admin.services.recouvrement import verifier_rupture_moratoires, envoyer_relances_automatiques
from school_admin.consumers.websocket_auth_middleware import _user_from_session


class RecoverySecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = CompteUser.objects.create_user(
            username='recovery.audit', email='recovery@example.test',
            password='Ancien@Test12!', nom='Audit', prenom='Compte', fonction='administrateur',
        )

    def start_recovery(self):
        response = self.client.post(reverse('school_admin:password_reset_request'), {'identifier': self.user.username})
        self.assertEqual(response.status_code, 302)
        code = re.search(r'\b[0-9]{6}\b', mail.outbox[-1].body).group()
        return response.url, code

    def submit(self, url, code, password='Nouveau@Test54!'):
        return self.client.post(url, {'reset_code': code, 'new_password': password, 'confirm_password': password})

    def test_legacy_routes_cannot_reset_any_profile(self):
        for kind in ('professeur', 'eleve', 'parent'):
            for step in ('verify', 'reset'):
                response = self.client.post(f'/password-reset/{kind}/{step}/MG000001/', {
                    'new_password': 'Pirate@Test34!', 'confirm_password': 'Pirate@Test34!',
                })
                self.assertRedirects(response, reverse('school_admin:password_reset_request'), fetch_redirect_response=False)

    def test_code_required_expiring_and_one_use(self):
        url, code = self.start_recovery()
        self.assertEqual(self.submit(url, 'xxxxxx').status_code, 400)
        self.assertEqual(self.submit(url, code).status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Nouveau@Test54!'))
        self.submit(url, code, 'Replay@Test54!')
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password('Replay@Test54!'))

    def test_other_session_cannot_use_code(self):
        url, code = self.start_recovery()
        response = Client().post(url, {'reset_code': code, 'new_password': 'Other@Test54!', 'confirm_password': 'Other@Test54!'})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Ancien@Test12!'))

    def test_expired_code_rejected(self):
        url, code = self.start_recovery()
        cache.delete('password-reset:' + self.client.session['password_reset_nonce'])
        self.assertEqual(self.submit(url, code).status_code, 400)

    def test_too_many_attempts_invalidate_correct_code(self):
        url, code = self.start_recovery()
        for _ in range(5):
            self.submit(url, 'xxxxxx')
        self.assertEqual(self.submit(url, code).status_code, 400)

    def test_django_password_validators_applied(self):
        url, code = self.start_recovery()
        self.assertEqual(self.submit(url, code, '12345678910').status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Ancien@Test12!'))

    def test_password_change_invalidates_pending_recovery(self):
        url, code = self.start_recovery()
        self.user.set_password('Changed@Test54!')
        self.user.save(update_fields=['password'])
        self.submit(url, code)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Changed@Test54!'))

    def test_unknown_identifier_same_redirect_shape(self):
        response = self.client.post(reverse('school_admin:password_reset_request'), {'identifier': 'absent@example.test'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/secure/', response.url)

    def test_dev_login_removed(self):
        with self.assertRaises(Resolver404):
            resolve('/dev-login/recovery.audit/')

    def test_private_response_not_cached_and_old_session_is_shortened(self):
        self.client.force_login(self.user)
        session = self.client.session
        session.set_expiry(315360000)
        session.save()
        response = self.client.get('/health/ready/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertLessEqual(self.client.session.get_expiry_age(), 28800)

    def test_disabled_account_loses_existing_session(self):
        self.client.force_login(self.user, backend='school_admin.authentication_backends.MultiUserBackend')
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        response = self.client.get('/finances/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/connexion/', response.url)


class FcmOwnershipTests(TestCase):
    def setUp(self):
        self.owner = CompteUser.objects.create_user(username='fcm-owner', email='owner@test.local', password='Test@12345', nom='A', prenom='B')
        self.other = CompteUser.objects.create_user(username='fcm-other', email='other@test.local', password='Test@12345', nom='C', prenom='D')
        self.token = FCMToken.objects.create(token='private-device-token', content_type=ContentType.objects.get_for_model(self.owner), object_id=self.owner.pk)

    def request(self, user):
        request = RequestFactory().post('/api/fcm/', {'token': self.token.token}, content_type='application/json')
        request.user = user
        return request

    def test_cannot_delete_other_accounts_device(self):
        self.assertEqual(delete_fcm_token(self.request(self.other)).status_code, 200)
        self.assertTrue(FCMToken.objects.filter(pk=self.token.pk).exists())
        delete_fcm_token(self.request(self.owner))
        self.assertFalse(FCMToken.objects.filter(pk=self.token.pk).exists())

    def test_cannot_reassign_other_accounts_device(self):
        self.assertEqual(save_fcm_token(self.request(self.other)).status_code, 403)
        self.token.refresh_from_db()
        self.assertEqual(self.token.object_id, self.owner.pk)


class DryRunTests(SimpleTestCase):
    @patch('school_admin.management.commands.envoyer_relances_impayes.envoyer_relances_automatiques', return_value={})
    @patch('school_admin.management.commands.envoyer_relances_impayes.verifier_rupture_moratoires', return_value=0)
    def test_command_propagates_simulation(self, moratoires, relances):
        call_command('envoyer_relances_impayes', '--dry-run', stdout=StringIO())
        moratoires.assert_called_once_with(dry_run=True)
        relances.assert_called_once_with(dry_run=True)

    @patch('school_admin.model.recouvrement_model.Moratoire.objects')
    def test_moratoire_simulation_does_not_write(self, manager):
        echeance = Mock(date_echeance=date(2026, 1, 1))
        echeance.est_totalement_paye.return_value = False
        moratoire = Mock()
        moratoire.echeances.all.return_value = [echeance]
        manager.filter.return_value.prefetch_related.return_value = [moratoire]
        self.assertEqual(verifier_rupture_moratoires(aujourdhui=date(2026, 2, 1), dry_run=True), 1)
        moratoire.save.assert_not_called()
        echeance.save.assert_not_called()


class WebSocketSecurityTests(SimpleTestCase):
    async def test_old_password_session_hash_refused(self):
        user = Mock()
        user.get_session_auth_hash.return_value = 'new-password-hash'
        user.get_session_auth_fallback_hash.return_value = []
        with patch('school_admin.authentication_backends.MultiUserBackend.get_user', return_value=user):
            resolved = await _user_from_session({'session': {
                '_auth_user_id': '1', '_auth_user_type': 'professeur',
                '_auth_user_hash': 'old-password-hash',
            }})
        self.assertFalse(resolved.is_authenticated)

    async def test_valid_session_hash_accepted(self):
        user = Mock()
        user.get_session_auth_hash.return_value = 'current-hash'
        user.get_session_auth_fallback_hash.return_value = []
        with patch('school_admin.authentication_backends.MultiUserBackend.get_user', return_value=user):
            resolved = await _user_from_session({'session': {
                '_auth_user_id': '1', '_auth_user_type': 'professeur',
                '_auth_user_hash': 'current-hash',
            }})
        self.assertIs(resolved, user)

    async def test_untrusted_origin_refused_by_asgi(self):
        from channels.testing import WebsocketCommunicator
        from school.asgi import application
        communicator = WebsocketCommunicator(application, '/ws/assistant/', headers=[
            (b'origin', b'https://untrusted.example'),
        ])
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()
