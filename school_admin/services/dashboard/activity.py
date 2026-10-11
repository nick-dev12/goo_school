"""Activité récente déterministe (Phase 2)."""
from __future__ import annotations

from django.urls import NoReverseMatch, reverse

from school_admin.services.dashboard.context import DashboardContext
from school_admin.services.dashboard.permissions import user_may
from school_admin.services.dashboard.querysets import apply_classe_filters

ACTIVITY_LIMIT = 6


def _montant(value):
    """45000.00 → « 45 000 » (espace fine insécable comme séparateur de milliers)."""
    try:
        return f'{int(round(float(value))):,}'.replace(',', ' ')
    except (TypeError, ValueError):
        return str(value)


def _url(name: str, args=None) -> str:
    try:
        return reverse(name, args=args or [])
    except NoReverseMatch:
        return ''


def build_activity_feed(ctx: DashboardContext) -> list[dict]:
    items = []

    if user_may(ctx, 'presences_liste'):
        from school_admin.model.presence_model import SoumissionListePresence

        qs = SoumissionListePresence.objects.filter(
            etablissement=ctx.etablissement,
        ).select_related('classe', 'professeur')
        if ctx.annee_scolaire:
            qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
        qs = apply_classe_filters(qs, ctx, classe_field='classe')
        for row in qs.order_by('-date_soumission')[:ACTIVITY_LIMIT]:
            items.append({
                'id': f'appel-{row.id}',
                'kind': 'presence',
                'icon': 'fa-user-check',
                'title': f"Appel · {row.classe.nom if row.classe_id else '—'}",
                'detail': row.professeur.nom_complet if row.professeur_id else '',
                'at': row.date_soumission,
                'url': _url('directeur:suivi_presence'),
            })

    if user_may(ctx, 'notes_liste'):
        from school_admin.model.releve_notes_model import ReleveNotes

        qs = ReleveNotes.objects.filter(
            etablissement=ctx.etablissement,
            soumis=True,
        ).select_related('classe', 'matiere', 'professeur')
        if ctx.annee_scolaire:
            qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
        qs = apply_classe_filters(qs, ctx, classe_field='classe')
        for row in qs.order_by('-date_soumission')[:ACTIVITY_LIMIT]:
            matiere = row.matiere.nom if row.matiere_id else 'notes'
            items.append({
                'id': f'releve-{row.id}',
                'kind': 'notes',
                'icon': 'fa-file-alt',
                'title': f"Relevé · {row.classe.nom if row.classe_id else '—'} · {matiere}",
                'detail': row.professeur.nom_complet if row.professeur_id else '',
                'at': row.date_soumission,
                'url': _url('directeur:notes_et_resultats'),
            })

        from school_admin.model.justification_note_model import JustificationNote

        just_qs = JustificationNote.objects.filter(
            etablissement=ctx.etablissement,
        ).select_related('eleve', 'classe')
        if ctx.annee_scolaire:
            just_qs = just_qs.filter(annee_scolaire=ctx.annee_scolaire)
        for row in just_qs.order_by('-date_creation')[:ACTIVITY_LIMIT]:
            items.append({
                'id': f'justif-{row.id}',
                'kind': 'justification',
                'icon': 'fa-pen-to-square',
                'title': f"Justification de note · {row.eleve.nom_complet if row.eleve_id else '—'}",
                'detail': row.classe.nom if row.classe_id else '',
                'at': row.date_creation,
                'url': _url('directeur:justifications_notes'),
            })

    if user_may(ctx, 'comptabilite_voir'):
        from school_admin.model.comptabilite_eleve_model import PaiementEleve

        pay_qs = PaiementEleve.objects.filter(
            etablissement=ctx.etablissement,
        ).select_related('eleve')
        if ctx.annee_scolaire:
            pay_qs = pay_qs.filter(annee_scolaire=ctx.annee_scolaire)
        for row in pay_qs.order_by('-date_paiement')[:ACTIVITY_LIMIT]:
            items.append({
                'id': f'paiement-{row.id}',
                'kind': 'paiement',
                'icon': 'fa-coins',
                'title': f"Paiement · {row.eleve.nom_complet if row.eleve_id else '—'}",
                'detail': f"{_montant(row.montant)} {getattr(ctx.etablissement, 'devise_monnaie', None) or 'FCFA'}",
                'at': row.date_paiement,
                'url': _url('directeur:liste_comptabilite_eleves_directeur'),
            })

    from school_admin.model.sanction_model import Sanction

    san_qs = Sanction.objects.filter(etablissement=ctx.etablissement).select_related(
        'eleve', 'classe'
    )
    if ctx.annee_scolaire:
        san_qs = san_qs.filter(annee_scolaire=ctx.annee_scolaire)
    san_qs = apply_classe_filters(san_qs, ctx, classe_field='classe')
    # Discipline : réservée aux profils autorisés à consulter les sanctions.
    if not user_may(ctx, 'sanctions_liste'):
        san_qs = san_qs.none()
    for row in san_qs.order_by('-date_sanction', '-date_creation')[:ACTIVITY_LIMIT]:
        when = getattr(row, 'date_creation', None) or getattr(row, 'date_sanction', None)
        items.append({
            'id': f'sanction-{row.id}',
            'kind': 'sanction',
            'icon': 'fa-gavel',
            'title': f"Sanction · {row.eleve.nom_complet if row.eleve_id else '—'}",
            'detail': row.classe.nom if row.classe_id else '',
            'at': when,
            'url': _url('directeur:gestion_pedagogique'),
        })

    items = [item for item in items if item.get('at')]
    items.sort(key=lambda item: item['at'], reverse=True)
    return items[:ACTIVITY_LIMIT]
