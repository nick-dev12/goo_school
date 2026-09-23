"""
Vague 2 — tools de pilotage (stats) et de scolarité pour l’assistant directeur.

Lecture : get_*  ·  Écriture : brouillon + confirmation (ACTION_SPECS).
Aucun tool de comptabilité générale ici.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from school_admin.services.assistant_actions import (
    ActionSpec,
    _err,
    _find_classe,
    _find_eleve,
    _incomplete,
    _ok,
    _pending,
    register_action,
)
from school_admin.services.assistant_search import CLASSE_PARAM_DESCRIPTION


def _search_limit():
    from school_admin.services.assistant_tools import SEARCH_LIMIT

    return SEARCH_LIMIT


def _eleves_qs(ctx):
    from school_admin.services.assistant_tools import _eleves_qs as finder

    return finder(ctx)


def _safe_decimal(value):
    from school_admin.services.assistant_tools import _safe_decimal as converter

    return converter(value)

logger = logging.getLogger(__name__)

ZERO = Decimal('0.00')
PRESENCE_PRESENT = frozenset({'present', 'retard'})
PRESENCE_ABSENT = frozenset({'absent', 'absent_justifie'})
IMPAYES_STATUTS = frozenset({'en_retard', 'impaye', 'en_attente'})


def _pct(part, total, digits=1):
    if not total:
        return None
    return round(100.0 * float(part) / float(total), digits)


def _money(value):
    if value is None:
        return 0.0
    return float(value)


def _reverse(route, args=None):
    try:
        return reverse(route, args=args or [])
    except NoReverseMatch:
        return None


def _compta_qs(ctx):
    from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve

    qs = ComptabiliteEleve.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    return qs


def _periodes_qs(ctx):
    from school_admin.model.periode_model import PeriodeScolaire

    qs = PeriodeScolaire.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire_fk=ctx.annee_scolaire)
            | Q(annee_scolaire=ctx.annee_scolaire.libelle)
        )
    return qs


def _find_periode(ctx, query=None):
    from school_admin.model.periode_model import PeriodeScolaire

    qs = _periodes_qs(ctx)
    text = (query or '').strip()
    if text:
        found = qs.filter(nom_periode__icontains=text).first()
        if found:
            return found
    active = PeriodeScolaire.get_periode_active(ctx.etablissement)
    if active and qs.filter(pk=active.pk).exists():
        return active
    return qs.order_by('-date_debut').first()


def _periode_precedente(ctx, periode):
    if not periode or not periode.date_debut:
        return None
    return (
        _periodes_qs(ctx)
        .filter(date_debut__lt=periode.date_debut)
        .order_by('-date_debut')
        .first()
    )


def _seuil_passage(ctx):
    from school_admin.model.standards_reussite_model import StandardsReussite

    standards = StandardsReussite.objects.filter(
        etablissement=ctx.etablissement
    ).first()
    if standards and standards.moyenne_passage is not None:
        return Decimal(str(standards.moyenne_passage))
    return Decimal('10.00')


def _presence_qs(ctx, jours=7, classe=None, eleve=None):
    from school_admin.model.presence_model import Presence

    try:
        jours = int(jours or 7)
    except (TypeError, ValueError):
        jours = 7
    jours = max(1, min(jours, 90))
    since = timezone.now().date() - timedelta(days=jours)
    qs = Presence.objects.filter(etablissement=ctx.etablissement, date__gte=since)
    if classe:
        qs = qs.filter(classe=classe)
    if eleve:
        qs = qs.filter(eleve=eleve)
    return qs, jours


def _taux_presence_payload(qs, jours, perimetre):
    totaux = {
        row['statut']: row['nb']
        for row in qs.values('statut').annotate(nb=Count('id'))
    }
    total = sum(totaux.values())
    presents = sum(totaux.get(key, 0) for key in PRESENCE_PRESENT)
    absents = sum(totaux.get(key, 0) for key in PRESENCE_ABSENT)
    return {
        'perimetre': perimetre,
        'periode_jours': jours,
        'nb_enregistrements': total,
        'nb_presents': presents,
        'nb_absents': absents,
        'totaux': totaux,
        'taux_presence': _pct(presents, total),
    }


def _moyennes_generales_qs(ctx, periode, classe=None):
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    qs = MoyennePeriode.objects.filter(
        etablissement=ctx.etablissement,
        periode=periode,
        est_moyenne_generale=True,
        moyenne_generale__isnull=False,
    )
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
        )
    if classe:
        qs = qs.filter(eleve__classe=classe)
    return qs


def _credits_periode(ctx, periode, classe=None):
    """Crédits matière si présents (supérieur). Ne rien inventer sinon."""
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    qs = MoyennePeriode.objects.filter(
        etablissement=ctx.etablissement,
        periode=periode,
        est_moyenne_generale=False,
        credits__isnull=False,
    )
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
        )
    if classe:
        qs = qs.filter(eleve__classe=classe)
    if not qs.exists():
        return None
    seuil = _seuil_passage(ctx)
    inscrits = qs.aggregate(total=Sum('credits'))['total'] or ZERO
    valides = qs.filter(moyenne_matiere__gte=seuil).aggregate(total=Sum('credits'))['total'] or ZERO
    return {
        'credits_inscrits': _safe_decimal(inscrits),
        'credits_valides': _safe_decimal(valides),
        'taux_credits': _pct(valides, inscrits),
        'seuil': _safe_decimal(seuil),
    }


def _synthese_moyennes(ctx, periode, classe=None):
    qs = _moyennes_generales_qs(ctx, periode, classe)
    seuil = _seuil_passage(ctx)
    nb = qs.count()
    reussis = qs.filter(moyenne_generale__gte=seuil).count()
    moyenne = qs.aggregate(m=Sum('moyenne_generale'))['m']
    moyenne_etab = None
    if nb and moyenne is not None:
        moyenne_etab = _safe_decimal(Decimal(str(moyenne)) / Decimal(nb))
    payload = {
        'periode': periode.nom_periode if periode else None,
        'seuil': _safe_decimal(seuil),
        'nb_moyennes': nb,
        'nb_au_dessus': reussis,
        'nb_en_dessous': max(0, nb - reussis),
        'taux_reussite': _pct(reussis, nb),
        'moyenne': moyenne_etab,
    }
    credits = _credits_periode(ctx, periode, classe) if getattr(ctx, 'est_superieur', False) else None
    if credits:
        payload['credits'] = credits
    return payload


def _charges_ouvertes(resume):
    items = []
    for charge in getattr(resume, 'charges', []) or []:
        if charge.reste <= ZERO:
            continue
        items.append({
            'libelle': charge.libelle,
            'kind': charge.kind,
            'montant': _money(charge.montant),
            'paye': _money(charge.montant_paye),
            'reste': _money(charge.reste),
            'echeance': charge.date_echeance.isoformat() if charge.date_echeance else None,
            'statut': charge.statut,
        })
    return items


def _parent_relance(eleve, reste):
    if reste is None or Decimal(str(reste)) <= ZERO:
        return None
    nom = getattr(eleve, 'parent_nom_complet', None) or ' '.join(
        part for part in (
            getattr(eleve, 'parent_prenom', '') or '',
            getattr(eleve, 'parent_nom', '') or '',
        ) if part
    ).strip()
    telephone = getattr(eleve, 'parent_telephone', None) or None
    if not nom and not telephone:
        return None
    return {'nom': nom or None, 'telephone': telephone}


def _dernier_paiement(ctx, eleve):
    from school_admin.model.comptabilite_eleve_model import PaiementEleve

    qs = PaiementEleve.objects.filter(
        etablissement=ctx.etablissement,
        eleve=eleve,
    )
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    return qs.order_by('-date_paiement', '-id').first()


def _recu_url(paiement):
    if not paiement:
        return None
    return _reverse('directeur:recu_paiement_directeur', args=[paiement.id])


def _lignes_scolarite(fiche):
    inscription = []
    for frais in fiche.frais_inscriptions.all():
        inscription.append({
            'libelle': frais.get_type_frais_display(),
            'montant': _money(frais.montant),
            'paye': _money(frais.montant_paye),
            'reste': _money(frais.get_reste_a_payer()),
            'statut': frais.get_statut_display(),
            'echeance': frais.date_echeance.isoformat() if frais.date_echeance else None,
        })
    mensualites = []
    for mens in fiche.mensualites.all().order_by('annee', 'mois'):
        mensualites.append({
            'periode': mens.periode,
            'montant': _money(mens.montant),
            'paye': _money(mens.montant_paye),
            'reste': _money(mens.get_reste_a_payer()) if hasattr(mens, 'get_reste_a_payer') else _money(mens.montant - mens.montant_paye),
            'statut': mens.get_statut_display(),
            'echeance': mens.date_echeance.isoformat() if mens.date_echeance else None,
        })
    annexes = []
    for frais in fiche.frais_annexes.all():
        annexes.append({
            'libelle': frais.libelle,
            'code': frais.code,
            'montant': _money(frais.montant),
            'paye': _money(frais.montant_paye),
            'reste': _money(frais.get_reste_a_payer()),
            'statut': frais.get_statut_display(),
            'echeance': frais.date_echeance.isoformat() if frais.date_echeance else None,
        })
    return inscription, mensualites, annexes


def _moratoire_item(moratoire):
    echeances = []
    for ech in moratoire.echeances.all().order_by('numero'):
        echeances.append({
            'numero': ech.numero,
            'montant': _money(ech.montant),
            'paye': _money(ech.montant_paye),
            'reste': _money(ech.get_reste_a_payer()),
            'statut': ech.get_statut_display(),
            'echeance': ech.date_echeance.isoformat() if ech.date_echeance else None,
        })
    return {
        'id': moratoire.id,
        'eleve': moratoire.eleve.nom_complet,
        'classe': moratoire.eleve.classe.nom if moratoire.eleve.classe_id else None,
        'motif': moratoire.motif,
        'statut': moratoire.get_statut_display(),
        'montant_total': _money(moratoire.montant_total),
        'paye': _money(moratoire.montant_paye()),
        'reste': _money(moratoire.reste_a_payer()),
        'echeances': echeances,
    }


def _anciennete_jours(date_echeance, today):
    if not date_echeance:
        return 0
    delta = (today - date_echeance).days
    return max(0, delta)


def _bucket_anciennete(jours):
    if jours <= 30:
        return '0-30'
    if jours <= 60:
        return '31-60'
    return '61+'


# ---------------------------------------------------------------------------
# Lecture — statistiques
# ---------------------------------------------------------------------------

def tool_statistiques_pilotage(ctx, args):
    """Tableau de bord vocal : effectifs + présence + recouvrement + sanctions."""
    from school_admin.services.assistant_tools import tool_effectifs, tool_sanctions

    args = args if isinstance(args, dict) else {}
    effectifs = tool_effectifs(ctx, args)
    jours = args.get('jours') or 7
    classe = _find_classe(ctx, (args.get('classe') or '').strip()) if args.get('classe') else None
    presence_qs, jours = _presence_qs(ctx, jours=jours, classe=classe)
    presence = _taux_presence_payload(
        presence_qs,
        jours,
        classe.nom if classe else 'etablissement',
    )

    fiches = _compta_qs(ctx)
    if classe:
        fiches = fiches.filter(eleve__classe=classe)
    total_du = ZERO
    total_paye = ZERO
    for fiche in fiches:
        total_du += fiche.calculer_total_du()
        total_paye += fiche.calculer_total_paye()
    reste = total_du - total_paye
    if reste < ZERO:
        reste = ZERO
    nb_impayes = fiches.filter(statut_paiement__in=['en_retard', 'impaye']).count()

    sanctions = tool_sanctions(ctx, {'classe': args.get('classe') or ''})
    return {
        'session': effectifs.get('session'),
        'perimetre': effectifs.get('perimetre'),
        'effectifs': {
            'nb_eleves': effectifs.get('nb_eleves_actifs'),
            'nb_filles': effectifs.get('nb_filles'),
            'nb_garcons': effectifs.get('nb_garcons'),
            'nb_classes': effectifs.get('nb_classes'),
            'nb_professeurs': effectifs.get('nb_professeurs'),
            'nb_personnel': effectifs.get('nb_personnel'),
            'capacite_totale': effectifs.get('capacite_totale'),
            'places_libres': effectifs.get('places_libres'),
        },
        'presence': {
            'periode_jours': presence['periode_jours'],
            'taux_presence': presence['taux_presence'],
            'nb_enregistrements': presence['nb_enregistrements'],
        },
        'scolarite': {
            'total_du': _money(total_du),
            'total_paye': _money(total_paye),
            'reste': _money(reste),
            'taux_recouvrement': _pct(total_paye, total_du),
            'nb_impayes': nb_impayes,
            'nb_a_jour': fiches.filter(statut_paiement='a_jour').count(),
        },
        'sanctions': {
            'nb_sanctions': sanctions.get('nb_sanctions', 0),
            'nb_eleves': sanctions.get('nb_eleves_avec_sanction', 0),
        },
    }


def tool_taux_reussite(ctx, args):
    args = args if isinstance(args, dict) else {}
    periode = _find_periode(ctx, args.get('periode') or args.get('query'))
    if not periode:
        return {'erreur': 'Aucune période scolaire trouvée pour cette session.'}
    classe = _find_classe(ctx, (args.get('classe') or '').strip()) if args.get('classe') else None
    payload = _synthese_moyennes(ctx, periode, classe)
    payload['perimetre'] = classe.nom if classe else 'etablissement'
    payload['session'] = ctx.annee_scolaire.libelle if ctx.annee_scolaire else None
    if payload['nb_moyennes'] == 0:
        payload['message'] = (
            'Aucune moyenne de période calculée. '
            'Lance d’abord le calcul des moyennes.'
        )
    return payload


def tool_taux_presence(ctx, args):
    args = args if isinstance(args, dict) else {}
    query = (args.get('query') or args.get('eleve') or '').strip()
    classe_nom = (args.get('classe') or '').strip()
    eleve = _find_eleve(ctx, query) if query else None
    if query and not eleve:
        return {'erreur': f'Aucun {ctx.libelle_eleve} trouvé pour « {query} ».'}
    classe = _find_classe(ctx, classe_nom) if classe_nom else None
    if classe_nom and not classe:
        return {'erreur': f'Classe introuvable : « {classe_nom} ».'}
    qs, jours = _presence_qs(ctx, jours=args.get('jours') or 7, classe=classe, eleve=eleve)
    if eleve:
        perimetre = eleve.nom_complet
    elif classe:
        perimetre = classe.nom
    else:
        perimetre = 'etablissement'
    payload = _taux_presence_payload(qs, jours, perimetre)
    if eleve:
        payload['eleve'] = eleve.nom_complet
        payload['classe'] = eleve.classe.nom if eleve.classe_id else None
    elif classe:
        payload['classe'] = classe.nom
    return payload


def tool_comparatif_periodes(ctx, args):
    args = args if isinstance(args, dict) else {}
    periode = _find_periode(ctx, args.get('periode'))
    if not periode:
        return {'erreur': 'Aucune période scolaire trouvée pour cette session.'}
    precedente = _periode_precedente(ctx, periode)
    classe = _find_classe(ctx, (args.get('classe') or '').strip()) if args.get('classe') else None
    actuelle = _synthese_moyennes(ctx, periode, classe)
    precedente_payload = _synthese_moyennes(ctx, precedente, classe) if precedente else None
    delta = None
    if (
        actuelle.get('moyenne') is not None
        and precedente_payload
        and precedente_payload.get('moyenne') is not None
    ):
        delta = round(actuelle['moyenne'] - precedente_payload['moyenne'], 2)
    payload = {
        'perimetre': classe.nom if classe else 'etablissement',
        'periode': actuelle,
        'periode_precedente': precedente_payload,
        'delta_moyenne': delta,
        'session': ctx.annee_scolaire.libelle if ctx.annee_scolaire else None,
    }
    if not precedente:
        payload['message'] = 'Pas de période précédente à comparer.'
    return payload


def tool_repartition_cycles(ctx, args):
    if not getattr(ctx, 'est_college_lycee', False):
        return {
            'erreur': (
                'La répartition par cycle n’est proposée '
                'que pour un établissement collège+lycée ou mixte.'
            )
        }
    args = args if isinstance(args, dict) else {}
    eleves = _eleves_qs(ctx)
    rows = (
        eleves.filter(classe_id__isnull=False)
        .values('classe__niveau')
        .annotate(
            effectif=Count('id'),
            filles=Count('id', filter=Q(sexe='F')),
            garcons=Count('id', filter=Q(sexe='M')),
            nb_classes=Count('classe_id', distinct=True),
        )
        .order_by('classe__niveau')
    )
    cycles = []
    labels = {'college': 'Collège', 'lycee': 'Lycée', 'primaire': 'Primaire'}
    for row in rows:
        niveau = row['classe__niveau']
        cycles.append({
            'cycle': niveau,
            'libelle': labels.get(niveau, niveau),
            'effectif': row['effectif'],
            'filles': row['filles'],
            'garcons': row['garcons'],
            'nb_classes': row['nb_classes'],
        })
    total = sum(item['effectif'] for item in cycles)
    for item in cycles:
        item['part'] = _pct(item['effectif'], total)
    return {
        'session': ctx.annee_scolaire.libelle if ctx.annee_scolaire else None,
        'nb_eleves': total,
        'cycles': cycles,
    }


# ---------------------------------------------------------------------------
# Lecture — scolarité
# ---------------------------------------------------------------------------

def tool_fiche_scolarite(ctx, args):
    from school_admin.services.recouvrement import moratoire_actif, resume_dette_eleve

    args = args if isinstance(args, dict) else {}
    query = (args.get('query') or args.get('eleve') or '').strip()
    if not query:
        return {'erreur': f'Indique le nom ou le matricule du {ctx.libelle_eleve}.'}
    eleve = _find_eleve(ctx, query)
    if not eleve:
        return {'erreur': f'Aucun {ctx.libelle_eleve} trouvé pour « {query} ».'}

    fiche = _compta_qs(ctx).filter(eleve=eleve).first()
    resume = None
    if ctx.annee_scolaire:
        resume = resume_dette_eleve(eleve, ctx.etablissement, ctx.annee_scolaire)

    inscription, mensualites, annexes = ([], [], [])
    statut = None
    total_du = resume.total_du if resume else ZERO
    total_paye = resume.total_paye if resume else ZERO
    reste = resume.reste if resume else ZERO
    if fiche:
        inscription, mensualites, annexes = _lignes_scolarite(fiche)
        statut = fiche.get_statut_paiement_display()
        if resume is None:
            total_du = fiche.calculer_total_du()
            total_paye = fiche.calculer_total_paye()
            reste = total_du - total_paye

    paiement = _dernier_paiement(ctx, eleve)
    mora = None
    if ctx.annee_scolaire:
        mora = moratoire_actif(eleve, ctx.etablissement, ctx.annee_scolaire)

    return {
        'eleve': eleve.nom_complet,
        'eleve_id': eleve.id,
        'matricule': eleve.matricule_eleve,
        'classe': eleve.classe.nom if eleve.classe_id else None,
        'classe_id': eleve.classe_id,
        'statut': statut or (resume.statut if resume else None),
        'total_du': _money(total_du),
        'total_paye': _money(total_paye),
        'reste': _money(reste),
        'prochaine_echeance': (
            resume.prochaine_echeance.isoformat()
            if resume and resume.prochaine_echeance else None
        ),
        'prochaine_libelle': resume.prochaine_libelle if resume else None,
        'charges_ouvertes': _charges_ouvertes(resume) if resume else [],
        'inscription': inscription,
        'mensualites': mensualites,
        'annexes': annexes,
        'dernier_recu': paiement.numero_recu or None if paiement else None,
        'dernier_paiement_montant': _money(paiement.montant) if paiement else None,
        'url_recu': _recu_url(paiement),
        'moratoire': _moratoire_item(mora) if mora else None,
        'parent_a_relancer': _parent_relance(eleve, reste),
        'url': _reverse('directeur:details_comptabilite_eleve_directeur', args=[eleve.id]),
    }


def tool_bilan_scolarite(ctx, args):
    args = args if isinstance(args, dict) else {}
    classe = _find_classe(ctx, (args.get('classe') or '').strip()) if args.get('classe') else None
    fiches = _compta_qs(ctx).select_related('eleve', 'eleve__classe')
    if classe:
        fiches = fiches.filter(eleve__classe=classe)

    total_du = ZERO
    total_paye = ZERO
    for fiche in fiches:
        total_du += fiche.calculer_total_du()
        total_paye += fiche.calculer_total_paye()
    reste = total_du - total_paye
    if reste < ZERO:
        reste = ZERO

    return {
        'session': ctx.annee_scolaire.libelle if ctx.annee_scolaire else None,
        'perimetre': classe.nom if classe else 'etablissement',
        'nb_fiches': fiches.count(),
        'total_du': _money(total_du),
        'total_paye': _money(total_paye),
        'reste': _money(reste),
        'taux_recouvrement': _pct(total_paye, total_du),
        'nb_a_jour': fiches.filter(statut_paiement='a_jour').count(),
        'nb_en_retard': fiches.filter(statut_paiement='en_retard').count(),
        'nb_impaye': fiches.filter(statut_paiement='impaye').count(),
    }


def tool_impayes(ctx, args):
    from school_admin.services.recouvrement import collecter_impayes_par_classe

    args = args if isinstance(args, dict) else {}
    if not ctx.annee_scolaire:
        return {'erreur': 'Aucune session scolaire active.'}

    classe = _find_classe(ctx, (args.get('classe') or '').strip()) if args.get('classe') else None
    statut = (args.get('statut') or '').strip().lower()
    if statut and statut not in IMPAYES_STATUTS:
        return {
            'erreur': 'Statut inconnu. Utilise en_retard, impaye ou en_attente.',
        }
    anciennete = (args.get('anciennete') or args.get('bucket') or '').strip()
    today = timezone.now().date()
    groupes = collecter_impayes_par_classe(ctx.etablissement, ctx.annee_scolaire)
    items = []
    buckets = {'0-30': 0, '31-60': 0, '61+': 0}
    total_reste = ZERO

    for groupe in groupes:
        if classe and groupe.get('classe_id') != classe.id:
            continue
        for row in groupe.get('eleves') or []:
            resume = row['resume']
            eleve = row['eleve']
            jours = _anciennete_jours(resume.prochaine_echeance, today)
            bucket = _bucket_anciennete(jours) if resume.prochaine_echeance and resume.prochaine_echeance < today else '0-30'
            if not resume.prochaine_echeance or resume.prochaine_echeance >= today:
                bucket = '0-30'
            if statut and resume.statut != statut:
                continue
            if anciennete and bucket != anciennete:
                continue
            items.append({
                'eleve': eleve.nom_complet,
                'eleve_id': eleve.id,
                'classe': groupe.get('classe_nom'),
                'classe_id': groupe.get('classe_id'),
                'statut': resume.statut,
                'reste': _money(resume.reste),
                'prochaine_echeance': (
                    resume.prochaine_echeance.isoformat()
                    if resume.prochaine_echeance else None
                ),
                'anciennete_jours': jours if resume.prochaine_echeance and resume.prochaine_echeance < today else 0,
                'bucket': bucket,
            })
            buckets[bucket] = buckets.get(bucket, 0) + 1
            total_reste += resume.reste

    items.sort(key=lambda row: (-row['anciennete_jours'], row['eleve']))
    return {
        'session': ctx.annee_scolaire.libelle,
        'perimetre': classe.nom if classe else 'etablissement',
        'filtre_statut': statut or None,
        'filtre_anciennete': anciennete or None,
        'nb': len(items),
        'total_reste': _money(total_reste),
        'balance_agee': buckets,
        'impayes': items[:_search_limit() * 2],
    }


def tool_ouvrir_recu(ctx, args):
    from school_admin.model.comptabilite_eleve_model import PaiementEleve

    args = args if isinstance(args, dict) else {}
    numero = (args.get('numero') or args.get('numero_recu') or '').strip()
    query = (args.get('query') or args.get('eleve') or '').strip()
    paiement = None
    if numero:
        paiement = PaiementEleve.objects.filter(
            etablissement=ctx.etablissement,
            numero_recu__iexact=numero,
        ).first()
        if paiement is None:
            paiement = PaiementEleve.objects.filter(
                etablissement=ctx.etablissement,
                numero_recu__icontains=numero,
            ).order_by('-date_paiement').first()
    elif query:
        eleve = _find_eleve(ctx, query)
        if not eleve:
            return {'erreur': f'Aucun {ctx.libelle_eleve} trouvé pour « {query} ».'}
        paiement = _dernier_paiement(ctx, eleve)
    else:
        return {
            'erreur': 'Indique un numéro de reçu ou le nom de l’élève.',
        }
    if not paiement:
        return {'erreur': 'Aucun reçu trouvé.'}
    url = _recu_url(paiement)
    ouvrir = args.get('ouvrir')
    if ouvrir is None:
        ouvrir = True
    return {
        'trouve': True,
        'numero_recu': paiement.numero_recu or None,
        'eleve': paiement.eleve.nom_complet,
        'montant': _money(paiement.montant),
        'date': paiement.date_paiement.isoformat() if paiement.date_paiement else None,
        'url': url,
        'ouvrir': bool(ouvrir),
        'titre': paiement.numero_recu or 'Reçu de paiement',
    }


def tool_moratoires(ctx, args):
    from school_admin.model.recouvrement_model import Moratoire

    args = args if isinstance(args, dict) else {}
    qs = Moratoire.objects.filter(etablissement=ctx.etablissement).select_related(
        'eleve', 'eleve__classe'
    ).prefetch_related('echeances')
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    query = (args.get('query') or args.get('eleve') or '').strip()
    if query:
        eleve = _find_eleve(ctx, query)
        if not eleve:
            return {'erreur': f'Aucun {ctx.libelle_eleve} trouvé pour « {query} ».'}
        qs = qs.filter(eleve=eleve)
    statut = (args.get('statut') or '').strip()
    if statut:
        qs = qs.filter(statut=statut)
    items = [_moratoire_item(m) for m in qs.order_by('-date_creation')[:_search_limit()]]
    return {
        'session': ctx.annee_scolaire.libelle if ctx.annee_scolaire else None,
        'nb': qs.count(),
        'moratoires': items,
    }


# ---------------------------------------------------------------------------
# Écriture — confirmation obligatoire
# ---------------------------------------------------------------------------

def prepare_verifier_statuts_paiement(ctx, args):
    fiches = _compta_qs(ctx)
    nb = fiches.count()
    if not nb:
        return _err('Aucune fiche de scolarité à vérifier pour cette session.')
    return _pending(
        'verifier_statuts_paiement',
        f'Recalculer les statuts de paiement de {nb} fiche(s) de la session.',
        nb=nb,
    )


def apply_verifier_statuts_paiement(ctx, draft):
    fiches = list(_compta_qs(ctx))
    modifies = 0
    for fiche in fiches:
        ancien = fiche.statut_paiement
        nouveau = fiche.verifier_statut_paiement()
        if ancien != nouveau:
            modifies += 1
    return _ok(
        f'Vérification terminée. {modifies} statut(s) modifié(s) sur {len(fiches)} fiche(s).',
        nb=len(fiches),
        nb_modifies=modifies,
        url=_reverse('directeur:liste_comptabilite_eleves_directeur'),
    )


def prepare_synchroniser_remises_fratrie(ctx, args):
    args = args if isinstance(args, dict) else {}
    query = (args.get('query') or args.get('eleve') or '').strip()
    if query:
        eleve = _find_eleve(ctx, query)
        if not eleve:
            return _err(f'Aucun {ctx.libelle_eleve} trouvé pour « {query} ».')
        return _pending(
            'synchroniser_remises_fratrie',
            f'Recalculer la remise fratrie pour {eleve.nom_complet}.',
            eleve_id=eleve.id,
            nom=eleve.nom_complet,
            perimetre='eleve',
        )
    if not ctx.annee_scolaire:
        return _err('Aucune session scolaire active.')
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    nb = InscriptionEleve.objects.filter(
        etablissement=ctx.etablissement,
        annee_scolaire=ctx.annee_scolaire,
        eleve__isnull=False,
        eleve__actif=True,
    ).count()
    return _pending(
        'synchroniser_remises_fratrie',
        f'Appliquer les remises fratrie aux {nb} inscrits de la session.',
        perimetre='etablissement',
        nb=nb,
    )


def apply_synchroniser_remises_fratrie(ctx, draft):
    from school_admin.controllers.comptabilite_controller import ComptabiliteController
    from school_admin.model.eleve_model import Eleve
    from school_admin.services.recouvrement import (
        synchroniser_remises_fratrie_eleve,
        synchroniser_remises_fratrie_etablissement,
    )

    if not ctx.annee_scolaire:
        return _err('Aucune session scolaire active.')
    eleve_id = draft.get('eleve_id')
    if eleve_id:
        eleve = Eleve.objects.filter(
            pk=eleve_id,
            etablissement=ctx.etablissement,
        ).select_related('classe').first()
        if not eleve:
            return _err('Élève introuvable.')
        parametres = None
        if eleve.classe_id:
            parametres = ComptabiliteController._get_parametres_for_classe(
                ctx.etablissement, eleve.classe
            )
        if parametres is None:
            return _err('Aucun barème de scolarité pour la classe de cet élève.')
        temoin = synchroniser_remises_fratrie_eleve(
            eleve, ctx.etablissement, ctx.annee_scolaire, parametres
        )
        return _ok(
            f'Remise fratrie recalculée pour {eleve.nom_complet}.',
            eleve=eleve.nom_complet,
            taux=getattr(temoin, 'taux', None),
            url=_reverse('directeur:details_comptabilite_eleve_directeur', args=[eleve.id]),
        )
    nb = synchroniser_remises_fratrie_etablissement(
        ctx.etablissement, ctx.annee_scolaire
    )
    return _ok(
        f'Remises fratrie synchronisées pour {nb} inscrit(s).',
        nb=nb,
        url=_reverse('directeur:liste_comptabilite_eleves_directeur'),
    )


_STR = {'type': 'string'}
_CLASSE = {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION}

register_action(ActionSpec(
    'verifier_statuts_paiement',
    'Relance le recalcul des statuts de paiement (à jour / en retard / impayé) de toutes les fiches de la session.',
    {},
    prepare=prepare_verifier_statuts_paiement,
    apply=apply_verifier_statuts_paiement,
))
register_action(ActionSpec(
    'synchroniser_remises_fratrie',
    'Recalcule les remises fratrie (un élève ou toute la session) à partir du barème déjà paramétré.',
    {
        'query': {'type': 'string', 'description': 'Nom d’un élève (optionnel : sinon toute la session)'},
        'eleve': _STR,
    },
    prepare=prepare_synchroniser_remises_fratrie,
    apply=apply_synchroniser_remises_fratrie,
))


VAGUE2_READ_SCHEMA = [
    {
        'type': 'function',
        'function': {
            'name': 'get_statistiques_pilotage',
            'description': (
                'Tableau de bord vocal : effectifs F/M, classes, professeurs, personnel, '
                'places libres, taux de présence des N derniers jours, taux de recouvrement '
                'de la session, nombre d’impayés et de sanctions. '
                'À utiliser pour « comment va l’établissement », « le tableau de bord ».'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': _CLASSE,
                    'jours': {
                        'type': 'integer',
                        'description': 'Fenêtre de présence (1-90), défaut 7',
                    },
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_taux_reussite',
            'description': (
                'Pourcentage d’élèves au-dessus de la moyenne de passage, '
                'pour une période (active par défaut) et éventuellement une classe. '
                'En supérieur, ajoute le taux de crédits validés s’ils sont déjà calculés. '
                'N’invente jamais de crédits ECTS.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'periode': {'type': 'string', 'description': 'Nom de la période'},
                    'classe': _CLASSE,
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_taux_presence',
            'description': (
                'Taux de présence (présent + retard) sur N jours. '
                'Établissement, une classe, ou un élève nommé.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom d’un élève (optionnel)'},
                    'classe': _CLASSE,
                    'jours': {'type': 'integer', 'description': '1-90, défaut 7'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_comparatif_periodes',
            'description': (
                'Compare les moyennes (et crédits si supérieur) de la période '
                'demandée avec la période précédente.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'periode': {'type': 'string'},
                    'classe': _CLASSE,
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_repartition_cycles',
            'description': (
                'Effectifs par cycle (collège / lycée) dans un établissement '
                'collège+lycée ou mixte uniquement.'
            ),
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_fiche_scolarite',
            'description': (
                'Fiche de scolarité enrichie d’un élève : inscription, mensualités, '
                'annexes, charges ouvertes, dernier reçu, moratoire, parent à relancer.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom, prénom ou matricule'},
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_bilan_scolarite',
            'description': (
                'Totaux dus / payés / reste et taux de recouvrement, '
                'pour l’établissement ou une classe.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {'classe': _CLASSE},
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_impayes',
            'description': (
                'Liste des impayés avec filtres classe, statut '
                '(en_retard, impaye, en_attente) et ancienneté (0-30, 31-60, 61+).'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': _CLASSE,
                    'statut': {
                        'type': 'string',
                        'enum': ['en_retard', 'impaye', 'en_attente'],
                    },
                    'anciennete': {
                        'type': 'string',
                        'enum': ['0-30', '31-60', '61+'],
                        'description': 'Balance âgée applicative',
                    },
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ouvrir_recu',
            'description': (
                'Ouvre un reçu de paiement par numéro (REC-…) ou le dernier reçu d’un élève. '
                'Navigation uniquement, aucune écriture.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'numero': {'type': 'string', 'description': 'Numéro de reçu'},
                    'query': {'type': 'string', 'description': 'Nom de l’élève'},
                    'ouvrir': {'type': 'boolean'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_moratoires',
            'description': (
                'Liste les moratoires de la session, avec échéances. '
                'Avec query : moratoires d’un élève. Pour créer : creer_moratoire.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                    'statut': {
                        'type': 'string',
                        'enum': ['actif', 'solde', 'rompu', 'annule'],
                    },
                },
            },
        },
    },
]

VAGUE2_READ_HANDLERS = {
    'get_statistiques_pilotage': tool_statistiques_pilotage,
    'get_taux_reussite': tool_taux_reussite,
    'get_taux_presence': tool_taux_presence,
    'get_comparatif_periodes': tool_comparatif_periodes,
    'get_repartition_cycles': tool_repartition_cycles,
    'get_fiche_scolarite': tool_fiche_scolarite,
    'get_bilan_scolarite': tool_bilan_scolarite,
    'get_impayes': tool_impayes,
    'ouvrir_recu': tool_ouvrir_recu,
    'get_moratoires': tool_moratoires,
}
