"""
Vue de test pour vérifier l'envoi de notifications lors de l'enregistrement des notes
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
import logging

from school_admin.model.fcm_token_model import FCMToken
from school_admin.model.eleve_model import Eleve
from school_admin.model.note_primaire_model import NotePrimaire
from school_admin.model.evaluation_primaire_model import EvaluationPrimaire
from school_admin.services.firebase_service import FirebaseService

logger = logging.getLogger(__name__)

@login_required
def test_notes_notifications_page(request):
    """
    Page de test pour les notifications de notes
    """
    return render(request, 'school_admin/test_notes_notifications.html')


@require_http_methods(["POST"])
@login_required
def test_send_note_notification(request):
    """
    Teste l'envoi de notifications pour une note spécifique
    """
    import json
    
    try:
        data = json.loads(request.body)
        eleve_id = data.get('eleve_id')
        
        if not eleve_id:
            return JsonResponse({'success': False, 'message': 'ID élève manquant'}, status=400)
        
        # Récupérer l'élève
        try:
            eleve = Eleve.objects.get(id=eleve_id)
        except Eleve.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Élève introuvable'}, status=404)
        
        # Vérifier les tokens FCM de l'élève
        content_type = ContentType.objects.get_for_model(eleve)
        fcm_tokens = FCMToken.objects.filter(
            content_type=content_type,
            object_id=eleve.id,
            is_active=True
        )
        
        logs = []
        logs.append(f"✅ Élève trouvé : {eleve.nom_complet}")
        logs.append(f"📱 Tokens FCM actifs : {fcm_tokens.count()}")
        
        if not fcm_tokens.exists():
            return JsonResponse({
                'success': False, 
                'message': f'Aucun token FCM actif pour {eleve.nom_complet}',
                'logs': logs
            })
        
        # Afficher les tokens
        for token_obj in fcm_tokens:
            logs.append(f"  - Token: {token_obj.token[:30]}... (créé le {token_obj.created_at.strftime('%Y-%m-%d %H:%M')})")
        
        # Préparer et envoyer la notification
        title = "🎓 Nouvelle note disponible - TEST"
        body = f"Votre professeur vient de saisir une nouvelle note. Ceci est un test de notification."
        data_notif = {
            'type': 'nouvelle_note',
            'eleve_id': str(eleve.id),
            'eleve_nom': eleve.nom_complet,
            'timestamp': str(timezone.now()),
            'url': '/eleve/dashboard/'
        }
        
        logs.append(f"📤 Envoi de la notification...")
        logs.append(f"  Titre: {title}")
        logs.append(f"  Message: {body}")
        
        # Envoyer la notification
        result = FirebaseService.send_notification_to_multiple_users(
            users=[eleve],
            title=title,
            body=body,
            data=data_notif
        )
        
        logs.append(f"✉️ Résultat de l'envoi:")
        logs.append(f"  - Succès: {result['success_count']}")
        logs.append(f"  - Échecs: {result['failure_count']}")
        
        # Afficher l'erreur si présente
        if 'error' in result:
            logs.append(f"❌ Erreur Firebase: {result['error']}")
        
        # Afficher les détails des réponses individuelles
        if 'responses' in result and result['responses']:
            for i, resp in enumerate(result['responses']):
                if hasattr(resp, 'exception') and resp.exception:
                    logs.append(f"  Token {i+1} - Erreur: {resp.exception}")
        
        if result['success_count'] > 0:
            return JsonResponse({
                'success': True,
                'message': f'Notification envoyée avec succès à {eleve.nom_complet}',
                'logs': logs,
                'success_count': result['success_count'],
                'failure_count': result['failure_count']
            })
        else:
            return JsonResponse({
                'success': False,
                'message': f'Échec de l\'envoi de la notification',
                'logs': logs,
                'success_count': result['success_count'],
                'failure_count': result['failure_count']
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'JSON invalide'}, status=400)
    except Exception as e:
        logger.error(f"Erreur lors du test de notification de note: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False, 
            'message': f'Erreur interne: {str(e)}',
            'logs': logs if 'logs' in locals() else []
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_eleves_with_tokens(request):
    """
    Récupère la liste des élèves avec leurs tokens FCM
    """
    try:
        eleves_data = []
        eleves = Eleve.objects.all()[:50]  # Limiter à 50 pour ne pas surcharger
        
        for eleve in eleves:
            content_type = ContentType.objects.get_for_model(eleve)
            tokens_count = FCMToken.objects.filter(
                content_type=content_type,
                object_id=eleve.id,
                is_active=True
            ).count()
            
            eleves_data.append({
                'id': eleve.id,
                'nom_complet': eleve.nom_complet,
                'classe': str(eleve.classe) if eleve.classe else 'N/A',
                'tokens_count': tokens_count,
                'has_tokens': tokens_count > 0
            })
        
        return JsonResponse({
            'success': True,
            'eleves': eleves_data,
            'total': len(eleves_data)
        })
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des élèves: {str(e)}")
        return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'}, status=500)

