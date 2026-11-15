import json
import hashlib
import logging
from datetime import datetime, timedelta, time
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from school_admin.model.context_popup_model import ContextPopupState, ContextPopupVisit
from school_admin.services.context_popups import eligible, candidates, greeting, snoozed_keys, progress

logger = logging.getLogger(__name__)

POPUP_MAX = 4      # cartes présentées dans la synthèse d'arrivée
CENTRE_MAX = 30    # cartes listées dans le centre « À faire »


def _snooze_until(item, now):
    """Report au lendemain 7 h ; quatre heures seulement si l'échéance est aujourd'hui ou dépassée."""
    until = timezone.make_aware(datetime.combine(timezone.localdate() + timedelta(days=1), time(7)))
    if item.get('deadline'):
        if datetime.fromisoformat(item['deadline']).date() <= timezone.localdate():
            until = min(until, now + timedelta(hours=4))
    return until


@never_cache
@require_http_methods(['GET', 'POST'])
def context_popup(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Connexion requise.'}, status=401)
    user = request.user
    owner = dict(content_type=ContentType.objects.get_for_model(user), object_id=user.pk)
    try:
        if request.method == 'GET':
            if request.GET.get('centre'):
                # Centre « À faire » : tout ce qui attend la personne, sans rien marquer comme vu.
                items = candidates(user)
                if getattr(settings, 'CONTEXT_POPUP_TOTAL_TTL', 0):  # la pastille repart du décompte frais
                    cache.set(f'context-popup-total:{owner["content_type"].pk}:{user.pk}', len(items),
                              settings.CONTEXT_POPUP_TOTAL_TTL)
                later = snoozed_keys(user, items)
                for item in items:
                    item['snoozed'] = item['key'] in later
                return JsonResponse({'cards': items[:CENTRE_MAX], 'total': len(items), 'greeting': greeting(user),
                                     'progress': progress(user)})
            return JsonResponse({'cards': eligible(user)[:POPUP_MAX]})
        data = json.loads(request.body or '{}')
        action = data.get('action')
        now = timezone.now()

        # Actions du centre « À faire » : pas de visite, la situation est revalidée à chaque clic.
        if action in ('go', 'later'):
            item = next((item for item in candidates(user) if item['key'] == data.get('key')), None)
            if not item:
                return JsonResponse({'error': 'Cette situation a été résolue ou votre accès a changé.'}, status=409)
            if action == 'go':
                ContextPopupState.objects.update_or_create(**owner, key=item['key'], defaults={'opened_at': now})
                return JsonResponse({'url': item['url']})
            ContextPopupState.objects.update_or_create(**owner, key=item['key'], defaults={
                'seen_version': '', 'evidence': {}, 'snooze_until': _snooze_until(item, now)})
            return JsonResponse({'success': True})

        client_visit = data.get('visit_key', '')
        if client_visit and (not isinstance(client_visit, str) or len(client_visit) != 32 or any(char not in '0123456789abcdef' for char in client_visit)):
            return JsonResponse({'error': 'Visite invalide.'}, status=400)
        base_key = request.session.get('context_popup_login')
        if not base_key:
            base_key = hashlib.sha256(f'{request.session.session_key}:{owner["content_type"].pk}:{user.pk}'.encode()).hexdigest()
            request.session['context_popup_login'] = base_key
        login_key = hashlib.sha256(f'{base_key}:{client_visit}'.encode()).hexdigest() if client_visit else base_key
        if action == 'claim':
            # Page suivante d'une visite déjà ouverte : seule la pastille a besoin du nombre d'actions. Il est
            # réutilisé quelques secondes au lieu de relancer tout le calcul des situations à chaque page.
            ttl = getattr(settings, 'CONTEXT_POPUP_TOTAL_TTL', 0)
            total_key = f'context-popup-total:{owner["content_type"].pk}:{user.pk}'
            if ttl:
                opened = ContextPopupVisit.objects.filter(**owner, login_key=login_key).values_list('pk', flat=True).first()
                total = cache.get(total_key) if opened else None
                if total is not None:
                    return JsonResponse({'visit': opened, 'cards': [], 'total': total, 'greeting': greeting(user),
                                         'progress': None})
            items = candidates(user)
            if ttl:
                cache.set(total_key, len(items), ttl)
            with transaction.atomic():
                visit, created = ContextPopupVisit.objects.get_or_create(
                    **owner, login_key=login_key,
                    defaults={'cards': eligible(user, repeat=bool(client_visit), items=items)[:POPUP_MAX]})
            return JsonResponse({'visit': visit.pk, 'cards': visit.cards if created else [],
                                 'total': len(items), 'greeting': greeting(user),
                                 'progress': progress(user) if created and visit.cards else None})
        with transaction.atomic():
            visit = ContextPopupVisit.objects.select_for_update().filter(pk=data.get('visit'), **owner).first()
            if not visit or visit.login_key != login_key:
                return JsonResponse({'error': 'Présentation expirée.'}, status=403)
            if action == 'shown':
                if visit.confirmed:
                    return JsonResponse({'cards': []})
                current = {item['key']: item for item in candidates(user)}
                cards = [item for item in visit.cards if item['key'] in current and current[item['key']]['version'] == item['version']]
                for item in cards:
                    ContextPopupState.objects.update_or_create(**owner, key=item['key'], defaults={
                        'seen_version': item['version'], 'evidence': item.get('evidence', {}),
                        'last_shown': now, 'snooze_until': None})
                visit.confirmed = True
                visit.cards = cards
                visit.save(update_fields=['confirmed', 'cards'])
                return JsonResponse({'cards': cards, 'total': len(current)})
            if action not in ('open', 'snooze', 'dismiss') or not visit.confirmed:
                return JsonResponse({'error': 'Action invalide.'}, status=400)
            selected = [item for item in visit.cards if not data.get('key') or item['key'] == data['key']]
            if not selected:
                return JsonResponse({'error': 'Information introuvable.'}, status=404)
            if action == 'open':
                item = next((item for item in candidates(user) if item['key'] == selected[0]['key']), None)
                if not item:
                    return JsonResponse({'error': 'Cette situation a été résolue ou votre accès a changé.'}, status=409)
                ContextPopupState.objects.filter(**owner, key=item['key']).update(opened_at=now)
                return JsonResponse({'url': item['url']})
            if action == 'snooze':
                for item in selected:
                    ContextPopupState.objects.filter(**owner, key=item['key']).update(
                        seen_version='', evidence={}, snooze_until=_snooze_until(item, now))
            return JsonResponse({'success': True})
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'error': 'Requête invalide.'}, status=400)
    except Exception:
        logger.exception('Calcul des informations contextuelles indisponible')
        return JsonResponse({'error': 'Informations temporairement indisponibles.'}, status=503)
