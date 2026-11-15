"""Moteur des rappels planifiés : calcule ce qui est dû, journalise, notifie et pousse."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.utils import timezone

from school_admin.model.rappel_model import NotificationPersonnel, ParametresRappels, RappelEnvoye

logger = logging.getLogger(__name__)

RELANCE_JOURS = 3      # délai entre deux rappels d'une situation sans échéance
RELANCES_MAX = 3       # relances après le premier rappel
FAMILLES = {
    'devoirs': 'Devoirs à rendre',
    'evaluations': 'Évaluations',
    'convocations': 'Convocations',
    'scolarite': 'Scolarité et échéances',
    'inscriptions': 'Inscriptions et accès parents',
    'notes': 'Notes, relevés et bulletins',
    'presences': 'Appels et présences',
    'cahier': 'Cahier de texte',
    'planning': 'Emploi du temps et examens',
}


def proprietaire(user) -> dict:
    return {'content_type': ContentType.objects.get_for_model(user), 'object_id': user.pk}


def parametres(etablissement_id, cache=None):
    """Réglages d'un établissement (créés avec les valeurs par défaut au premier besoin)."""
    if cache is not None and etablissement_id in cache:
        return cache[etablissement_id]
    params = None
    if etablissement_id:
        params = ParametresRappels.objects.filter(etablissement_id=etablissement_id).first()
        if params is None:
            try:
                with transaction.atomic():
                    params = ParametresRappels.objects.create(etablissement_id=etablissement_id)
            except IntegrityError:
                params = ParametresRappels.objects.get(etablissement_id=etablissement_id)
    if cache is not None:
        cache[etablissement_id] = params
    return params


def heures_calmes(params, maintenant=None) -> bool:
    if params is None:
        return False
    heure = timezone.localtime(maintenant or timezone.now()).time()
    debut, fin = params.debut_heures_calmes, params.fin_heures_calmes
    if debut == fin:
        return False
    return (debut <= heure or heure < fin) if debut > fin else (debut <= heure < fin)


def _autorise(item, params) -> bool:
    if params is None:
        return True
    return params.actif and item.get('family') not in (params.familles_desactivees or [])


def _relance_scolarite_recente(item, maintenant) -> bool:
    """La relance de scolarité (WhatsApp/SMS/push) a déjà prévenu la famille : pas de doublon."""
    if item.get('family') != 'scolarite' or not item.get('eleve_id'):
        return False
    from school_admin.model.recouvrement_model import RelanceImpaye
    return RelanceImpaye.objects.filter(
        eleve_id=item['eleve_id'], date_envoi__gte=maintenant - timedelta(days=RELANCE_JOURS)).exists()


def rappels_dus(user, maintenant=None, cache=None) -> list:
    """Couples (carte, seuil) à émettre maintenant pour cette personne. Aucune écriture métier."""
    from school_admin.services.context_popups import candidates

    maintenant = maintenant or timezone.now()
    items = [item for item in candidates(user) if item.get('push')]
    if not items:
        return []
    journal = {}
    for row in RappelEnvoye.objects.filter(**proprietaire(user), key__in=[item['key'] for item in items]):
        journal.setdefault(row.key, []).append(row)
    result = []
    for item in items:
        params = parametres(item.get('etab'), cache)
        if not _autorise(item, params) or heures_calmes(params, maintenant):
            continue
        rows = sorted(journal.get(item['key'], []), key=lambda row: row.created_at, reverse=True)
        if item.get('stage'):
            # Échéance datée : un rappel par seuil franchi.
            stage = item['stage'] if all(row.stage != item['stage'] for row in rows) else None
        elif not rows:
            stage = 'initial'
        elif item.get('once'):
            stage = None  # information ponctuelle : jamais relancée
        else:
            known = {key for row in rows for key in (row.evidence or {})}
            relances = sum(1 for row in rows if row.stage.startswith('relance-'))
            if item.get('evidence') and set(item['evidence']) - known:
                stage = f"nouveau-{item['version'][:12]}"  # de nouveaux dossiers sont arrivés
            elif relances < RELANCES_MAX and maintenant - rows[0].created_at >= timedelta(days=RELANCE_JOURS):
                stage = f'relance-{relances + 1}'
            else:
                stage = None
        if stage and not _relance_scolarite_recente(item, maintenant):
            result.append((item, stage))
    return result


def _notifier(user, item, stage):
    """Crée la notification persistante du rôle ; renvoie son identifiant (ou None)."""
    role = user._meta.model_name
    donnees = {'rappel': item.get('code') or 'RAPPEL', 'key': item['key'], 'stage': stage,
               'url': item['url'], 'redirect_url': item['url']}
    message = ' — '.join(part for part in (item.get('context'), item['text']) if part)
    common = dict(titre=item['title'][:180], message=message, type_notification='information', donnees=donnees)
    if role == 'eleve':
        from school_admin.model.notification_eleve_model import NotificationEleve
        return NotificationEleve.objects.create(eleve=user, **common).pk
    if role == 'parent':
        if not item.get('eleve_id'):
            return None
        from school_admin.model.notification_parent_model import NotificationParent
        return NotificationParent.objects.create(parent=user, eleve_id=item['eleve_id'], **common).pk
    if role == 'professeur':
        from school_admin.model.notification_enseignant_model import NotificationEnseignant
        return NotificationEnseignant.objects.create(enseignant=user, **common).pk
    if role == 'etablissement':
        from school_admin.model.notification_directeur_model import NotificationDirecteur
        return NotificationDirecteur.objects.create(etablissement=user, **common).pk
    if role == 'personneladministratif':
        return NotificationPersonnel.objects.create(personnel=user, **{**common, 'type_notification': 'rappel'}).pk
    return None


