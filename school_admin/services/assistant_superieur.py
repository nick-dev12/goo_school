"""
Vague 4 — tools LMD / ECTS pour l’assistant directeur (supérieur uniquement).

Lecture : ECTS étudiant/classe, maquette (modules + UE + crédits), relevé.
Écriture : affecter un module, fixer les crédits (brouillon + confirmation).
Les périodes (get_periodes / creer_periode) sont étendues ailleurs ;
ce module fournit les helpers de normalisation LMD.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.urls import NoReverseMatch, reverse

from school_admin.model.periode_model import (
    NIVEAUX_PERIODE_SUPERIEUR_KEYS,
    SEMESTRES_PAR_NIVEAU_LMD,
    est_semestre_valide_pour_niveau,
)
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

logger = logging.getLogger(__name__)

MODULES_LIMIT = 40
ELEVES_LIMIT = 24

NIVEAU_LMD_ENUM = [
    'L1', 'L2', 'L3',
    'BTS1', 'BTS2',
    'DUT1', 'DUT2',
    'M1', 'M2',
    'D1', 'D2', 'D3',
]

NIVEAU_LMD_ALIASES = {
    'L1': ('l1', 'l 1', 'licence 1', 'licence1', 'licence i', 'lic 1'),
    'L2': ('l2', 'l 2', 'licence 2', 'licence2', 'licence ii', 'lic 2'),
    'L3': ('l3', 'l 3', 'licence 3', 'licence3', 'licence iii', 'lic 3'),
    'M1': ('m1', 'm 1', 'master 1', 'master1', 'master i'),
    'M2': ('m2', 'm 2', 'master 2', 'master2', 'master ii'),
    'D1': ('d1', 'd 1', 'doctorat 1', 'doctorat1', 'these 1', 'thèse 1'),
    'D2': ('d2', 'd 2', 'doctorat 2', 'doctorat2'),
    'D3': ('d3', 'd 3', 'doctorat 3', 'doctorat3'),
    'BTS1': ('bts1', 'bts 1', 'bts i'),
    'BTS2': ('bts2', 'bts 2', 'bts ii'),
    'DUT1': ('dut1', 'dut 1', 'dut i'),
    'DUT2': ('dut2', 'dut 2', 'dut ii'),
}

_SEMESTRE_NUM_RE = re.compile(
    r'(?:s|sem(?:estre)?)\s*(\d{1,2})\b',
    re.IGNORECASE,
)
_STR = {'type': 'string'}
_CLASSE = {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION}


def _fold(text):
    raw = unicodedata.normalize('NFD', (text or '').strip())
    raw = ''.join(ch for ch in raw if unicodedata.category(ch) != 'Mn')
    return re.sub(r'\s+', ' ', raw).lower().strip()


def normalize_niveau_lmd(raw):
    text = (raw or '').strip()
    if not text:
        return None
    if text.upper() in NIVEAUX_PERIODE_SUPERIEUR_KEYS:
        return text.upper()
    folded = _fold(text)
    if folded.upper() in NIVEAUX_PERIODE_SUPERIEUR_KEYS:
        return folded.upper()
    for code, aliases in NIVEAU_LMD_ALIASES.items():
        if folded == code.lower() or folded in aliases:
            return code
    return None


def resolve_nom_periode(raw, niveau_lmd):
    """Nom officiel (ex. « Semestre 1 ») ou le texte tel quel."""
    text = (raw or '').strip()
    niveau = normalize_niveau_lmd(niveau_lmd) or (niveau_lmd or '').strip()
    if text and est_semestre_valide_pour_niveau(text, niveau):
        return text
    match = _SEMESTRE_NUM_RE.search(text)
    if match:
        candidate = f'Semestre {int(match.group(1))}'
        if est_semestre_valide_pour_niveau(candidate, niveau):
            return candidate
    pairs = SEMESTRES_PAR_NIVEAU_LMD.get(niveau, [])
    folded = _fold(text)
    if pairs:
        if any(token in folded for token in ('1er', 'premier', '1e semestre', 'premiere')):
            return pairs[0][0]
        if any(token in folded for token in ('2e', '2eme', 'deuxieme', 'second')):
            return pairs[1][0] if len(pairs) > 1 else pairs[0][0]
    return text or None


def _require_superieur(ctx):
    if not getattr(ctx, 'est_superieur', False):
        return _err('Cet outil n’est proposé que pour un établissement supérieur.')
    return None


def _reverse(route, args=None):
    try:
        return reverse(route, args=args or [])
    except NoReverseMatch:
        return None


def _safe(value):
    if value is None:
        return None
    return float(value)


def _parse_credits(raw):
    if raw is None or raw == '':
        return None
    text = str(raw).strip().replace(',', '.')
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if value < 0 or value > 60:
        return None
    return value.quantize(Decimal('0.01'))


def _seuil_passage(ctx):
    from school_admin.services.assistant_pilotage import _seuil_passage as finder

    return finder(ctx)


def _find_module(ctx, query):
    from school_admin.services.assistant_dossiers import _find_module as finder

    return finder(ctx, query)


def _find_periode(ctx, query=None, niveau_lmd=None):
    from school_admin.model.periode_model import PeriodeScolaire

    qs = PeriodeScolaire.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire_fk=ctx.annee_scolaire)
            | Q(annee_scolaire=ctx.annee_scolaire.libelle)
        )
    niveau = normalize_niveau_lmd(niveau_lmd)
    if niveau:
        qs = qs.filter(Q(niveau_lmd=niveau) | Q(niveau_lmd=''))
    raw = (query or '').strip()
    if not raw:
        if niveau:
            scoped = qs.filter(niveau_lmd=niveau)
            return (
                scoped.filter(est_active=True).first()
                or scoped.order_by('date_debut').first()
                or PeriodeScolaire.get_periode_active(ctx.etablissement)
            )
        return PeriodeScolaire.get_periode_active(ctx.etablissement) or qs.order_by(
            'date_debut'
        ).first()
    nom = resolve_nom_periode(raw, niveau) if niveau else raw
    found = qs.filter(
        Q(nom_periode__iexact=nom) | Q(nom_periode__icontains=nom)
    ).order_by('niveau_lmd').first()
    if found:
        return found
    return qs.filter(
        Q(nom_periode__icontains=raw) | Q(type_periode__icontains=raw)
    ).first()


_QUERY_NOISE = re.compile(
    r'\b(credits?|crédits?|ects|ue|module|modules|maquette|releve|relevé|'
    r'etudiant|étudiant|etudiante|étudiante|de|du|des|la|le|les|un|une|'
    r'combien|quels?|quelles?)\b',
    re.IGNORECASE,
)


def _find_etudiant(ctx, query):
    eleve = _find_eleve(ctx, query)
    if eleve:
        return eleve
    cleaned = _QUERY_NOISE.sub(' ', query or '')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if cleaned and cleaned != (query or '').strip():
        return _find_eleve(ctx, cleaned)
    return None


def _eleves_classe(ctx, classe):
    from school_admin.model.eleve_model import Eleve
    from school_admin.services.assistant_tools import _eleves_qs

    qs = _eleves_qs(ctx).filter(classe=classe).select_related('classe')
    if qs.exists():
        return qs
    return Eleve.objects.filter(
        etablissement=ctx.etablissement,
        classe=classe,
        actif=True,
    ).select_related('classe')


def _maquette_qs(classe):
    from school_admin.model.module_model import ModuleClasse

    return ModuleClasse.objects.filter(classe=classe).select_related(
        'module', 'periode'
    )


def _serialize_module_classe(mc):
    periode = mc.periode
    return {
        'module': mc.module.nom,
        'code': mc.module.code,
        'credits': _safe(mc.credits),
        'numero_ue': (mc.numero_ue or '').strip() or None,
        'periode': periode.nom_periode if periode else None,
        'niveau_lmd': (periode.niveau_lmd if periode else None)
        or mc.module.niveau_lmd
        or None,
    }


def _credits_valides_qs(ctx, eleve, periode=None):
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    qs = MoyennePeriode.objects.filter(
        etablissement=ctx.etablissement,
        eleve=eleve,
        est_moyenne_generale=False,
        credits__isnull=False,
    )
    if ctx.annee_scolaire:
        qs = qs.filter(Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True))
    if periode:
        qs = qs.filter(periode=periode)
    return qs


def _ects_pour_eleve(ctx, eleve, periode=None):
    classe = eleve.classe
    maquette = _maquette_qs(classe)
    if periode:
        maquette = maquette.filter(Q(periode=periode) | Q(periode__isnull=True))
    inscrits = sum((mc.credits or Decimal('0')) for mc in maquette)
    seuil = _seuil_passage(ctx)
    credits_rows = list(_credits_valides_qs(ctx, eleve, periode=periode))
    valides = sum(
        (row.credits or Decimal('0'))
        for row in credits_rows
        if row.moyenne_matiere is not None and row.moyenne_matiere >= seuil
    )
    restants = inscrits - valides
    if restants < 0:
        restants = Decimal('0')
    return {
        'credits_inscrits': _safe(inscrits),
        'credits_valides': _safe(valides) if credits_rows else 0.0 if inscrits else 0.0,
        'credits_restants': _safe(restants),
        'credits_calcules': bool(credits_rows),
        'seuil': _safe(seuil),
    }


def _ects_par_semestre(ctx, eleve):
    classe = eleve.classe
    groupes = {}
    for mc in _maquette_qs(classe):
        key = mc.periode_id or 0
        bucket = groupes.setdefault(
            key,
            {
                'periode': mc.periode.nom_periode if mc.periode else 'Sans période',
                'niveau_lmd': (
                    (mc.periode.niveau_lmd if mc.periode else None)
                    or classe.niveau_lmd
                    or None
                ),
                'inscrits': Decimal('0'),
                'modules': [],
                '_periode': mc.periode,
            },
        )
        bucket['inscrits'] += mc.credits or Decimal('0')
        bucket['modules'].append(_serialize_module_classe(mc))

    seuil = _seuil_passage(ctx)
    items = []
    for bucket in groupes.values():
        periode = bucket.pop('_periode')
        rows = list(_credits_valides_qs(ctx, eleve, periode=periode)) if periode else []
        valides = sum(
            (row.credits or Decimal('0'))
            for row in rows
            if row.moyenne_matiere is not None and row.moyenne_matiere >= seuil
        )
        restants = bucket['inscrits'] - valides
        if restants < 0:
            restants = Decimal('0')
        items.append({
            'periode': bucket['periode'],
            'niveau_lmd': bucket['niveau_lmd'],
            'credits_inscrits': _safe(bucket['inscrits']),
            'credits_valides': _safe(valides),
            'credits_restants': _safe(restants),
            'modules': bucket['modules'],
        })
    items.sort(key=lambda item: item['periode'] or '')
    return items


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

def tool_ects_etudiant(ctx, args):
    denied = _require_superieur(ctx)
    if denied:
        return denied
    args = args if isinstance(args, dict) else {}
    eleve = _find_etudiant(ctx, args.get('query') or args.get('etudiant') or '')
    if not eleve:
        return {'erreur': 'Indique l’étudiant dont tu veux les crédits ECTS.'}
    if not eleve.classe_id:
        return {'erreur': f'{eleve.nom_complet} n’est rattaché à aucune promotion.'}
    niveau = normalize_niveau_lmd(args.get('niveau_lmd')) or eleve.classe.niveau_lmd
    periode = None
    if args.get('periode'):
        periode = _find_periode(ctx, args.get('periode'), niveau_lmd=niveau)
        if not periode:
            return {'erreur': f'Période introuvable pour « {args.get("periode")} ».'}
    totaux = _ects_pour_eleve(ctx, eleve, periode=periode)
    return {
        'etudiant': eleve.nom_complet,
        'classe': eleve.classe.nom,
        'niveau_lmd': eleve.classe.niveau_lmd or None,
        'periode': periode.nom_periode if periode else None,
        'invente': False,
        **totaux,
        'par_semestre': _ects_par_semestre(ctx, eleve),
    }


def tool_ects_classe(ctx, args):
    denied = _require_superieur(ctx)
    if denied:
        return denied
    args = args if isinstance(args, dict) else {}
    classe = _find_classe(ctx, args.get('classe') or args.get('query') or '')
    if not classe:
        return {'erreur': 'Indique la promotion dont tu veux la maquette ECTS.'}
    niveau = normalize_niveau_lmd(args.get('niveau_lmd')) or classe.niveau_lmd
    periode = None
    if args.get('periode'):
        periode = _find_periode(ctx, args.get('periode'), niveau_lmd=niveau)
    maquette_qs = _maquette_qs(classe)
    if periode:
        maquette_qs = maquette_qs.filter(Q(periode=periode) | Q(periode__isnull=True))
    maquette = [_serialize_module_classe(mc) for mc in maquette_qs.order_by(
        'numero_ue', 'module__nom'
    )[:MODULES_LIMIT]]
    credits_maquette = sum((mc.credits or Decimal('0')) for mc in maquette_qs)
    etudiants = []
    for eleve in _eleves_classe(ctx, classe).order_by('nom', 'prenom')[:ELEVES_LIMIT]:
        totaux = _ects_pour_eleve(ctx, eleve, periode=periode)
        etudiants.append({
            'etudiant': eleve.nom_complet,
            **totaux,
        })
    return {
        'classe': classe.nom,
        'niveau_lmd': classe.niveau_lmd or None,
        'periode': periode.nom_periode if periode else None,
        'credits_maquette': _safe(credits_maquette),
        'nb_modules': len(maquette),
        'maquette': maquette,
        'nb_etudiants': len(etudiants),
        'etudiants': etudiants,
        'invente': False,
    }


def tool_modules_classe(ctx, args):
    denied = _require_superieur(ctx)
    if denied:
        return denied
    args = args if isinstance(args, dict) else {}
    classe = _find_classe(ctx, args.get('classe') or args.get('query') or '')
    if not classe:
        return {'erreur': 'Indique la promotion dont tu veux les modules.'}
    items = [
        _serialize_module_classe(mc)
        for mc in _maquette_qs(classe).order_by('numero_ue', 'module__nom')[:MODULES_LIMIT]
    ]
    return {
        'classe': classe.nom,
        'niveau_lmd': classe.niveau_lmd or None,
        'nb': len(items),
        'credits_total': _safe(sum(
            Decimal(str(item['credits'] or 0)) for item in items
        )),
        'modules': items,
    }


def tool_releve_ects(ctx, args):
    denied = _require_superieur(ctx)
    if denied:
        return denied
    args = args if isinstance(args, dict) else {}
    query = (args.get('query') or args.get('etudiant') or '').strip()
    classe_label = (args.get('classe') or '').strip()
    if query:
        eleve = _find_etudiant(ctx, query)
        if not eleve:
            return {'erreur': f'Aucun étudiant trouvé pour « {query} ».'}
        if not eleve.classe_id:
            return {'erreur': f'{eleve.nom_complet} n’est rattaché à aucune promotion.'}
        totaux = tool_ects_etudiant(ctx, {'query': query, 'periode': args.get('periode')})
        url = _reverse('directeur:voir_bulletin_eleve', args=[eleve.classe_id, eleve.id])
        return {
            **totaux,
            'ouvrir': True,
            'url': url,
            'message': (
                f'Relevé ECTS de {eleve.nom_complet} : '
                f'{totaux.get("credits_valides") or 0} crédits validés sur '
                f'{totaux.get("credits_inscrits") or 0} inscrits.'
            ),
        }
    if classe_label:
        classe = _find_classe(ctx, classe_label)
        if not classe:
            return {'erreur': f'Promotion introuvable pour « {classe_label} ».'}
        url = _reverse('directeur:imprimer_releve_notes', args=[classe.id])
        return {
            'classe': classe.nom,
            'niveau_lmd': classe.niveau_lmd or None,
            'ouvrir': True,
            'url': url,
            'message': f'Ouverture du relevé de notes de {classe.nom}.',
        }
    return {'erreur': 'Indique un étudiant ou une promotion pour le relevé ECTS.'}


def tool_structure_superieur(ctx, args):
    denied = _require_superieur(ctx)
    if denied:
        return denied
    from school_admin.model.academic_structure_model import Department
    from school_admin.model.module_model import Module

    args = args if isinstance(args, dict) else {}
    query = (args.get('query') or '').strip()
    deps = Department.objects.filter(etablissement=ctx.etablissement)
    modules = Module.objects.filter(etablissement=ctx.etablissement).prefetch_related(
        'module_classes__classe',
        'module_classes__periode',
        'module_departments__department',
    )
    if query:
        deps = deps.filter(Q(nom__icontains=query) | Q(sigle__icontains=query))
        modules = modules.filter(Q(nom__icontains=query) | Q(code__icontains=query))

    module_items = []
    for module in modules.order_by('nom')[:20]:
        liaisons = list(module.module_classes.all())
        credits_total = sum((mc.credits or Decimal('0')) for mc in liaisons)
        ues = sorted({(mc.numero_ue or '').strip() for mc in liaisons if (mc.numero_ue or '').strip()})
        semestres = sorted({
            mc.periode.nom_periode for mc in liaisons if mc.periode_id
        })
        classes = sorted({mc.classe.nom for mc in liaisons if mc.classe_id})
        module_items.append({
            'nom': module.nom,
            'code': module.code,
            'niveau_lmd': module.niveau_lmd or None,
            'credits_totaux': _safe(credits_total) if liaisons else _safe(module.total_credits),
            'ues': ues,
            'semestres': semestres,
            'classes': classes,
            'specialites': [d.nom for d in module.get_linked_departments()],
        })
    return {
        'departements': [
            {'nom': dep.nom, 'sigle': dep.sigle or None}
            for dep in deps.order_by('ordre', 'nom')[:20]
        ],
        'modules': module_items,
    }


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

def prepare_affecter_module_classe(ctx, args):
    denied = _require_superieur(ctx)
    if denied:
        return denied
    args = args if isinstance(args, dict) else {}
    module = _find_module(ctx, args.get('module') or args.get('query') or args.get('nom'))
    if not module:
        return _incomplete(
            'affecter_module_classe',
            ['module'],
            'Quel module dois-je affecter ?',
        )
    classe = _find_classe(ctx, args.get('classe') or '')
    if not classe:
        return _incomplete(
            'affecter_module_classe',
            ['classe'],
            f'À quelle promotion rattacher « {module.nom} » ?',
        )
    credits = _parse_credits(args.get('credits'))
    if credits is None:
        return _incomplete(
            'affecter_module_classe',
            ['credits'],
            f'Combien de crédits ECTS pour {module.nom} en {classe.nom} ?',
            module=module.nom,
            classe=classe.nom,
        )
    numero_ue = (args.get('numero_ue') or args.get('ue') or '').strip()[:80]
    periode = None
    if args.get('periode') or args.get('semestre'):
        periode = _find_periode(
            ctx,
            args.get('periode') or args.get('semestre'),
            niveau_lmd=classe.niveau_lmd,
        )
        if not periode:
            return _incomplete(
                'affecter_module_classe',
                ['periode'],
                'Quel semestre ? (ex. Semestre 1 pour L1)',
                module=module.nom,
                classe=classe.nom,
                credits=str(credits),
            )
    resume = f'affecte {module.nom} à {classe.nom} ({credits} crédits'
    if numero_ue:
        resume += f', {numero_ue}'
    if periode:
        resume += f', {periode.nom_periode}'
    resume += ')'
    return _pending(
        'affecter_module_classe',
        resume,
        module_id=module.id,
        module=module.nom,
        classe_id=classe.id,
        classe=classe.nom,
        credits=str(credits),
        numero_ue=numero_ue,
        periode_id=periode.id if periode else None,
        periode=periode.nom_periode if periode else None,
    )


def apply_affecter_module_classe(ctx, draft):
    from school_admin.model.classe_model import Classe
    from school_admin.model.module_model import Module, ModuleClasse
    from school_admin.model.periode_model import PeriodeScolaire

    denied = _require_superieur(ctx)
    if denied:
        return denied
    module = Module.objects.filter(
        pk=draft.get('module_id'), etablissement=ctx.etablissement
    ).first()
    classe = Classe.objects.filter(
        pk=draft.get('classe_id'), etablissement=ctx.etablissement
    ).first()
    if not module or not classe:
        return _err('Module ou promotion introuvable.')
    credits = _parse_credits(draft.get('credits'))
    if credits is None:
        return _err('Crédits ECTS invalides.')
    periode = None
    if draft.get('periode_id'):
        periode = PeriodeScolaire.objects.filter(
            pk=draft['periode_id'], etablissement=ctx.etablissement
        ).first()
    mc, created = ModuleClasse.objects.update_or_create(
        module=module,
        classe=classe,
        defaults={
            'credits': credits,
            'numero_ue': (draft.get('numero_ue') or '')[:80],
            'periode': periode,
        },
    )
    verbe = 'affecté' if created else 'mis à jour'
    return _ok(
        f'Module {module.nom} {verbe} pour {classe.nom} ({credits} crédits).',
        id=mc.id,
        created=created,
    )


def prepare_fixer_credits_module(ctx, args):
    denied = _require_superieur(ctx)
    if denied:
        return denied
    args = args if isinstance(args, dict) else {}
    module = _find_module(ctx, args.get('module') or args.get('query') or args.get('nom'))
    if not module:
        return _incomplete('fixer_credits_module', ['module'], 'De quel module s’agit-il ?')
    classe = _find_classe(ctx, args.get('classe') or '')
    if not classe:
        liaisons = list(module.module_classes.select_related('classe')[:6])
        if len(liaisons) == 1:
            classe = liaisons[0].classe
        else:
            return _incomplete(
                'fixer_credits_module',
                ['classe'],
                f'Pour quelle promotion fixer les crédits de {module.nom} ?',
            )
    credits = _parse_credits(args.get('credits'))
    if credits is None:
        return _incomplete(
            'fixer_credits_module',
            ['credits'],
            f'Combien de crédits pour {module.nom} en {classe.nom} ?',
            module=module.nom,
            classe=classe.nom,
        )
    from school_admin.model.module_model import ModuleClasse

    mc = ModuleClasse.objects.filter(module=module, classe=classe).first()
    if not mc:
        return _err(
            f'{module.nom} n’est pas encore affecté à {classe.nom}. '
            'Utilise affecter_module_classe.'
        )
    return _pending(
        'fixer_credits_module',
        f'passe {module.nom} ({classe.nom}) de {mc.credits} à {credits} crédits',
        module_id=module.id,
        module=module.nom,
        classe_id=classe.id,
        classe=classe.nom,
        credits=str(credits),
        credits_avant=str(mc.credits),
        numero_ue=mc.numero_ue or '',
    )


def apply_fixer_credits_module(ctx, draft):
    from school_admin.model.module_model import Module, ModuleClasse
    from school_admin.model.classe_model import Classe

    denied = _require_superieur(ctx)
    if denied:
        return denied
    module = Module.objects.filter(
        pk=draft.get('module_id'), etablissement=ctx.etablissement
    ).first()
    classe = Classe.objects.filter(
        pk=draft.get('classe_id'), etablissement=ctx.etablissement
    ).first()
    credits = _parse_credits(draft.get('credits'))
    if not module or not classe or credits is None:
        return _err('Module, promotion ou crédits manquants.')
    mc = ModuleClasse.objects.filter(module=module, classe=classe).first()
    if not mc:
        return _err(f'{module.nom} n’est pas affecté à {classe.nom}.')
    avant = mc.credits
    mc.credits = credits
    mc.save(update_fields=['credits'])
    return _ok(
        f'Crédits de {module.nom} ({classe.nom}) : {avant} → {credits}.',
        id=mc.id,
    )


register_action(ActionSpec(
    'affecter_module_classe',
    'Affecte un module LMD à une promotion (crédits, UE, semestre).',
    {
        'module': _STR,
        'query': _STR,
        'nom': _STR,
        'classe': _CLASSE,
        'credits': {'type': 'string', 'description': 'Crédits ECTS (ex. 6)'},
        'numero_ue': {'type': 'string', 'description': 'Numéro d’UE (ex. UE3.1.1)'},
        'ue': _STR,
        'periode': {'type': 'string', 'description': 'Semestre (ex. Semestre 1)'},
        'semestre': _STR,
    },
    prepare=prepare_affecter_module_classe,
    apply=apply_affecter_module_classe,
))

register_action(ActionSpec(
    'fixer_credits_module',
    'Met à jour les crédits ECTS d’un module pour une promotion (ModuleClasse.credits).',
    {
        'module': _STR,
        'query': _STR,
        'nom': _STR,
        'classe': _CLASSE,
        'credits': {'type': 'string', 'description': 'Nouveau nombre de crédits'},
    },
    required=('credits',),
    prepare=prepare_fixer_credits_module,
    apply=apply_fixer_credits_module,
))


VAGUE4_READ_SCHEMA = [
    {
        'type': 'function',
        'function': {
            'name': 'get_ects_etudiant',
            'description': (
                'Crédits ECTS d’un étudiant : inscrits (maquette ModuleClasse), '
                'validés (MoyennePeriode.credits si déjà calculés), restants, '
                'détail par semestre. N’invente aucun crédit.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom ou matricule'},
                    'etudiant': _STR,
                    'periode': _STR,
                    'niveau_lmd': {'type': 'string', 'enum': NIVEAU_LMD_ENUM},
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_ects_classe',
            'description': (
                'Maquette ECTS d’une promotion (modules, UE, crédits, semestre) '
                'et validation par étudiant. N’invente aucun crédit.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': _CLASSE,
                    'periode': _STR,
                    'niveau_lmd': {'type': 'string', 'enum': NIVEAU_LMD_ENUM},
                },
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_modules_classe',
            'description': (
                'Modules d’une promotion : nom, crédits, numéro d’UE, semestre.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {'classe': _CLASSE},
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_releve_ects',
            'description': (
                'Résume et ouvre le relevé ECTS / bulletin d’un étudiant '
                '(URL existante, pas de PDF magique). Avec une classe : '
                'ouvre l’impression du relevé de la promotion.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom ou matricule'},
                    'etudiant': _STR,
                    'classe': _CLASSE,
                    'periode': _STR,
                    'ouvrir': {'type': 'boolean'},
                },
            },
        },
    },
]

VAGUE4_READ_HANDLERS = {
    'get_ects_etudiant': tool_ects_etudiant,
    'get_ects_classe': tool_ects_classe,
    'get_modules_classe': tool_modules_classe,
    'get_releve_ects': tool_releve_ects,
    'get_structure_superieur': tool_structure_superieur,
}
