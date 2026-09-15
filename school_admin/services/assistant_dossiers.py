"""
Actions assistant pour les fiches longues du directeur :
dossier élève, réinscription, moratoire, moyennes, affectations, etc.
Les champs manquants sont demandés un par un (statut incomplet), jamais via un formulaire.
"""
from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from django.db import transaction
from django.db.models import Q

from school_admin.services.assistant_actions import (
    ActionSpec,
    _emit,
    _err,
    _find_classe,
    _find_eleve,
    _incomplete,
    _ok,
    _parse_date,
    _parse_money,
    _pending,
    _reverse,
    register_action,
)
from school_admin.services.assistant_staff import (
    _find_matiere,
    _find_personnel,
    _find_professeur,
    _normalize_fonction,
)

_STR = {'type': 'string'}
_ELEVE_FIELDS = (
    'nom', 'prenom', 'classe', 'adresse', 'telephone', 'email',
    'date_naissance', 'lieu_naissance', 'sexe', 'nationalite',
    'parent_nom', 'parent_prenom', 'parent_telephone', 'parent_lien',
    'parent_email', 'parent_adresse', 'parent_profession',
)
_PROF_FIELDS = (
    'nom', 'prenom', 'telephone', 'email', 'sexe', 'matiere', 'prix_horaire',
)
_PERS_FIELDS = ('nom', 'prenom', 'telephone', 'email', 'sexe', 'fonction')


def _first(*values):
    for value in values:
        if value is not None and str(value).strip():
            return value
    return None


def _parse_champs_libres(args):
    """Interprète une dictée libre (« téléphone 690… et adresse 12 rue X »)."""
    raw = (args.get('champs') or args.get('modifications') or '').strip()
    if not raw:
        return args
    merged = dict(args)
    compact = re.sub(r'\s+', '', raw)
    tel = re.search(
        r'(?:t[ée]l[ée]phone|tel)\s*(?:est|:)?\s*([0-9+\s.\-]{6,})',
        raw,
        re.I,
    )
    if tel:
        merged.setdefault('telephone', re.sub(r'\s+', '', tel.group(1)))
    elif re.fullmatch(r'[+\d][\d.\-]{7,15}', compact):
        merged.setdefault('telephone', compact)
    mail = re.search(r'[\w.+-]+@[\w.-]+\.\w+', raw)
    if mail:
        merged.setdefault('email', mail.group(0))
    parent_tel = re.search(
        r'(?:parent|tuteur|p[eè]re|m[eè]re).{0,20}(?:t[ée]l[ée]phone|tel)\s*(?:est|:)?\s*([0-9+\s.\-]{6,})',
        raw,
        re.I,
    )
    if parent_tel:
        merged.setdefault('parent_telephone', re.sub(r'\s+', '', parent_tel.group(1)))
    parent_nom = re.search(
        r'(?:parent|tuteur).{0,12}(?:nom)\s*(?:est|:)?\s*([A-Za-zÀ-ÿ\'\- ]{2,40})',
        raw,
        re.I,
    )
    if parent_nom:
        merged.setdefault('parent_nom', parent_nom.group(1).strip().rstrip('.!?'))
    classe = re.search(
        r'(?:classe|en)\s+([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 \-]{1,40})',
        raw,
        re.I,
    )
    if classe:
        merged.setdefault('classe', classe.group(1).strip().rstrip('.!?'))
    adresse = re.search(
        r'(?:adresse|habite|demeur)\s*(?:est|:|à|au)?\s*(.+?)(?:\.|et\s+|$)',
        raw,
        re.I,
    )
    if adresse:
        merged.setdefault('adresse', adresse.group(1).strip())
    naissance = re.search(
        r'(?:n[ée]e?|naissance)\s+(?:le\s+)?(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}-\d{2}-\d{2})',
        raw,
        re.I,
    )
    if naissance:
        merged.setdefault('date_naissance', naissance.group(1))
    elif re.fullmatch(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}', compact):
        merged.setdefault('date_naissance', raw.strip())
    sexe = re.search(r'\b(masculin|f[ée]minin|gar[cç]on|fille|homme|femme)\b', raw, re.I)
    if sexe:
        merged.setdefault('sexe', sexe.group(1))
    if 'adresse' not in merged and not any(
        merged.get(key) for key in ('telephone', 'email', 'classe', 'date_naissance', 'sexe', 'parent_telephone')
    ):
        if re.search(r'\b(rue|quartier|bp|avenue|impasse|carrefour)\b', raw, re.I) or len(raw) > 18:
            merged.setdefault('adresse', raw)
    return merged


def _picked(args, fields):
    return {key: args.get(key) for key in fields if (args.get(key) or '').strip()}


def _normalize_sexe(raw):
    value = (raw or '').strip().upper()
    if value in ('MASCULIN', 'GARCON', 'GARÇON', 'HOMME', 'M', 'M.'):
        return 'M'
    if value in ('FEMININ', 'FÉMININ', 'FILLE', 'FEMME', 'F'):
        return 'F'
    return value if value in ('M', 'F') else ''


def _normalize_lien(raw):
    text = (raw or '').strip().lower().replace(' ', '_')
    aliases = {
        'pere': 'pere',
        'père': 'pere',
        'papa': 'pere',
        'paternel': 'pere',
        'mere': 'mere',
        'mère': 'mere',
        'maman': 'mere',
        'maternel': 'mere',
        'tuteur': 'tuteur_legal',
        'tutrice': 'tuteur_legal',
        'tuteur_legal': 'tuteur_legal',
        'grand_parent': 'grand_parent',
        'grand-parent': 'grand_parent',
        'oncle_tante': 'oncle_tante',
        'oncle': 'oncle_tante',
        'tante': 'oncle_tante',
        'frere_soeur': 'frere_soeur',
        'frère': 'frere_soeur',
        'soeur': 'frere_soeur',
        'autre_famille': 'autre_famille',
        'autre': 'autre',
    }
    if text in aliases:
        return aliases[text]
    for key, value in aliases.items():
        if key in text:
            return value
    return ''


def _lien_compte_parent(lien):
    return lien if lien in ('pere', 'mere') else 'tuteur'


def _eleve_from_args(ctx, args):
    from school_admin.model.eleve_model import Eleve

    if args.get('id'):
        found = Eleve.objects.filter(pk=args['id'], etablissement=ctx.etablissement).first()
        if found:
            return found
    return _find_eleve(ctx, args.get('query') or args.get('nom'))


_SANCTION_TYPES = (
    ('avertissement_conduite', r'avertissement\s+de\s+conduite'),
    ('exclusion_temporaire', r'exclusion\s+temporaire'),
    ('exclusion_cours', r'exclusion(?:\s+de)?(?:\s+le)?\s+cours'),
    ('travaux_interet_general', r'travaux(?:\s+d[\'’]int[ée]r[êe]t)?|t\.?i\.?g\.?'),
    ('convocation_parents', r'convocation(?:\s+des?\s+parents)?'),
    ('avertissement', r'avertissement'),
    ('blame', r'bl[aâ]me'),
    ('retenue', r'retenue'),
)
_SANCTION_RAISONS = (
    ('absence_non_justifiee', r'absence'),
    ('retards_repetes', r'retard'),
    ('manque_respect', r'respect'),
    ('violence', r'violence|bagarre|frappe'),
    ('triche', r'triche'),
    ('desobeissance', r'd[ée]sob[ée]i'),
    ('perturbation_cours', r'perturb'),
    ('degradation_materiel', r'd[ée]grad'),
    ('vol', r'\bvol(?:er|é)?\b'),
    ('comportement_inapproprie', r'inappropri'),
    ('non_respect_reglement', r'r[eè]glement'),
    ('indiscipline', r'indisciplin'),
    ('autre', r'\bautre\b'),
)
_SANCTION_GRAVITES = (
    ('tres_grave', r'tr[eè]s\s+grave'),
    ('grave', r'\bgrave\b'),
    ('legere', r'l[eé]g[eè]re'),
    ('moyenne', r'moyenne'),
)
_TYPE_CODES = {code for code, _pat in _SANCTION_TYPES}
_RAISON_CODES = {code for code, _pat in _SANCTION_RAISONS}
_GRAVITE_CODES = {code for code, _pat in _SANCTION_GRAVITES}


def _match_alias(raw, table):
    text = (raw or '').strip().lower()
    if not text:
        return None
    for code, pattern in table:
        if text == code or re.search(pattern, text, re.I):
            return code
    return None


def parse_sanction_speech(raw):
    """Extrait type / raison / gravité d’une dictée libre."""
    text = (raw or '').strip()
    found = {}
    kind = _match_alias(text, _SANCTION_TYPES)
    if kind:
        found['type_sanction'] = kind
    reason = _match_alias(text, _SANCTION_RAISONS)
    if reason:
        found['raison'] = reason
    gravite = _match_alias(text, _SANCTION_GRAVITES)
    if gravite:
        found['gravite'] = gravite
    return found


def _normalize_sanction_type(raw):
    text = (raw or '').strip()
    if text in _TYPE_CODES:
        return text
    return _match_alias(text, _SANCTION_TYPES)


def _normalize_sanction_raison(raw):
    text = (raw or '').strip()
    if text in _RAISON_CODES:
        return text
    return _match_alias(text, _SANCTION_RAISONS)


def _normalize_sanction_gravite(raw, default=None):
    text = (raw or '').strip()
    if text in _GRAVITE_CODES:
        return text
    return _match_alias(text, _SANCTION_GRAVITES) or default


