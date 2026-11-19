"""Changement de mot de passe imposé à la première connexion, et nouveau mot de passe provisoire donné
par la direction quand une personne a oublié le sien."""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import (
    CommonPasswordValidator, MinimumLengthValidator, UserAttributeSimilarityValidator, validate_password)
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from school_admin.services.mots_de_passe import SESSION_CLE, attribuer_provisoire, concerne

logger = logging.getLogger(__name__)

# Chiffres seuls acceptés : beaucoup de familles retiennent plus facilement un code chiffré.
VALIDATEURS = [MinimumLengthValidator(8), CommonPasswordValidator(), UserAttributeSimilarityValidator()]


def _suite(request):
    suite = request.POST.get('next') or request.GET.get('next') or ''
    if suite and url_has_allowed_host_and_scheme(suite, {request.get_host()}, require_https=request.is_secure()):
        return suite
    return '/'


def choisir_mot_de_passe(request):
    user = request.user
    if not user.is_authenticated or not concerne(user):
        return redirect('/')
    if request.GET.get('sortir'):
        from django.contrib.auth import logout
        logout(request)
        return redirect('school_admin:connexion_compte_user')
    erreurs = []
    if request.method == 'POST':
        nouveau = request.POST.get('nouveau', '')
        confirmation = request.POST.get('confirmation', '')
        if nouveau != confirmation:
            erreurs.append("Les deux mots de passe ne sont pas identiques.")
        elif nouveau == (user.mot_de_passe_provisoire or ''):
            erreurs.append("Choisissez un mot de passe différent de celui donné par l'établissement.")
        else:
            try:
                validate_password(nouveau, user, password_validators=VALIDATEURS)
            except ValidationError as erreur:
                erreurs.extend(erreur.messages)
        if not erreurs:
            user.set_password(nouveau)
            user.save()  # le signal efface le mot de passe provisoire en clair
            update_session_auth_hash(request, user)
            request.session.pop(SESSION_CLE, None)
            messages.success(request, "Votre nouveau mot de passe est enregistré. Gardez-le pour vous.")
            return redirect(_suite(request))
    return render(request, 'school_admin/securite/choisir_mot_de_passe.html', {
        'erreurs': erreurs, 'suite': _suite(request), 'obligatoire': bool(request.session.get(SESSION_CLE)),
        'prenom': getattr(user, 'prenom', '') or '',
    })


class ChangementObligatoireMiddleware:
    """Tant que le mot de passe provisoire est en vigueur, toute page renvoie vers son remplacement."""

    LIBRES = ('/securite/nouveau-mot-de-passe/', '/static/', '/media/', '/api/', '/health/', '/service-worker.js',
              '/firebase-messaging-sw.js', '/manifest.json', '/favicon.ico', '/push-config.js', '/robots.txt')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session = getattr(request, 'session', None)
        if (session is not None and session.get(SESSION_CLE) and getattr(request, 'user', None) is not None
                and request.user.is_authenticated and not request.path.startswith(self.LIBRES)
                and 'deconnexion' not in request.path and 'logout' not in request.path):
            from urllib.parse import quote
            suite = request.get_full_path() if request.method == 'GET' else '/'
            return redirect(f'/securite/nouveau-mot-de-passe/?next={quote(suite)}')
        return self.get_response(request)


# --------------------------------------------------------------------------- oubli : action de la direction
def _cible(type_compte, pk):
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.parent_model import Parent
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    from school_admin.model.professeur_model import Professeur
    modeles = {'eleve': Eleve, 'parent': Parent, 'professeur': Professeur, 'personnel': PersonnelAdministratif}
    modele = modeles.get(type_compte)
    cible = modele.objects.filter(pk=pk).first() if modele else None
    if cible is None:
        raise Http404
    return cible


def _peut_reinitialiser(user, type_compte, cible):
    from school_admin.utils.decorators_permissions import check_permission
    role = user._meta.model_name
    if role not in ('etablissement', 'personneladministratif'):
        return False
    etablissement_id = user.pk if role == 'etablissement' else user.etablissement_id
    if type_compte == 'parent':
        from school_admin.model.lien_familial_model import LienFamilial
        dans_etab = (cible.etablissement_id == etablissement_id or LienFamilial.objects.filter(
            parent=cible, eleve__etablissement_id=etablissement_id).exists())
    else:
        dans_etab = cible.etablissement_id == etablissement_id
    if not dans_etab:
        return False
    if role == 'etablissement':
        return True
    if type_compte == 'personnel' and cible.pk == user.pk:
        return False  # on ne se donne pas soi-même un mot de passe provisoire
    permission = {'eleve': 'eleves_modifier', 'parent': 'eleves_modifier',
                  'professeur': 'professeurs_modifier', 'personnel': 'personnel_modifier'}[type_compte]
    return check_permission(user, permission)


@require_POST
def nouveau_mot_de_passe_provisoire(request, type_compte, pk):
    user = request.user
    if not user.is_authenticated:
        return redirect('school_admin:connexion_compte_user')
    cible = _cible(type_compte, pk)
    if not _peut_reinitialiser(user, type_compte, cible):
        raise Http404
    mot = attribuer_provisoire(cible)
    nom = f"{getattr(cible, 'prenom', '')} {getattr(cible, 'nom', '')}".strip()
    logger.info('Nouveau mot de passe provisoire : %s #%s par %s #%s', type_compte, cible.pk,
                user._meta.model_name, user.pk)
    messages.success(request, f"Nouveau mot de passe provisoire pour {nom} : {mot}. Transmettez-le en main propre ; "
                              "la personne devra en choisir un autre à sa prochaine connexion.")
    retour = request.META.get('HTTP_REFERER', '')
    if not url_has_allowed_host_and_scheme(retour, {request.get_host()}, require_https=request.is_secure()):
        retour = '/'
    return redirect(retour)
