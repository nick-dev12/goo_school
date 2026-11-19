"""Contrôle central des fichiers envoyés au site.

Toutes les vues d'envoi passent par ici : une extension hors liste, un contenu qui ne correspond pas à
son extension ou un fichier trop lourd est refusé avant que la vue ne s'exécute. Un fichier HTML, SVG
ou exécutable ne peut donc plus être déposé, quel que soit le formulaire utilisé.
"""
from __future__ import annotations

import os

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

TAILLE_MAX = 20 * 1024 * 1024  # 20 Mo par fichier

ZIP = (b'PK\x03\x04',)
OLE = (b'\xd0\xcf\x11\xe0',)
SIGNATURES = {
    'pdf': (b'%PDF',),
    'png': (b'\x89PNG',),
    'jpg': (b'\xff\xd8\xff',),
    'jpeg': (b'\xff\xd8\xff',),
    'gif': (b'GIF87a', b'GIF89a'),
    'webp': (b'RIFF',),
    'docx': ZIP, 'xlsx': ZIP, 'xlsm': ZIP, 'odt': ZIP, 'ods': ZIP,
    'doc': OLE, 'xls': OLE,
    'heic': None, 'heif': None,  # vérifiés par la marque « ftyp »
    'csv': None, 'txt': None,    # texte : vérifié par l'absence de balises
}
BALISES = (b'<script', b'<html', b'<svg', b'<iframe', b'<!doctype', b'<?php', b'javascript:')


def motif_refus(fichier):
    """Raison du refus en français, ou None si le fichier est accepté."""
    nom = os.path.basename(getattr(fichier, 'name', '') or '')
    extension = nom.rsplit('.', 1)[-1].lower() if '.' in nom else ''
    if extension not in SIGNATURES:
        return (f"Le fichier « {nom} » n'est pas accepté. Formats autorisés : PDF, images (JPG, PNG, WEBP, GIF, "
                "HEIC), Word, Excel, OpenDocument, CSV et texte.")
    if fichier.size is not None and fichier.size > TAILLE_MAX:
        return f"Le fichier « {nom} » dépasse {TAILLE_MAX // (1024 * 1024)} Mo."
    position = fichier.tell() if hasattr(fichier, 'tell') else 0
    try:
        fichier.seek(0)
        debut = fichier.read(2048) or b''
    finally:
        fichier.seek(position)
    if isinstance(debut, str):
        debut = debut.encode('utf-8', 'ignore')
    attendu = SIGNATURES[extension]
    if extension in ('heic', 'heif'):
        valide = debut[4:8] == b'ftyp'
    elif extension == 'webp':
        valide = debut[:4] == b'RIFF' and debut[8:12] == b'WEBP'
    elif attendu is None:
        valide = not any(balise in debut.lower() for balise in BALISES)
    else:
        valide = debut.startswith(attendu)
    if not valide:
        return f"Le contenu du fichier « {nom} » ne correspond pas à son format."
    return None


class UploadGuardMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ('POST', 'PUT', 'PATCH') and request.content_type == 'multipart/form-data':
            for _champ, fichiers in request.FILES.lists():
                for fichier in fichiers:
                    motif = motif_refus(fichier)
                    if motif:
                        return self._refuser(request, motif)
        return self.get_response(request)

    @staticmethod
    def _refuser(request, motif):
        attend_json = ('application/json' in request.headers.get('Accept', '')
                       or request.headers.get('X-Requested-With') == 'XMLHttpRequest')
        if attend_json:
            return JsonResponse({'ok': False, 'success': False, 'error': motif}, status=400)
        messages.error(request, motif)
        retour = request.META.get('HTTP_REFERER', '')
        if not url_has_allowed_host_and_scheme(retour, {request.get_host()}, require_https=request.is_secure()):
            retour = request.path
        return redirect(retour)
