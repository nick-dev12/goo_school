"""
Vues de test pour les notifications FCM
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import json
import logging

from school_admin.model.fcm_token_model import FCMToken
from school_admin.services.firebase_service import FirebaseService

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
@login_required
def test_notification(request):
    """
    Envoie une notification de test à l'utilisateur connecté
    """
    try:
        # Récupérer l'utilisateur connecté
        user = request.user
        
        # Chercher le token FCM de l'utilisateur
        from django.contrib.contenttypes.models import ContentType
        content_type = ContentType.objects.get_for_model(user.__class__)
        
        tokens = FCMToken.objects.filter(
            content_type=content_type,
            object_id=user.id,
            is_active=True
        )
        
        if not tokens.exists():
            return JsonResponse({
                'success': False,
                'error': 'Aucun token FCM trouvé pour cet utilisateur',
                'user_type': user.__class__.__name__,
                'user_id': user.id
            })
        
        # Initialiser Firebase
        if not FirebaseService.initialize():
            return JsonResponse({
                'success': False,
                'error': 'Impossible d\'initialiser Firebase'
            })
        
        # Préparer la notification de test
        title = "🔔 Test de notification"
        body = f"Bonjour {user.prenom} {user.nom}, cette notification de test confirme que le système fonctionne correctement !"
        
        results = []
        for fcm_token in tokens:
            try:
                result = FirebaseService.send_notification(
                    token=fcm_token.token,
                    title=title,
                    body=body,
                    data={
                        'type': 'test',
                        'url': '/eleve/dashboard/',
                        'test_time': str(timezone.now())
                    }
                )
                
                results.append({
                    'token_id': fcm_token.id,
                    'token_preview': fcm_token.token[:20] + '...',
                    'success': True,
                    'message_id': result if result else 'Aucun ID retourné'
                })
                
            except Exception as e:
                logger.error(f"Erreur envoi notification test: {str(e)}")
                results.append({
                    'token_id': fcm_token.id,
                    'token_preview': fcm_token.token[:20] + '...',
                    'success': False,
                    'error': str(e)
                })
        
        return JsonResponse({
            'success': True,
            'message': f'Notification(s) de test envoyée(s) à {len(results)} token(s)',
            'results': results,
            'user': {
                'type': user.__class__.__name__,
                'id': user.id,
                'nom': f'{user.prenom} {user.nom}'
            }
        })
        
    except Exception as e:
        logger.error(f"Erreur test notification: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
@login_required
def check_fcm_status(request):
    """
    Vérifie le statut FCM de l'utilisateur connecté
    """
    try:
        user = request.user
        
        # Chercher les tokens de l'utilisateur
        from django.contrib.contenttypes.models import ContentType
        from django.utils import timezone
        
        content_type = ContentType.objects.get_for_model(user.__class__)
        
        tokens = FCMToken.objects.filter(
            content_type=content_type,
            object_id=user.id
        )
        
        token_list = []
        for token in tokens:
            token_list.append({
                'id': token.id,
                'token_preview': token.token[:30] + '...' if len(token.token) > 30 else token.token,
                'device_type': token.device_type,
                'device_name': token.device_name,
                'is_active': token.is_active,
                'created_at': token.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': token.updated_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        # Vérifier si Firebase est initialisé
        firebase_initialized = FirebaseService.initialize()
        
        return JsonResponse({
            'success': True,
            'user': {
                'type': user.__class__.__name__,
                'id': user.id,
                'nom': f'{user.prenom} {user.nom}'
            },
            'tokens_count': len(token_list),
            'tokens': token_list,
            'firebase_initialized': firebase_initialized
        })
        
    except Exception as e:
        logger.error(f"Erreur check FCM status: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
@login_required
def test_notification_eleve(request):
    """
    Teste l'envoi de notification à un élève spécifique (pour les tests)
    """
    try:
        from django.contrib.contenttypes.models import ContentType
        from school_admin.model.eleve_model import Eleve
        import json
        
        data = json.loads(request.body) if request.body else {}
        eleve_id = data.get('eleve_id', request.user.id if isinstance(request.user, Eleve) else None)
        token_id = data.get('token_id')
        
        if not eleve_id:
            return JsonResponse({
                'success': False,
                'error': 'ID élève manquant'
            }, status=400)
        
        # Récupérer l'élève
        try:
            eleve = Eleve.objects.get(id=eleve_id)
        except Eleve.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Élève avec ID {eleve_id} introuvable'
            }, status=404)
        
        # Récupérer les tokens
        content_type = ContentType.objects.get_for_model(Eleve)
        tokens_query = FCMToken.objects.filter(
            content_type=content_type,
            object_id=eleve.id,
            is_active=True
        )
        
        if token_id:
            tokens_query = tokens_query.filter(id=token_id)
        
        tokens = list(tokens_query)
        
        if not tokens:
            return JsonResponse({
                'success': False,
                'error': f'Aucun token FCM actif trouvé pour l\'élève {eleve.nom_complet}',
                'eleve_id': eleve.id,
                'content_type_id': content_type.id
            })
        
        # Initialiser Firebase
        if not FirebaseService.initialize():
            return JsonResponse({
                'success': False,
                'error': 'Impossible d\'initialiser Firebase'
            })
        
        # Préparer la notification de test
        title = "🔔 Test de notification FCM"
        body = f"Bonjour {eleve.prenom}, ceci est un test de notification push. Si vous recevez ce message, le système fonctionne correctement !"
        test_data = {
            'type': 'test_notification',
            'eleve_id': str(eleve.id),
            'eleve_nom': eleve.nom_complet,
            'timestamp': timezone.now().isoformat(),
            'url': '/eleve/dashboard/',
            'test': 'true'
        }
        
        # Envoyer la notification
        result = FirebaseService.send_notification_to_multiple_users(
            users=[eleve],
            title=title,
            body=body,
            data=test_data
        )
        
        logs = []
        logs.append(f"✅ Élève: {eleve.nom_complet} (ID: {eleve.id})")
        logs.append(f"📱 Tokens trouvés: {len(tokens)}")
        for token_obj in tokens:
            logs.append(f"   - Token ID: {token_obj.id}, Device: {token_obj.device_type}")
        logs.append(f"📤 Notification envoyée")
        logs.append(f"   Titre: {title}")
        logs.append(f"   Message: {body}")
        logs.append(f"📊 Résultats:")
        logs.append(f"   ✅ Succès: {result.get('success_count', 0)}")
        logs.append(f"   ❌ Échecs: {result.get('failure_count', 0)}")
        
        if result.get('error'):
            logs.append(f"   ⚠️  Erreur: {result['error']}")
        
        if result.get('responses'):
            for idx, response in enumerate(result['responses'], 1):
                if hasattr(response, 'success') and response.success:
                    logs.append(f"   ✅ Token {idx}: Envoyé avec succès")
                elif hasattr(response, 'exception') and response.exception:
                    logs.append(f"   ❌ Token {idx}: {response.exception}")
        
        return JsonResponse({
            'success': result.get('success_count', 0) > 0,
            'message': f'Notification envoyée à {eleve.nom_complet}',
            'logs': logs,
            'result': result,
            'eleve': {
                'id': eleve.id,
                'nom': eleve.nom_complet
            },
            'tokens_count': len(tokens)
        })
        
    except Exception as e:
        logger.error(f"Erreur test notification élève: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
