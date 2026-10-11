"""Bloc « Aujourd’hui » — uniquement des données réellement disponibles."""
from __future__ import annotations

from django.db.models import Count, Q, Sum

from school_admin.model.presence_model import Presence, SoumissionListePresence
from school_admin.services.dashboard.context import DashboardContext
from school_admin.services.dashboard.querysets import apply_classe_filters


def _may(ctx: DashboardContext, permission: str) -> bool:
    if ctx.is_directeur:
        return True
    if ctx.permissions is None:
        return False
    return permission in ctx.permissions


def build_today_block(ctx: DashboardContext) -> dict:
    items = []
    items.append({
        'id': 'date',
        'label': 'Date',
        'value': ctx.today.strftime('%d/%m/%Y'),
        'empty': False,
    })

    if _may(ctx, 'presences_liste'):
        presence_qs = Presence.objects.filter(
            etablissement=ctx.etablissement,
            date=ctx.today,
        )
        if ctx.annee_scolaire:
            presence_qs = presence_qs.filter(annee_scolaire=ctx.annee_scolaire)
        presence_qs = apply_classe_filters(presence_qs, ctx, classe_field='classe')
        agg = presence_qs.aggregate(
            total=Count('id'),
            presents=Count('id', filter=Q(statut='present')),
            absents=Count('id', filter=Q(statut='absent')),
        )
        total = agg['total'] or 0
        if total:
            rate = round((agg['presents'] or 0) / total * 100, 1)
            items.append({
                'id': 'presence_today',
                'label': 'Présence du jour',
                'value': f"{rate} %",
                'detail': f"{agg['presents']} / {total} appels",
                'icon': 'fa-user-check',
                'empty': False,
                'url_name': 'directeur:suivi_presence',
            })
        else:
            items.append({
                'id': 'presence_today',
                'label': 'Présence du jour',
                'value': None,
                'detail': '',
                'icon': 'fa-user-check',
                'empty': True,
                'empty_reason': 'Aucun appel aujourd’hui.',
                'url_name': 'directeur:suivi_presence',
            })

        soum_qs = SoumissionListePresence.objects.filter(
            etablissement=ctx.etablissement,
            date=ctx.today,
        )
        if ctx.annee_scolaire:
            soum_qs = soum_qs.filter(annee_scolaire=ctx.annee_scolaire)
        soum_qs = apply_classe_filters(soum_qs, ctx, classe_field='classe')
        items.append({
            'id': 'appels_today',
            'label': 'Appels reçus',
            'value': soum_qs.count(),
            'detail': 'soumissions du jour',
            'icon': 'fa-clipboard-check',
            'empty': False,
            'url_name': 'directeur:suivi_presence',
        })

        weekday = (
            'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'
        )[ctx.today.weekday()]
        from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps

        creneaux = CreneauEmploiDuTemps.objects.filter(
            jour=weekday,
            emploi_du_temps__classe__etablissement=ctx.etablissement,
            emploi_du_temps__statut_publication='publie',
            emploi_du_temps__est_actif=True,
        )
        creneaux = apply_classe_filters(creneaux, ctx, classe_field='emploi_du_temps__classe')
        if ctx.annee_scolaire:
            creneaux = creneaux.filter(
                Q(emploi_du_temps__annee_scolaire_fk=ctx.annee_scolaire)
                | Q(emploi_du_temps__annee_scolaire=ctx.annee_scolaire.libelle)
            )
        n_cours = creneaux.count()
        if n_cours:
            items.append({
                'id': 'cours_today',
                'label': 'Cours programmés',
                'value': n_cours,
                'detail': 'emplois du temps publiés',
                'icon': 'fa-chalkboard',
                'empty': False,
                'url_name': 'directeur:gestion_etablissement',
            })
        else:
            items.append({
                'id': 'cours_today',
                'label': 'Cours programmés',
                'value': None,
                'icon': 'fa-chalkboard',
                'empty': True,
                'empty_reason': 'Aucun EDT publié pour aujourd’hui.',
            })

    from school_admin.model.annonce_model import Annonce

    annonces = Annonce.objects.filter(
        etablissement=ctx.etablissement,
        statut='publiee',
        date_publication__date=ctx.today,
    )
    if ctx.annee_scolaire:
        annonces = annonces.filter(
            Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
        )
    n_annonces = annonces.count()
    items.append({
        'id': 'events_today',
        'label': 'Événements',
        'value': n_annonces if n_annonces else None,
        'detail': 'annonces publiées aujourd’hui' if n_annonces else '',
        'icon': 'fa-calendar-day',
        'empty': not n_annonces,
        'empty_reason': 'Aucune annonce publiée aujourd’hui.',
        'url_name': 'directeur:annonces_directeur',
    })

    if _may(ctx, 'comptabilite_voir'):
        from school_admin.model.comptabilite_eleve_model import PaiementEleve
        from school_admin.services.recouvrement import devise_etablissement

        paiements = PaiementEleve.objects.filter(
            etablissement=ctx.etablissement,
            date_paiement__date=ctx.today,
        )
        if ctx.annee_scolaire:
            paiements = paiements.filter(annee_scolaire=ctx.annee_scolaire)
        pay_agg = paiements.aggregate(n=Count('id'), total=Sum('montant'))
        n_pay = pay_agg['n'] or 0
        total_pay = pay_agg['total']
        if n_pay:
            devise = devise_etablissement(ctx.etablissement)
            montant = f"{float(total_pay):,.0f}".replace(',', ' ') if total_pay else '0'
            items.append({
                'id': 'paiements_today',
                'label': 'Paiements du jour',
                'value': f"{montant} {devise}",
                'detail': f"{n_pay} encaissement(s)",
                'icon': 'fa-coins',
                'empty': False,
                'url_name': 'directeur:liste_comptabilite_eleves_directeur',
            })
        else:
            items.append({
                'id': 'paiements_today',
                'label': 'Paiements du jour',
                'value': None,
                'icon': 'fa-coins',
                'empty': True,
                'empty_reason': 'Aucun encaissement aujourd’hui.',
                'url_name': 'directeur:liste_comptabilite_eleves_directeur',
            })

    return {
        'block_id': 'today',
        'title': 'Aujourd’hui',
        'items': items,
        'meta': ctx.freshness_meta(),
        'empty': False,
    }
