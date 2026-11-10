"""Récupération de compte : preuve de possession, expiration et usage unique."""
import logging
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils.crypto import salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .utils.login_throttle import get_client_ip

logger = logging.getLogger(__name__)
RESET_TTL = 900
MAX_ATTEMPTS = 5


def _models():
    from .model.compte_user import CompteUser
    from .model.etablissement_model import Etablissement
    from .model.professeur_model import Professeur
    from .model.eleve_model import Eleve
    from .model.parent_model import Parent
    return {
        'compte_user': (CompteUser, ('username', 'email'), 'is_active'),
        'etablissement': (Etablissement, ('username', 'email'), 'actif'),
        'professeur': (Professeur, ('username', 'numero_employe', 'email'), 'actif'),
        'eleve': (Eleve, ('username', 'matricule_eleve', 'email'), 'actif'),
        'parent': (Parent, ('username', 'matricule_parental', 'email'), 'actif'),
    }


def _limited(scope, value, limit, timeout):
    digest = salted_hmac('password-reset-rate', value).hexdigest()
    key = f'password-reset-rate:{scope}:{digest}'
    if cache.add(key, 1, timeout):
        return False
    try:
        return cache.incr(key) > limit
    except ValueError:
        # La fenêtre peut expirer entre add et incr.
        return not cache.add(key, 1, timeout)


def _find_account(identifier):
    candidates = []
    for kind, (model, fields, active) in _models().items():
        query = Q()
        for field in fields:
            query |= Q(**{f'{field}__iexact': identifier})
        candidates.extend((kind, user) for user in model.objects.filter(
            query, **{active: True}
        )[:2])
    # Un identifiant ambigu ne doit jamais choisir arbitrairement un titulaire.
    return candidates[0] if len(candidates) == 1 else (None, None)


@never_cache
@require_http_methods(['GET', 'POST'])
def password_reset_request(request):
    if request.method == 'GET':
        return render(request, 'school_admin/password_reset_request.html', {'form_data': {}})
    identifier = request.POST.get('identifier', '').strip()[:254]
    if not identifier:
        return render(request, 'school_admin/password_reset_request.html', {
            'field_errors': {'identifier': 'Ce champ est obligatoire.'}, 'form_data': {},
        }, status=400)
    old_nonce = request.session.pop('password_reset_nonce', None)
    if old_nonce:
        cache.delete(f'password-reset:{old_nonce}')
    nonce = secrets.token_urlsafe(32)
    request.session['password_reset_nonce'] = nonce
    limited = _limited('ip', get_client_ip(request), 10, RESET_TTL)
    limited = _limited('account', identifier.casefold(), 3, RESET_TTL) or limited
    if not limited:
        kind, user = _find_account(identifier)
        # Un élève sans adresse propre peut utiliser l'adresse du tuteur enregistrée.
        email = (getattr(user, 'email', '') or '').strip()
        if kind == 'eleve' and not email:
            email = (getattr(user, 'parent_email', '') or '').strip()
        if user is not None and email:
            code = f'{secrets.randbelow(1_000_000):06d}'
            cache.set(f'password-reset:{nonce}', {
                'kind': kind, 'pk': user.pk, 'code_hash': make_password(code),
                'password_token': default_token_generator.make_token(user),
            }, RESET_TTL)
            try:
                send_mail(
                    'Réinitialisation de votre mot de passe - Aria',
                    f'Votre code de réinitialisation est : {code}. Il expire dans 15 minutes.',
                    settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False,
                )
            except Exception:
                cache.delete(f'password-reset:{nonce}')
                logger.error('Échec de remise du code de récupération de compte.')
    messages.success(request, "Si ce compte possède une adresse de récupération, un code y a été envoyé. Sinon, contactez votre administration.")
    return redirect('school_admin:password_reset_verify', identifier=nonce, user_type='secure')


@never_cache
@require_http_methods(['GET', 'POST'])
def password_reset_verify(request, identifier, user_type):
    if user_type != 'secure' or not secrets.compare_digest(
        request.session.get('password_reset_nonce', ''), identifier
    ):
        return redirect('school_admin:password_reset_request')
    context = {'identifier': identifier, 'user_type': 'secure', 'form_data': {}}
    if request.method == 'GET':
        return render(request, 'school_admin/password_reset_verify.html', context)
    key = f'password-reset:{identifier}'
    data = cache.get(key)
    limited = _limited('verify-ip', get_client_ip(request), 30, RESET_TTL)
    limited = _limited('verify', identifier, MAX_ATTEMPTS, RESET_TTL) or limited
    code = request.POST.get('reset_code', '')
    if limited or not data or not check_password(code, data['code_hash']):
        if limited:
            cache.delete(key)
        messages.error(request, 'Code incorrect, expiré ou nombre maximal de tentatives atteint.')
        return render(request, 'school_admin/password_reset_verify.html', context, status=400)
    model, _, active = _models()[data['kind']]
    with transaction.atomic():
        user = model.objects.select_for_update().filter(pk=data['pk'], **{active: True}).first()
        if user is None or not default_token_generator.check_token(user, data['password_token']):
            cache.delete(key)
            return redirect('school_admin:password_reset_request')
        password = request.POST.get('new_password', '')
        try:
            if password != request.POST.get('confirm_password', ''):
                raise ValidationError('Les mots de passe ne correspondent pas.')
            validate_password(password, user)
        except ValidationError as error:
            for message in error.messages:
                messages.error(request, message)
            return render(request, 'school_admin/password_reset_verify.html', context, status=400)
        user.set_password(password)
        fields = ['password']
        for field in ('mot_de_passe_eleve_modifie', 'mot_de_passe_modifie'):
            if hasattr(user, field):
                setattr(user, field, True)
                fields.append(field)
        user.save(update_fields=fields)
        cache.delete(key)
        request.session.pop('password_reset_nonce', None)
    messages.success(request, 'Votre mot de passe a été réinitialisé. Vous pouvez vous connecter.')
    return redirect('school_admin:connexion_compte_user')


@never_cache
@require_http_methods(['GET', 'POST'])
def legacy_password_reset(request, matricule):
    """Les anciennes URLs ne peuvent plus écrire ni certifier une identité."""
    return redirect('school_admin:password_reset_request')
