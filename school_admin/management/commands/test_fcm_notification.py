"""
Commande Django pour tester l'envoi de notifications FCM
Usage: python manage.py test_fcm_notification --eleve_id 2237
"""

from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from school_admin.model.eleve_model import Eleve
from school_admin.model.fcm_token_model import FCMToken
from school_admin.services.firebase_service import FirebaseService
from django.utils import timezone
import json


class Command(BaseCommand):
    help = 'Teste l\'envoi de notifications FCM à un élève spécifique'

    def add_arguments(self, parser):
        parser.add_argument(
            '--eleve_id',
            type=int,
            help='ID de l\'élève à tester',
            default=2237
        )
        parser.add_argument(
            '--token_id',
            type=int,
            help='ID du token FCM à tester (optionnel)',
            default=None
        )
        parser.add_argument(
            '--token',
            type=str,
            help='Token FCM direct à tester (optionnel)',
            default=None
        )

    def handle(self, *args, **options):
        eleve_id = options['eleve_id']
        token_id = options.get('token_id')
        token_direct = options.get('token')

        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('TEST DE NOTIFICATION FCM'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))

        # Récupérer l'élève
        try:
            eleve = Eleve.objects.get(id=eleve_id)
            self.stdout.write(self.style.SUCCESS(f'[OK] Eleve trouve: {eleve.nom_complet} (ID: {eleve.id})'))
        except Eleve.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'[ERREUR] Eleve avec ID {eleve_id} introuvable'))
            return

        # Récupérer les tokens FCM
        content_type = ContentType.objects.get_for_model(Eleve)
        tokens_query = FCMToken.objects.filter(
            content_type=content_type,
            object_id=eleve.id,
            is_active=True
        )

        if token_id:
            tokens_query = tokens_query.filter(id=token_id)

        tokens = list(tokens_query)

        if not tokens and not token_direct:
            self.stdout.write(self.style.WARNING(f'[ATTENTION] Aucun token FCM actif trouve pour l\'eleve {eleve.nom_complet}'))
            self.stdout.write(self.style.WARNING(f'   ContentType ID: {content_type.id}, Object ID: {eleve.id}'))
            return

        # Afficher les informations des tokens
        self.stdout.write(f'\n[TOKENS] Tokens FCM trouves: {len(tokens)}')
        for idx, token_obj in enumerate(tokens, 1):
            self.stdout.write(f'   {idx}. Token ID: {token_obj.id}')
            self.stdout.write(f'      Token: {token_obj.token[:50]}...')
            self.stdout.write(f'      Device: {token_obj.device_type} - {token_obj.device_name}')
            self.stdout.write(f'      Cree le: {token_obj.created_at}')
            self.stdout.write(f'      Actif: {token_obj.is_active}')

        # Si un token direct est fourni, l'ajouter
        if token_direct:
            self.stdout.write(f'\n[TOKEN] Token direct fourni: {token_direct[:50]}...')
            tokens_to_test = [token_direct]
        else:
            tokens_to_test = [t.token for t in tokens]

        # Initialiser Firebase
        self.stdout.write(f'\n[FIREBASE] Initialisation de Firebase...')
        if not FirebaseService.initialize():
            self.stdout.write(self.style.ERROR('[ERREUR] Echec de l\'initialisation Firebase'))
            return
        self.stdout.write(self.style.SUCCESS('[OK] Firebase initialise avec succes'))

        # Préparer la notification de test
        title = "Test de notification FCM"
        body = f"Bonjour {eleve.prenom}, ceci est un test de notification push. Si vous recevez ce message, le systeme fonctionne correctement !"
        test_data = {
            'type': 'test_notification',
            'eleve_id': str(eleve.id),
            'eleve_nom': eleve.nom_complet,
            'timestamp': timezone.now().isoformat(),
            'url': '/eleve/dashboard/',
            'test': 'true'
        }

        self.stdout.write(f'\n[ENVOI] Envoi de la notification...')
        self.stdout.write(f'   Titre: {title}')
        self.stdout.write(f'   Message: {body}')
        self.stdout.write(f'   Donnees: {json.dumps(test_data, indent=2, ensure_ascii=False)}')

        # Test 1: Envoi via send_notification_to_multiple_users (méthode utilisée dans le code)
        self.stdout.write(f'\n' + '-'*60)
        self.stdout.write(self.style.SUCCESS('TEST 1: Envoi via send_notification_to_multiple_users'))
        self.stdout.write('-'*60)
        
        try:
            result1 = FirebaseService.send_notification_to_multiple_users(
                users=[eleve],
                title=title,
                body=body,
                data=test_data
            )

            self.stdout.write(f'\n[RESULTATS] Resultats:')
            self.stdout.write(f'   [OK] Succes: {result1.get("success_count", 0)}')
            self.stdout.write(f'   [ERREUR] Echecs: {result1.get("failure_count", 0)}')

            if result1.get("error"):
                self.stdout.write(self.style.ERROR(f'   [ATTENTION] Erreur: {result1["error"]}'))

            if result1.get("responses"):
                for idx, response in enumerate(result1["responses"], 1):
                    if hasattr(response, 'success') and response.success:
                        self.stdout.write(self.style.SUCCESS(f'   [OK] Token {idx}: Notification envoyee avec succes'))
                    elif hasattr(response, 'exception') and response.exception:
                        self.stdout.write(self.style.ERROR(f'   [ERREUR] Token {idx}: {response.exception}'))
                    else:
                        self.stdout.write(f'   [ATTENTION] Token {idx}: Reponse inconnue')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'[ERREUR] Erreur lors de l\'envoi: {str(e)}'))
            import traceback
            self.stdout.write(self.style.ERROR(traceback.format_exc()))

        # Test 2: Envoi direct avec le token (si token direct fourni ou si on veut tester un token spécifique)
        if token_direct or len(tokens) == 1:
            self.stdout.write(f'\n' + '-'*60)
            self.stdout.write(self.style.SUCCESS('TEST 2: Envoi direct avec le token'))
            self.stdout.write('-'*60)
            
            token_to_test = token_direct if token_direct else tokens[0].token
            
            try:
                result2 = FirebaseService.send_notification(
                    token=token_to_test,
                    title=title + " (Test direct)",
                    body=body,
                    data=test_data
                )

                if result2:
                    self.stdout.write(self.style.SUCCESS(f'[OK] Notification envoyee avec succes (methode directe)'))
                else:
                    self.stdout.write(self.style.ERROR(f'[ERREUR] Echec de l\'envoi (methode directe)'))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'[ERREUR] Erreur lors de l\'envoi direct: {str(e)}'))
                import traceback
                self.stdout.write(self.style.ERROR(traceback.format_exc()))

        # Test 3: Envoi via multicast avec les tokens
        if tokens_to_test:
            self.stdout.write(f'\n' + '-'*60)
            self.stdout.write(self.style.SUCCESS('TEST 3: Envoi via send_multicast'))
            self.stdout.write('-'*60)
            
            try:
                result3 = FirebaseService.send_multicast(
                    tokens=tokens_to_test,
                    title=title + " (Test multicast)",
                    body=body,
                    data=test_data
                )

                self.stdout.write(f'\n[RESULTATS] Resultats multicast:')
                self.stdout.write(f'   [OK] Succes: {result3.get("success_count", 0)}')
                self.stdout.write(f'   [ERREUR] Echecs: {result3.get("failure_count", 0)}')

                if result3.get("error"):
                    self.stdout.write(self.style.ERROR(f'   [ATTENTION] Erreur: {result3["error"]}'))

                if result3.get("responses"):
                    for idx, response in enumerate(result3["responses"], 1):
                        if hasattr(response, 'success') and response.success:
                            self.stdout.write(self.style.SUCCESS(f'   [OK] Token {idx}: Notification envoyee'))
                        elif hasattr(response, 'exception') and response.exception:
                            self.stdout.write(self.style.ERROR(f'   [ERREUR] Token {idx}: {response.exception}'))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'[ERREUR] Erreur lors de l\'envoi multicast: {str(e)}'))
                import traceback
                self.stdout.write(self.style.ERROR(traceback.format_exc()))

        # Vérifier les tokens dans la base de données
        self.stdout.write(f'\n' + '-'*60)
        self.stdout.write(self.style.SUCCESS('VERIFICATION DES TOKENS EN BASE'))
        self.stdout.write('-'*60)
        
        all_tokens = FCMToken.objects.filter(
            content_type=content_type,
            object_id=eleve.id
        )
        
        self.stdout.write(f'\n[TOKENS] Tous les tokens (actifs et inactifs): {all_tokens.count()}')
        for token_obj in all_tokens:
            status = '[ACTIF]' if token_obj.is_active else '[INACTIF]'
            self.stdout.write(f'   {status} - ID: {token_obj.id} - Token: {token_obj.token[:50]}...')
            self.stdout.write(f'      Device: {token_obj.device_type} - Cree: {token_obj.created_at}')

        self.stdout.write(f'\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('TEST TERMINE'))
        self.stdout.write('='*60 + '\n')

