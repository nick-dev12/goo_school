"""Politique de sécurité du contenu (CSP).

Elle dit au navigateur d'où une page peut charger des scripts, des styles, des images et des connexions.
Si un jour une injection de script passait quelque part, le navigateur refuserait de contacter un site tiers.

Mise en place prudente : en mode « report » (par défaut), rien n'est bloqué ; le navigateur envoie
seulement un rapport à /securite/csp-rapport/ pour chaque élément qui aurait été refusé. Une fois les
rapports examinés et la liste ajustée, passer CSP_MODE=enforce pour l'appliquer réellement.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger('school_admin.csp')

GOOGLE = 'https://*.googleapis.com https://*.gstatic.com https://www.gstatic.com'
POLITIQUE = '; '.join([
    "default-src 'self'",
    # Les gabarits contiennent encore beaucoup de scripts et de styles en ligne.
    f"script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net "
    f"https://cdn.gtranslate.net https://translate.google.com {GOOGLE}",
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net "
    "https://fonts.googleapis.com https://cdn.gtranslate.net https://*.gstatic.com",
    "font-src 'self' data: https://cdnjs.cloudflare.com https://fonts.gstatic.com https://cdn.jsdelivr.net",
    "img-src 'self' data: blob: https:",
    f"connect-src 'self' wss: {GOOGLE} https://ipapi.co https://*.gtranslate.net https://translate.google.com",
    "media-src 'self' blob: data:",
    "worker-src 'self' blob:",
    f"frame-src 'self' https://translate.google.com {GOOGLE}",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    'report-uri /securite/csp-rapport/',
])


class CspMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        mode = getattr(settings, 'CSP_MODE', 'report')
        if mode in ('report', 'enforce') and 'text/html' in response.get('Content-Type', ''):
            entete = 'Content-Security-Policy' if mode == 'enforce' else 'Content-Security-Policy-Report-Only'
            response.setdefault(entete, POLITIQUE)
        return response


@csrf_exempt  # envoyé par le navigateur lui-même, sans jeton ; la vue ne fait qu'écrire un journal
@require_POST
def rapport_csp(request):
    # Au plus 60 rapports journalisés par minute, pour qu'un robot ne remplisse pas les journaux.
    cle = 'csp:rapports:minute'
    if cache.add(cle, 0, 60) or cache.incr(cle) <= 60:
        try:
            donnees = json.loads(request.body[:8192] or b'{}').get('csp-report', {})
        except (ValueError, AttributeError):
            donnees = {}
        logger.warning('CSP : %s bloquerait %s sur %s', str(donnees.get('violated-directive', '?'))[:80],
                       str(donnees.get('blocked-uri', '?'))[:200], str(donnees.get('document-uri', '?'))[:200])
    return HttpResponse(status=204)
