"""
Vues API pour la gestion des tokens FCM
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.contenttypes.models import ContentType
import json
import logging
from django.db import transaction

from school_admin.model.fcm_token_model import FCMToken

logger = logging.getLogger(__name__)


@require_http_methods(['POST'])
def test_own_push(request):
    """Test volontaire limité aux appareils du compte connecté."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Connexion requise.'}, status=401)
    from django.core.cache import cache
    content_type = ContentType.objects.get_for_model(request.user)
    if not FCMToken.objects.filter(content_type=content_type, object_id=request.user.pk, is_active=True).exists():
        return JsonResponse({'error': 'Activez les notifications sur cet appareil avant le test.'}, status=400)
    key = f'push-self-test:{content_type.pk}:{request.user.pk}'
    if not cache.add(key, True, timeout=30):
        return JsonResponse({'error': 'Patientez 30 secondes entre deux tests.'}, status=429)
    from school_admin.services.firebase_service import FirebaseService
    result = FirebaseService.send_notification_to_user(
        request.user, 'Aria — test de notification',
        'Le test push réel fonctionne. Confirme dans la conversation si tu vois ce message.',
        {'url': '/', 'type': 'self_test'},
    )
    return JsonResponse({'success': True, 'queued': result.get('queued_count', 0)})


@require_http_methods(["POST"])
def save_fcm_token(request):
    """
    Sauvegarde le token FCM pour l'utilisateur connecté
    """
    try:
        # Vérifier que l'utilisateur est connecté
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Non authentifié'}, status=401)
        
        # Parser les données JSON
        data = json.loads(request.body)
        token = data.get('token')
        device_type = data.get('device_type', 'web')
        device_name = data.get('device_name', '')
        
        if not token:
            return JsonResponse({'error': 'Token manquant'}, status=400)
        
        # Obtenir le content type de l'utilisateur
        content_type = ContentType.objects.get_for_model(request.user)
        
        # Créer ou mettre à jour le token
        with transaction.atomic():
            fcm_token, created = FCMToken.objects.select_for_update().get_or_create(
                token=token,
                defaults={
                    'content_type': content_type, 'object_id': request.user.pk,
                    'device_type': device_type, 'device_name': device_name,
                    'is_active': True,
                },
            )
            if (fcm_token.content_type_id, fcm_token.object_id) != (content_type.pk, request.user.pk):
                return JsonResponse({'error': 'Token déjà associé à un autre compte.'}, status=403)
            if not created:
                fcm_token.device_type = device_type
                fcm_token.device_name = device_name
                fcm_token.is_active = True
                fcm_token.save(update_fields=['device_type', 'device_name', 'is_active', 'updated_at'])
            request.session['fcm_token_id'] = fcm_token.pk
        
        logger.info(f"Token FCM {'créé' if created else 'mis à jour'} pour {request.user}")
        
        return JsonResponse({
            'success': True,
            'message': 'Token sauvegardé avec succès',
            'created': created
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Données JSON invalides'}, status=400)
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde du token FCM: {str(e)}")
        return JsonResponse({'error': 'Une erreur interne est survenue.'}, status=500)


@require_http_methods(["POST"])
def delete_fcm_token(request):
    """
    Supprime le token FCM de l'utilisateur connecté
    """
    try:
        # Vérifier que l'utilisateur est connecté
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Non authentifié'}, status=401)
        
        # Parser les données JSON
        data = json.loads(request.body)
        token = data.get('token')
        
        if not token:
            return JsonResponse({'error': 'Token manquant'}, status=400)
        
        # Supprimer le token
        deleted_count, _ = FCMToken.objects.filter(
            token=token, content_type=ContentType.objects.get_for_model(request.user),
            object_id=request.user.pk,
        ).delete()
        
        logger.info(f"Token FCM supprimé pour {request.user}")
        
        return JsonResponse({
            'success': True,
            'message': 'Token supprimé avec succès',
            'deleted': deleted_count > 0
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Données JSON invalides'}, status=400)
    except Exception as e:
        logger.error(f"Erreur lors de la suppression du token FCM: {str(e)}")
        return JsonResponse({'error': 'Une erreur interne est survenue.'}, status=500)