def _split_eleve_queries(raw):
    text = re.sub(r'\s+', ' ', (raw or '').strip())
    if not text:
        return []
    parts = re.split(r'\s*(?:,|;|\bet\b|\band\b)\s*', text, flags=re.I)
    return [part.strip(' .') for part in parts if part.strip(' .')]


def _eleves_from_args(ctx, args):
    found = []
    missing = []
    seen = set()
    queries = args.get('queries') or args.get('eleves')
    if isinstance(queries, str):
        queries = _split_eleve_queries(queries)
    if not isinstance(queries, (list, tuple)):
        queries = []
    queries = [str(item).strip() for item in queries if str(item).strip()]
    if not queries:
        queries = _split_eleve_queries(args.get('query') or args.get('nom') or '')
    stored = args.get('eleves_ids') or args.get('ids')
    if stored and not queries:
        from school_admin.model.eleve_model import Eleve

        ids = stored if isinstance(stored, (list, tuple)) else [stored]
        for pk in ids:
            eleve = Eleve.objects.filter(pk=pk, etablissement=ctx.etablissement).first()
            if eleve and eleve.id not in seen:
                seen.add(eleve.id)
                found.append(eleve)
        return found, missing
    if args.get('id') and not queries:
        eleve = _eleve_from_args(ctx, args)
        return ([eleve] if eleve else []), missing
    for query in queries:
        eleve = _find_eleve(ctx, query)
        if not eleve:
            missing.append(query)
            continue
        if eleve.id in seen:
            continue
        seen.add(eleve.id)
        found.append(eleve)
    return found, missing


def _noms_eleves(eleves):
    noms = [getattr(eleve, 'nom_complet', '') for eleve in eleves]
    noms = [nom for nom in noms if nom]
    if not noms:
        return 'ces élèves'
    if len(noms) == 1:
        return noms[0]
    return f'{", ".join(noms[:-1])} et {noms[-1]}'


def _rediger_note_sanction(type_label, raison_label, gravite_label, eleves):
    cible = _noms_eleves(eleves)
    return (
        f'{type_label} pour {cible}, motif : {raison_label.lower()}, '
        f'gravité {gravite_label.lower()}.'
    )


def choices_for_donner_sanction(draft):
    from school_admin.model.sanction_model import Sanction

    data = draft or {}
    manquants = list(data.get('manquants') or [])
    if 'type_sanction' in manquants:
        return _sanction_select_choices(Sanction.TYPE_SANCTION_CHOICES, 'Choisir le type')
    if 'raison' in manquants:
        return _sanction_select_choices(Sanction.RAISON_SANCTION_CHOICES, 'Choisir la raison')
    if 'gravite' in manquants:
        return _sanction_select_choices(Sanction.GRAVITE_CHOICES, 'Choisir la gravité')
    return []


def _sanction_select_choices(pairs, placeholder):
    return [
        {
            'label': label,
            'value': code,
            'intent': 'fill',
            'widget': 'select',
            'placeholder': placeholder,
        }
        for code, label in pairs
    ]


def _normalize_methode(raw):
    text = (raw or '').strip().lower()
    aliases = {
        'classique': 'classique_50_50',
        '50/50': 'classique_50_50',
        '50 50': 'classique_50_50',
        'exigeante': 'exigeante_40_60',
        '40/60': 'exigeante_40_60',
        'continu': 'continu_60_40',
        '60/40': 'continu_60_40',
        'speciale': 'speciale_30_70',
        'spéciale': 'speciale_30_70',
        '30/70': 'speciale_30_70',
        'classique_50_50': 'classique_50_50',
        'exigeante_40_60': 'exigeante_40_60',
        'continu_60_40': 'continu_60_40',
        'speciale_30_70': 'speciale_30_70',
    }
    return aliases.get(text) or aliases.get(text.replace(' ', '_'))


def _find_salle(ctx, query):
    from school_admin.model.salle_model import Salle

    raw = (query or '').strip()
    if not raw:
        return None
    return Salle.objects.filter(etablissement=ctx.etablissement).filter(
        Q(nom__icontains=raw) | Q(numero__icontains=raw)
    ).first()


def _find_filiere(ctx, query):
    from school_admin.model.academic_structure_model import Department

    raw = (query or '').strip()
    if not raw:
        return None
    return Department.objects.filter(etablissement=ctx.etablissement).filter(
        Q(nom__icontains=raw) | Q(sigle__icontains=raw)
    ).first()


def _find_module(ctx, query):
    from school_admin.model.module_model import Module

    raw = (query or '').strip()
    if not raw:
        return None
    return Module.objects.filter(etablissement=ctx.etablissement).filter(
        Q(nom__icontains=raw) | Q(code__icontains=raw)
    ).first()


def _repartir_echeances(reste, nombre, debut=None):
    n = max(2, int(nombre or 2))
    reste = Decimal(reste).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    part = (reste / n).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    jour = debut or date.today()
    lignes = []
    cumul = Decimal('0.00')
    for index in range(n):
        month = jour.month + index
        year = jour.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(jour.day, monthrange(year, month)[1])
        montant = part if index < n - 1 else (reste - cumul)
        cumul += montant
        lignes.append({'date': date(year, month, day), 'montant': montant})
    return lignes


# ---------------------------------------------------------------------------
# Dossier élève
# ---------------------------------------------------------------------------

def prepare_modifier_eleve(ctx, args):
    args = _parse_champs_libres(args)
    eleve = _eleve_from_args(ctx, args)
    if not eleve:
        return _incomplete(
            'modifier_eleve',
            ['query'],
            'Quel élève dois-je modifier ? Donnez le nom ou le matricule.',
        )
    picked = _picked(args, _ELEVE_FIELDS)
    lookup = (args.get('query') or '').strip().lower()
    for key in ('nom', 'prenom'):
        value = (picked.get(key) or '').strip().lower()
        if value and value in {
            lookup,
            (eleve.nom or '').lower(),
            (eleve.prenom or '').lower(),
            (eleve.nom_complet or '').lower(),
        }:
            picked.pop(key, None)
    if args.get('sexe'):
        sexe = _normalize_sexe(args.get('sexe'))
        if sexe:
            picked['sexe'] = sexe
        else:
            return _incomplete('modifier_eleve', ['sexe'], 'Sexe : M ou F ?')
    if 'classe' in picked:
        classe = _find_classe(ctx, picked['classe'])
        if not classe:
            return _incomplete('modifier_eleve', ['classe'], 'Quelle classe ?')
        picked['classe_id'] = classe.id
        picked['classe_nom'] = classe.nom
        picked.pop('classe', None)
    if args.get('date_naissance'):
        naissance = _parse_date(args.get('date_naissance'))
        if not naissance:
            return _incomplete(
                'modifier_eleve',
                ['date_naissance'],
                'Date de naissance au format jour/mois/année.',
            )
        picked['date_naissance'] = naissance.isoformat()
    if not picked:
        return _incomplete(
            'modifier_eleve',
            ['champs'],
            f'Que dois-je changer pour {eleve.nom_complet} ? '
            'Dictez tous les champs : nom, prénom, classe, adresse, téléphone, '
            'email, naissance, nationalité ou infos du parent.',
            id=eleve.id,
            query=eleve.nom_complet,
        )
    labels = ', '.join(f'{k}={v}' for k, v in picked.items() if k not in ('classe_id',))
    return _pending(
        'modifier_eleve',
        f'mets à jour le dossier de {eleve.nom_complet} ({labels})',
        id=eleve.id,
        nom=eleve.nom_complet,
        changements=picked,
        url=_reverse('secretaire:detail_eleve', args=[eleve.id]),
    )


