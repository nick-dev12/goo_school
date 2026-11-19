"""Connexion à l'administration Django : mêmes limites de tentatives que la connexion principale.

Sans cela, la page de connexion de /admin/ acceptait un nombre illimité d'essais de mot de passe sur les
comptes de l'équipe Aria, qui ont tous les droits.
"""
from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse

from school_admin.utils.login_throttle import clear_on_success, get_seconds_remaining, register_auth_failure


class AdminLoginThrottleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        chemin = '/' + getattr(settings, 'ADMIN_URL', 'admin/').strip('/') + '/login/'
        if request.method != 'POST' or request.path != chemin:
            return self.get_response(request)
        identifiant = request.POST.get('username', '')
        attente = get_seconds_remaining(request, identifiant)
        if attente:
            return self._pause(attente)
        response = self.get_response(request)
        if response.status_code == 200:  # formulaire réaffiché : mauvais identifiants
            attente = register_auth_failure(request, identifiant)
            if attente:
                return self._pause(attente)
        elif response.status_code in (301, 302):
            clear_on_success(request, identifiant)
        return response

    @staticmethod
    def _pause(secondes):
        response = HttpResponse(
            '<!doctype html><meta charset="utf-8"><title>Patientez</title>'
            '<p style="font-family:system-ui,sans-serif;max-width:30rem;margin:15vh auto;padding:0 1rem">'
            'Trop de tentatives de connexion. Réessayez plus tard.</p>',
            status=429, content_type='text/html; charset=utf-8')
        response['Retry-After'] = str(max(1, secondes))
        return response