def _pousser(user, titre, corps, url, event_key, notification_id=None):
    from school_admin.services.push_delivery import enqueue
    data = {'type': 'rappel', 'url': url, 'redirect_url': url, 'event_key': event_key}
    if notification_id:
        data['_push_notification_ids'] = {str(user.pk): notification_id}
    enqueue([user], titre, corps, data)


def emettre(user, item, stage, silencieux=False) -> bool:
    """Journalise puis notifie ; la contrainte d'unicité garantit un seul rappel par seuil."""
    try:
        with transaction.atomic():
            RappelEnvoye.objects.create(
                **proprietaire(user), etablissement_id=item.get('etab'), key=item['key'], stage=stage,
                code=item.get('code', ''),
                version=item.get('version', ''), evidence=item.get('evidence') or {}, titre=item['title'][:180])
            if silencieux:
                return True
            notification_id = _notifier(user, item, stage)
            corps = ' · '.join(part for part in (item.get('due'), item['text']) if part)
            _pousser(user, item['title'], corps[:400], item['url'], f"rappel:{item['key']}:{stage}", notification_id)
        return True
    except IntegrityError:
        return False  # déjà émis par un autre passage


def traiter(user, maintenant=None, cache=None, dry_run=False) -> list:
    """Émet les rappels dus d'une personne en respectant son plafond quotidien."""
    maintenant = maintenant or timezone.now()
    dus = rappels_dus(user, maintenant, cache)
    if dry_run or not dus:
        return dus
    debut_jour = timezone.localtime(maintenant).replace(hour=0, minute=0, second=0, microsecond=0)
    deja = RappelEnvoye.objects.filter(
        **proprietaire(user), created_at__gte=debut_jour).exclude(key='synthese').count()
    restants = []
    for item, stage in dus:
        params = parametres(item.get('etab'), cache)
        plafond = params.plafond_quotidien if params else 4
        if deja < plafond:
            deja += emettre(user, item, stage)
        else:
            restants.append((item, stage))
    if restants:
        # Au-delà du plafond : un seul message regroupé, une fois par jour.
        emis = [pair for pair in restants if emettre(user, pair[0], pair[1], silencieux=True)]
        jour = timezone.localdate(maintenant).isoformat()
        if emis and not RappelEnvoye.objects.filter(**proprietaire(user), key='synthese', stage=jour).exists():
            n = len(emis)
            pluriel = n > 1
            titre = (f"{n} autres actions vous attendent" if pluriel else "Une autre action vous attend")
            synthese = {'key': 'synthese', 'title': titre,
                        'text': ' · '.join(item['title'] for item, _ in emis[:4]), 'url': emis[0][0]['url'],
                        'code': 'SYNTHESE', 'context': '', 'eleve_id': emis[0][0].get('eleve_id'),
                        'etab': emis[0][0].get('etab')}
            emettre(user, synthese, jour)
    return dus


def destinataires(etablissement, vus_parents=None):
    """Toutes les personnes actives rattachées à un établissement."""
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.lien_familial_model import LienFamilial
    from school_admin.model.parent_model import Parent
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    from school_admin.model.professeur_model import Professeur

    yield etablissement
    yield from PersonnelAdministratif.objects.filter(etablissement=etablissement, actif=True).iterator()
    yield from Professeur.objects.filter(etablissement=etablissement, actif=True).iterator()
    yield from Eleve.objects.filter(etablissement=etablissement, actif=True).select_related('etablissement').iterator()
    ids = set(LienFamilial.objects.filter(
        actif=True, statut='valide', eleve__actif=True,
        eleve__etablissement=etablissement).values_list('parent_id', flat=True))
    if vus_parents is not None:
        ids -= vus_parents
        vus_parents |= ids
    yield from Parent.objects.filter(pk__in=ids, actif=True).iterator()


def generer(etablissement_ids=None, dry_run=False, maintenant=None) -> dict:
    """Passage complet du planificateur. Renvoie un résumé chiffré (et le détail en simulation)."""
    from school_admin.model.etablissement_model import Etablissement

    maintenant = maintenant or timezone.now()
    cache, vus_parents = {}, set()
    stats = {'etablissements': 0, 'personnes': 0, 'rappels': 0, 'erreurs': 0, 'calmes': 0, 'detail': []}
    etablissements = Etablissement.objects.filter(actif=True)
    if etablissement_ids:
        etablissements = etablissements.filter(pk__in=etablissement_ids)
    for etablissement in etablissements.iterator():
        params = parametres(etablissement.pk, cache)
        if not params.actif:
            continue
        if heures_calmes(params, maintenant):
            stats['calmes'] += 1
            continue
        stats['etablissements'] += 1
        for user in destinataires(etablissement, vus_parents):
            stats['personnes'] += 1
            try:
                dus = traiter(user, maintenant, cache, dry_run)
            except Exception:
                stats['erreurs'] += 1
                logger.exception('Rappels indisponibles pour %s #%s', user._meta.model_name, user.pk)
                continue
            stats['rappels'] += len(dus)
            if dry_run:
                stats['detail'].extend(
                    (user._meta.model_name, user.pk, item.get('code'), stage, item['title']) for item, stage in dus)
        if not dry_run:
            ParametresRappels.objects.filter(pk=params.pk).update(dernier_passage=maintenant)
    return stats