def apply_modifier_eleve(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.eleve_model import Eleve

    eleve = Eleve.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not eleve:
        return _err('Élève introuvable.')
    changes = dict(draft.get('changements') or {})
    if changes.get('classe_id'):
        classe = Classe.objects.filter(
            pk=changes['classe_id'], etablissement=ctx.etablissement, actif=True
        ).first()
        if not classe:
            return _err('Classe introuvable.')
        eleve.classe = classe
        changes.pop('classe_id', None)
        changes.pop('classe_nom', None)
    if changes.get('date_naissance'):
        eleve.date_naissance = _parse_date(changes.pop('date_naissance'))
    for field, value in changes.items():
        if hasattr(eleve, field):
            setattr(eleve, field, value if value != '' else None)
    eleve.save()
    _emit(ctx, 'eleve.inscrit', {'id': eleve.id, 'action': 'modifie'})
    return _ok(
        f'Le dossier de {eleve.nom_complet} a été mis à jour.',
        url=_reverse('secretaire:detail_eleve', args=[eleve.id]),
    )


_REINSCRIRE_QUESTIONS = (
    ('classe', 'En quelle classe réinscrire {nom} ?'),
    ('date_naissance', 'Quelle est la date de naissance de {nom}, jour mois année ?'),
    ('lieu_naissance', 'Quel est le lieu de naissance ?'),
    ('sexe', 'Sexe : garçon ou fille ?'),
    ('nationalite', 'Quelle nationalité ?'),
    ('parent_nom', 'Nom du parent ou tuteur ?'),
    ('parent_prenom', 'Prénom du parent ou tuteur ?'),
    ('parent_telephone', 'Téléphone du parent ?'),
    ('parent_lien', 'Lien : père, mère ou tuteur ?'),
)


def prepare_reinscrire_eleve(ctx, args):
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    args = _parse_champs_libres(args)
    eleve = _eleve_from_args(ctx, args)
    if not eleve:
        return _incomplete('reinscrire_eleve', ['query'], 'Quel élève dois-je réinscrire ?')
    if not ctx.annee_scolaire:
        return _err('Aucune année scolaire active.')
    if InscriptionEleve.objects.filter(
        eleve=eleve, annee_scolaire=ctx.annee_scolaire, etablissement=ctx.etablissement
    ).exists():
        return _err(
            f'{eleve.nom_complet} est déjà inscrit pour {ctx.annee_scolaire.libelle}.'
        )
    extras = {
        'id': eleve.id,
        'query': eleve.nom_complet,
        'classe': args.get('classe') or (eleve.classe.nom if eleve.classe else ''),
        'date_naissance': args.get('date_naissance') or (
            eleve.date_naissance.isoformat() if eleve.date_naissance else ''
        ),
        'lieu_naissance': args.get('lieu_naissance') or eleve.lieu_naissance or '',
        'sexe': _normalize_sexe(args.get('sexe')) or eleve.sexe or '',
        'nationalite': args.get('nationalite') or eleve.nationalite or '',
        'parent_nom': args.get('parent_nom') or eleve.parent_nom or '',
        'parent_prenom': args.get('parent_prenom') or eleve.parent_prenom or '',
        'parent_telephone': args.get('parent_telephone') or eleve.parent_telephone or '',
        'parent_lien': _normalize_lien(args.get('parent_lien')) or eleve.parent_lien or '',
        'adresse': args.get('adresse') or eleve.adresse or '',
        'telephone': args.get('telephone') or eleve.telephone or '',
        'email': args.get('email') or eleve.email or '',
    }
    classe = _find_classe(ctx, extras['classe']) or eleve.classe
    if classe:
        extras['classe'] = classe.nom
        extras['classe_id'] = classe.id
    for key, prompt in _REINSCRIRE_QUESTIONS:
        if key == 'classe' and classe:
            continue
        if key == 'date_naissance' and (eleve.date_naissance or _parse_date(extras.get(key))):
            extras['date_naissance'] = (
                _parse_date(extras.get(key)) or eleve.date_naissance
            ).isoformat()
            continue
        if key == 'sexe':
            extras['sexe'] = _normalize_sexe(extras.get('sexe')) or eleve.sexe or ''
            if extras['sexe']:
                continue
        if key == 'parent_lien':
            extras['parent_lien'] = _normalize_lien(extras.get('parent_lien')) or eleve.parent_lien or ''
            if extras['parent_lien']:
                continue
        if extras.get(key):
            continue
        return _incomplete(
            'reinscrire_eleve',
            [key],
            prompt.format(nom=eleve.nom_complet),
            **extras,
        )
    if not classe:
        return _incomplete(
            'reinscrire_eleve',
            ['classe'],
            f'En quelle classe réinscrire {eleve.nom_complet} ?',
            **extras,
        )
    naissance = _parse_date(extras.get('date_naissance')) or eleve.date_naissance
    return _pending(
        'reinscrire_eleve',
        f'réinscrit {eleve.nom_complet} en {classe.nom} pour {ctx.annee_scolaire.libelle}',
        id=eleve.id,
        classe_id=classe.id,
        classe_nom=classe.nom,
        date_naissance=naissance.isoformat() if naissance else None,
        lieu_naissance=extras['lieu_naissance'],
        sexe=extras['sexe'],
        nationalite=extras['nationalite'],
        parent_nom=extras['parent_nom'],
        parent_prenom=extras['parent_prenom'],
        parent_telephone=extras['parent_telephone'],
        parent_lien=extras['parent_lien'] or 'tuteur_legal',
        adresse=extras['adresse'],
        telephone=extras['telephone'],
        email=extras['email'],
        url=_reverse('directeur:liste_reinscription'),
    )


def apply_reinscrire_eleve(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.inscription_eleve_model import InscriptionEleve
    from school_admin.model.lien_familial_model import LienFamilial
    from school_admin.model.parent_model import Parent
    from school_admin.personal_views.secretaire_view import _archiver_inscription_eleve_parent

    if InscriptionEleve.objects.filter(
        eleve_id=draft.get('id'),
        annee_scolaire=ctx.annee_scolaire,
        etablissement=ctx.etablissement,
    ).exists():
        return _err('Cet élève est déjà réinscrit pour cette année.')
    eleve = Eleve.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    classe = Classe.objects.filter(
        pk=draft.get('classe_id'), etablissement=ctx.etablissement, actif=True
    ).first()
    if not eleve or not classe:
        return _err('Élève ou classe introuvable.')
    naissance = _parse_date(draft.get('date_naissance')) or eleve.date_naissance
    with transaction.atomic():
        eleve.classe = classe
        eleve.date_inscription = date.today()
        eleve.statut = 'reinscription'
        eleve.actif = True
        eleve.is_active = True
        if naissance:
            eleve.date_naissance = naissance
        if draft.get('lieu_naissance'):
            eleve.lieu_naissance = draft['lieu_naissance']
        if draft.get('sexe') in ('M', 'F'):
            eleve.sexe = draft['sexe']
        if draft.get('nationalite'):
            eleve.nationalite = draft['nationalite']
        if draft.get('adresse'):
            eleve.adresse = draft['adresse']
        if draft.get('telephone'):
            eleve.telephone = draft['telephone']
        if draft.get('email'):
            eleve.email = draft['email']
        eleve.parent_nom = draft.get('parent_nom') or eleve.parent_nom
        eleve.parent_prenom = draft.get('parent_prenom') or eleve.parent_prenom
        eleve.parent_telephone = draft.get('parent_telephone') or eleve.parent_telephone
        lien = draft.get('parent_lien') or eleve.parent_lien or 'tuteur_legal'
        lien = _normalize_lien(lien) or lien
        if lien not in dict(Eleve.LIEN_PARENT_CHOICES):
            lien = 'tuteur_legal'
        eleve.parent_lien = lien
        eleve.save()
        compte_lien = _lien_compte_parent(lien)
        parent = Parent.objects.filter(
            telephone=eleve.parent_telephone,
            etablissement=ctx.etablissement,
        ).first()
        if parent is None and eleve.parent_telephone:
            matricule_parent = Parent.generer_matricule_parent(ctx.etablissement)
            mot_parent = Parent.generer_mot_de_passe()
            parent = Parent(
                matricule_parental=matricule_parent,
                type_parent=compte_lien,
                nom=eleve.parent_nom,
                prenom=eleve.parent_prenom or '',
                telephone=eleve.parent_telephone,
                etablissement=ctx.etablissement,
                mot_de_passe_provisoire=mot_parent,
                username=matricule_parent,
                is_active=True,
            )
            parent.set_password(mot_parent)
            parent.save()
        if parent:
            LienFamilial.objects.update_or_create(
                parent=parent,
                eleve=eleve,
                defaults={
                    'type_lien': compte_lien,
                    'statut': 'valide',
                    'est_inscripteur': True,
                    'actif': True,
                },
            )
        _archiver_inscription_eleve_parent(
            eleve=eleve,
            parent=parent,
            etablissement=ctx.etablissement,
            annee_scolaire=ctx.annee_scolaire,
            date_inscription=date.today(),
        )
        if getattr(ctx.etablissement, 'module_comptabilite', False):
            from school_admin.utils.comptabilite_utils import creer_frais_inscription

            try:
                creer_frais_inscription(eleve, ctx.annee_scolaire, 'reinscription')
            except Exception:
                pass
        _emit(ctx, 'eleve.inscrit', {'id': eleve.id, 'action': 'reinscrit'})
    return _ok(
        f'{eleve.nom_complet} est réinscrit en {classe.nom} pour {ctx.annee_scolaire.libelle}.',
        url=_reverse('secretaire:detail_eleve', args=[eleve.id]),
    )


def prepare_activer_eleve(ctx, args):
    from school_admin.model.eleve_model import Eleve

    raw = (args.get('query') or args.get('nom') or '').strip()
    eleve = Eleve.objects.filter(etablissement=ctx.etablissement).filter(
        Q(nom__icontains=raw) | Q(prenom__icontains=raw) | Q(matricule_eleve__icontains=raw)
    ).first() if raw else None
    if not eleve:
        return _incomplete('activer_eleve', ['query'], 'Quel élève dois-je réactiver ?')
    return _pending('activer_eleve', f'réactive {eleve.nom_complet}', id=eleve.id)


def apply_activer_eleve(ctx, draft):
    from school_admin.model.eleve_model import Eleve

    eleve = Eleve.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not eleve:
        return _err('Élève introuvable.')
    eleve.actif = True
    eleve.is_active = True
    eleve.save(update_fields=['actif', 'is_active'])
    _emit(ctx, 'eleve.inscrit', {'id': eleve.id, 'action': 'active'})
    return _ok(f'{eleve.nom_complet} a été réactivé.')


# ---------------------------------------------------------------------------
# Sanction disciplinaire (même enregistrement que le modal directeur)
# ---------------------------------------------------------------------------

_TYPE_SANCTION_PROMPT = 'Quel type de sanction ? Choisissez dans la liste.'
_RAISON_SANCTION_PROMPT = 'Quelle raison ? Choisissez dans la liste.'
_GRAVITE_SANCTION_PROMPT = 'Quelle gravité ? Choisissez dans la liste.'


def prepare_donner_sanction(ctx, args):
    spoken = ' '.join(
        str(args.get(key) or '')
        for key in ('query', 'queries', 'type_sanction', 'raison', 'gravite', 'champs', 'description')
    )
    parsed = parse_sanction_speech(spoken)
    type_sanction = _normalize_sanction_type(args.get('type_sanction')) or parsed.get('type_sanction')
    raison = _normalize_sanction_raison(args.get('raison')) or parsed.get('raison')
    gravite = _normalize_sanction_gravite(args.get('gravite') or parsed.get('gravite'))
    description = (args.get('description') or '').strip()
    date_sanction = _parse_date(args.get('date_sanction')) or date.today()
    eleves, missing = _eleves_from_args(ctx, args)
    extras = {
        'type_sanction': type_sanction or '',
        'raison': raison or '',
        'gravite': gravite or '',
        'description': description,
        'date_sanction': date_sanction.isoformat(),
    }
    if missing and not eleves:
        extras['query'] = args.get('query') or ''
        return _incomplete(
            'donner_sanction',
            ['query'],
            f'Je n’ai pas trouvé {", ".join(missing)}. Donnez le nom ou le matricule.',
            **{k: v for k, v in extras.items() if v},
        )
    if not eleves:
        extras['query'] = args.get('query') or ''
        return _incomplete(
            'donner_sanction',
            ['query'],
            'Quel élève dois-je sanctionner ? Donnez un ou plusieurs noms.',
            **{k: v for k, v in extras.items() if v},
        )
    if missing:
        extras['query'] = ' et '.join(eleve.nom_complet for eleve in eleves)
        extras['eleves_ids'] = [eleve.id for eleve in eleves]
        return _incomplete(
            'donner_sanction',
            ['query'],
            f'Je n’ai pas trouvé {", ".join(missing)}. Précisez ces noms.',
            **{k: v for k, v in extras.items() if v},
        )
    sans_classe = [eleve.nom_complet for eleve in eleves if not eleve.classe]
    if sans_classe:
        return _err(f'{", ".join(sans_classe)} n’est rattaché à aucune classe.')
    extras['id'] = eleves[0].id
    extras['nom'] = _noms_eleves(eleves)
    extras['query'] = ' et '.join(eleve.nom_complet for eleve in eleves)
    extras['eleves_ids'] = [eleve.id for eleve in eleves]
    extras['classe_id'] = eleves[0].classe.id
    extras['classe_nom'] = eleves[0].classe.nom
    extras['url'] = _reverse('secretaire:detail_eleve', args=[eleves[0].id])
    if not type_sanction:
        return _incomplete(
            'donner_sanction',
            ['type_sanction'],
            f'{_TYPE_SANCTION_PROMPT} Pour {_noms_eleves(eleves)}.',
            **{k: v for k, v in extras.items() if v},
        )
    if not raison:
        return _incomplete(
            'donner_sanction',
            ['raison'],
            f'{_RAISON_SANCTION_PROMPT} Pour {_noms_eleves(eleves)}.',
            **{k: v for k, v in extras.items() if v},
        )
    if not gravite:
        return _incomplete(
            'donner_sanction',
            ['gravite'],
            f'{_GRAVITE_SANCTION_PROMPT} Pour {_noms_eleves(eleves)}.',
            **{k: v for k, v in extras.items() if v},
        )
    from school_admin.model.sanction_model import Sanction

    type_label = dict(Sanction.TYPE_SANCTION_CHOICES).get(type_sanction, type_sanction)
    raison_label = dict(Sanction.RAISON_SANCTION_CHOICES).get(raison, raison)
    gravite_label = dict(Sanction.GRAVITE_CHOICES).get(gravite, gravite)
    if not description:
        description = _rediger_note_sanction(type_label, raison_label, gravite_label, eleves)
    return _pending(
        'donner_sanction',
        f'enregistre {type_label.lower()} pour {_noms_eleves(eleves)}',
        id=eleves[0].id,
        nom=_noms_eleves(eleves),
        classe_id=eleves[0].classe.id,
        classe_nom=eleves[0].classe.nom,
        eleves_ids=[eleve.id for eleve in eleves],
        type_sanction=type_sanction,
        raison=raison,
        gravite=gravite,
        description=description,
        date_sanction=date_sanction.isoformat(),
        url=_reverse('secretaire:detail_eleve', args=[eleves[0].id]),
        auto_appliquer=True,
    )


def apply_donner_sanction(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.sanction_model import Sanction

    if not ctx.annee_scolaire:
        return _err('Aucune année scolaire active.')
    type_sanction = _normalize_sanction_type(draft.get('type_sanction'))
    raison = _normalize_sanction_raison(draft.get('raison'))
    if not type_sanction or not raison:
        return _err('Type de sanction et raison sont obligatoires.')
    gravite = _normalize_sanction_gravite(draft.get('gravite'), default='moyenne')
    date_sanction = _parse_date(draft.get('date_sanction')) or date.today()
    etablissement = ctx.etablissement
    attribue_par_nom = ' '.join(
        part for part in (
            getattr(etablissement, 'directeur_prenom', '') or '',
            getattr(etablissement, 'directeur_nom', '') or '',
        ) if part
    ).strip() or 'Directeur'
    ids = draft.get('eleves_ids') or [draft.get('id')]
    eleves = list(
        Eleve.objects.filter(pk__in=[pk for pk in ids if pk], etablissement=etablissement)
    )
    if not eleves:
        return _err('Élève introuvable.')
    created = []
    type_label = dict(Sanction.TYPE_SANCTION_CHOICES).get(type_sanction, type_sanction)
    raison_label = dict(Sanction.RAISON_SANCTION_CHOICES).get(raison, raison)
    gravite_label = dict(Sanction.GRAVITE_CHOICES).get(gravite, gravite)
    description = (draft.get('description') or '').strip() or _rediger_note_sanction(
        type_label, raison_label, gravite_label, eleves
    )
    for eleve in eleves:
        classe = Classe.objects.filter(
            pk=getattr(eleve.classe, 'id', None),
            etablissement=etablissement,
            actif=True,
        ).first() or eleve.classe
        if not classe:
            return _err(f'{eleve.nom_complet} n’est rattaché à aucune classe.')
        sanction = Sanction.objects.create(
            eleve=eleve,
            classe=classe,
            professeur=None,
            etablissement=etablissement,
            type_sanction=type_sanction,
            raison=raison,
            gravite=gravite,
            description=description,
            date_sanction=date_sanction,
            attribue_par_type='directeur',
            attribue_par_nom=attribue_par_nom,
            annee_scolaire=ctx.annee_scolaire,
        )
        created.append(sanction)
        _emit(
            ctx,
            'sanction.ajoutee',
            {
                'id': sanction.id,
                'eleve_id': eleve.id,
                'eleve_nom': eleve.nom_complet,
                'classe_id': classe.id,
                'classe_nom': classe.nom,
                'type_sanction': sanction.get_type_sanction_display(),
            },
            eleve_id=eleve.id,
            classe_id=classe.id,
        )
    first = created[0]
    return _ok(
        f'{first.get_type_sanction_display()} enregistré pour {_noms_eleves(eleves)}.',
        id=first.id,
        ids=[item.id for item in created],
        url=_reverse('secretaire:detail_eleve', args=[eleves[0].id]),
        description=description,
    )


# ---------------------------------------------------------------------------
# Moratoire / relance / visibilité
# ---------------------------------------------------------------------------

def prepare_creer_moratoire(ctx, args):
    from school_admin.services.recouvrement import moratoire_actif, resume_dette_eleve

    eleve = _find_eleve(ctx, args.get('query') or args.get('nom'))
    if not eleve:
        return _incomplete('creer_moratoire', ['query'], 'Pour quel élève créer un moratoire ?')
    if not ctx.annee_scolaire:
        return _err('Aucune année scolaire active.')
    if moratoire_actif(eleve, ctx.etablissement, ctx.annee_scolaire):
        return _err(f'Un moratoire actif existe déjà pour {eleve.nom_complet}.')
    resume = resume_dette_eleve(eleve, ctx.etablissement, ctx.annee_scolaire)
    if resume.reste <= 0:
        return _err(f'{eleve.nom_complet} n’a rien à payer : moratoire inutile.')
    motif = (args.get('motif') or '').strip() or 'Échéancier convenu avec la famille'
    try:
        nombre = int(str(args.get('nombre_echeances') or args.get('echeances') or '2'))
    except (TypeError, ValueError):
        nombre = 0
    if nombre < 2:
        return _incomplete(
            'creer_moratoire',
            ['nombre_echeances'],
            f'Le reste dû est {resume.reste}. En combien d’échéances (au moins 2) ?',
            query=eleve.nom_complet,
            motif=motif,
        )
    lignes = _repartir_echeances(resume.reste, nombre)
    detail = ' ; '.join(f'{l["date"].isoformat()} : {l["montant"]}' for l in lignes)
    return _pending(
        'creer_moratoire',
        f'crée un moratoire de {nombre} échéances pour {eleve.nom_complet} ({detail})',
        id=eleve.id,
        motif=motif,
        nombre=nombre,
        echeances=[
            {'date': ligne['date'].isoformat(), 'montant': str(ligne['montant'])}
            for ligne in lignes
        ],
        url=_reverse('directeur:details_comptabilite_eleve_directeur', args=[eleve.id]),
    )


def apply_creer_moratoire(ctx, draft):
    from school_admin.model.eleve_model import Eleve
    from school_admin.services.recouvrement import creer_moratoire

    eleve = Eleve.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not eleve:
        return _err('Élève introuvable.')
    lignes = []
    for item in draft.get('echeances') or []:
        jour = _parse_date(item.get('date'))
        montant = _parse_money(item.get('montant'))
        if jour and montant:
            lignes.append({'date': jour, 'montant': montant})
    try:
        creer_moratoire(eleve, ctx.etablissement, ctx.annee_scolaire, draft.get('motif') or 'Moratoire', lignes)
    except ValueError as exc:
        return _err(str(exc))
    _emit(ctx, 'comptabilite.mise_a_jour', {'id': eleve.id, 'action': 'moratoire'})
    return _ok(
        f'Moratoire enregistré pour {eleve.nom_complet}.',
        url=_reverse('directeur:details_comptabilite_eleve_directeur', args=[eleve.id]),
    )


def prepare_payer_echeance_moratoire(ctx, args):
    from school_admin.model.recouvrement_model import EcheanceMoratoire

    eleve = _find_eleve(ctx, args.get('query') or args.get('nom'))
    if not eleve:
        return _incomplete('payer_echeance_moratoire', ['query'], 'Pour quel élève payer une échéance ?')
    echeances = EcheanceMoratoire.objects.filter(
        moratoire__eleve=eleve,
        moratoire__etablissement=ctx.etablissement,
        moratoire__annee_scolaire=ctx.annee_scolaire,
    ).exclude(statut='paye').order_by('date_echeance', 'numero')
    echeance = next((item for item in echeances if item.get_reste_a_payer() > 0), None)
    if not echeance:
        return _err(f'Aucune échéance de moratoire à payer pour {eleve.nom_complet}.')
    montant = _parse_money(args.get('montant')) or echeance.get_reste_a_payer()
    return _pending(
        'payer_echeance_moratoire',
        f'paie l’échéance de {eleve.nom_complet} ({montant})',
        id=eleve.id,
        echeance_id=echeance.id,
        montant=str(montant),
        url=_reverse('directeur:details_comptabilite_eleve_directeur', args=[eleve.id]),
    )


def apply_payer_echeance_moratoire(ctx, draft):
    from school_admin.model.recouvrement_model import EcheanceMoratoire
    from school_admin.services.recouvrement import payer_echeance_moratoire

    echeance = EcheanceMoratoire.objects.filter(
        pk=draft.get('echeance_id'),
        moratoire__etablissement=ctx.etablissement,
    ).select_related('moratoire').first()
    if not echeance:
        return _err('Échéance introuvable.')
    montant = _parse_money(draft.get('montant')) or echeance.get_reste_a_payer()
    try:
        payer_echeance_moratoire(echeance, montant)
    except Exception as exc:
        return _err(str(exc))
    _emit(ctx, 'comptabilite.mise_a_jour', {'id': draft.get('id'), 'action': 'echeance'})
    return _ok('Échéance de moratoire payée.')


def prepare_relancer_impaye(ctx, args):
    eleve = _find_eleve(ctx, args.get('query') or args.get('nom'))
    classe = None if eleve else _find_classe(ctx, args.get('classe') or args.get('query'))
    if not eleve and not classe:
        return _incomplete(
            'relancer_impaye',
            ['query'],
            'Quel élève ou quelle classe dois-je relancer pour impayé ?',
        )
    cible = eleve.nom_complet if eleve else f'la classe {classe.nom}'
    return _pending(
        'relancer_impaye',
        f'relance {cible}',
        eleve_id=eleve.id if eleve else None,
        classe_id=classe.id if classe else None,
        url=_reverse('directeur:liste_impayes_directeur'),
    )


def apply_relancer_impaye(ctx, draft):
    from school_admin.model.inscription_eleve_model import InscriptionEleve
    from school_admin.services.recouvrement import envoyer_relance_eleve, resume_dette_eleve

    envoyees = 0
    if draft.get('eleve_id'):
        inscription = InscriptionEleve.objects.filter(
            eleve_id=draft['eleve_id'],
            etablissement=ctx.etablissement,
            annee_scolaire=ctx.annee_scolaire,
        ).select_related('eleve').first()
        inscriptions = [inscription] if inscription else []
    else:
        inscriptions = list(
            InscriptionEleve.objects.filter(
                etablissement=ctx.etablissement,
                annee_scolaire=ctx.annee_scolaire,
                classe_id=draft.get('classe_id'),
                eleve__actif=True,
            ).select_related('eleve')
        )
    for inscription in inscriptions:
        if not inscription:
            continue
        if resume_dette_eleve(inscription.eleve, ctx.etablissement, ctx.annee_scolaire).reste <= 0:
            continue
        if envoyer_relance_eleve(
            inscription.eleve,
            ctx.etablissement,
            ctx.annee_scolaire,
            declenche_par='assistant',
            ignorer_doublon_jour=True,
        ):
            envoyees += 1
    _emit(ctx, 'comptabilite.mise_a_jour', {'action': 'relance'})
    if not envoyees:
        return _ok('Aucune relance envoyée (rien à recouvrer).')
    return _ok(f'{envoyees} relance(s) envoyée(s) aux familles.')


def prepare_configurer_visibilite_bulletins(ctx, args):
    classe = _find_classe(ctx, args.get('classe') or args.get('query'))
    if not classe:
        return _incomplete(
            'configurer_visibilite_bulletins',
            ['classe'],
            'Pour quelle classe dois-je changer la visibilité des bulletins ?',
        )
    visible_raw = str(args.get('visible') or args.get('afficher') or '').strip().lower()
    if visible_raw in ('1', 'true', 'oui', 'afficher', 'publier', 'visible'):
        visible = True
    elif visible_raw in ('0', 'false', 'non', 'masquer', 'cacher', 'invisible'):
        visible = False
    else:
        return _incomplete(
            'configurer_visibilite_bulletins',
            ['visible'],
            f'Afficher ou masquer les bulletins de {classe.nom} ?',
            classe=classe.nom,
        )
    return _pending(
        'configurer_visibilite_bulletins',
        f'{"affiche" if visible else "masque"} les bulletins de {classe.nom}',
        classe_id=classe.id,
        visible=visible,
        url=_reverse('directeur:bulletins_notes'),
    )


def apply_configurer_visibilite_bulletins(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.moyenne_periode_model import MoyennePeriode
    from school_admin.model.periode_model import PeriodeScolaire

    classe = Classe.objects.filter(pk=draft.get('classe_id'), etablissement=ctx.etablissement).first()
    periode = PeriodeScolaire.get_periode_active(ctx.etablissement)
    if not classe or not periode:
        return _err('Classe ou période introuvable.')
    qs = MoyennePeriode.objects.filter(
        etablissement=ctx.etablissement,
        periode=periode,
        est_moyenne_generale=True,
        eleve__classe=classe,
    )
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    visible = bool(draft.get('visible'))
    updated = qs.update(afficher_bulletin=visible)
    _emit(ctx, 'bulletin.mise_a_jour', {'classe_id': classe.id, 'action': 'visibilite'})
    etat = 'affichés' if visible else 'masqués'
    return _ok(f'Bulletins de {classe.nom} {etat} ({updated} élève(s)).')


# ---------------------------------------------------------------------------
# Moyennes / standards
# ---------------------------------------------------------------------------

def prepare_configurer_moyennes(ctx, args):
    methode = _normalize_methode(args.get('methode') or args.get('query') or args.get('champs'))
    if not methode:
        return _incomplete(
            'configurer_moyennes',
            ['methode'],
            'Quelle pondération ? Classique 50/50, exigeante 40/60, continu 60/40 ou spéciale 30/70.',
        )
    from school_admin.model.ponderation_model import Ponderation

    labels = dict(Ponderation.TYPE_CALCUL_CHOICES)
    return _pending(
        'configurer_moyennes',
        f'applique la pondération {labels.get(methode, methode)}',
        methode=methode,
        url=_reverse('directeur:configuration_moyennes_generales'),
    )


def apply_configurer_moyennes(ctx, draft):
    from school_admin.model.ponderation_model import Ponderation

    if not ctx.annee_scolaire:
        return _err('Aucune année scolaire active.')
    ponderation = Ponderation.get_or_create_for_year(ctx.etablissement, ctx.annee_scolaire.libelle)
    ponderation.appliquer_methode(draft.get('methode'))
    ponderation.save()
    _emit(ctx, 'bulletin.mise_a_jour', {'action': 'config_moyennes'})
    return _ok('Pondération des moyennes enregistrée.')


def prepare_configurer_standards(ctx, args):
    raw = args.get('moyenne_passage') or args.get('moyenne') or args.get('seuil') or args.get('champs')
    try:
        moyenne = Decimal(str(raw).replace(',', '.')).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError, AttributeError):
        moyenne = None
    if moyenne is None or moyenne < 0 or moyenne > 20:
        return _incomplete(
            'configurer_standards',
            ['moyenne_passage'],
            'Quelle moyenne de passage, entre 0 et 20 ?',
        )
    return _pending(
        'configurer_standards',
        f'fixe la moyenne de passage à {moyenne}',
        moyenne_passage=str(moyenne),
        url=_reverse('directeur:configuration_standards_reussite'),
    )


def apply_configurer_standards(ctx, draft):
    from school_admin.model.standards_reussite_model import StandardsReussite

    moyenne = Decimal(str(draft.get('moyenne_passage')))
    standards, _ = StandardsReussite.objects.get_or_create(
        etablissement=ctx.etablissement,
        defaults={'annee_scolaire': ctx.annee_scolaire},
    )
    standards.moyenne_passage = moyenne
    if ctx.annee_scolaire:
        standards.annee_scolaire = ctx.annee_scolaire
    standards.save()
    _emit(ctx, 'bulletin.mise_a_jour', {'action': 'config_standards'})
    return _ok(f'Moyenne de passage fixée à {moyenne}/20.')


# ---------------------------------------------------------------------------
# Professeurs / personnel / affectation / absences
# ---------------------------------------------------------------------------

def prepare_modifier_professeur(ctx, args):
    from school_admin.model.professeur_model import Professeur

    args = _parse_champs_libres(args)
    prof = None
    if args.get('id'):
        prof = Professeur.objects.filter(pk=args['id'], etablissement=ctx.etablissement).first()
    if not prof:
        prof = _find_professeur(ctx, args.get('query') or args.get('nom'))
    if not prof:
        return _incomplete('modifier_professeur', ['query'], 'Quel professeur dois-je modifier ?')
    picked = _picked(args, _PROF_FIELDS)
    if args.get('sexe'):
        sexe = _normalize_sexe(args.get('sexe'))
        if sexe:
            picked['sexe'] = sexe
    if picked.get('matiere'):
        matiere = _find_matiere(ctx, picked['matiere'])
        if not matiere:
            return _incomplete('modifier_professeur', ['matiere'], 'Quelle matière principale ?')
        picked['matiere_id'] = matiere.id
        picked['matiere_nom'] = matiere.nom
        picked.pop('matiere', None)
    if not picked:
        return _incomplete(
            'modifier_professeur',
            ['champs'],
            f'Que changer pour {prof.nom_complet} ? Dictez nom, prénom, téléphone, email, matière, tarif horaire.',
            id=prof.id,
            query=prof.nom_complet,
        )
    return _pending(
        'modifier_professeur',
        f'met à jour {prof.nom_complet}',
        id=prof.id,
        changements=picked,
        url=_reverse('professeur:detail_professeur', args=[prof.id]),
    )


def apply_modifier_professeur(ctx, draft):
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.professeur_model import Professeur

    prof = Professeur.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not prof:
        return _err('Professeur introuvable.')
    changes = dict(draft.get('changements') or {})
    if changes.get('matiere_id'):
        prof.matiere_principale = Matiere.objects.filter(
            pk=changes.pop('matiere_id'), etablissement=ctx.etablissement
        ).first()
        changes.pop('matiere_nom', None)
    if changes.get('prix_horaire'):
        try:
            prof.prix_volume_horaire = Decimal(str(changes.pop('prix_horaire')).replace(',', '.'))
        except (InvalidOperation, ValueError):
            return _err('Tarif horaire invalide.')
    for field, value in changes.items():
        if hasattr(prof, field):
            setattr(prof, field, value or None)
    prof.save()
    _emit(ctx, 'professeur.cree', {'id': prof.id, 'action': 'modifie'})
    return _ok(f'{prof.nom_complet} a été mis à jour.')


def prepare_modifier_personnel(ctx, args):
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif

    args = _parse_champs_libres(args)
    personnel = None
    if args.get('id'):
        personnel = PersonnelAdministratif.objects.filter(
            pk=args['id'], etablissement=ctx.etablissement
        ).first()
    if not personnel:
        personnel = _find_personnel(ctx, args.get('query') or args.get('nom'))
    if not personnel:
        return _incomplete('modifier_personnel', ['query'], 'Quel membre du personnel modifier ?')
    picked = _picked(args, _PERS_FIELDS)
    if args.get('fonction'):
        picked['fonction'] = _normalize_fonction(args.get('fonction'))
    if args.get('sexe'):
        sexe = _normalize_sexe(args.get('sexe'))
        if sexe:
            picked['sexe'] = sexe
    if not picked:
        return _incomplete(
            'modifier_personnel',
            ['champs'],
            f'Que changer pour {personnel.nom_complet} ? Dictez nom, prénom, téléphone, email, fonction.',
            id=personnel.id,
            query=personnel.nom_complet,
        )
    return _pending(
        'modifier_personnel',
        f'met à jour {personnel.nom_complet}',
        id=personnel.id,
        changements=picked,
        url=_reverse('personnel:detail_personnel', args=[personnel.id]),
    )


def apply_modifier_personnel(ctx, draft):
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif

    personnel = PersonnelAdministratif.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not personnel:
        return _err('Personnel introuvable.')
    for field, value in (draft.get('changements') or {}).items():
        if hasattr(personnel, field):
            setattr(personnel, field, value or None)
    personnel.save()
    _emit(ctx, 'personnel.cree', {'id': personnel.id, 'action': 'modifie'})
    return _ok(f'{personnel.nom_complet} a été mis à jour.')


def prepare_desactiver_personnel(ctx, args):
    personnel = _find_personnel(ctx, args.get('query') or args.get('nom'))
    if not personnel:
        return _incomplete('desactiver_personnel', ['query'], 'Quel membre du personnel désactiver ?')
    return _pending('desactiver_personnel', f'désactive {personnel.nom_complet}', id=personnel.id)


def apply_desactiver_personnel(ctx, draft):
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif

    personnel = PersonnelAdministratif.objects.filter(
        pk=draft.get('id'), etablissement=ctx.etablissement
    ).first()
    if not personnel:
        return _err('Personnel introuvable.')
    personnel.actif = False
    personnel.is_active = False
    personnel.save(update_fields=['actif', 'is_active'])
    _emit(ctx, 'personnel.cree', {'id': personnel.id, 'action': 'desactive'})
    return _ok(f'{personnel.nom_complet} a été désactivé.')


def prepare_affecter_professeur(ctx, args):
    prof = _find_professeur(ctx, args.get('professeur') or args.get('query'))
    classe = _find_classe(ctx, args.get('classe'))
    manquants = []
    if not prof:
        manquants.append('professeur')
    if not classe:
        manquants.append('classe')
    if manquants:
        return _incomplete(
            'affecter_professeur',
            manquants,
            'Pour affecter : le professeur et la classe, et la matière si ce n’est pas le primaire.',
        )
    matiere = _find_matiere(ctx, args.get('matiere')) or getattr(prof, 'matiere_principale', None)
    if ctx.etablissement.type_etablissement != 'primary' and not matiere:
        return _incomplete('affecter_professeur', ['matiere'], 'Quelle matière enseigner ?')
    action = 'remove' if str(args.get('action') or '').lower() in ('retirer', 'remove', 'enlever') else 'add'
    verbe = 'retire' if action == 'remove' else 'affecte'
    return _pending(
        'affecter_professeur',
        f'{verbe} {prof.nom_complet} ' + (f'sur {classe.nom}' if action == 'add' else f'de {classe.nom}'),
        professeur_id=prof.id,
        classe_id=classe.id,
        matiere_id=matiere.id if matiere else None,
        action=action,
        statut=(args.get('statut') or 'classique'),
        url=_reverse('affectation:affectation_professeurs'),
    )


def apply_affecter_professeur(ctx, draft):
    from school_admin.model.affectation_model import AffectationProfesseur
    from school_admin.model.classe_model import Classe
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.professeur_model import Professeur

    prof = Professeur.objects.filter(pk=draft.get('professeur_id'), etablissement=ctx.etablissement).first()
    classe = Classe.objects.filter(pk=draft.get('classe_id'), etablissement=ctx.etablissement).first()
    matiere = None
    if draft.get('matiere_id'):
        matiere = Matiere.objects.filter(pk=draft['matiere_id'], etablissement=ctx.etablissement).first()
    if not prof or not classe:
        return _err('Professeur ou classe introuvable.')
    if ctx.etablissement.type_etablissement == 'primary':
        from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire

        if draft.get('action') == 'remove':
            aff = AffectationProfesseurPrimaire.objects.filter(
                professeur=prof, classe=classe, actif=True, annee_scolaire=ctx.annee_scolaire
            ).first()
            if aff:
                aff.actif = False
                aff.save(update_fields=['actif'])
            _emit(ctx, 'affectation.mise_a_jour', {'action': 'remove'})
            return _ok(f'{prof.nom_complet} n’est plus affecté à {classe.nom}.')
        aff, created = AffectationProfesseurPrimaire.objects.get_or_create(
            professeur=prof,
            classe=classe,
            annee_scolaire=ctx.annee_scolaire,
            defaults={'statut': 'polyvalent', 'actif': True},
        )
        if not created:
            aff.actif = True
            aff.save(update_fields=['actif'])
        matieres = []
        if prof.matiere_principale:
            matieres.append(prof.matiere_principale)
        matieres.extend(list(prof.matieres_secondaires.all()))
        if matieres:
            aff.matieres.set(matieres)
        _emit(ctx, 'affectation.mise_a_jour', {'action': 'add'})
        return _ok(f'{prof.nom_complet} est affecté à {classe.nom}.')
    if not matiere:
        return _err('Indiquez la matière.')
    if draft.get('action') == 'remove':
        aff = AffectationProfesseur.objects.filter(
            professeur=prof, classe=classe, matiere=matiere, annee_scolaire=ctx.annee_scolaire
        ).first()
        if aff:
            aff.actif = False
            aff.save(update_fields=['actif'])
        _emit(ctx, 'affectation.mise_a_jour', {'action': 'remove'})
        return _ok(f'Affectation retirée pour {prof.nom_complet} / {classe.nom}.')
    aff, created = AffectationProfesseur.objects.get_or_create(
        professeur=prof,
        classe=classe,
        matiere=matiere,
        annee_scolaire=ctx.annee_scolaire,
        defaults={'statut': draft.get('statut') or 'classique', 'actif': True},
    )
    if not created:
        aff.actif = True
        aff.statut = draft.get('statut') or aff.statut
        aff.save()
    _emit(ctx, 'affectation.mise_a_jour', {'action': 'add'})
    return _ok(f'{prof.nom_complet} enseigne {matiere.nom} en {classe.nom}.')


def prepare_enregistrer_absence_professeur(ctx, args):
    prof = _find_professeur(ctx, args.get('query') or args.get('professeur'))
    if not prof:
        return _incomplete(
            'enregistrer_absence_professeur',
            ['query'],
            'Quel professeur est absent ?',
        )
    jour = _parse_date(args.get('date') or args.get('champs')) or (
        date.today() if (args.get('date') or '').strip().lower() in ('aujourd hui', "aujourd'hui", 'aujourdhui') else None
    )
    if not jour:
        return _incomplete(
            'enregistrer_absence_professeur',
            ['date'],
            f'Quelle date d’absence pour {prof.nom_complet} ?',
            query=prof.nom_complet,
        )
    remplacant = _find_professeur(ctx, args.get('remplacant'))
    return _pending(
        'enregistrer_absence_professeur',
        f'enregistre l’absence de {prof.nom_complet} le {jour.isoformat()}',
        id=prof.id,
        date=jour.isoformat(),
        remplacant_id=remplacant.id if remplacant else None,
        url=_reverse('directeur:detail_volume_horaire', args=[prof.id]),
    )


def apply_enregistrer_absence_professeur(ctx, draft):
    from school_admin.controllers.volume_horaire_controller import VolumeHoraireController
    from school_admin.model.caisse_etablissement_model import AbsenceEnseignant
    from school_admin.model.professeur_model import Professeur
    from school_admin.utils.volume_horaire import minutes_creneaux_pour_date

    prof = Professeur.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    jour = _parse_date(draft.get('date'))
    if not prof or not jour:
        return _err('Professeur ou date invalide.')
    remplacant = None
    if draft.get('remplacant_id'):
        remplacant = Professeur.objects.filter(
            pk=draft['remplacant_id'], etablissement=ctx.etablissement
        ).exclude(pk=prof.id).first()
    creneaux = list(
        VolumeHoraireController._creneaux_publies(ctx.etablissement, ctx.annee_scolaire, professeur=prof)
    )
    minutes = minutes_creneaux_pour_date(creneaux, jour)
    _obj, created = AbsenceEnseignant.objects.get_or_create(
        professeur=prof,
        date=jour,
        defaults={
            'etablissement': ctx.etablissement,
            'remplacant': remplacant,
            'minutes': minutes,
        },
    )
    _emit(ctx, 'paie.mise_a_jour', {'professeur_id': prof.id, 'action': 'absence'})
    if not created:
        return _ok(f'Une absence existe déjà pour {prof.nom_complet} le {jour.isoformat()}.')
    return _ok(f'Absence enregistrée pour {prof.nom_complet}.')


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def prepare_modifier_classe(ctx, args):
    classe = _find_classe(ctx, args.get('query') or args.get('classe'))
    if not classe:
        return _incomplete('modifier_classe', ['query'], 'Quelle classe modifier ?')
    nom = (args.get('nom') or args.get('nouveau_nom') or '').strip()
    capacite = args.get('capacite') or args.get('capacite_max')
    if not nom and not capacite:
        return _incomplete(
            'modifier_classe',
            ['nom'],
            f'Nouveau nom ou nouvelle capacité pour {classe.nom} ?',
        )
    return _pending(
        'modifier_classe',
        f'modifie {classe.nom}',
        id=classe.id,
        nom=nom or classe.nom,
        capacite=str(capacite or classe.capacite_max),
        url=_reverse('administrateur_etablissement:liste_classes'),
    )


def apply_modifier_classe(ctx, draft):
    from school_admin.model.classe_model import Classe

    classe = Classe.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not classe:
        return _err('Classe introuvable.')
    nom = (draft.get('nom') or classe.nom).strip()
    try:
        capacite = int(draft.get('capacite') or classe.capacite_max)
    except (TypeError, ValueError):
        return _err('Capacité invalide.')
    if capacite < getattr(classe, 'nombre_eleves', 0):
        return _err('La capacité ne peut pas être inférieure au nombre d’élèves actuel.')
    classe.nom = nom
    classe.capacite_max = capacite
    classe.save()
    _emit(ctx, 'classe.modifiee', {'id': classe.id, 'nom': classe.nom})
    return _ok(f'Classe {classe.nom} mise à jour.')


def prepare_modifier_salle(ctx, args):
    from school_admin.model.salle_model import Salle

    args = _parse_champs_libres(args)
    salle = None
    if args.get('id'):
        salle = Salle.objects.filter(pk=args['id'], etablissement=ctx.etablissement).first()
    if not salle:
        salle = _find_salle(ctx, args.get('query') or args.get('nom'))
    if not salle:
        return _incomplete('modifier_salle', ['query'], 'Quelle salle modifier ?')
    picked = {k: args.get(k) for k in ('nom', 'numero', 'capacite', 'etat') if args.get(k)}
    if not picked:
        return _incomplete(
            'modifier_salle',
            ['champs'],
            f'Que changer pour {salle.nom} ? Dictez le nom, le numéro, la capacité ou l’état.',
            id=salle.id,
            query=salle.nom,
        )
    return _pending(
        'modifier_salle',
        f'modifie {salle.nom}',
        id=salle.id,
        changements=picked,
        url=_reverse('salle:detail_salle', args=[salle.id]),
    )


def apply_modifier_salle(ctx, draft):
    from school_admin.controllers.salle_controller import SalleController
    from school_admin.model.salle_model import Salle

    salle = Salle.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not salle:
        return _err('Salle introuvable.')
    changes = draft.get('changements') or {}
    if changes.get('nom'):
        salle.nom = changes['nom']
    if changes.get('numero'):
        salle.numero = changes['numero']
    if changes.get('capacite'):
        try:
            salle.capacite_max = int(changes['capacite'])
        except (TypeError, ValueError):
            return _err('Capacité invalide.')
    if changes.get('etat'):
        salle.etat = changes['etat']
    salle.save()
    _emit(ctx, 'salle.modifiee', SalleController._serialize_salle_item(salle))
    return _ok(f'Salle {salle.nom} mise à jour.')


def prepare_modifier_filiere(ctx, args):
    if ctx.etablissement.type_etablissement != 'superieur':
        return _err('Les spécialités concernent uniquement le supérieur.')
    dept = _find_filiere(ctx, args.get('query') or args.get('nom'))
    if not dept:
        return _incomplete('modifier_filiere', ['query'], 'Quelle spécialité modifier ?')
    nom = (args.get('nouveau_nom') or args.get('nom') or '').strip()
    sigle = (args.get('sigle') or '').strip()
    if nom == dept.nom:
        nom = ''
    if not nom and not sigle:
        return _incomplete('modifier_filiere', ['nouveau_nom'], f'Nouveau nom ou sigle pour {dept.nom} ?')
    return _pending(
        'modifier_filiere',
        f'modifie {dept.nom}',
        id=dept.id,
        nom=nom or dept.nom,
        sigle=sigle or dept.sigle,
        url=_reverse('administrateur_etablissement:liste_filieres'),
    )


def apply_modifier_filiere(ctx, draft):
    from school_admin.controllers.classe_controller import ClasseController
    from school_admin.model.academic_structure_model import Department

    dept = Department.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not dept:
        return _err('Spécialité introuvable.')
    sigle, err = ClasseController._validate_department_sigle(
        ctx.etablissement, draft.get('sigle') or dept.sigle, exclude_id=dept.id
    )
    if err:
        return _err(err)
    dept.nom = draft.get('nom') or dept.nom
    dept.sigle = sigle
    dept.save()
    _emit(ctx, 'filiere.mise_a_jour', {'id': dept.id, 'action': 'modifiee'})
    return _ok(f'Spécialité {dept.nom} mise à jour.')


def prepare_supprimer_filiere(ctx, args):
    if ctx.etablissement.type_etablissement != 'superieur':
        return _err('Les spécialités concernent uniquement le supérieur.')
    dept = _find_filiere(ctx, args.get('query') or args.get('nom'))
    if not dept:
        return _incomplete('supprimer_filiere', ['query'], 'Quelle spécialité supprimer ?')
    return _pending(
        'supprimer_filiere',
        f'supprime {dept.nom}',
        id=dept.id,
        nom=dept.nom,
    )


def apply_supprimer_filiere(ctx, draft):
    from school_admin.model.academic_structure_model import Department

    dept = Department.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not dept:
        return _err('Spécialité introuvable.')
    if dept.classes.count():
        return _err(f'Impossible : {dept.nom} contient encore des classes.')
    nom = dept.nom
    dept.delete()
    _emit(ctx, 'filiere.mise_a_jour', {'nom': nom, 'action': 'supprimee'})
    return _ok(f'Spécialité {nom} supprimée.')


def prepare_creer_module(ctx, args):
    if ctx.etablissement.type_etablissement != 'superieur':
        return _err('Les modules LMD concernent uniquement le supérieur.')
    nom = (args.get('nom') or args.get('query') or '').strip()
    if not nom:
        return _incomplete('creer_module', ['nom'], 'Quel nom pour le module ?')
    dept = _find_filiere(ctx, args.get('filiere') or args.get('specialite') or args.get('department'))
    if not dept:
        return _incomplete('creer_module', ['filiere'], f'À quelle spécialité rattacher « {nom} » ?')
    return _pending(
        'creer_module',
        f'crée le module {nom} ({dept.nom})',
        nom=nom,
        department_id=dept.id,
        url=_reverse('matiere:liste_matieres'),
    )


def apply_creer_module(ctx, draft):
    from school_admin.controllers.module_controller import _sync_module_departments
    from school_admin.model.academic_structure_model import Department
    from school_admin.model.module_model import Module

    nom = (draft.get('nom') or '').strip()
    dept = Department.objects.filter(
        pk=draft.get('department_id'), etablissement=ctx.etablissement
    ).first()
    if not nom or not dept:
        return _err('Nom ou spécialité manquant.')
    dernier = Module.objects.filter(etablissement=ctx.etablissement).count()
    code = f'MOD-{dernier + 1:04d}'
    while Module.objects.filter(etablissement=ctx.etablissement, code=code).exists():
        dernier += 1
        code = f'MOD-{dernier + 1:04d}'
    module = Module.objects.create(
        nom=nom,
        code=code,
        etablissement=ctx.etablissement,
        department=dept,
    )
    _sync_module_departments(module, [str(dept.id)])
    _emit(ctx, 'matiere.creee', {'id': module.id, 'nom': module.nom, 'action': 'module'})
    return _ok(f'Module {module.nom} créé ({code}).')


def prepare_supprimer_module(ctx, args):
    if ctx.etablissement.type_etablissement != 'superieur':
        return _err('Les modules LMD concernent uniquement le supérieur.')
    module = _find_module(ctx, args.get('query') or args.get('nom'))
    if not module:
        return _incomplete('supprimer_module', ['query'], 'Quel module supprimer ?')
    return _pending('supprimer_module', f'supprime {module.nom}', id=module.id, nom=module.nom)


def apply_supprimer_module(ctx, draft):
    from school_admin.model.module_model import Module

    module = Module.objects.filter(pk=draft.get('id'), etablissement=ctx.etablissement).first()
    if not module:
        return _err('Module introuvable.')
    nom = module.nom
    module.delete()
    _emit(ctx, 'matiere.supprimee', {'nom': nom, 'action': 'module'})
    return _ok(f'Module {nom} supprimé.')


_DOSSIER_ACTIONS = (
    ActionSpec(
        'modifier_eleve',
        'Modifie le dossier d’un élève (nom, classe, adresse, téléphone, parent, naissance…). Dictez tous les champs utiles.',
        {key: _STR for key in ('query', 'champs') + _ELEVE_FIELDS},
        prepare=prepare_modifier_eleve,
        apply=apply_modifier_eleve,
    ),
    ActionSpec(
        'reinscrire_eleve',
        'Réinscrit un élève pour l’année active (élève + classe ; le dossier existant est repris).',
        {
            'query': _STR, 'classe': _STR, 'date_naissance': _STR, 'lieu_naissance': _STR,
            'parent_nom': _STR, 'parent_prenom': _STR, 'parent_telephone': _STR, 'parent_lien': _STR,
        },
        prepare=prepare_reinscrire_eleve,
        apply=apply_reinscrire_eleve,
    ),
    ActionSpec(
        'activer_eleve',
        'Réactive un élève désactivé.',
        {'query': _STR},
        prepare=prepare_activer_eleve,
        apply=apply_activer_eleve,
    ),
    ActionSpec(
        'donner_sanction',
        (
            'Enregistre une sanction disciplinaire pour un ou plusieurs élèves. '
            'Ne liste jamais les types ni les raisons à l’oral : demande le type, '
            'puis la raison, puis la gravité. La note est rédigée automatiquement. '
            'Pour plusieurs élèves, envoie leurs noms dans query (séparés par « et »).'
        ),
        {
            'query': _STR, 'queries': _STR, 'type_sanction': _STR, 'raison': _STR,
            'gravite': _STR, 'description': _STR, 'date_sanction': _STR,
        },
        prepare=prepare_donner_sanction,
        apply=apply_donner_sanction,
        choices=choices_for_donner_sanction,
    ),
    ActionSpec(
        'creer_moratoire',
        'Crée un moratoire : l’élève, le motif, le nombre d’échéances (le reste dû est réparti).',
        {'query': _STR, 'motif': _STR, 'nombre_echeances': _STR, 'echeances': _STR},
        prepare=prepare_creer_moratoire,
        apply=apply_creer_moratoire,
    ),
    ActionSpec(
        'payer_echeance_moratoire',
        'Paie la prochaine échéance de moratoire d’un élève.',
        {'query': _STR, 'montant': _STR},
        prepare=prepare_payer_echeance_moratoire,
        apply=apply_payer_echeance_moratoire,
    ),
    ActionSpec(
        'relancer_impaye',
        'Envoie une relance d’impayé à un élève ou à une classe.',
        {'query': _STR, 'classe': _STR},
        prepare=prepare_relancer_impaye,
        apply=apply_relancer_impaye,
    ),
    ActionSpec(
        'configurer_visibilite_bulletins',
        'Affiche ou masque les bulletins d’une classe.',
        {'classe': _STR, 'query': _STR, 'visible': _STR, 'afficher': _STR},
        prepare=prepare_configurer_visibilite_bulletins,
        apply=apply_configurer_visibilite_bulletins,
    ),
    ActionSpec(
        'configurer_moyennes',
        'Configure la pondération des moyennes (classique 50/50, exigeante 40/60, continu 60/40, spéciale 30/70).',
        {'methode': _STR, 'query': _STR, 'champs': _STR},
        prepare=prepare_configurer_moyennes,
        apply=apply_configurer_moyennes,
    ),
    ActionSpec(
        'configurer_standards',
        'Fixe la moyenne de passage (0 à 20).',
        {'moyenne_passage': _STR, 'moyenne': _STR, 'seuil': _STR, 'champs': _STR},
        prepare=prepare_configurer_standards,
        apply=apply_configurer_standards,
    ),
    ActionSpec(
        'modifier_professeur',
        'Modifie un professeur (nom, téléphone, email, matière, tarif horaire).',
        {key: _STR for key in ('query', 'champs') + _PROF_FIELDS},
        prepare=prepare_modifier_professeur,
        apply=apply_modifier_professeur,
    ),
    ActionSpec(
        'modifier_personnel',
        'Modifie un membre du personnel (nom, téléphone, email, fonction).',
        {key: _STR for key in ('query', 'champs') + _PERS_FIELDS},
        prepare=prepare_modifier_personnel,
        apply=apply_modifier_personnel,
    ),
    ActionSpec(
        'desactiver_personnel',
        'Désactive un membre du personnel.',
        {'query': _STR},
        destructive=True,
        prepare=prepare_desactiver_personnel,
        apply=apply_desactiver_personnel,
    ),
    ActionSpec(
        'affecter_professeur',
        'Affecte ou retire un professeur d’une classe (et d’une matière hors primaire).',
        {'professeur': _STR, 'query': _STR, 'classe': _STR, 'matiere': _STR, 'action': _STR, 'statut': _STR},
        prepare=prepare_affecter_professeur,
        apply=apply_affecter_professeur,
    ),
    ActionSpec(
        'enregistrer_absence_professeur',
        'Enregistre l’absence d’un professeur (date, remplaçant optionnel).',
        {'query': _STR, 'professeur': _STR, 'date': _STR, 'remplacant': _STR, 'champs': _STR},
        prepare=prepare_enregistrer_absence_professeur,
        apply=apply_enregistrer_absence_professeur,
    ),
    ActionSpec(
        'modifier_classe',
        'Modifie le nom ou la capacité d’une classe.',
        {'query': _STR, 'classe': _STR, 'nom': _STR, 'nouveau_nom': _STR, 'capacite': _STR, 'capacite_max': _STR},
        prepare=prepare_modifier_classe,
        apply=apply_modifier_classe,
    ),
    ActionSpec(
        'modifier_salle',
        'Modifie une salle (nom, numéro, capacité, état).',
        {'query': _STR, 'nom': _STR, 'numero': _STR, 'capacite': _STR, 'etat': _STR, 'champs': _STR},
        prepare=prepare_modifier_salle,
        apply=apply_modifier_salle,
    ),
    ActionSpec(
        'modifier_filiere',
        'Modifie une spécialité (nom, sigle).',
        {'query': _STR, 'nom': _STR, 'nouveau_nom': _STR, 'sigle': _STR},
        prepare=prepare_modifier_filiere,
        apply=apply_modifier_filiere,
    ),
    ActionSpec(
        'supprimer_filiere',
        'Supprime une spécialité sans classe.',
        {'query': _STR, 'nom': _STR},
        destructive=True,
        prepare=prepare_supprimer_filiere,
        apply=apply_supprimer_filiere,
    ),
    ActionSpec(
        'creer_module',
        'Crée un module LMD (nom + spécialité).',
        {'nom': _STR, 'query': _STR, 'filiere': _STR, 'specialite': _STR, 'department': _STR},
        prepare=prepare_creer_module,
        apply=apply_creer_module,
    ),
    ActionSpec(
        'supprimer_module',
        'Supprime un module LMD.',
        {'query': _STR, 'nom': _STR},
        destructive=True,
        prepare=prepare_supprimer_module,
        apply=apply_supprimer_module,
    ),
)

for _spec in _DOSSIER_ACTIONS:
    register_action(_spec)
