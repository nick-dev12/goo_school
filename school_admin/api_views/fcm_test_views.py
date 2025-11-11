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

