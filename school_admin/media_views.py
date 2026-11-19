"""Fichiers déposés (media/) servis après contrôle des droits.

Seuls les logos d'établissement sont publics. Pour tout le reste, l'application retrouve l'objet
propriétaire du fichier, vérifie que la personne connectée y a droit, puis laisse Nginx envoyer le
fichier (en-tête X-Accel-Redirect) ; en développement, Django l'envoie lui-même.

Un fichier inconnu ou interdit répond 404 : on ne révèle pas qu'il existe.
"""
from __future__ import annotations

import mimetypes
import os
import posixpath
from urllib.parse import quote

from django.conf import settings
from django.core import signing
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET

PUBLIC_PREFIXES = ('etablissements/logos/',)
# Affichés dans le navigateur ; tout le reste est proposé au téléchargement (un HTML ou un SVG
# déposé ne peut donc jamais s'exécuter sur aria-edu.com).
INLINE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf'}
SIGNATURE_SALT = 'aria.media.signee'
SIGNATURE_MAX_AGE = 15 * 60


def url_signee(field_file, max_age=SIGNATURE_MAX_AGE):
    """Adresse temporaire d'un fichier privé, pour une page publique (ex. vérification de carte)."""
    if not field_file:
        return ''
    signature = signing.dumps(field_file.name, salt=SIGNATURE_SALT)
    return f'{field_file.url}?s={quote(signature)}'


def _signature_valide(request, path):
    token = request.GET.get('s')
    if not token:
        return False
    try:
        return signing.loads(token, salt=SIGNATURE_SALT, max_age=SIGNATURE_MAX_AGE) == path
    except signing.BadSignature:
        return False


def _normaliser(path):
    """Chemin relatif sûr dans media/, ou None (remontée de dossier, chemin absolu, octet nul)."""
    if not path or '\x00' in path or '\\' in path:
        return None
    clean = posixpath.normpath(path).lstrip('/')
    if clean in ('', '.') or clean.startswith('..') or '/../' in f'/{clean}/':
        return None
    return clean


# --------------------------------------------------------------------------- appartenance
def _role(user):
    return user._meta.model_name if user is not None and user.is_authenticated else None


def _etablissement_de(user):
    role = _role(user)
    if role == 'etablissement':
        return user.pk
    return getattr(user, 'etablissement_id', None)


def _enfants(parent):
    from school_admin.model.lien_familial_model import LienFamilial
    return set(LienFamilial.objects.filter(parent=parent, actif=True, statut='valide')
               .values_list('eleve_id', flat=True))


def _est_personnel(user, etablissement_id):
    """Direction, personnel administratif ou professeur de cet établissement."""
    return (etablissement_id is not None
            and _role(user) in ('etablissement', 'personneladministratif', 'professeur')
            and _etablissement_de(user) == etablissement_id)


def _membre(user, etablissement_id):
    """Toute personne rattachée à l'établissement, familles comprises."""
    if _est_personnel(user, etablissement_id) or (_role(user) == 'eleve' and user.etablissement_id == etablissement_id):
        return True
    if _role(user) == 'parent':
        from school_admin.model.eleve_model import Eleve
        return (user.etablissement_id == etablissement_id
                or Eleve.objects.filter(pk__in=_enfants(user), etablissement_id=etablissement_id).exists())
    return False


def _acces_eleve(user, eleve_id, etablissement_id):
    if _est_personnel(user, etablissement_id):
        return True
    if _role(user) == 'eleve':
        return user.pk == eleve_id
    if _role(user) == 'parent':
        return eleve_id in _enfants(user)
    return False


