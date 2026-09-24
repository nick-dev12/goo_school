"""
Actions confirmées assistant parent (Par7) — brouillon puis apply après oui explicite.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from school_admin.services.assistant_actions import (
    ActionSpec,
    _incomplete,
    _ok,
    _pending,
    default_choices,
)

logger = logging.getLogger(__name__)

PARENT_ACTION_SPECS: dict[str, ActionSpec] = {}

PARENT_CONFIRM_CHOICES = [
    {'label': 'Oui, c’est bon', 'value': 'Oui, c’est bon.', 'intent': 'confirm'},
    {'label': 'Modifier', 'value': 'Je veux modifier les informations.', 'intent': 'chat'},
    {'label': 'Annuler', 'value': 'Annuler.', 'intent': 'cancel'},
]

PARENT_VOCAL_BLOCKED = frozenset({
    'enregistrer_paiement',
    'change_password',
    'modifier_mot_de_passe',
    'changer_mot_de_passe',
})


def register_parent_action(spec: ActionSpec):
    PARENT_ACTION_SPECS[spec.name] = spec
    return spec


def get_parent_action(name):
    return PARENT_ACTION_SPECS.get(name)


def is_parent_write_action(name):
    return name in PARENT_ACTION_SPECS


def choices_for_parent_action(name, draft):
    if (draft or {}).get('statut') == 'en_attente_confirmation':
        return list(PARENT_CONFIRM_CHOICES)
    return default_choices(draft)


def _reverse(route, args=None):
    try:
        return reverse(route, args=args or [])
    except NoReverseMatch:
        return None


def _notifications_parent_qs(ctx):
    from school_admin.model.notification_parent_model import NotificationParent

    parent = getattr(ctx, 'parent', None)
    if not parent:
        return NotificationParent.objects.none()
    qs = NotificationParent.objects.filter(parent=parent)
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    return qs


def prepare_marquer_notification_lue(ctx, args):
    parent = getattr(ctx, 'parent', None)
    if not parent:
        return {'erreur': 'Compte parent requis.'}

    qs = _notifications_parent_qs(ctx).filter(lu=False)
    notif_id = args.get('notification_id') or args.get('id')
    if notif_id:
        qs = qs.filter(pk=notif_id)
        if not qs.exists():
            return {'erreur': 'Notification introuvable, déjà lue ou hors de votre compte.'}
        notif = qs.first()
        titre = (notif.titre or 'Notification')[:80]
        resume = f'marque comme lue la notification « {titre} »'
        draft_ids = [notif.id]
    else:
        count = qs.count()
        if count == 0:
            return {'erreur': 'Aucune notification parent non lue.'}
        if count == 1:
            notif = qs.first()
            titre = (notif.titre or 'Notification')[:80]
            resume = f'marque comme lue la notification « {titre} »'
        else:
            resume = f'marque {count} notification(s) parent comme lues'
        draft_ids = list(qs.values_list('id', flat=True)[:50])

    return _pending(
        'marquer_notification_lue',
        resume,
        notification_ids=draft_ids,
        manquants=[],
        url=_reverse('school_admin:notifications_parent'),
    )


def apply_marquer_notification_lue(ctx, draft):
    parent = getattr(ctx, 'parent', None)
    if not parent:
        return {'erreur': 'Compte parent requis.'}

    ids = draft.get('notification_ids') or []
    if not ids:
        return {'erreur': 'Aucune notification à marquer.'}

    qs = _notifications_parent_qs(ctx).filter(pk__in=ids, lu=False)
    updated = 0
    for notif in qs:
        notif.marquer_comme_lue()
        updated += 1
    if updated == 0:
        return {'erreur': 'Notification déjà lue ou introuvable.'}

    url = draft.get('url') or _reverse('school_admin:notifications_parent')
    return _ok(
        f'{updated} notification(s) marquée(s) comme lue(s).',
        url=url,
    )


def _tentatives_echec_matricule(matricule_eleve):
    from school_admin.model.demande_liaison_model import DemandeLiaisonParent

    return DemandeLiaisonParent.objects.filter(
        matricule_eleve=matricule_eleve,
        statut__in=['echec', 'bloquee'],
    ).count()


def _enregistrer_echec_liaison(parent, eleve, matricule_eleve, annee_scolaire):
    from school_admin.model.demande_liaison_model import DemandeLiaisonParent

    tentatives_echec = _tentatives_echec_matricule(matricule_eleve)
    nouvelle_tentative = tentatives_echec + 1
    demande = DemandeLiaisonParent.objects.create(
        parent_demandeur=parent,
        matricule_eleve=matricule_eleve,
        nom_eleve=eleve.nom,
        prenom_eleve=eleve.prenom,
        date_naissance_eleve=eleve.date_naissance,
        type_lien='tuteur',
        statut='echec',
        nombre_tentatives=1,
        raison_echec='Mot de passe incorrect',
        eleve_valide=eleve,
        annee_scolaire=annee_scolaire,
    )
    if nouvelle_tentative >= 5:
        demande.statut = 'bloquee'
        demande.save(update_fields=['statut'])
        return (
            'Mot de passe incorrect. Après 5 tentatives pour ce matricule, '
            'la liaison est bloquée. Contactez l’établissement.'
        )
    restantes = 5 - nouvelle_tentative
    suffix = 's' if restantes > 1 else ''
    return (
        f'Mot de passe incorrect. Il reste {restantes} tentative{suffix} '
        f'avant le blocage de ce matricule.'
    )


def prepare_demande_liaison_enfant(ctx, args):
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.lien_familial_model import LienFamilial

    parent = getattr(ctx, 'parent', None)
    if not parent:
        return {'erreur': 'Compte parent requis.'}

    matricule_eleve = (args.get('matricule_eleve') or args.get('matricule') or '').strip()
    mot_de_passe = (args.get('mot_de_passe_eleve') or args.get('mot_de_passe') or '').strip()
    if not matricule_eleve:
        return _incomplete(
            'demande_liaison_enfant',
            ['matricule_eleve'],
            'Quel est le matricule de l’enfant à lier ?',
        )
    if not mot_de_passe:
        return _incomplete(
            'demande_liaison_enfant',
            ['mot_de_passe_eleve'],
            'Quel est le mot de passe élève pour confirmer la liaison ?',
        )

    eleve = Eleve.objects.filter(matricule_eleve=matricule_eleve, actif=True).first()
    if not eleve:
        return {'erreur': 'Matricule incorrect. Cet élève n’est inscrit dans aucun établissement.'}

    if LienFamilial.objects.filter(parent=parent, eleve=eleve, actif=True).exists():
        return {
            'erreur': f'Vous êtes déjà lié à {eleve.nom_complet}.',
            'statut': 'deja_lie',
        }

    if _tentatives_echec_matricule(matricule_eleve) >= 5:
        return {
            'erreur': (
                'Ce matricule est bloqué après 5 tentatives infructueuses. '
                'Contactez l’établissement pour débloquer la liaison.'
            ),
            'statut': 'bloque',
        }

    if not eleve.check_password(mot_de_passe):
        annee = ctx.annee_scolaire
        if not annee and eleve.etablissement_id:
            from school_admin.model.annee_scolaire_model import AnneeScolaire

            annee = AnneeScolaire.get_session_active(eleve.etablissement)
        msg = _enregistrer_echec_liaison(parent, eleve, matricule_eleve, annee)
        return {'erreur': msg, 'statut': 'echec'}

    type_lien = (args.get('type_lien') or 'tuteur').strip() or 'tuteur'
    resume = f'lie {eleve.prenom} {eleve.nom} (matricule {matricule_eleve}) à votre compte'
    return _pending(
        'demande_liaison_enfant',
        resume,
        eleve_id=eleve.id,
        matricule_eleve=matricule_eleve,
        mot_de_passe_eleve=mot_de_passe,
        type_lien=type_lien,
        nom_enfant=eleve.nom_complet,
        manquants=[],
        url=_reverse('school_admin:dashboard_parent'),
    )


@transaction.atomic
def apply_demande_liaison_enfant(ctx, draft):
    from school_admin.model.demande_liaison_model import DemandeLiaisonParent
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.lien_familial_model import LienFamilial

    parent = getattr(ctx, 'parent', None)
    if not parent:
        return {'erreur': 'Compte parent requis.'}

    eleve_id = draft.get('eleve_id')
    matricule = (draft.get('matricule_eleve') or '').strip()
    mot_de_passe = (draft.get('mot_de_passe_eleve') or '').strip()
    if not eleve_id or not matricule or not mot_de_passe:
        return {'erreur': 'Informations de liaison incomplètes.'}

    eleve = Eleve.objects.filter(pk=eleve_id, actif=True, matricule_eleve=matricule).first()
    if not eleve:
        return {'erreur': 'Élève introuvable pour cette demande.'}

    if LienFamilial.objects.filter(parent=parent, eleve=eleve, actif=True).exists():
        return _ok(f'Vous êtes déjà lié à {eleve.nom_complet}.')

    if _tentatives_echec_matricule(matricule) >= 5:
        return {
            'erreur': 'Ce matricule est bloqué. Contactez l’établissement.',
            'statut': 'bloque',
        }

    if not eleve.check_password(mot_de_passe):
        annee = ctx.annee_scolaire
        if not annee and eleve.etablissement_id:
            from school_admin.model.annee_scolaire_model import AnneeScolaire

            annee = AnneeScolaire.get_session_active(eleve.etablissement)
        msg = _enregistrer_echec_liaison(parent, eleve, matricule, annee)
        return {'erreur': msg}

    type_lien = (draft.get('type_lien') or 'tuteur').strip() or 'tuteur'
    lien = LienFamilial.objects.create(
        parent=parent,
        eleve=eleve,
        type_lien=type_lien,
        statut='valide',
        est_inscripteur=False,
    )
    lien.valider()

    annee = ctx.annee_scolaire
    if not annee and eleve.etablissement_id:
        from school_admin.model.annee_scolaire_model import AnneeScolaire

        annee = AnneeScolaire.get_session_active(eleve.etablissement)

    DemandeLiaisonParent.objects.create(
        parent_demandeur=parent,
        matricule_eleve=matricule,
        nom_eleve=eleve.nom,
        prenom_eleve=eleve.prenom,
        date_naissance_eleve=eleve.date_naissance,
        type_lien=type_lien,
        statut='reussie',
        nombre_tentatives=1,
        eleve_valide=eleve,
        annee_scolaire=annee,
    )

    url = draft.get('url') or _reverse('school_admin:dashboard_parent')
    return _ok(
        f'Votre enfant {eleve.nom_complet} a été lié avec succès à votre espace.',
        url=url,
        eleve_id=eleve.id,
    )


def build_parent_action_schemas():
    schemas = []
    for spec in PARENT_ACTION_SPECS.values():
        extra = ' Confirmation obligatoire avant toute écriture.'
        schemas.append({
            'type': 'function',
            'function': {
                'name': spec.name,
                'description': spec.description + extra,
                'parameters': {
                    'type': 'object',
                    'properties': spec.properties,
                    'required': list(spec.required),
                },
            },
        })
    return schemas


register_parent_action(
    ActionSpec(
        name='marquer_notification_lue',
        description=(
            'Marque une notification parent (hub) comme lue. '
            'Aligné sur la page notifications parent — pas les tools directeur.'
        ),
        properties={
            'notification_id': {'type': 'integer', 'description': 'ID notification parent'},
            'id': {'type': 'integer'},
        },
        required=(),
        prepare=prepare_marquer_notification_lue,
        apply=apply_marquer_notification_lue,
    )
)

register_parent_action(
    ActionSpec(
        name='demande_liaison_enfant',
        description=(
            'Demande de liaison avec un enfant via matricule et mot de passe élève. '
            'Mêmes contrôles que le formulaire dashboard parent (limite 5 tentatives / matricule).'
        ),
        properties={
            'matricule_eleve': {'type': 'string'},
            'matricule': {'type': 'string'},
            'mot_de_passe_eleve': {'type': 'string'},
            'mot_de_passe': {'type': 'string'},
            'type_lien': {'type': 'string', 'description': 'Optionnel, défaut tuteur'},
        },
        required=(),
        prepare=prepare_demande_liaison_enfant,
        apply=apply_demande_liaison_enfant,
    )
)
