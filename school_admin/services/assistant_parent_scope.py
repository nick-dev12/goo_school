"""
Périmètre des données accessibles à l'assistant parent (enfants liés uniquement).
"""
from school_admin.model.lien_familial_model import LienFamilial


def liens_valides_qs(parent):
    if not parent:
        from school_admin.model.lien_familial_model import LienFamilial as LF

        return LF.objects.none()
    return LienFamilial.objects.filter(
        parent=parent,
        actif=True,
        statut='valide',
    ).select_related(
        'eleve',
        'eleve__etablissement',
        'eleve__classe',
    )


def enfants_lies_ids(parent):
    return list(
        liens_valides_qs(parent)
        .filter(eleve__actif=True)
        .values_list('eleve_id', flat=True)
        .distinct()
    )


def get_eleve_lie(parent, eleve_id):
    """Retourne l'élève si le lien familial est valide, sinon None."""
    if not parent or not eleve_id:
        return None
    try:
        eleve_id = int(eleve_id)
    except (TypeError, ValueError):
        return None
    lien = liens_valides_qs(parent).filter(eleve_id=eleve_id).first()
    if not lien or not lien.eleve or not lien.eleve.actif:
        return None
    return lien.eleve


def eleve_depuis_session(parent, session_store=None):
    """Élève consulté (session parent) si lien valide."""
    session_store = session_store or {}
    raw = session_store.get('eleve_consulte_id')
    if not raw:
        return None
    return get_eleve_lie(parent, raw)


def refus_acces_eleve(eleve_id=None):
    return {
        'erreur': (
            "Vous n'avez pas accès aux informations de cet élève. "
            "Choisissez un enfant lié à votre compte."
        ),
        'eleve_id': eleve_id,
        'statut': 'acces_refuse',
    }


def assert_eleve_autorise(parent, eleve_id):
    """None si OK, sinon dict erreur JSON."""
    eleve = get_eleve_lie(parent, eleve_id)
    if eleve:
        return None
    return refus_acces_eleve(eleve_id)


def resume_enfants(parent, limit=12):
    """Liste courte pour le prompt / contexte."""
    items = []
    for lien in liens_valides_qs(parent).filter(eleve__actif=True)[:limit]:
        eleve = lien.eleve
        items.append(
            {
                'id': eleve.id,
                'nom': getattr(eleve, 'nom_complet', None) or f'{eleve.prenom} {eleve.nom}',
                'classe': eleve.classe.nom if getattr(eleve, 'classe_id', None) else None,
                'etablissement': (
                    eleve.etablissement.nom if getattr(eleve, 'etablissement_id', None) else None
                ),
                'lien': lien.get_type_lien_display(),
            }
        )
    return items


def find_enfant_par_nom(parent, query):
    """Recherche un enfant lié par nom / prénom / matricule (partiel)."""
    q = (query or '').strip().lower()
    if not q or not parent:
        return None
    for lien in liens_valides_qs(parent).filter(eleve__actif=True):
        el = lien.eleve
        haystack = ' '.join(
            filter(
                None,
                [
                    getattr(el, 'nom_complet', ''),
                    el.nom,
                    el.prenom,
                    getattr(el, 'matricule_eleve', ''),
                ],
            )
        ).lower()
        if q in haystack:
            return el
    return None


def apply_consultation_session(session, parent, eleve):
    """Pose les clés session comme dashboard_enfant."""
    if session is None or not parent or not eleve:
        return False
    session['parent_id'] = parent.id
    if getattr(parent, 'matricule_parental', None):
        session['parent_matricule'] = parent.matricule_parental
    session['eleve_consulte_id'] = eleve.id
    session['eleve_consulte_nom'] = getattr(eleve, 'nom_complet', None) or f'{eleve.prenom} {eleve.nom}'
    session['mode_consultation_parent'] = True
    if hasattr(session, 'save'):
        session.save()
    return True


def etablissement_effectif(parent, eleve_consulte=None):
    """Établissement de référence pour le type pédagogique (enfant consulté prioritaire)."""
    if eleve_consulte and getattr(eleve_consulte, 'etablissement_id', None):
        return eleve_consulte.etablissement
    if parent and getattr(parent, 'etablissement_id', None):
        return parent.etablissement
    return None