def autorise(user, path):
    """True si cette personne peut lire ce fichier. Lève Http404 si aucun objet ne le référence."""
    from school_admin.model.annonce_model import Annonce
    from school_admin.model.demande_liaison_model import DemandeLiaisonParent
    from school_admin.model.depense_model import Depense
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.employe_dossier_model import DocumentEmploye
    from school_admin.model.finances_model import PieceFinanciere
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    role = _role(user)
    if role is None:
        return False
    equipe_aria = role == 'compteuser'

    if path.startswith('admin_photos/'):
        return True  # photos de profil de l'équipe Aria, sans donnée sensible
    if path.startswith('rapports_mensuels/'):
        return equipe_aria
    if path.startswith('eleves/'):
        eleve = Eleve.objects.filter(photo_profil=path).only('pk', 'etablissement_id').first() \
            or Eleve.objects.filter(qr_code_image=path).only('pk', 'etablissement_id').first()
        if eleve is None:
            raise Http404
        return _acces_eleve(user, eleve.pk, eleve.etablissement_id)
    if path.startswith('bulletins/'):
        moyenne = MoyennePeriode.objects.filter(qr_code_image=path).only('eleve_id', 'etablissement_id').first()
        if moyenne is None:
            raise Http404
        return _acces_eleve(user, moyenne.eleve_id, moyenne.etablissement_id)
    if path.startswith('annonces/'):
        annonce = Annonce.objects.filter(fichier_joint=path).only('etablissement_id').first()
        if annonce is None:
            raise Http404
        return _membre(user, annonce.etablissement_id)
    if path.startswith('justificatifs_liaison/'):
        demande = DemandeLiaisonParent.objects.filter(justificatif=path).select_related('parent_demandeur').first()
        if demande is None:
            raise Http404
        if role == 'parent' and demande.parent_demandeur_id == user.pk:
            return True
        etablissements = {demande.parent_demandeur.etablissement_id,
                          getattr(demande.eleve_valide, 'etablissement_id', None)}
        return role in ('etablissement', 'personneladministratif') and _etablissement_de(user) in etablissements
    if path.startswith('employes/'):
        document = DocumentEmploye.objects.filter(fichier=path).select_related(
            'professeur', 'personnel_administratif').first()
        if document is None:
            raise Http404
        titulaire = document.professeur or document.personnel_administratif
        if titulaire is not None and titulaire._meta.model_name == role and titulaire.pk == user.pk:
            return True
        etablissement_id = getattr(titulaire, 'etablissement_id', None)
        return role in ('etablissement', 'personneladministratif') and _etablissement_de(user) == etablissement_id
    if path.startswith('depenses/'):
        depense = Depense.objects.filter(piece_jointe=path).only('etablissement_id').first()
        if depense is None:
            raise Http404
        if depense.etablissement_id is None:
            return equipe_aria  # dépenses de la plateforme Aria
        return role in ('etablissement', 'personneladministratif') and _etablissement_de(user) == depense.etablissement_id
    if path.startswith('finances/'):
        piece = PieceFinanciere.objects.filter(fichier=path).only('etablissement_id').first()
        if piece is None:
            raise Http404
        return role in ('etablissement', 'personneladministratif') and _etablissement_de(user) == piece.etablissement_id
    return False  # dossier inconnu : refusé par défaut


# --------------------------------------------------------------------------- envoi
def _envoyer(path, public=False):
    full = os.path.join(settings.MEDIA_ROOT, *path.split('/'))
    if not os.path.isfile(full):
        raise Http404
    content_type = mimetypes.guess_type(full)[0] or 'application/octet-stream'
    nom = quote(os.path.basename(path))
    disposition = 'inline' if content_type in INLINE_TYPES else 'attachment'
    accel = getattr(settings, 'MEDIA_ACCEL_PREFIX', '')
    if accel:
        response = HttpResponse(content_type=content_type)
        response['X-Accel-Redirect'] = accel.rstrip('/') + '/' + quote(path)
    else:
        response = FileResponse(open(full, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f"{disposition}; filename*=UTF-8''{nom}"
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'public, max-age=604800' if public else 'private, max-age=3600'
    return response


@require_GET
def servir_media(request, path):
    path = _normaliser(path)
    if path is None:
        raise Http404
    if path.startswith(PUBLIC_PREFIXES):
        return _envoyer(path, public=True)
    if _signature_valide(request, path):
        return _envoyer(path)
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return redirect(f"{reverse('school_admin:connexion_compte_user')}?next={quote(request.path)}")
    if not autorise(user, path):
        raise Http404
    return _envoyer(path)
