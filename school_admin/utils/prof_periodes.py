"""Périodes scolaires pour les hubs professeur (présence, fiche élève, etc.)."""
from __future__ import annotations

from school_admin.model.periode_model import PeriodeScolaire


def load_periodes(etablissement, annee=None, classe=None):
    """Toutes les périodes configurées de l'année (pas seulement est_active)."""
    if not etablissement:
        return PeriodeScolaire.objects.none()
    qs = PeriodeScolaire.objects.filter(etablissement=etablissement)
    if annee:
        qs = qs.filter(annee_scolaire_fk=annee)
    qs = PeriodeScolaire.filter_queryset_for_classe(qs, etablissement, classe)
    return qs.order_by('date_debut')


def select_periode(request, periodes):
    pid = request.GET.get('periode') if request is not None else None
    if pid:
        selected = periodes.filter(id=pid).first()
        if selected:
            return selected
    for periode in periodes:
        if periode.est_en_cours:
            return periode
    return periodes.first()


def apply_date_range(qs, periode, field='date'):
    if not periode:
        return qs
    if periode.date_debut:
        qs = qs.filter(**{f'{field}__gte': periode.date_debut})
    if periode.date_fin:
        qs = qs.filter(**{f'{field}__lte': periode.date_fin})
    return qs


def ensure_query_params(request, **params):
    from django.http import HttpResponseRedirect

    wanted = {k: str(v) for k, v in params.items() if v not in (None, '')}
    if not wanted:
        return None
    if all(str(request.GET.get(k) or '') == v for k, v in wanted.items()):
        return None
    q = request.GET.copy()
    for k, v in wanted.items():
        q[k] = v
    return HttpResponseRedirect(request.path + '?' + q.urlencode())
