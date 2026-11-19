"""Limite de rythme par compte connecté : freine l'aspiration de données avec un compte légitime.

Un utilisateur normal ouvre au plus quelques pages par minute ; un programme qui parcourt toutes les
fiches d'élèves en ouvre des centaines. Au-delà du seuil, la réponse est 429 jusqu'à la fin de la fenêtre.
Les fichiers statiques, les images et les appels techniques fréquents ne sont pas comptés.
Les visiteurs non connectés sont limités par adresse IP dans Nginx.
"""
from __future__ import annotations

import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse

logger = logging.getLogger(__name__)

EXCLUS = ('/static/', '/media/', '/api/context-popup/', '/api/sync/', '/api/push/', '/api/fcm/',
          '/service-worker.js', '/firebase-messaging-sw.js', '/manifest.json', '/favicon.ico', '/health/')


class AccountRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and not request.path.startswith(EXCLUS):
            refus = self._compter(request, user)
            if refus is not None:
                return refus
        return self.get_response(request)

    @staticmethod
    def _compter(request, user):
        limite = getattr(settings, 'ACCOUNT_RATE_LIMIT', 300)
        fenetre = getattr(settings, 'ACCOUNT_RATE_WINDOW', 300)
        if not limite:
            return None
        debut = int(time.time()) // fenetre * fenetre
        cle = f'rl:compte:{user._meta.model_name}:{user.pk}:{debut}'
        if cache.add(cle, 1, fenetre + 30):
            return None
        try:
            total = cache.incr(cle)
        except ValueError:  # clé expirée entre-temps
            cache.set(cle, 1, fenetre + 30)
            return None
        if total <= limite:
            return None
        attente = debut + fenetre - int(time.time())
        if total == limite + 1:
            logger.warning('Rythme anormal : %s #%s a dépassé %s requêtes en %s s (%s)',
                           user._meta.model_name, user.pk, limite, fenetre, request.path)
        message = (f"Trop de pages ouvertes en peu de temps. Réessayez dans {max(1, attente // 60)} minute(s). "
                   "Si vous n'avez rien fait d'inhabituel, prévenez l'établissement.")
        if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            reponse = JsonResponse({'ok': False, 'error': message}, status=429)
        else:
            reponse = HttpResponse(
                '<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" '
                'content="width=device-width,initial-scale=1"><title>Patientez un instant</title>'
                '<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem;'
                'color:#101828"><h1 style="font-size:1.4rem">Patientez un instant</h1>'
                f'<p style="line-height:1.6;color:#475467">{message}</p></body></html>',
                status=429, content_type='text/html; charset=utf-8')
        reponse['Retry-After'] = str(max(1, attente))
        return reponse
