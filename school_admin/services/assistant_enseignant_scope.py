"""
Périmètre des données accessibles à l'assistant enseignant primaire.
"""
from django.db.models import Q

from school_admin.services.assistant_search import find_classe as _find_classe_global


def affectations_qs(ctx):
    from school_admin.model.affectation_professeur_primaire_model import (
        AffectationProfesseurPrimaire,
    )

    if not ctx.professeur:
        return AffectationProfesseurPrimaire.objects.none()
    qs = AffectationProfesseurPrimaire.objects.filter(
        professeur=ctx.professeur,
        actif=True,
        classe__etablissement=ctx.etablissement,
    ).select_related('classe').prefetch_related('matieres')
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    return qs


def classe_ids_for_prof(ctx):
    return list(affectations_qs(ctx).values_list('classe_id', flat=True))


def matiere_ids_for_prof(ctx, classe=None):
    ids = set()
    for aff in affectations_qs(ctx):
        if classe and aff.classe_id != classe.id:
            continue
        ids.update(aff.matieres.values_list('id', flat=True))
    return list(ids)


def find_classe_prof(ctx, query):
    """Classe parmi celles affectées au professeur."""
    ids = classe_ids_for_prof(ctx)
    if not ids:
        return None
    from school_admin.model.classe_model import Classe

    narrowed = type(ctx)(
        etablissement=ctx.etablissement,
        annee_scolaire=ctx.annee_scolaire,
        est_superieur=ctx.est_superieur,
        est_primaire=ctx.est_primaire,
        libelle_eleve=ctx.libelle_eleve,
        personnel=ctx.personnel,
        professeur=ctx.professeur,
        persona=ctx.persona,
    )
    found = _find_classe_global(narrowed, query)
    if found and found.id in ids:
        return found
    if not query:
        return None
    q = (query or '').strip()
    return (
        Classe.objects.filter(id__in=ids, actif=True)
        .filter(Q(nom__icontains=q) | Q(code__icontains=q))
        .first()
    )


def ensure_classe_access(ctx, classe):
    if not classe:
        return {'erreur': 'Classe introuvable.'}
    if classe.id not in classe_ids_for_prof(ctx):
        return {'erreur': 'Vous n’êtes pas affecté à cette classe.'}
    return None


def ensure_matiere_in_classe(ctx, classe, matiere):
    err = ensure_classe_access(ctx, classe)
    if err:
        return err
    if matiere.id not in matiere_ids_for_prof(ctx, classe):
        return {'erreur': 'Vous n’enseignez pas cette matière dans cette classe.'}
    return None


def eleves_qs_for_prof(ctx, classe=None):
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    class_ids = [classe.id] if classe else classe_ids_for_prof(ctx)
    if not class_ids:
        return Eleve.objects.none()
    if ctx.annee_scolaire:
        eleve_ids = InscriptionEleve.objects.filter(
            annee_scolaire=ctx.annee_scolaire,
            classe_id__in=class_ids,
            etablissement=ctx.etablissement,
        ).values_list('eleve_id', flat=True)
        return Eleve.objects.filter(id__in=eleve_ids, actif=True)
    return Eleve.objects.filter(classe_id__in=class_ids, actif=True)


def find_eleve_prof(ctx, query, classe=None):
    from school_admin.services.assistant_tools import _eleve_name_filter

    raw = (query or '').strip()
    if not raw:
        return None
    qs = eleves_qs_for_prof(ctx, classe).select_related('classe')
    return qs.filter(_eleve_name_filter(raw)).first()


def ensure_eleve_access(ctx, eleve):
    if not eleve:
        return {'erreur': 'Élève introuvable.'}
    if not eleves_qs_for_prof(ctx).filter(pk=eleve.pk).exists():
        return {'erreur': 'Cet élève n’est pas dans vos classes.'}
    return None


def classe_eleve_active(ctx, eleve):
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    if ctx.annee_scolaire:
        ins = InscriptionEleve.objects.filter(
            eleve=eleve,
            annee_scolaire=ctx.annee_scolaire,
            etablissement=ctx.etablissement,
        ).select_related('classe').first()
        if ins and ins.classe_id:
            return ins.classe
    return eleve.classe if getattr(eleve, 'classe_id', None) else None


def affectations_summary(ctx):
    items = []
    for aff in affectations_qs(ctx):
        items.append({
            'classe': aff.classe.nom,
            'classe_id': aff.classe_id,
            'matieres': [m.nom for m in aff.matieres.all()],
        })
    return items
