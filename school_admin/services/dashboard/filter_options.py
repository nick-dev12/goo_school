"""Options de filtres cascade (cycle → classe) pour le dashboard D1."""
from __future__ import annotations

from school_admin.model.classe_model import Classe
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.services.dashboard.context import CYCLE_VALUES, DashboardContext

CYCLE_LABELS = {
    'maternelle': 'Maternelle',
    'primaire': 'Primaire',
    'college': 'Collège',
    'lycee': 'Lycée',
    'superieur': 'Supérieur',
}


def build_filter_options(ctx: DashboardContext) -> dict:
    classes = Classe.objects.filter(
        etablissement=ctx.etablissement,
        actif=True,
    ).order_by('niveau', 'nom')

    cycles_present = list(classes.values_list('niveau', flat=True).distinct())
    cycles = [
        {'value': key, 'label': CYCLE_LABELS[key]}
        for key in ('maternelle', 'primaire', 'college', 'lycee', 'superieur')
        if key in cycles_present
    ]

    classes_qs = classes
    if ctx.filters.cycle in CYCLE_VALUES:
        classes_qs = classes_qs.filter(niveau=ctx.filters.cycle)

    classe_options = [
        {'id': c.id, 'nom': c.nom, 'niveau': c.niveau}
        for c in classes_qs
    ]
    valid_classe_ids = {c['id'] for c in classe_options}
    classe_id = ctx.filters.classe_id if ctx.filters.classe_id in valid_classe_ids else None

    periodes_qs = PeriodeScolaire.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        periodes_qs = periodes_qs.filter(annee_scolaire_fk=ctx.annee_scolaire)
    periodes = [
        {'id': p.id, 'label': p.nom_periode}
        for p in periodes_qs.order_by('date_debut')
    ]

    filieres = []
    if ctx.filters.cycle == 'superieur' or any(c.niveau == 'superieur' for c in classes):
        from school_admin.model.academic_structure_model import Department

        filieres = list(
            Department.objects.filter(etablissement=ctx.etablissement)
            .order_by('ordre', 'nom')
            .values('id', 'nom')
        )

    return {
        'cycles': cycles,
        'classes': classe_options,
        'periodes': periodes,
        'filieres': filieres,
        'selected_classe_id': classe_id,
        'has_active_filters': bool(
            ctx.filters.cycle or classe_id or ctx.filters.periode_id or ctx.filters.filiere
        ),
    }
