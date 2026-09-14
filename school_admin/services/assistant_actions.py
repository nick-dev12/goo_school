"""
Actions mutantes de l'assistant directeur — comptabilité / frais annexes.

Les outils d'écriture préparent un brouillon (`en_attente_confirmation`).
L'écriture réelle n'a lieu qu'après confirmation explicite du directeur.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.urls import reverse

from school_admin.utils.frais_annexes import (
    extraire_frais_annexes_depuis_args,
    frais_annexes_actifs,
    get_frais_annexes_from_parametres,
    serialiser_frais_annexes_pour_stockage,
)

logger = logging.getLogger(__name__)

COMPTA_MUTATION_TOOLS = frozenset({
    'creer_parametres_comptabilite',
    'modifier_parametres_comptabilite',
    'supprimer_parametres_comptabilite',
    'enregistrer_paiement',
})


def _decimal(value, default='0'):
    if value is None or value == '':
        return Decimal(default)
    try:
        return Decimal(str(value).replace(',', '.').replace(' ', ''))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _serialize_parametre(parametre):
    actifs = frais_annexes_actifs(getattr(parametre, 'frais_annexes', None))
    return {
        'id': parametre.id,
        'nom': parametre.nom,
        'groupes_classes': list(parametre.groupes_classes or []),
        'montant_frais_inscription': str(parametre.montant_frais_inscription or 0),
        'montant_frais_reinscription': str(parametre.montant_frais_reinscription or 0),
        'montant_mensualite': str(parametre.montant_mensualite or 0),
        'montant_facturation_annuelle': str(parametre.montant_facturation_annuelle or 0),
        'type_facturation': parametre.type_facturation,
        'autoriser_paiements_partiels': parametre.autoriser_paiements_partiels,
        'frais_annexes': [
            {
                'code': item['code'],
                'libelle': item['libelle'],
                'montant': item['montant'],
                'actif': item['actif'],
                'periodicite': item['periodicite'],
                'periodicite_display': item['periodicite_display'],
            }
            for item in actifs
        ],
        'frais_annexes_catalogue': get_frais_annexes_from_parametres(parametre),
    }


def tool_get_parametres_comptabilite(ctx, args):
    from school_admin.model.parametres_comptabilite_groupe_classe_model import (
        ParametresComptabiliteGroupeClasse,
    )
    from school_admin.model.parametres_comptabilite_model import ParametresComptabilite

    args = args if isinstance(args, dict) else {}
    query = (args.get('query') or args.get('groupe') or args.get('nom') or '').strip()
    groupes = ParametresComptabiliteGroupeClasse.objects.filter(
        etablissement=ctx.etablissement
    ).order_by('nom')
    if query:
        lowered = query.lower()
        filtered = []
        for parametre in groupes:
            hay = ' '.join([parametre.nom] + list(parametre.groupes_classes or [])).lower()
            if lowered in hay:
                filtered.append(parametre)
        groupes = filtered
    items = [_serialize_parametre(parametre) for parametre in groupes]
    general = ParametresComptabilite.objects.filter(etablissement=ctx.etablissement).first()
    return {
        'parametres_groupes': items,
        'parametres_generaux': _serialize_parametre(general) if general else None,
        'url': reverse('directeur:parametres_comptabilite_directeur'),
    }


def _find_parametre(ctx, args):
    from school_admin.model.parametres_comptabilite_groupe_classe_model import (
        ParametresComptabiliteGroupeClasse,
    )

    parametre_id = args.get('parametre_id') or args.get('id')
    if parametre_id:
        return ParametresComptabiliteGroupeClasse.objects.filter(
            pk=parametre_id,
            etablissement=ctx.etablissement,
        ).first()
    query = (args.get('query') or args.get('nom') or args.get('groupe') or '').strip()
    qs = ParametresComptabiliteGroupeClasse.objects.filter(etablissement=ctx.etablissement)
    if not query:
        return qs.first() if qs.count() == 1 else None
    lowered = query.lower()
    matches = [
        parametre
        for parametre in qs
        if lowered in ' '.join([parametre.nom] + list(parametre.groupes_classes or [])).lower()
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _parametre_fields_from_args(args, existing=None):
    data = {}
    mapping = {
        'nom': 'nom',
        'type_facturation': 'type_facturation',
        'montant_frais_inscription': 'montant_frais_inscription',
        'montant_frais_reinscription': 'montant_frais_reinscription',
        'montant_mensualite': 'montant_mensualite',
        'montant_facturation_annuelle': 'montant_facturation_annuelle',
        'delai_tolerance_retard': 'delai_tolerance_retard',
        'nombre_max_paiements_partiels': 'nombre_max_paiements_partiels',
        'jour_versement': 'jour_versement',
        'mois_debut_facturation': 'mois_debut_facturation',
        'mois_fin_facturation': 'mois_fin_facturation',
    }
    for src, dest in mapping.items():
        if args.get(src) is not None:
            data[dest] = args[src]
    if args.get('groupes_classes') is not None:
        groupes = args.get('groupes_classes')
        if isinstance(groupes, str):
            groupes = [part.strip() for part in groupes.split(',') if part.strip()]
        data['groupes_classes'] = list(groupes or [])
    existants = getattr(existing, 'frais_annexes', None) if existing is not None else None
    if args.get('frais_annexes') is not None:
        data['frais_annexes'] = extraire_frais_annexes_depuis_args(args, existants)
    elif existing is not None:
        data['frais_annexes'] = serialiser_frais_annexes_pour_stockage(
            get_frais_annexes_from_parametres(existing)
        )
    return data


def tool_creer_parametres_comptabilite(ctx, args):
    args = args if isinstance(args, dict) else {}
    draft = _parametre_fields_from_args(args)
    if not (draft.get('nom') or '').strip():
        return {'erreur': 'Le nom du jeu de paramètres est obligatoire.'}
    if not draft.get('groupes_classes'):
        return {'erreur': 'Indique au moins un groupe de classes (ex. 6e, 5e, CE1).'}
    return {
        'statut': 'en_attente_confirmation',
        'action': 'creer_parametres_comptabilite',
        'draft': draft,
        'message': (
            f"Je vais créer les paramètres « {draft['nom']} » pour "
            f"{', '.join(draft['groupes_classes'])}, y compris les frais annexes. "
            "Confirme pour enregistrer."
        ),
    }


def tool_modifier_parametres_comptabilite(ctx, args):
    args = args if isinstance(args, dict) else {}
    parametre = _find_parametre(ctx, args)
    if parametre is None:
        return {'erreur': 'Aucun jeu de paramètres correspondant. Précise le nom ou le groupe.'}
    draft = _parametre_fields_from_args(args, parametre)
    draft['parametre_id'] = parametre.id
    draft.setdefault('nom', parametre.nom)
    return {
        'statut': 'en_attente_confirmation',
        'action': 'modifier_parametres_comptabilite',
        'draft': draft,
        'actuel': _serialize_parametre(parametre),
        'message': (
            f"Je vais modifier « {parametre.nom} » (frais annexes compris). "
            "Confirme pour appliquer."
        ),
    }


def tool_supprimer_parametres_comptabilite(ctx, args):
    args = args if isinstance(args, dict) else {}
    parametre = _find_parametre(ctx, args)
    if parametre is None:
        return {'erreur': 'Aucun jeu de paramètres à supprimer.'}
    return {
        'statut': 'en_attente_confirmation',
        'action': 'supprimer_parametres_comptabilite',
        'draft': {'parametre_id': parametre.id, 'nom': parametre.nom},
        'message': f"Je vais supprimer les paramètres « {parametre.nom} ». Confirme pour continuer.",
    }


def _find_eleve_paiement(ctx, query):
    from school_admin.services.assistant_tools import _find_eleve

    return _find_eleve(ctx, query)


def tool_enregistrer_paiement(ctx, args):
    from school_admin.model.comptabilite_eleve_model import (
        FraisAnnexe,
        FraisInscription,
        Mensualite,
    )
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    args = args if isinstance(args, dict) else {}
    eleve = _find_eleve_paiement(ctx, args.get('eleve') or args.get('query'))
    if eleve is None:
        return {'erreur': f'Aucun {ctx.libelle_eleve} trouvé pour enregistrer un paiement.'}
    montant = _decimal(args.get('montant'))
    if montant is None or montant <= 0:
        return {'erreur': 'Le montant du paiement est obligatoire et doit être positif.'}

    type_paiement = (args.get('type_paiement') or args.get('type') or '').strip()
    aliases = {
        'inscription': 'frais_inscription',
        'frais_inscription': 'frais_inscription',
        'mensualite': 'mensualite',
        'mensualité': 'mensualite',
        'annexe': 'frais_annexe',
        'frais_annexe': 'frais_annexe',
        'tenue': 'frais_annexe',
        'carte': 'frais_annexe',
        'assurance': 'frais_annexe',
    }
    type_paiement = aliases.get(type_paiement.lower(), type_paiement or 'frais_annexe')
    if type_paiement not in {'frais_inscription', 'mensualite', 'frais_annexe'}:
        type_paiement = 'frais_annexe'

    cible = {
        'eleve_id': eleve.id,
        'eleve': eleve.nom_complet,
        'type_paiement': type_paiement,
        'montant': str(montant),
        'mode_paiement': args.get('mode_paiement') or 'especes',
    }

    if type_paiement == 'frais_inscription':
        frais = FraisInscription.objects.filter(
            eleve=eleve,
            etablissement=ctx.etablissement,
            annee_scolaire=ctx.annee_scolaire,
        ).first()
        if not frais:
            return {'erreur': "Aucun frais d'inscription à payer pour cet élève."}
        cible['frais_inscription_id'] = frais.id
        cible['libelle'] = frais.get_type_frais_display()
        cible['reste'] = str(frais.get_reste_a_payer())
    elif type_paiement == 'mensualite':
        periode = (args.get('periode') or args.get('mois') or '').strip()
        qs = Mensualite.objects.filter(
            eleve=eleve,
            etablissement=ctx.etablissement,
            annee_scolaire=ctx.annee_scolaire,
        )
        mensualite = None
        if periode:
            mensualite = qs.filter(periode__icontains=periode).first()
        if mensualite is None:
            mensualite = qs.exclude(statut='paye').order_by('annee', 'mois').first()
        if mensualite is None:
            return {'erreur': 'Aucune mensualité à payer pour cet élève.'}
        cible['mensualite_id'] = mensualite.id
        cible['libelle'] = mensualite.periode
        cible['reste'] = str(mensualite.get_reste_a_payer())
    else:
        code = (args.get('frais_annexe_code') or args.get('code') or args.get('frais') or '').strip()
        qs = FraisAnnexe.objects.filter(
            eleve=eleve,
            etablissement=ctx.etablissement,
            annee_scolaire=ctx.annee_scolaire,
        )
        frais = None
        if args.get('frais_annexe_id'):
            frais = qs.filter(pk=args['frais_annexe_id']).first()
        if frais is None and code:
            lowered = code.lower()
            frais = qs.filter(code__iexact=lowered).first() or qs.filter(libelle__icontains=code).first()
        if frais is None:
            frais = qs.exclude(statut='paye').order_by('libelle').first()
        if frais is None:
            inscription = InscriptionEleve.objects.filter(
                eleve=eleve,
                etablissement=ctx.etablissement,
                annee_scolaire=ctx.annee_scolaire,
            ).first()
            return {
                'erreur': (
                    "Aucun frais annexe à payer. Configure-les d'abord dans les paramètres "
                    f"de scolarité{' de ' + inscription.classe.nom if inscription and inscription.classe else ''}."
                ),
            }
        cible['frais_annexe_id'] = frais.id
        cible['frais_annexe_code'] = frais.code
        cible['libelle'] = frais.libelle
        cible['reste'] = str(frais.get_reste_a_payer())

    return {
        'statut': 'en_attente_confirmation',
        'action': 'enregistrer_paiement',
        'draft': cible,
        'message': (
            f"Je vais enregistrer {cible['montant']} sur {cible.get('libelle', 'cette échéance')} "
            f"pour {eleve.nom_complet}. Confirme pour valider."
        ),
        'url': reverse('directeur:details_comptabilite_eleve_directeur', args=[eleve.id]),
    }


def apply_creer_parametres(ctx, draft):
    from school_admin.controllers.comptabilite_controller import ComptabiliteController
    from school_admin.model.parametres_comptabilite_groupe_classe_model import (
        ParametresComptabiliteGroupeClasse,
    )

    nom = (draft.get('nom') or '').strip()
    groupes = draft.get('groupes_classes') or []
    if not nom or not groupes:
        return {'erreur': 'Nom et groupes de classes sont obligatoires.'}

    deja = ParametresComptabiliteGroupeClasse.get_groupes_deja_assignes(ctx.etablissement)
    conflits = set(groupes) & set(deja)
    if conflits:
        return {'erreur': f"Groupes déjà assignés : {', '.join(sorted(conflits))}."}

    parametre = ParametresComptabiliteGroupeClasse.objects.create(
        etablissement=ctx.etablissement,
        nom=nom,
        groupes_classes=groupes,
        montant_frais_inscription=_decimal(draft.get('montant_frais_inscription'), '0') or Decimal('0'),
        montant_frais_reinscription=_decimal(draft.get('montant_frais_reinscription'), '0') or Decimal('0'),
        montant_mensualite=_decimal(draft.get('montant_mensualite'), '0') or Decimal('0'),
        montant_facturation_annuelle=_decimal(draft.get('montant_facturation_annuelle'), '0') or Decimal('0'),
        type_facturation=draft.get('type_facturation') or 'mensuel',
        frais_annexes=draft.get('frais_annexes') or [],
        modifie_par=ctx.personnel,
    )
    parametre.mettre_a_jour_systeme_comptabilite()
    ComptabiliteController._emit_parametres_live(ctx.etablissement, parametre, action='created')
    return {
        'ok': True,
        'parametre_id': parametre.id,
        'message': f"Paramètres « {parametre.nom} » créés, échéances mises à jour.",
        'url': reverse('directeur:parametres_comptabilite_directeur'),
    }


def apply_modifier_parametres(ctx, draft):
    from school_admin.controllers.comptabilite_controller import ComptabiliteController
    from school_admin.model.parametres_comptabilite_groupe_classe_model import (
        ParametresComptabiliteGroupeClasse,
    )

    parametre = ParametresComptabiliteGroupeClasse.objects.filter(
        pk=draft.get('parametre_id'),
        etablissement=ctx.etablissement,
    ).first()
    if parametre is None:
        return {'erreur': 'Paramètre introuvable.'}

    if draft.get('nom'):
        parametre.nom = draft['nom']
    if draft.get('groupes_classes') is not None:
        deja = ParametresComptabiliteGroupeClasse.get_groupes_deja_assignes(
            ctx.etablissement, exclude_pk=parametre.pk
        )
        conflits = set(draft['groupes_classes']) & set(deja)
        if conflits:
            return {'erreur': f"Groupes déjà assignés : {', '.join(sorted(conflits))}."}
        parametre.groupes_classes = draft['groupes_classes']
    for field in (
        'montant_frais_inscription',
        'montant_frais_reinscription',
        'montant_mensualite',
        'montant_facturation_annuelle',
    ):
        if draft.get(field) is not None:
            value = _decimal(draft[field], '0')
            if value is not None:
                setattr(parametre, field, value)
    if draft.get('type_facturation'):
        parametre.type_facturation = draft['type_facturation']
    if draft.get('frais_annexes') is not None:
        parametre.frais_annexes = draft['frais_annexes']
    parametre.modifie_par = ctx.personnel
    parametre.save()
    parametre.mettre_a_jour_systeme_comptabilite()
    ComptabiliteController._emit_parametres_live(ctx.etablissement, parametre, action='updated')
    return {
        'ok': True,
        'parametre_id': parametre.id,
        'message': f"Paramètres « {parametre.nom} » mis à jour.",
        'url': reverse('directeur:parametres_comptabilite_directeur'),
    }


def apply_supprimer_parametres(ctx, draft):
    from school_admin.controllers.comptabilite_controller import ComptabiliteController
    from school_admin.model.parametres_comptabilite_groupe_classe_model import (
        ParametresComptabiliteGroupeClasse,
    )

    parametre = ParametresComptabiliteGroupeClasse.objects.filter(
        pk=draft.get('parametre_id'),
        etablissement=ctx.etablissement,
    ).first()
    if parametre is None:
        return {'erreur': 'Paramètre introuvable.'}
    nom = parametre.nom
    parametre_id = parametre.id
    parametre.delete()
    ComptabiliteController._emit_parametres_live(
        ctx.etablissement, None, action='deleted', parametre_id=parametre_id
    )
    return {
        'ok': True,
        'message': f"Paramètres « {nom} » supprimés.",
        'url': reverse('directeur:parametres_comptabilite_directeur'),
    }


def apply_enregistrer_paiement(ctx, draft):
    from school_admin.model.compte_user import CompteUser
    from school_admin.model.comptabilite_eleve_model import (
        ComptabiliteEleve,
        FraisAnnexe,
        FraisInscription,
        Mensualite,
        PaiementEleve,
    )
    from school_admin.model.eleve_model import Eleve
    from school_admin.services.live_serializers import (
        serialize_comptabilite_eleve_snapshot,
        serialize_comptabilite_paiement_result,
    )
    from school_admin.services.realtime_helpers import emit_live

    eleve = Eleve.objects.filter(pk=draft.get('eleve_id'), etablissement=ctx.etablissement).first()
    if eleve is None:
        return {'erreur': 'Élève introuvable.'}
    montant = _decimal(draft.get('montant'))
    if montant is None or montant <= 0:
        return {'erreur': 'Montant invalide.'}

    type_paiement = draft.get('type_paiement')
    cible = None
    if type_paiement == 'frais_inscription':
        cible = FraisInscription.objects.filter(
            pk=draft.get('frais_inscription_id'),
            eleve=eleve,
            etablissement=ctx.etablissement,
        ).first()
    elif type_paiement == 'mensualite':
        cible = Mensualite.objects.filter(
            pk=draft.get('mensualite_id'),
            eleve=eleve,
            etablissement=ctx.etablissement,
        ).first()
    else:
        cible = FraisAnnexe.objects.filter(
            pk=draft.get('frais_annexe_id'),
            eleve=eleve,
            etablissement=ctx.etablissement,
        ).first()
        type_paiement = 'frais_annexe'

    if cible is None:
        return {'erreur': 'Échéance introuvable.'}

    reste = cible.get_reste_a_payer()
    if montant > reste:
        return {'erreur': f'Le montant ({montant}) dépasse le reste à payer ({reste}).'}

    cible.ajouter_paiement(montant)
    enregistre_par = ctx.personnel if isinstance(getattr(ctx, 'personnel', None), CompteUser) else None
    paiement_kwargs = {
        'eleve': eleve,
        'etablissement': ctx.etablissement,
        'annee_scolaire': ctx.annee_scolaire,
        'type_paiement': type_paiement,
        'montant': montant,
        'mode_paiement': draft.get('mode_paiement') or 'especes',
        'enregistre_par': enregistre_par,
    }
    if type_paiement == 'frais_inscription':
        paiement_kwargs['frais_inscription'] = cible
    elif type_paiement == 'mensualite':
        paiement_kwargs['mensualite'] = cible
    else:
        paiement_kwargs['frais_annexe'] = cible
    PaiementEleve.objects.create(**paiement_kwargs)

    comptabilite = ComptabiliteEleve.objects.filter(
        eleve=eleve,
        etablissement=ctx.etablissement,
        annee_scolaire=ctx.annee_scolaire,
    ).first()
    if comptabilite:
        comptabilite.verifier_statut_paiement()

    snapshot = serialize_comptabilite_eleve_snapshot(
        eleve.id, ctx.etablissement, ctx.annee_scolaire
    )
    message = f"Paiement de {montant} enregistré pour {eleve.nom_complet}."
    live_item = serialize_comptabilite_paiement_result(eleve.id, message, snapshot=snapshot)
    emit_live(
        ctx.etablissement.id,
        'comptabilite.mise_a_jour',
        {'event': 'comptabilite.mise_a_jour', 'item': live_item},
    )
    return {
        'ok': True,
        'message': message,
        'reste': str(cible.get_reste_a_payer()),
        'url': reverse('directeur:details_comptabilite_eleve_directeur', args=[eleve.id]),
    }


def apply_pending_comptabilite(ctx, name, draft):
    draft = draft if isinstance(draft, dict) else {}
    if name == 'creer_parametres_comptabilite':
        return apply_creer_parametres(ctx, draft)
    if name == 'modifier_parametres_comptabilite':
        return apply_modifier_parametres(ctx, draft)
    if name == 'supprimer_parametres_comptabilite':
        return apply_supprimer_parametres(ctx, draft)
    if name == 'enregistrer_paiement':
        return apply_enregistrer_paiement(ctx, draft)
    return {'erreur': f'Action inconnue : {name}'}
