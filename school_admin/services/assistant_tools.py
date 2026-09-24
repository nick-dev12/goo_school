"""
Outils ORM scopés à l'établissement pour l'assistant vocal directeur.
"""
import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from school_admin.services.assistant_search import CLASSE_PARAM_DESCRIPTION

logger = logging.getLogger(__name__)

SEARCH_LIMIT = 12
NOTES_LIMIT = 10
ANNONCE_CONTENU_MAX = 8000

DESTINATAIRE_VALIDES = {
    'tous',
    'enseignants',
    'parents',
    'eleves',
    'personnel_administratif',
}
DESTINATAIRE_ALIASES = {
    'tous': 'tous',
    'tout': 'tous',
    'toute': 'tous',
    'tout le monde': 'tous',
    'enseignants': 'enseignants',
    'enseignant': 'enseignants',
    'professeurs': 'enseignants',
    'professeur': 'enseignants',
    'profs': 'enseignants',
    'prof': 'enseignants',
    'parents': 'parents',
    'parent': 'parents',
    'eleves': 'eleves',
    'eleve': 'eleves',
    'élève': 'eleves',
    'élèves': 'eleves',
    'etudiants': 'eleves',
    'etudiant': 'eleves',
    'étudiants': 'eleves',
    'étudiant': 'eleves',
    'personnel': 'personnel_administratif',
    'personnel administratif': 'personnel_administratif',
    'administratif': 'personnel_administratif',
    'admin': 'personnel_administratif',
}


@dataclass
class AssistantContext:
    etablissement: object
    annee_scolaire: object
    est_superieur: bool
    est_primaire: bool
    libelle_eleve: str
    personnel: object = None
    professeur: object = None
    parent: object = None
    eleve: object = None
    eleve_consulte: object = None
    enfants_lies: list = None
    session_store: dict = None
    persona: str = 'directeur'
    affectations_resume: list = None
    est_college: bool = False
    est_lycee: bool = False
    est_college_lycee: bool = False
    cycle_requis: bool = False


def build_assistant_context(
    etablissement,
    session_store=None,
    personnel=None,
    professeur=None,
    parent=None,
    eleve=None,
    persona='directeur',
):
    """Construit le contexte établissement + session consultée."""
    from school_admin.model.annee_scolaire_model import AnneeScolaire

    session_store = session_store if session_store is not None else {}
    annee = None
    session_id = session_store.get('annee_scolaire_consultee_id')
    if session_id and etablissement:
        annee = AnneeScolaire.objects.filter(
            pk=session_id,
            etablissement=etablissement,
        ).first()
    if annee is None and etablissement:
        annee = AnneeScolaire.get_session_active(etablissement)

    from school_admin.services.assistant_schema import classify_etablissement

    eleve_consulte = None
    enfants_lies = None
    if persona == 'parent' and parent:
        from school_admin.services.assistant_parent_scope import (
            eleve_depuis_session,
            etablissement_effectif,
            resume_enfants,
        )

        eleve_consulte = eleve_depuis_session(parent, session_store)
        enfants_lies = resume_enfants(parent)
        etab_ref = etablissement_effectif(parent, eleve_consulte) or etablissement
        if etab_ref and (not etablissement or etab_ref.pk != getattr(etablissement, 'pk', None)):
            etablissement = etab_ref
            if annee is None:
                annee = AnneeScolaire.get_session_active(etablissement)

    if persona == 'eleve' and eleve:
        etab_ref = getattr(eleve, 'etablissement', None)
        if etab_ref and (not etablissement or etab_ref.pk != getattr(etablissement, 'pk', None)):
            etablissement = etab_ref
            if annee is None:
                annee = AnneeScolaire.get_session_active(etablissement)

    flags = classify_etablissement(etablissement) if etablissement else {
        'est_superieur': False,
        'est_primaire': False,
        'est_college': False,
        'est_lycee': False,
        'est_college_lycee': False,
        'cycle_requis': False,
    }
    ctx = AssistantContext(
        etablissement=etablissement,
        annee_scolaire=annee,
        est_superieur=flags['est_superieur'],
        est_primaire=flags['est_primaire'],
        libelle_eleve='étudiant' if flags['est_superieur'] else 'élève',
        personnel=personnel,
        professeur=professeur,
        parent=parent,
        eleve=eleve,
        eleve_consulte=eleve_consulte,
        enfants_lies=enfants_lies or [],
        session_store=session_store,
        persona=persona or 'directeur',
        affectations_resume=None,
        est_college=flags['est_college'],
        est_lycee=flags['est_lycee'],
        est_college_lycee=flags['est_college_lycee'],
        cycle_requis=flags['cycle_requis'],
    )
    if ctx.persona in ('enseignant_primaire', 'enseignant') and ctx.professeur:
        from school_admin.services.assistant_enseignant_scope import affectations_summary

        ctx.affectations_resume = affectations_summary(ctx)
    return ctx


def context_snapshot(ctx):
    """Résumé court injecté dans le system prompt."""
    etab = ctx.etablissement
    payload = {
        'nom': etab.nom,
        'code': etab.code_etablissement,
        'type': etab.type_etablissement,
        'ville': etab.ville,
        'pays': etab.pays,
        'session': ctx.annee_scolaire.libelle if ctx.annee_scolaire else None,
        'libelle_apprenant': ctx.libelle_eleve,
        'est_superieur': ctx.est_superieur,
        'est_primaire': ctx.est_primaire,
        'est_college': getattr(ctx, 'est_college', False),
        'est_lycee': getattr(ctx, 'est_lycee', False),
        'est_college_lycee': getattr(ctx, 'est_college_lycee', False),
        'cycle_requis': getattr(ctx, 'cycle_requis', False),
        'persona': getattr(ctx, 'persona', 'directeur'),
    }
    if getattr(ctx, 'persona', 'directeur') == 'parent' and getattr(ctx, 'parent', None):
        par = ctx.parent
        payload['parent'] = getattr(par, 'nom_complet', None) or f'{par.prenom} {par.nom}'
        payload['enfants_lies'] = getattr(ctx, 'enfants_lies', None) or []
        if getattr(ctx, 'eleve_consulte', None):
            el = ctx.eleve_consulte
            payload['enfant_consulte'] = {
                'id': el.id,
                'nom': getattr(el, 'nom_complet', None) or f'{el.prenom} {el.nom}',
            }
    if getattr(ctx, 'persona', 'directeur') == 'eleve' and getattr(ctx, 'eleve', None):
        el = ctx.eleve
        payload['eleve'] = getattr(el, 'nom_complet', None) or f'{el.prenom} {el.nom}'
        if getattr(el, 'classe_id', None) and el.classe:
            payload['classe'] = el.classe.nom
    if getattr(ctx, 'persona', 'directeur') in ('enseignant_primaire', 'enseignant') and ctx.professeur:
        prof = ctx.professeur
        payload['professeur'] = getattr(prof, 'nom_complet', None) or f'{prof.prenom} {prof.nom}'
        payload['affectations'] = getattr(ctx, 'affectations_resume', None) or []
    return payload


def _inscrits_ids(ctx):
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    if not ctx.annee_scolaire:
        return None
    return list(
        InscriptionEleve.objects.filter(
            annee_scolaire=ctx.annee_scolaire,
            etablissement=ctx.etablissement,
            eleve_id__isnull=False,
        ).values_list('eleve_id', flat=True)
    )


def _eleves_qs(ctx):
    from school_admin.model.eleve_model import Eleve

    qs = Eleve.objects.filter(etablissement=ctx.etablissement, actif=True)
    ids = _inscrits_ids(ctx)
    if ids is not None:
        qs = qs.filter(id__in=ids)
    return qs


def _eleve_name_filter(query):
    raw = (query or '').strip()
    if not raw:
        return Q()
    tokens = [part for part in re.split(r'\s+', raw) if part]
    combined = Q()
    for token in tokens:
        piece = (
            Q(nom__icontains=token)
            | Q(prenom__icontains=token)
            | Q(matricule_eleve__icontains=token)
        )
        combined = piece if not combined else combined & piece
    return combined


def _find_eleve(ctx, query):
    from school_admin.model.eleve_model import Eleve

    if not query:
        return None
    name_q = _eleve_name_filter(query)
    found = _eleves_qs(ctx).select_related('classe').filter(name_q).first()
    if found:
        return found
    return Eleve.objects.filter(
        etablissement=ctx.etablissement,
        actif=True,
    ).filter(name_q).select_related('classe').first()


def _find_classe(ctx, query):
    from school_admin.services.assistant_search import find_classe

    return find_classe(ctx, query)


def _safe_decimal(value):
    if value is None:
        return None
    return float(value)


def _count_by_sexe(qs):
    return qs.aggregate(
        total=Count('id'),
        filles=Count('id', filter=Q(sexe='F')),
        garcons=Count('id', filter=Q(sexe='M')),
        non_renseigne=Count('id', filter=~Q(sexe__in=['F', 'M'])),
    )


def tool_effectifs(ctx, args):
    from school_admin.model.classe_model import Classe
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    from school_admin.model.professeur_model import Professeur

    args = args if isinstance(args, dict) else {}
    classe = _find_classe(ctx, (args.get('classe') or args.get('query') or '').strip())
    eleves = _eleves_qs(ctx)
    if classe:
        eleves = eleves.filter(classe=classe)
    sexes = _count_by_sexe(eleves)

    classes = Classe.objects.filter(etablissement=ctx.etablissement, actif=True)
    par_classe = []
    if classe:
        capacite = classe.capacite_max or 0
        par_classe.append({
            'nom': classe.nom,
            'niveau': classe.get_niveau_display(),
            'effectif': sexes['total'],
            'filles': sexes['filles'],
            'garcons': sexes['garcons'],
            'capacite_max': capacite,
            'places_libres': max(0, capacite - (sexes['total'] or 0)),
        })
        capacite_totale = capacite
        places_libres = max(0, capacite - (sexes['total'] or 0))
    else:
        capacite_totale = classes.aggregate(cap=Sum('capacite_max'))['cap'] or 0
        places_libres = max(0, capacite_totale - (sexes['total'] or 0))
        rows = (
            eleves.filter(classe_id__isnull=False)
            .values('classe__nom', 'classe__niveau', 'classe__capacite_max')
            .annotate(
                effectif=Count('id'),
                filles=Count('id', filter=Q(sexe='F')),
                garcons=Count('id', filter=Q(sexe='M')),
            )
            .order_by('classe__niveau', 'classe__nom')[:30]
        )
        for row in rows:
            cap = row['classe__capacite_max'] or 0
            par_classe.append({
                'nom': row['classe__nom'],
                'effectif': row['effectif'],
                'filles': row['filles'],
                'garcons': row['garcons'],
                'capacite_max': cap,
                'places_libres': max(0, cap - (row['effectif'] or 0)),
            })

    payload = {
        'session': ctx.annee_scolaire.libelle if ctx.annee_scolaire else None,
        'perimetre': classe.nom if classe else 'etablissement',
        'nb_eleves_actifs': sexes['total'],
        'nb_filles': sexes['filles'],
        'nb_garcons': sexes['garcons'],
        'nb_sexe_non_renseigne': sexes['non_renseigne'],
        'nb_classes': classes.count(),
        'nb_professeurs': Professeur.objects.filter(
            etablissement=ctx.etablissement, actif=True
        ).count(),
        'nb_personnel': PersonnelAdministratif.objects.filter(
            etablissement=ctx.etablissement, actif=True
        ).count(),
        'capacite_totale': capacite_totale,
        'places_libres': places_libres,
        'classes': par_classe,
    }
    if classe:
        payload['classe'] = classe.nom
        payload['classe_id'] = classe.id
    return payload


def tool_rechercher_eleves(ctx, args):
    query = (args.get('query') or '').strip()
    classe_nom = (args.get('classe') or '').strip()
    qs = _eleves_qs(ctx).select_related('classe')
    if query:
        qs = qs.filter(_eleve_name_filter(query))
    if classe_nom:
        qs = qs.filter(classe__nom__icontains=classe_nom)
    results = []
    for eleve in qs.order_by('nom', 'prenom')[:SEARCH_LIMIT]:
        results.append({
            'id': eleve.id,
            'nom': eleve.nom_complet,
            'matricule': eleve.matricule_eleve,
            'classe': eleve.classe.nom if eleve.classe_id else None,
            'classe_id': eleve.classe_id,
        })
    return {'nb_trouves': qs.count(), 'eleves': results}


def _classes_qs(ctx):
    from school_admin.model.classe_model import Classe

    return Classe.objects.filter(
        etablissement=ctx.etablissement,
        actif=True,
    ).select_related('department', 'academic_level')


def _classe_item(ctx, classe):
    item = {
        'id': classe.id,
        'nom': classe.nom,
        'niveau': classe.get_niveau_display(),
        'code': classe.code_classe,
        'effectif': _eleves_qs(ctx).filter(classe=classe).count(),
        'capacite_max': classe.capacite_max,
        'url': _classe_url(classe),
    }
    if ctx.est_superieur:
        item['niveau_lmd'] = classe.niveau_lmd or None
        if classe.department_id:
            item['departement'] = classe.department.nom
            item['sigle'] = classe.department.sigle or None
        extras = []
        if classe.niveau_lmd:
            extras.append(classe.niveau_lmd)
        if classe.department_id:
            extras.append(classe.department.sigle or classe.department.nom)
        if extras:
            item['libelle'] = f"{classe.nom} — {' '.join(extras)}"
        else:
            item['libelle'] = classe.nom
    item.setdefault('libelle', classe.nom)
    return item


def _classe_url(classe):
    from django.urls import reverse

    return reverse('administrateur_etablissement:detail_classe', args=[classe.id])


def list_classe_choices(ctx, limit=5):
    """Propose des classes cliquables quand l’utilisateur n’a pas précisé laquelle."""
    classes = list(_classes_qs(ctx).order_by('niveau', 'nom')[:limit])
    return [
        {
            'label': classe.nom,
            'value': f'Ouvre la classe {classe.nom}',
            'url': _classe_url(classe),
            'intent': 'open',
        }
        for classe in classes
    ]


def tool_rechercher_classes(ctx, args):
    from school_admin.services.assistant_search import search_classes

    query = (args.get('query') or '').strip()
    if query:
        result = search_classes(ctx, query, limit=SEARCH_LIMIT)
        items = result.get('classes') or []
        if result.get('statut') == 'ok':
            items = [{
                key: result[key]
                for key in (
                    'id', 'nom', 'niveau', 'code', 'effectif',
                    'capacite_max', 'url', 'niveau_lmd',
                    'departement', 'sigle', 'libelle',
                )
                if key in result
            }]
        return {
            'classes': items,
            'trouve': bool(items),
            'query_normalisee': result.get('query_normalisee'),
            'suggestions_possibles': result.get('suggestions_possibles') or items,
        }
    items = [_classe_item(ctx, classe) for classe in _classes_qs(ctx).order_by('niveau', 'nom')[:SEARCH_LIMIT]]
    return {'classes': items}


def _normalize_class_query(query):
    text = (query or '').strip()
    text = re.sub(r'(\d+)\s*(?:e|è|eme|ème)\b', r'\1ème', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text)
    return text


def tool_ouvrir_classe(ctx, args):
    """Trouve une classe et renvoie l’URL de sa fiche pour navigation."""
    from school_admin.services.assistant_search import search_classes

    query = (args.get('query') or args.get('classe') or '').strip()
    result = search_classes(ctx, query)
    if result.get('statut') == 'ok':
        ouvrir = args.get('ouvrir')
        if ouvrir is None:
            ouvrir = True
        result['ouvrir'] = bool(ouvrir)
        result['titre'] = result.get('nom')
        return result
    return result


def tool_rechercher_professeurs(ctx, args):
    from school_admin.model.professeur_model import Professeur

    query = (args.get('query') or '').strip()
    qs = Professeur.objects.filter(
        etablissement=ctx.etablissement, actif=True
    ).select_related('matiere_principale')
    if query:
        qs = qs.filter(
            Q(nom__icontains=query)
            | Q(prenom__icontains=query)
            | Q(numero_employe__icontains=query)
        )
    items = []
    for prof in qs.order_by('nom', 'prenom')[:SEARCH_LIMIT]:
        items.append({
            'nom': f'{prof.prenom} {prof.nom}',
            'matiere': prof.matiere_principale.nom if prof.matiere_principale_id else None,
            'telephone': prof.telephone,
        })
    return {'professeurs': items}


def _classe_nom(classe):
    if not classe:
        return ''
    return getattr(classe, 'nom', '') or str(classe)


def _professeur_nom(prof):
    if not prof:
        return ''
    return getattr(prof, 'nom_complet', None) or f'{prof.prenom} {prof.nom}'.strip()


def _serialize_affectation_row(affectation, primaire=False):
    prof = getattr(affectation, 'professeur', None)
    classe = getattr(affectation, 'classe', None)
    row = {
        'professeur': _professeur_nom(prof),
        'classe': _classe_nom(classe),
        'statut': affectation.get_statut_display() if hasattr(affectation, 'get_statut_display') else '',
        'actif': bool(getattr(affectation, 'actif', True)),
    }
    if primaire:
        matieres = list(affectation.matieres.all()) if hasattr(affectation, 'matieres') else []
        row['matiere'] = ', '.join(m.nom for m in matieres if getattr(m, 'nom', None)) or None
    else:
        matiere = getattr(affectation, 'matiere', None)
        row['matiere'] = matiere.nom if matiere else None
    return row


def _queryset_affectations(ctx, prof=None, classe=None):
    annee = ctx.annee_scolaire
    est_primaire = getattr(ctx.etablissement, 'type_etablissement', '') == 'primary'
    if est_primaire:
        from school_admin.model.affectation_professeur_primaire_model import (
            AffectationProfesseurPrimaire,
        )

        qs = AffectationProfesseurPrimaire.objects.filter(
            professeur__etablissement=ctx.etablissement,
            actif=True,
        ).select_related('professeur', 'classe').prefetch_related('matieres')
    else:
        from school_admin.model.affectation_model import AffectationProfesseur

        qs = AffectationProfesseur.objects.filter(
            professeur__etablissement=ctx.etablissement,
            actif=True,
        ).select_related('professeur', 'classe', 'matiere')
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    else:
        qs = qs.none()
    if prof:
        qs = qs.filter(professeur=prof)
    if classe:
        qs = qs.filter(classe=classe)
    return qs, est_primaire


def tool_affectations(ctx, args):
    """Liste les affectations actives de l'année scolaire en cours."""
    from school_admin.model.professeur_model import Professeur
    from school_admin.services.assistant_staff import _find_professeur

    args = args if isinstance(args, dict) else {}
    query = (args.get('query') or args.get('professeur') or args.get('question') or '').strip()
    classe_query = (args.get('classe') or '').strip()
    if not ctx.annee_scolaire:
        return {
            'trouve': False,
            'erreur': (
                "Aucune année scolaire active. Activez une année pour voir "
                "les affectations."
            ),
            'affectations': [],
            'nb_affectations': 0,
        }

    look_name = query
    lowered = query.lower()
    if 'affectation' in lowered or 'liste' in lowered:
        from school_admin.services.assistant_intents import _extract_person_query

        candidate = (_extract_person_query(query) or '').strip()
        if candidate.lower() in (
            'professeur', 'professeurs', 'enseignant', 'enseignants',
            'classe', 'classes',
        ):
            candidate = ''
        look_name = candidate
    prof = _find_professeur(ctx, look_name) if look_name else None
    classe = _find_classe(ctx, classe_query) if classe_query else None
    qs, primaire = _queryset_affectations(ctx, prof=prof, classe=classe)
    rows = [_serialize_affectation_row(item, primaire=primaire) for item in qs[:80]]
    affectes_ids = set(qs.values_list('professeur_id', flat=True).distinct())
    total_profs = Professeur.objects.filter(
        etablissement=ctx.etablissement, actif=True
    ).count()
    sans = []
    if not prof and not classe:
        sans_qs = Professeur.objects.filter(
            etablissement=ctx.etablissement, actif=True
        ).exclude(pk__in=affectes_ids).order_by('nom', 'prenom')
        sans = [_professeur_nom(item) for item in sans_qs[:20]]
    try:
        from django.urls import reverse

        url = reverse('affectation:affectation_professeurs')
    except Exception:
        url = '/affectation/professeurs/'
    return {
        'trouve': True,
        'annee': str(ctx.annee_scolaire),
        'nb_affectations': qs.count(),
        'nb_professeurs_affectes': len(affectes_ids),
        'nb_professeurs_sans_affectation': max(0, total_profs - len(affectes_ids)),
        'filtre_professeur': _professeur_nom(prof) if prof else None,
        'filtre_classe': _classe_nom(classe) if classe else None,
        'affectations': rows,
        'sans_affectation': sans,
        'url': url,
    }


def spoken_from_affectations(result):
    """Résumé oral des affectations, sans markdown."""
    data = result or {}
    if data.get('erreur'):
        return data['erreur']
    items = data.get('affectations') or []
    nb = data.get('nb_affectations') or len(items)
    if not items:
        cible = data.get('filtre_professeur') or data.get('filtre_classe')
        if cible:
            return f"Je ne trouve aucune affectation active pour {cible} cette année."
        return (
            "Je ne trouve aucune affectation active pour cette année scolaire. "
            "Vous pouvez en créer depuis la page d’affectation des professeurs."
        )
    parts = [f"Il y a {nb} affectation{'s' if nb > 1 else ''} active{'s' if nb > 1 else ''}."]
    for item in items[:12]:
        nom = item.get('professeur') or 'Un professeur'
        classe = item.get('classe') or 'une classe'
        matiere = item.get('matiere')
        if matiere:
            parts.append(f"{nom} enseigne {matiere} en {classe}.")
        else:
            parts.append(f"{nom} est affecté à {classe}.")
    rest = nb - min(12, len(items))
    if rest > 0:
        parts.append(f"Et {rest} autres.")
    sans = data.get('nb_professeurs_sans_affectation') or 0
    if sans and not data.get('filtre_professeur') and not data.get('filtre_classe'):
        parts.append(f"{sans} professeur{'s' if sans > 1 else ''} n’a encore aucune classe.")
    return ' '.join(parts)


def spoken_from_tool_results(tool_results, ctx=None):
    """Repli oral : combine les outils parlants du tour (effectifs + listes)."""
    parts = []
    for item in tool_results or []:
        if not item:
            continue
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            name, result = item[0], item[1]
        else:
            continue
        spoken = spoken_from_tool_result(name, result, ctx=ctx)
        if spoken and spoken not in parts:
            parts.append(spoken)
    return ' '.join(parts)


CLASS_SNAPSHOT_TOOLS_DIRECTEUR = (
    'get_effectifs',
    'rechercher_eleves',
    'get_affectations',
)
CLASS_SNAPSHOT_TOOLS_ENSEIGNANT = ('get_effectifs', 'rechercher_eleves')
THIN_CLASS_TOOLS_DIRECTEUR = frozenset({'ouvrir_classe', 'get_affectations'})
THIN_CLASS_TOOLS_ENSEIGNANT = frozenset({'ouvrir_classe', 'get_mes_classes'})


def looks_like_class_info(question):
    text = (question or '').lower()
    return any(
        token in text
        for token in (
            'information',
            'informations',
            'infos',
            'détail',
            'detail',
            'de cette classe',
        )
    )


def enrich_class_snapshot(ctx, tool_results, refs=None, question=''):
    """Si le tour n’a que l’ouverture / les profs, complète effectifs + élèves."""
    extra = [item for item in (tool_results or []) if item]
    names = {
        item[0]
        for item in extra
        if isinstance(item, (tuple, list)) and item
    }
    classe = ((refs or {}).get('classe') or '').strip()
    if not ctx or not classe:
        return extra
    persona = getattr(ctx, 'persona', 'directeur')
    if persona in ('parent', 'eleve'):
        return extra
    if persona in ('enseignant_primaire', 'enseignant'):
        snapshot_tools = CLASS_SNAPSHOT_TOOLS_ENSEIGNANT
        thin_tools = THIN_CLASS_TOOLS_ENSEIGNANT
    else:
        snapshot_tools = CLASS_SNAPSHOT_TOOLS_DIRECTEUR
        thin_tools = THIN_CLASS_TOOLS_DIRECTEUR
    thin = bool(names) and names <= thin_tools
    if not thin and not looks_like_class_info(question):
        return extra
    if not thin and set(snapshot_tools).issubset(names):
        return extra
    for name in snapshot_tools:
        if name in names:
            continue
        try:
            extra.append((name, execute_tool(ctx, name, {'classe': classe})))
        except Exception:
            logger.exception('Repli fiche classe, outil %s', name)
    return extra


def _suggestions_after_read_enseignant(tool_results, refs=None, ctx=None):
    names = {
        item[0]
        for item in (tool_results or [])
        if isinstance(item, (tuple, list)) and item
    }
    classe = ((refs or {}).get('classe') or '').strip()
    items = []
    if 'get_eleves_difficulte' in names or any(
        isinstance(item, (tuple, list))
        and isinstance(item[1], dict)
        and item[1].get('source') == 'difficulte'
        for item in (tool_results or [])
        if item
    ):
        items = [
            {
                'label': 'Toute la classe',
                'value': f'Cite-moi les élèves de {classe}.' if classe else 'Liste les élèves.',
            },
            {
                'label': 'Les notes',
                'value': f'Les notes de {classe}.' if classe else 'Montre les notes.',
            },
            {
                'label': 'Présences',
                'value': f'Les absences en {classe}.' if classe else 'Les présences cette semaine.',
            },
        ]
    elif 'get_mes_classes' in names and not (
        names & {'ouvrir_classe', 'get_effectifs', 'rechercher_eleves'}
    ):
        items = [
            {
                'label': f'Ouvre {classe}' if classe else 'Ouvre une classe',
                'value': f'Ouvre {classe}.' if classe else 'Ouvre ma première classe.',
            },
            {'label': 'Effectifs', 'value': 'Quels sont les effectifs ?'},
            {'label': 'Évaluations', 'value': 'Mes prochaines évaluations.'},
        ]
    elif names & {
        'ouvrir_classe', 'get_effectifs', 'rechercher_eleves', 'get_mes_classes',
    }:
        items = [
            {
                'label': 'Élèves',
                'value': f'Cite-moi les élèves de {classe}.' if classe else 'Liste les élèves.',
            },
            {
                'label': 'Notes',
                'value': f'Les notes de {classe}.' if classe else 'Les notes.',
            },
            {
                'label': 'Appel',
                'value': f'Présence du jour en {classe}.' if classe else 'Faire l’appel.',
            },
        ]
    elif names & {'get_evaluations_classe', 'get_notes_classe'}:
        items = [
            {'label': 'Noter', 'value': f'Je veux noter {classe}.' if classe else 'Noter une classe.'},
            {'label': 'Difficulté', 'value': 'Élèves en difficulté.'},
            {'label': 'Moyennes', 'value': f'Calcule les moyennes de {classe}.' if classe else 'Calcule les moyennes.'},
        ]
    elif names & {'get_examens_prof', 'get_notes_examen', 'ouvrir_noter_examen'}:
        items = [
            {
                'label': 'Noter',
                'value': f'Noter l\'examen en {classe}.' if classe else 'Ouvrir noter examen.',
            },
            {'label': 'Notes examen', 'value': 'Les notes d\'examen de la classe.'},
            {'label': 'Sessions', 'value': 'Quelles sessions d\'examen ?'},
        ]
    elif ctx and getattr(ctx, 'est_superieur', False) and names & {
        'get_modules_classe', 'get_credits_etudiant',
    }:
        items = [
            {
                'label': 'Modules',
                'value': f'Quels modules en {classe} ?' if classe else 'Modules de ma promotion.',
            },
            {'label': 'Crédits', 'value': 'Crédits d’un étudiant.'},
            {'label': 'Évaluation', 'value': f'Créer une évaluation en {classe}.' if classe else 'Créer une évaluation.'},
        ]
    return normalize_suggestions(items, limit=3)


def suggestions_after_read(tool_results, refs=None, ctx=None):
    """2–3 puces de suite, même si Gemini n’a pas appelé proposer_actions."""
    if ctx and getattr(ctx, 'persona', 'directeur') == 'parent':
        from school_admin.services.assistant_parent_tools import suggestions_after_parent_read

        sugg = suggestions_after_parent_read(tool_results)
        if sugg:
            return sugg
    if ctx and getattr(ctx, 'persona', 'directeur') == 'eleve':
        from school_admin.services.assistant_eleve_tools import suggestions_after_eleve_read

        sugg = suggestions_after_eleve_read(tool_results)
        if sugg:
            return sugg
    if ctx and getattr(ctx, 'persona', 'directeur') in ('enseignant_primaire', 'enseignant'):
        return _suggestions_after_read_enseignant(tool_results, refs, ctx=ctx)
    names = {
        item[0]
        for item in (tool_results or [])
        if isinstance(item, (tuple, list)) and item
    }
    classe = ((refs or {}).get('classe') or '').strip()
    items = []
    if 'get_eleves_difficulte' in names or any(
        isinstance(item, (tuple, list))
        and isinstance(item[1], dict)
        and item[1].get('source') == 'difficulte'
        for item in (tool_results or [])
        if item
    ):
        items = [
            {
                'label': 'Toute la classe',
                'value': f'Cite-moi les élèves de {classe}.' if classe else 'Liste les élèves.',
            },
            {
                'label': 'Les notes',
                'value': f'Les notes de {classe}.' if classe else 'Montre les notes.',
            },
            {'label': 'Annonce parents', 'value': 'Prépare une annonce aux parents.'},
        ]
    elif 'rechercher_classes' in names and not (
        names & {'ouvrir_classe', 'get_effectifs', 'rechercher_eleves'}
    ):
        items = [
            {
                'label': f'Ouvre {classe}' if classe else 'Ouvre une classe',
                'value': f'Ouvre {classe}.' if classe else 'Ouvre la première classe.',
            },
            {'label': 'Effectifs', 'value': 'Quels sont les effectifs ?'},
            {
                'label': 'Impayés',
                'value': f'Il y a des impayés en {classe} ?' if classe else 'Quels sont les impayés ?',
            },
        ]
    elif names & {
        'ouvrir_classe', 'get_effectifs', 'rechercher_eleves', 'get_affectations',
    }:
        items = [
            {
                'label': 'Élèves',
                'value': f'Cite-moi les élèves de {classe}.' if classe else 'Liste les élèves.',
            },
            {
                'label': 'Notes',
                'value': f'Les notes de {classe}.' if classe else 'Les notes.',
            },
            {
                'label': 'Impayés',
                'value': f'Il y a des impayés en {classe} ?' if classe else 'Quels sont les impayés ?',
            },
        ]
    elif 'get_impayes' in names:
        items = [
            {'label': 'Relancer', 'value': 'Relance les familles.'},
            {'label': 'Ouvrir une fiche', 'value': 'Ouvre la fiche du plus élevé.'},
            {'label': 'Caisse', 'value': 'Et la caisse du mois ?'},
        ]
    return normalize_suggestions(items, limit=3)


def spoken_from_tool_result(name, result, ctx=None):
    if name == 'get_affectations' or (
        isinstance(result, dict) and result.get('source') == 'affectations'
    ):
        return spoken_from_affectations(result)
    persona = getattr(ctx, 'persona', 'directeur') if ctx else 'directeur'
    if persona == 'parent':
        from school_admin.services.assistant_parent_tools import spoken_from_parent_tool

        spoken = spoken_from_parent_tool(name, result)
        if spoken:
            return spoken
    if persona == 'eleve':
        from school_admin.services.assistant_eleve_tools import spoken_from_eleve_tool

        spoken = spoken_from_eleve_tool(name, result)
        if spoken:
            return spoken
    if persona == 'enseignant_primaire':
        from school_admin.services.assistant_enseignant_primaire_tools import (
            spoken_from_enseignant_tool,
        )

        spoken = spoken_from_enseignant_tool(name, result)
        if spoken:
            return spoken
    if persona == 'enseignant':
        from school_admin.services.assistant_enseignant_secondaire_tools import (
            spoken_from_enseignant_tool,
        )

        spoken = spoken_from_enseignant_tool(name, result)
        if spoken:
            return spoken
    if not isinstance(result, dict):
        return ''
    # get_effectifs.classes est un détail : on dit d’abord les totaux (50 / 5 / 7).
    if name == 'get_effectifs':
        summary = _spoken_read_summary(name, result)
        if summary:
            return summary
    listed = _spoken_name_list(result)
    if listed:
        return listed
    text = (result.get('message') or result.get('erreur') or '').strip()
    if text:
        if (
            name == 'get_eleves_difficulte' or result.get('source') == 'difficulte'
        ) and not result.get('nb') and 'Je peux' not in text:
            text += ' Je peux lister toute la classe ou ouvrir les notes.'
        return text
    return _spoken_read_summary(name, result)


def _spoken_name_list(result, limit=12):
    for key in ('eleves', 'professeurs', 'personnel', 'classes'):
        items = result.get(key)
        if not isinstance(items, list) or not items:
            continue
        names = []
        for item in items:
            if isinstance(item, dict):
                label = (
                    item.get('nom')
                    or item.get('nom_complet')
                    or item.get('eleve')
                    or ''
                ).strip()
            else:
                label = str(item).strip()
            if label:
                names.append(label)
        if not names:
            continue
        shown = names[:limit]
        text = ', '.join(shown)
        extra = len(names) - len(shown)
        if extra > 0:
            text += f', et {extra} autres'
        total = result.get('nb_trouves') or len(names)
        if key == 'eleves':
            return f'Voici {total} élèves : {text}.'
        if key == 'professeurs':
            return f'Voici {len(names)} professeurs : {text}.'
        if key == 'classes':
            word = 'classe' if len(names) == 1 else 'classes'
            return f'Voici {len(names)} {word} : {text}.'
        return f'Voici {len(names)} membres du personnel : {text}.'
    return ''


def _spoken_amount(value):
    if value in (None, ''):
        return ''
    text = str(value).strip()
    return text.replace('.00', '') if text.endswith('.00') else text


def _spoken_read_summary(name, result):
    """Repli chiffré si Gemini se tait après un outil de lecture réussi."""
    if not isinstance(result, dict):
        return ''
    if name == 'get_effectifs':
        total = result.get('nb_eleves_actifs')
        if total is None:
            return ''
        classe = result.get('classe') or ''
        filles = result.get('nb_filles')
        garcons = result.get('nb_garcons')
        if classe:
            extra = ''
            if filles is not None and garcons is not None:
                extra = f' ({filles} filles, {garcons} garçons)'
            return f'La {classe} compte {total} élèves{extra}.'
        classes = result.get('nb_classes')
        profs = result.get('nb_professeurs')
        parts = [f'L’établissement compte {total} élèves actifs']
        if classes is not None:
            parts.append(f'{classes} classes')
        if profs is not None:
            parts.append(f'{profs} professeurs')
        return f'{parts[0]}, {", ".join(parts[1:])}.' if len(parts) > 1 else f'{parts[0]}.'
    if name == 'get_impayes':
        nb = result.get('nb')
        if nb is None:
            return ''
        perimetre = result.get('perimetre') or 'l’établissement'
        if perimetre == 'etablissement':
            perimetre = 'l’établissement'
        reste = _spoken_amount(result.get('total_reste'))
        if not nb:
            return f'Aucun impayé pour {perimetre}.'
        phrase = f'Il y a {nb} impayé{"s" if nb > 1 else ""} pour {perimetre}'
        if reste:
            phrase += f', soit {reste} restant'
        return phrase + '. Je peux relancer les familles ou ouvrir une fiche.'
    if name == 'get_caisse':
        mois = result.get('mois')
        solde = _spoken_amount(result.get('solde'))
        if not mois and solde == '':
            return ''
        entrees = _spoken_amount(result.get('entrees'))
        sorties = _spoken_amount(result.get('sorties'))
        devise = result.get('devise') or ''
        suffix = f' {devise}' if devise else ''
        return (
            f'Pour {mois or "ce mois"}, les entrées sont de {entrees}{suffix}, '
            f'les sorties de {sorties}{suffix}, solde {solde}{suffix}.'
        )
    if name in ('get_notes_classe', 'get_notes_examen'):
        nb = result.get('nb')
        classe = result.get('classe') or 'cette classe'
        label = 'notes d’examen' if name == 'get_notes_examen' else 'notes publiées'
        if not nb:
            return f'Aucune {label} pour {classe}.'
        return f'J’ai {nb} {label} pour {classe}.'
    if name == 'get_emploi_du_temps':
        classe = result.get('classe') or 'cette classe'
        creneaux = result.get('creneaux') or []
        if not creneaux:
            return f'Aucun emploi du temps actif pour {classe}.'
        statut = result.get('statut')
        phrase = f'L’emploi du temps de {classe} a {len(creneaux)} créneau{"x" if len(creneaux) > 1 else ""}.'
        if statut:
            phrase += f' Statut : {statut}.'
        return phrase
    if name == 'ouvrir_classe':
        nom = result.get('nom') or result.get('titre') or result.get('classe')
        if not nom:
            return ''
        effectif = result.get('effectif')
        if effectif is not None:
            return f'J’ouvre {nom}, {effectif} élèves.'
        return f'J’ouvre {nom}.'
    if name == 'rechercher_classes':
        return 'Je ne trouve aucune classe.'
    if name == 'rechercher_eleves':
        return 'Je ne trouve aucun élève.'
    if name == 'rechercher_professeurs':
        return 'Je ne trouve aucun professeur.'
    if result.get('statut') == 'en_attente_confirmation':
        titre = (result.get('titre') or result.get('resume') or '').strip()
        if titre:
            return f'J’ai préparé « {titre} ». C’est bon ?'
        return 'J’ai préparé l’action. C’est bon ?'
    return ''


def json_safe_tool_result(payload):
    """Dict JSON-safe pour Gemini function_response (évite Decimal / date / ValidationError)."""
    if not isinstance(payload, dict):
        return {'result': str(payload)}
    try:
        return json.loads(dumps_tool_result(payload))
    except Exception:
        return {'ok': True}


def tool_rechercher_personnel(ctx, args):
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif

    query = (args.get('query') or '').strip()
    qs = PersonnelAdministratif.objects.filter(
        etablissement=ctx.etablissement, actif=True
    )
    if query:
        qs = qs.filter(Q(nom__icontains=query) | Q(prenom__icontains=query))
    items = [
        {
            'nom': f'{p.prenom} {p.nom}',
            'fonction': p.get_fonction_display(),
        }
        for p in qs.order_by('nom', 'prenom')[:SEARCH_LIMIT]
    ]
    return {'personnel': items}


def tool_notes_eleve(ctx, args):
    query = (args.get('query') or '').strip()
    eleve = _find_eleve(ctx, query)
    if not eleve:
        return {'erreur': f'Aucun {ctx.libelle_eleve} trouvé pour « {query} ».'}

    notes = []
    if ctx.est_primaire:
        from school_admin.model.note_primaire_model import NotePrimaire

        qs = NotePrimaire.objects.filter(
            eleve=eleve,
            statut_publication=NotePrimaire.STATUT_PUBLIEE,
        ).select_related('evaluation_primaire', 'evaluation_primaire__matiere')
        if ctx.annee_scolaire:
            qs = qs.filter(
                Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
            )
        for note in qs.order_by('-id')[:NOTES_LIMIT]:
            evaluation = note.evaluation_primaire
            notes.append({
                'matiere': evaluation.matiere.nom if evaluation and evaluation.matiere_id else None,
                'evaluation': evaluation.titre if evaluation else None,
                'note': _safe_decimal(note.note),
            })
    else:
        from school_admin.model.evaluation_model import Note

        qs = Note.objects.filter(
            eleve=eleve,
            statut_publication=Note.STATUT_PUBLIEE,
            evaluation__classe__etablissement=ctx.etablissement,
        ).select_related('evaluation', 'evaluation__matiere', 'matiere')
        if ctx.annee_scolaire:
            qs = qs.filter(
                Q(evaluation__annee_scolaire=ctx.annee_scolaire)
                | Q(evaluation__annee_scolaire__isnull=True)
            )
        for note in qs.order_by('-id')[:NOTES_LIMIT]:
            matiere = note.matiere or (note.evaluation.matiere if note.evaluation_id else None)
            notes.append({
                'matiere': matiere.nom if matiere else None,
                'evaluation': note.evaluation.titre if note.evaluation_id else None,
                'note': _safe_decimal(note.note),
                'bareme': _safe_decimal(note.evaluation.bareme) if note.evaluation_id else 20,
            })

    moyennes = []
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    moy_qs = MoyennePeriode.objects.filter(
        eleve=eleve,
        etablissement=ctx.etablissement,
        est_moyenne_generale=True,
    ).select_related('periode')
    if ctx.annee_scolaire:
        moy_qs = moy_qs.filter(
            Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
        )
    for moy in moy_qs.order_by('-id')[:6]:
        moyennes.append({
            'periode': moy.periode.nom_periode if moy.periode_id else None,
            'moyenne': _safe_decimal(moy.moyenne_generale),
            'rang': moy.rang,
        })

    return {
        'eleve': eleve.nom_complet,
        'classe': eleve.classe.nom if eleve.classe_id else None,
        'notes': notes,
        'moyennes_periode': moyennes,
    }


def tool_emploi_du_temps(ctx, args):
    from school_admin.model.emploi_du_temps_model import EmploiDuTemps

    classe = _find_classe(ctx, args.get('classe') or '')
    if not classe:
        return {'erreur': 'Classe introuvable. Précisez le nom exact de la classe.'}

    qs = EmploiDuTemps.objects.filter(classe=classe, est_actif=True)
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire_fk=ctx.annee_scolaire)
            | Q(annee_scolaire=ctx.annee_scolaire.libelle)
        )
    emploi = qs.order_by('-date_modification').first()
    if not emploi:
        return {'classe': classe.nom, 'emploi': None, 'message': 'Aucun emploi du temps actif.'}

    creneaux = []
    for creneau in emploi.creneaux.select_related('matiere', 'professeur', 'salle').order_by(
        'jour', 'heure_debut'
    )[:40]:
        creneaux.append({
            'jour': creneau.get_jour_display(),
            'debut': creneau.heure_debut.strftime('%H:%M') if creneau.heure_debut else None,
            'fin': creneau.heure_fin.strftime('%H:%M') if creneau.heure_fin else None,
            'matiere': creneau.matiere.nom if creneau.matiere_id else None,
            'professeur': (
                f'{creneau.professeur.prenom} {creneau.professeur.nom}'
                if creneau.professeur_id else None
            ),
            'salle': creneau.salle.nom if creneau.salle_id else None,
        })
    return {
        'classe': classe.nom,
        'statut': emploi.get_statut_publication_display(),
        'creneaux': creneaux,
    }


def tool_presences(ctx, args):
    from school_admin.model.presence_model import Presence

    jours = int(args.get('jours') or 7)
    jours = max(1, min(jours, 31))
    since = timezone.now().date() - timedelta(days=jours)
    qs = Presence.objects.filter(etablissement=ctx.etablissement, date__gte=since)
    query = (args.get('query') or '').strip()
    if query:
        eleve = _find_eleve(ctx, query)
        if not eleve:
            return {'erreur': f'Aucun {ctx.libelle_eleve} trouvé pour « {query} ».'}
        qs = qs.filter(eleve=eleve)
        details = [
            {
                'date': p.date.isoformat(),
                'statut': p.get_statut_display(),
                'classe': p.classe.nom if p.classe_id else None,
            }
            for p in qs.select_related('classe').order_by('-date')[:20]
        ]
        return {
            'eleve': eleve.nom_complet,
            'periode_jours': jours,
            'details': details,
        }

    stats = list(qs.values('statut').annotate(nb=Count('id')))
    return {
        'periode_jours': jours,
        'totaux': {row['statut']: row['nb'] for row in stats},
        'nb_enregistrements': qs.count(),
    }


def tool_annonces(ctx, _args):
    from school_admin.model.annonce_model import Annonce

    qs = Annonce.objects.filter(
        etablissement=ctx.etablissement,
        statut='publiee',
    )
    if ctx.annee_scolaire:
        qs = qs.filter(Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True))
    items = [
        {
            'titre': a.titre,
            'date': a.date_publication.isoformat() if a.date_publication else None,
            'destinataires': a.destinataires,
        }
        for a in qs.order_by('-date_publication', '-date_creation')[:8]
    ]
    return {'annonces': items}


def _normalize_destinataires(raw):
    if raw is None or raw == '':
        return ['tous']
    if isinstance(raw, str):
        pieces = [part.strip() for part in re.split(r'[,;/]| et ', raw) if part.strip()]
    elif isinstance(raw, (list, tuple)):
        pieces = [str(part).strip() for part in raw if str(part).strip()]
    else:
        pieces = []

    result = []
    for item in pieces:
        key = DESTINATAIRE_ALIASES.get(item.lower(), item.lower())
        if key in DESTINATAIRE_VALIDES and key not in result:
            result.append(key)
    if 'tous' in result:
        return ['tous']
    return result or ['tous']


def _destinataires_libelle(codes):
    from school_admin.model.annonce_model import Annonce

    labels = dict(Annonce.DESTINATAIRES_CHOICES)
    if 'tous' in codes:
        return labels['tous']
    return ', '.join(labels.get(code, code) for code in codes)


def _prepare_annonce_draft(ctx, args):
    titre = (args.get('titre') or '').strip()
    contenu = (args.get('contenu') or '').strip()
    if not contenu:
        return {'erreur': 'Le contenu de l’annonce est obligatoire.'}
    if len(contenu) > ANNONCE_CONTENU_MAX:
        return {
            'erreur': f'Le contenu est trop long ({ANNONCE_CONTENU_MAX} caractères maximum).',
        }
    if not titre:
        titre = contenu[:80]
        if len(contenu) > 80:
            titre = titre.rsplit(' ', 1)[0] or titre
    titre = titre[:255]
    destinataires = _normalize_destinataires(args.get('destinataires'))
    publier = args.get('publier')
    if publier is None:
        publier = True
    return {
        'statut': 'en_attente_confirmation',
        'action': 'creer_publier_annonce',
        'titre': titre,
        'contenu': contenu,
        'destinataires': destinataires,
        'destinataires_libelle': _destinataires_libelle(destinataires),
        'publier': bool(publier),
        'message': (
            'Rien n’a encore été créé. Lis ce brouillon à voix haute et demande '
            'une confirmation explicite avant publication.'
        ),
    }


def tool_creer_publier_annonce(ctx, args):
    """Prépare une annonce. L’écriture réelle n’a lieu qu’après confirmation."""
    return _prepare_annonce_draft(ctx, args)


def apply_annonce_draft(ctx, draft):
    """Crée l’annonce (même logique que le formulaire directeur)."""
    from school_admin.model.annonce_model import Annonce

    titre = (draft.get('titre') or '').strip()
    contenu = (draft.get('contenu') or '').strip()
    if not titre or not contenu:
        return {'erreur': 'Titre et contenu sont obligatoires.'}

    destinataires = _normalize_destinataires(draft.get('destinataires'))
    annonce = Annonce.objects.create(
        etablissement=ctx.etablissement,
        auteur_directeur=ctx.etablissement,
        auteur_personnel=ctx.personnel,
        titre=titre,
        contenu=contenu,
        destinataires=destinataires,
        statut='brouillon',
        annee_scolaire=ctx.annee_scolaire,
    )
    if draft.get('publier', True):
        annonce.publier()

    logger.info(
        "Assistant: annonce %s id=%s etab=%s",
        annonce.statut,
        annonce.id,
        ctx.etablissement.pk,
    )
    from django.urls import reverse
    from school_admin.services.realtime_helpers import emit_live

    try:
        emit_live(
            ctx.etablissement.id,
            'annonce.mise_a_jour',
            {
                'event': 'annonce.mise_a_jour',
                'item': {
                    'id': annonce.id,
                    'action': 'publiee' if annonce.statut == 'publiee' else 'creee',
                },
            },
        )
    except Exception:
        logger.exception('Émission temps réel annonce assistant')

    return {
        'statut': 'ok',
        'id': annonce.id,
        'titre': annonce.titre,
        'publiee': annonce.statut == 'publiee',
        'destinataires': destinataires,
        'destinataires_libelle': annonce.get_destinataires_display(),
        'url': reverse('directeur:apercu_annonce', args=[annonce.id]),
    }


def tool_periodes(ctx, args):
    from school_admin.model.periode_model import PeriodeScolaire, SEMESTRES_PAR_NIVEAU_LMD

    args = args if isinstance(args, dict) else {}
    periode_active = PeriodeScolaire.get_periode_active(ctx.etablissement)
    qs = PeriodeScolaire.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire_fk=ctx.annee_scolaire)
            | Q(annee_scolaire=ctx.annee_scolaire.libelle)
        )
    niveau = None
    if getattr(ctx, 'est_superieur', False):
        from school_admin.services.assistant_superieur import normalize_niveau_lmd

        niveau = normalize_niveau_lmd(args.get('niveau_lmd') or args.get('niveau'))
        if niveau:
            qs = qs.filter(Q(niveau_lmd=niveau) | Q(niveau_lmd=''))
    items = []
    for p in qs.order_by('niveau_lmd', 'date_debut')[:24]:
        item = {
            'nom': p.nom_periode,
            'type': p.get_type_periode_display(),
            'debut': p.date_debut.isoformat() if p.date_debut else None,
            'fin': p.date_fin.isoformat() if p.date_fin else None,
            'active': bool(periode_active and p.pk == periode_active.pk),
            'niveau_lmd': (p.niveau_lmd or None) or None,
        }
        if getattr(ctx, 'est_superieur', False) and p.niveau_lmd:
            from school_admin.model.periode_model import libelle_long_semestre

            item['libelle'] = libelle_long_semestre(p.nom_periode, p.niveau_lmd)
        items.append(item)
    payload = {
        'session': ctx.annee_scolaire.libelle if ctx.annee_scolaire else None,
        'periode_active': periode_active.nom_periode if periode_active else None,
        'periodes': items,
    }
    if getattr(ctx, 'est_superieur', False):
        payload['filtre_niveau_lmd'] = niveau
        payload['semestres_par_niveau'] = {
            code: [nom for nom, _lib in pairs]
            for code, pairs in SEMESTRES_PAR_NIVEAU_LMD.items()
        }
    return payload


def tool_comptabilite(ctx, args):
    from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve

    query = (args.get('query') or '').strip()
    qs = ComptabiliteEleve.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)

    if query:
        from school_admin.services.assistant_pilotage import tool_fiche_scolarite

        return tool_fiche_scolarite(ctx, args)

    impayes = qs.filter(statut_paiement__in=['en_retard', 'impaye']).select_related('eleve')
    items = []
    for fiche in impayes.order_by('statut_paiement')[:SEARCH_LIMIT]:
        total_du = fiche.calculer_total_du()
        total_paye = fiche.calculer_total_paye()
        items.append({
            'eleve': fiche.eleve.nom_complet,
            'eleve_id': fiche.eleve_id,
            'statut': fiche.get_statut_paiement_display(),
            'reste': _safe_decimal(total_du - total_paye),
        })
    return {
        'nb_a_jour': qs.filter(statut_paiement='a_jour').count(),
        'nb_en_retard': qs.filter(statut_paiement='en_retard').count(),
        'nb_impaye': qs.filter(statut_paiement='impaye').count(),
        'impayes': items,
    }


def tool_parametres_comptabilite(ctx, args):
    from school_admin.model.parametres_comptabilite_groupe_classe_model import (
        ParametresComptabiliteGroupeClasse,
    )
    from school_admin.utils.frais_annexes import frais_annexes_actifs

    groupes = ParametresComptabiliteGroupeClasse.get_groupes_disponibles(ctx.etablissement)
    deja = ParametresComptabiliteGroupeClasse.get_groupes_deja_assignes(ctx.etablissement)
    items = []
    for parametre in ParametresComptabiliteGroupeClasse.objects.filter(
        etablissement=ctx.etablissement
    ).order_by('nom'):
        items.append({
            'id': parametre.id,
            'nom': parametre.nom,
            'groupes': list(parametre.groupes_classes or []),
            'type_facturation': parametre.type_facturation,
            'montant_frais_inscription': str(parametre.montant_frais_inscription or '0'),
            'montant_mensualite': str(parametre.montant_mensualite or '0'),
            'frais_annexes': [
                {
                    'code': item['code'],
                    'libelle': item['libelle'],
                    'montant': item['montant'],
                    'periodicite': item.get('periodicite'),
                }
                for item in frais_annexes_actifs(getattr(parametre, 'frais_annexes', None))
            ],
        })
    return {
        'module_actif': bool(ctx.etablissement.module_comptabilite),
        'groupes_disponibles': groupes,
        'groupes_deja_assignes': deja,
        'parametres': items,
        'url': '/comptabilite/parametres/',
    }


def tool_structure_superieur(ctx, args):
    if not ctx.est_superieur:
        return {'erreur': 'Cet établissement n’est pas un établissement supérieur.'}

    from school_admin.model.academic_structure_model import Department
    from school_admin.model.module_model import Module

    query = (args.get('query') or '').strip()
    deps = Department.objects.filter(etablissement=ctx.etablissement)
    modules = Module.objects.filter(etablissement=ctx.etablissement)
    if query:
        deps = deps.filter(Q(nom__icontains=query) | Q(sigle__icontains=query))
        modules = modules.filter(Q(nom__icontains=query) | Q(code__icontains=query))

    return {
        'departements': [
            {'nom': d.nom, 'sigle': d.sigle or None}
            for d in deps.order_by('ordre', 'nom')[:20]
        ],
        'modules': [
            {'nom': m.nom, 'code': m.code}
            for m in modules.order_by('nom')[:20]
        ],
    }


def _sanctions_queryset(ctx, args=None):
    from school_admin.model.sanction_model import Sanction

    args = args or {}
    qs = Sanction.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    classe_label = (args.get('classe') or '').strip()
    if classe_label:
        classe = _find_classe(ctx, classe_label)
        if classe:
            qs = qs.filter(classe=classe)
    return qs


def tool_sanctions(ctx, args):
    """Sanctions disciplinaires : effectifs, liste ou dossier d'un élève."""
    from school_admin.model.sanction_model import Sanction

    args = args if isinstance(args, dict) else {}
    query = (args.get('query') or '').strip()
    qs = _sanctions_queryset(ctx, args).select_related('eleve', 'classe')
    session = ctx.annee_scolaire.libelle if ctx.annee_scolaire else None

    if query:
        eleve = _find_eleve(ctx, query)
        if not eleve:
            return {'erreur': f'Aucun {ctx.libelle_eleve} trouvé pour « {query} ».'}
        sancs = qs.filter(eleve=eleve).order_by('-date_sanction', '-date_creation')[:SEARCH_LIMIT]
        items = [
            {
                'type': s.get_type_sanction_display(),
                'type_code': s.type_sanction,
                'raison': s.get_raison_display(),
                'gravite': s.get_gravite_display(),
                'date': s.date_sanction.isoformat() if s.date_sanction else None,
                'classe': s.classe.nom if s.classe_id else None,
            }
            for s in sancs
        ]
        return {
            'session': session,
            'eleve': eleve.nom_complet,
            'nb_sanctions': qs.filter(eleve=eleve).count(),
            'sanctions': items,
        }

    nb_sanctions = qs.count()
    nb_eleves = qs.values('eleve_id').distinct().count()
    type_labels = dict(Sanction.TYPE_SANCTION_CHOICES)
    par_eleve = (
        qs.values('eleve_id', 'eleve__nom', 'eleve__prenom', 'classe__nom')
        .annotate(nb_sanctions=Count('id'), derniere_sanction=Max('date_sanction'))
        .order_by('-nb_sanctions', 'eleve__nom')[:SEARCH_LIMIT]
    )
    eleves = [
        {
            'nom_complet': f"{row['eleve__prenom']} {row['eleve__nom']}".strip(),
            'classe': row['classe__nom'],
            'nb_sanctions': row['nb_sanctions'],
            'derniere_sanction': (
                row['derniere_sanction'].isoformat() if row['derniere_sanction'] else None
            ),
        }
        for row in par_eleve
    ]
    dernieres = [
        {
            'eleve': s.eleve.nom_complet,
            'classe': s.classe.nom if s.classe_id else None,
            'type': s.get_type_sanction_display(),
            'date': s.date_sanction.isoformat() if s.date_sanction else None,
        }
        for s in qs.order_by('-date_sanction', '-date_creation')[:8]
    ]
    par_type = {
        type_labels.get(row['type_sanction'], row['type_sanction']): row['nb']
        for row in qs.values('type_sanction').annotate(nb=Count('id'))
    }
    return {
        'session': session,
        'nb_sanctions': nb_sanctions,
        'nb_eleves_avec_sanction': nb_eleves,
        'repartition_par_type': par_type,
        'eleves': eleves,
        'dernieres_sanctions': dernieres,
    }


def tool_chercher_en_base(ctx, args):
    """Cherche une donnée scolaire en base quand elle n'est pas déjà connue."""
    args = args if isinstance(args, dict) else {}
    question = (args.get('question') or args.get('query') or '').strip()
    lowered = question.lower()
    payload = {
        'query': question,
        'classe': (args.get('classe') or '').strip(),
    }

    if any(
        token in lowered
        for token in (
            'fille', 'garçon', 'garcon', 'sexe', 'féminin', 'feminin',
            'masculin', 'genre', 'effectif', 'inscrit',
        )
    ):
        found = tool_effectifs(ctx, payload)
        return {'trouve': True, 'source': 'effectifs', **found}
    if any(
        token in lowered
        for token in (
            'justification', 'justifications', 'rectification de note',
        )
    ):
        from school_admin.services.assistant_pedagogie import tool_justifications_notes

        found = tool_justifications_notes(ctx, payload)
        return {'trouve': True, 'source': 'justifications', **found}
    if any(
        token in lowered
        for token in (
            'en difficulté', 'en difficulte', 'sous le seuil', 'élèves faibles',
            'eleves faibles',
        )
    ):
        from school_admin.services.assistant_pedagogie import tool_eleves_difficulte

        found = tool_eleves_difficulte(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'difficulte', **found}
    if any(token in lowered for token in ('coefficient', 'coefficients')):
        from school_admin.services.assistant_pedagogie import tool_coefficients

        found = tool_coefficients(ctx, payload)
        return {'trouve': True, 'source': 'coefficients', **found}
    if any(
        token in lowered
        for token in ('évaluation', 'evaluation', 'évaluations', 'evaluations')
    ):
        from school_admin.services.assistant_pedagogie import tool_evaluations

        found = tool_evaluations(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'evaluations', **found}
    if any(
        token in lowered
        for token in (
            'notes de la classe', 'notes de classe', 'notes de la ',
            'notes des élèves de', 'notes des eleves de',
        )
    ):
        from school_admin.services.assistant_pedagogie import tool_notes_classe

        found = tool_notes_classe(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'notes_classe', **found}
    if any(
        token in lowered
        for token in (
            'moyennes de la classe', 'moyennes de classe', 'moyennes de la ',
        )
    ):
        from school_admin.services.assistant_pedagogie import tool_moyennes_classe

        found = tool_moyennes_classe(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'moyennes_classe', **found}
    if getattr(ctx, 'est_superieur', False) and any(
        token in lowered
        for token in (
            'ects', 'crédit', 'credit', 'crédits', 'credits',
            'unité d’enseignement', "unité d'enseignement", ' ue ',
        )
    ):
        from school_admin.services.assistant_superieur import (
            tool_ects_classe,
            tool_ects_etudiant,
            tool_modules_classe,
            tool_releve_ects,
        )

        if any(token in lowered for token in ('relevé', 'releve')):
            found = tool_releve_ects(ctx, {**payload, 'query': question})
            return {'trouve': not bool(found.get('erreur')), 'source': 'releve_ects', **found}
        if any(token in lowered for token in ('module', 'maquette', 'ue')) and (
            payload.get('classe') or 'classe' in lowered or 'promo' in lowered
        ):
            found = tool_modules_classe(ctx, payload)
            return {
                'trouve': not bool(found.get('erreur')),
                'source': 'modules_classe',
                **found,
            }
        if payload.get('classe') or any(
            token in lowered for token in ('classe', 'promo', 'promotion')
        ):
            found = tool_ects_classe(ctx, payload)
            return {
                'trouve': not bool(found.get('erreur')),
                'source': 'ects_classe',
                **found,
            }
        found = tool_ects_etudiant(ctx, {**payload, 'query': question})
        return {'trouve': not bool(found.get('erreur')), 'source': 'ects', **found}
    if getattr(ctx, 'est_superieur', False) and any(
        token in lowered for token in ('module de', 'modules de', 'maquette')
    ):
        from school_admin.services.assistant_superieur import tool_modules_classe

        found = tool_modules_classe(ctx, payload)
        return {
            'trouve': not bool(found.get('erreur')),
            'source': 'modules_classe',
            **found,
        }
    if any(token in lowered for token in ('bulletin', 'bulletins')):
        from school_admin.services.assistant_pedagogie import tool_bulletin_eleve

        found = tool_bulletin_eleve(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'bulletin', **found}
    if 'examen' in lowered and any(
        token in lowered for token in ('note', 'notes', 'résultat', 'resultat')
    ):
        from school_admin.services.assistant_examens import tool_notes_examen

        found = tool_notes_examen(ctx, {**payload, 'query': question})
        return {
            'trouve': not bool(found.get('erreur')),
            'source': 'notes_examen',
            **found,
        }
    if any(token in lowered for token in ('note', 'moyenne', 'résultat', 'resultat')):
        found = tool_notes_eleve(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'notes', **found}
    if any(
        token in lowered
        for token in (
            'taux de présence', 'taux de presence', 'taux présence', 'taux presence',
        )
    ):
        from school_admin.services.assistant_pilotage import tool_taux_presence

        found = tool_taux_presence(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'presence_taux', **found}
    if any(
        token in lowered
        for token in ('fiche de paie', 'fiche paie', 'bulletin de paie')
    ):
        from school_admin.services.assistant_rh import tool_ouvrir_fiche_paie

        found = tool_ouvrir_fiche_paie(ctx, {**payload, 'query': question})
        return {'trouve': not bool(found.get('erreur')), 'source': 'fiche_paie', **found}
    if any(
        token in lowered
        for token in (
            'dossier employ', 'cnss', 'n° cnss', 'numero cnss',
            'salaire de base', 'type de contrat', ' rib', 'rib ',
        )
    ) or re.search(r'\brib\b', lowered):
        from school_admin.services.assistant_rh import tool_dossier_employe

        found = tool_dossier_employe(ctx, {**payload, 'query': question})
        return {
            'trouve': not bool(found.get('erreur')),
            'source': 'dossier_employe',
            **found,
        }
    if any(
        token in lowered
        for token in (
            'absence du professeur', 'absences du professeur',
            'absence professeur', 'absences professeur',
            'absence enseignant', 'absences enseignant',
            'absence de l’enseignant', "absence de l'enseignant",
        )
    ):
        from school_admin.services.assistant_rh import tool_absences_professeur

        found = tool_absences_professeur(ctx, {**payload, 'query': question})
        return {
            'trouve': not bool(found.get('erreur')),
            'source': 'absences_professeur',
            **found,
        }
    if any(token in lowered for token in ('absence', 'présent', 'present', 'présence', 'presence')):
        found = tool_presences(ctx, payload)
        return {'trouve': True, 'source': 'presences', **found}
    if any(
        token in lowered
        for token in ('sanction', 'sanctions', 'blâme', 'blame', 'disciplinaire')
    ) or re.search(r'\bsanctionn', lowered):
        found = tool_sanctions(ctx, payload)
        return {'trouve': 'erreur' not in found, 'source': 'sanctions', **found}
    if any(token in lowered for token in ('caisse', 'dépense', 'depense', 'solde du mois', 'sorties')):
        found = tool_caisse(ctx, payload)
        return {'trouve': True, 'source': 'caisse', **found}
    if any(token in lowered for token in ('volume horaire', 'paie', 'vacataire', 'heures à payer')):
        found = tool_volume_horaire(ctx, payload)
        return {'trouve': True, 'source': 'volume_horaire', **found}
    if any(
        token in lowered
        for token in (
            'tableau de bord', 'pilotage', 'statistiques', 'recouvrement',
        )
    ):
        from school_admin.services.assistant_pilotage import tool_statistiques_pilotage

        found = tool_statistiques_pilotage(ctx, payload)
        return {'trouve': True, 'source': 'pilotage', **found}
    if any(
        token in lowered
        for token in ('taux de réussite', 'taux de reussite', 'réussite', 'reussite')
    ):
        from school_admin.services.assistant_pilotage import tool_taux_reussite

        found = tool_taux_reussite(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'reussite', **found}
    if any(
        token in lowered
        for token in ('comparatif', 'comparer les périodes', 'comparer les periodes')
    ):
        from school_admin.services.assistant_pilotage import tool_comparatif_periodes

        found = tool_comparatif_periodes(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'comparatif', **found}
    if any(
        token in lowered
        for token in ('répartition', 'repartition', 'par cycle', 'collège et lycée')
    ) and getattr(ctx, 'est_college_lycee', False):
        from school_admin.services.assistant_pilotage import tool_repartition_cycles

        found = tool_repartition_cycles(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'cycles', **found}
    if any(token in lowered for token in ('reçu', 'recu', 'numéro de reçu', 'numero de recu')):
        from school_admin.services.assistant_pilotage import tool_ouvrir_recu

        found = tool_ouvrir_recu(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'recu', **found}
    if any(token in lowered for token in ('moratoire',)):
        from school_admin.services.assistant_pilotage import tool_moratoires

        found = tool_moratoires(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'moratoires', **found}
    if any(token in lowered for token in ('bilan scolar', 'totaux scolar', 'recouvrement session')):
        from school_admin.services.assistant_pilotage import tool_bilan_scolarite

        found = tool_bilan_scolarite(ctx, payload)
        return {'trouve': True, 'source': 'bilan', **found}
    if any(token in lowered for token in ('impay',)):
        from school_admin.services.assistant_pilotage import tool_impayes

        found = tool_impayes(ctx, payload)
        return {'trouve': True, 'source': 'impayes', **found}
    if any(token in lowered for token in ('fiche scolar', 'scolarité de', 'scolarite de')):
        from school_admin.services.assistant_pilotage import tool_fiche_scolarite

        found = tool_fiche_scolarite(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'scolarite', **found}
    if any(token in lowered for token in ('paiement', 'impay', 'frais', 'scolarité', 'scolarite', 'dette')):
        found = tool_comptabilite(ctx, payload)
        return {'trouve': True, 'source': 'comptabilite', **found}
    if any(token in lowered for token in ('emploi du temps', 'edt', 'cours du')):
        found = tool_emploi_du_temps(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'emploi', **found}
    if any(token in lowered for token in ('période', 'periode', 'semestre', 'trimestre')):
        found = tool_periodes(ctx, payload)
        return {'trouve': True, 'source': 'periodes', **found}
    if any(token in lowered for token in ('annonce',)):
        found = tool_annonces(ctx, payload)
        return {'trouve': True, 'source': 'annonces', **found}
    if any(token in lowered for token in ('préinscription', 'preinscription', 'candidat')):
        found = tool_preinscriptions(ctx, payload)
        return {'trouve': True, 'source': 'preinscriptions', **found}
    if any(token in lowered for token in ('liaison',)):
        found = tool_liaisons(ctx, payload)
        return {'trouve': True, 'source': 'liaisons', **found}
    if (
        'examen' in lowered
        and any(token in lowered for token in ('créneau', 'creneau', 'emploi'))
    ):
        from school_admin.services.assistant_examens import tool_emploi_examens

        found = tool_emploi_examens(ctx, {**payload, 'query': question})
        return {
            'trouve': not bool(found.get('erreur')),
            'source': 'emploi_examens',
            **found,
        }
    if any(token in lowered for token in ('examen', 'session d')):
        from school_admin.services.assistant_examens import tool_examens as examens_handler

        found = examens_handler(ctx, payload)
        return {'trouve': True, 'source': 'examens', **found}
    if any(token in lowered for token in ('année scolaire', 'annee scolaire', 'session 20')):
        found = tool_annees(ctx, payload)
        return {'trouve': True, 'source': 'annees', **found}
    if any(token in lowered for token in ('salle',)):
        found = tool_salles(ctx, payload)
        return {'trouve': True, 'source': 'salles', **found}
    if any(token in lowered for token in ('matière', 'matiere')):
        found = tool_matieres(ctx, payload)
        return {'trouve': True, 'source': 'matieres', **found}
    if any(token in lowered for token in ('notification',)):
        found = tool_notifications(ctx, payload)
        return {'trouve': True, 'source': 'notifications', **found}
    if any(token in lowered for token in ('département', 'departement', 'module', 'spécialité', 'specialite')):
        found = tool_structure_superieur(ctx, payload)
        return {'trouve': True, 'source': 'structure', **found}
    if any(
        token in lowered
        for token in (
            'affectation', 'affectations', 'professeur affecté', 'enseignants affectés',
        )
    ):
        found = tool_affectations(ctx, payload)
        return {'trouve': not bool(found.get('erreur')), 'source': 'affectations', **found}
    if any(token in lowered for token in ('professeur', 'enseignant', 'prof ')):
        found = tool_rechercher_professeurs(ctx, payload)
        return {'trouve': bool(found.get('professeurs')), 'source': 'professeurs', **found}
    if any(token in lowered for token in ('personnel', 'secrétaire', 'secretaire')):
        found = tool_rechercher_personnel(ctx, payload)
        return {'trouve': bool(found.get('personnel')), 'source': 'personnel', **found}
    if any(token in lowered for token in ('élève', 'eleve', 'étudiant', 'etudiant', 'matricule')):
        found = tool_rechercher_eleves(ctx, payload)
        return {'trouve': bool(found.get('eleves')), 'source': 'eleves', **found}
    if any(token in lowered for token in ('classe', 'promotion', 'filière', 'filiere')):
        found = tool_rechercher_classes(ctx, payload)
        return {'trouve': bool(found.get('classes')), 'source': 'classes', **found}

    found = tool_effectifs(ctx, payload)
    return {
        'trouve': True,
        'source': 'effectifs',
        'precision': (
            "Recherche générale : voici les effectifs. "
            "Reformule si tu visais une autre donnée."
        ),
        **found,
    }


def tool_notifications(ctx, _args):
    from school_admin.model.notification_directeur_model import NotificationDirecteur

    qs = NotificationDirecteur.objects.filter(etablissement=ctx.etablissement)
    items = [
        {
            'titre': n.titre if hasattr(n, 'titre') else str(n),
            'lu': getattr(n, 'lu', False),
            'date': n.date_creation.isoformat() if getattr(n, 'date_creation', None) else None,
        }
        for n in qs.order_by('-date_creation')[:12]
    ]
    return {
        'nb_non_lues': qs.filter(lu=False).count() if hasattr(NotificationDirecteur, 'lu') else 0,
        'notifications': items,
        'url': '/notifications/',
    }


def tool_preinscriptions(ctx, args):
    from school_admin.model.preinscription_model import PreinscriptionEleve

    qs = PreinscriptionEleve.objects.filter(etablissement=ctx.etablissement)
    statut = (args.get('statut') or 'en_attente').strip()
    if statut:
        qs = qs.filter(statut=statut)
    items = [
        {
            'id': p.id,
            'nom': f'{p.prenom} {p.nom}',
            'classe': p.classe_souhaitee.nom if p.classe_souhaitee_id else None,
            'statut': p.statut,
        }
        for p in qs.order_by('-id')[:SEARCH_LIMIT]
    ]
    return {'nb': qs.count(), 'preinscriptions': items}


def tool_liaisons(ctx, args):
    from school_admin.model.demande_liaison_model import DemandeLiaisonParent

    qs = DemandeLiaisonParent.objects.filter(
        Q(etablissement=ctx.etablissement)
        | Q(eleve_valide__etablissement=ctx.etablissement)
    ).select_related('parent_demandeur', 'eleve_valide')
    statut = (args.get('statut') or '').strip()
    if statut:
        qs = qs.filter(statut=statut)
    items = [
        {
            'id': d.id,
            'parent': getattr(d.parent_demandeur, 'nom_complet', ''),
            'eleve': (
                d.eleve_valide.nom_complet
                if d.eleve_valide_id
                else f'{d.prenom_eleve} {d.nom_eleve}'
            ),
            'statut': d.statut,
        }
        for d in qs.order_by('-date_demande')[:SEARCH_LIMIT]
    ]
    return {'nb': qs.count(), 'demandes': items}


def tool_examens(ctx, _args):
    from school_admin.model.session_examen_model import SessionExamen

    qs = SessionExamen.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        qs = qs.filter(Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True))
    items = [
        {
            'id': s.id,
            'nom': s.nom_examen,
            'periode': s.periode.nom_periode if s.periode_id else None,
            'debut': s.date_debut.isoformat() if s.date_debut else None,
            'fin': s.date_fin.isoformat() if s.date_fin else None,
        }
        for s in qs.select_related('periode').order_by('-date_creation')[:SEARCH_LIMIT]
    ]
    return {'sessions': items}


def tool_annees(ctx, _args):
    from school_admin.model.annee_scolaire_model import AnneeScolaire

    items = [
        {
            'id': a.id,
            'libelle': a.libelle,
            'active': a.est_active,
            'ouverte': a.est_ouverte,
            'debut': a.date_debut.isoformat() if a.date_debut else None,
            'fin': a.date_fin.isoformat() if a.date_fin else None,
        }
        for a in AnneeScolaire.objects.filter(
            etablissement=ctx.etablissement
        ).order_by('-annee_debut')[:16]
    ]
    return {'annees': items}


def tool_salles(ctx, args):
    from school_admin.model.salle_model import Salle

    qs = Salle.objects.filter(etablissement=ctx.etablissement, actif=True)
    query = (args.get('query') or '').strip()
    if query:
        qs = qs.filter(Q(nom__icontains=query) | Q(numero__icontains=query))
    items = [
        {'id': s.id, 'nom': s.nom, 'numero': s.numero, 'type': s.get_type_salle_display()}
        for s in qs.order_by('numero')[:SEARCH_LIMIT]
    ]
    return {'salles': items}


def tool_matieres(ctx, args):
    from school_admin.model.matiere_model import Matiere

    qs = Matiere.objects.filter(etablissement=ctx.etablissement, actif=True)
    query = (args.get('query') or '').strip()
    if query:
        qs = qs.filter(Q(nom__icontains=query) | Q(code__icontains=query))
    items = [
        {'id': m.id, 'nom': m.nom, 'code': getattr(m, 'code', None)}
        for m in qs.order_by('nom')[:SEARCH_LIMIT]
    ]
    return {'matieres': items}


def tool_caisse(ctx, args):
    from datetime import date as date_cls

    from school_admin.services.caisse import (
        bornes_mois,
        depenses_mois,
        parser_mois,
        solde_mois,
        total_depenses,
        total_recettes,
    )
    from school_admin.services.recouvrement import devise_etablissement

    reference = parser_mois(args.get('mois') or args.get('query'), date_cls.today())
    bornes = bornes_mois(reference)
    depenses = [
        {
            'id': depense.id,
            'date': depense.date_depense.isoformat(),
            'motif': depense.get_motif_display(),
            'libelle': depense.libelle,
            'montant': str(depense.montant),
        }
        for depense in depenses_mois(ctx.etablissement, bornes.debut, bornes.fin)[:SEARCH_LIMIT]
    ]
    return {
        'mois': bornes.label,
        'entrees': str(total_recettes(ctx.etablissement, bornes.debut, bornes.fin)),
        'sorties': str(total_depenses(ctx.etablissement, bornes.debut, bornes.fin)),
        'solde': str(solde_mois(ctx.etablissement, bornes.debut, bornes.fin)),
        'devise': devise_etablissement(ctx.etablissement),
        'depenses': depenses,
    }


def tool_volume_horaire(ctx, args):
    from school_admin.services.assistant_rh import tool_volume_horaire as handler

    return handler(ctx, args)


def tool_lister_pages(ctx, _args):
    from school_admin.services.assistant_pages import list_pages
    from school_admin.services.assistant_schema import pages_visibles

    return {
        'pages': [
            {'key': page['key'], 'titre': page['titre']}
            for page in pages_visibles(ctx, list_pages())
        ],
    }


def tool_ouvrir_page(ctx, args):
    from school_admin.services.assistant_pages import find_page, related_pages
    from school_admin.services.assistant_schema import pages_visibles

    page = find_page(args.get('page_key') or args.get('query'))
    visibles = {item['key'] for item in pages_visibles(ctx, [page] if page else [])}
    if not page or page['key'] not in visibles:
        return {
            'erreur': 'Page inconnue. Utilise lister_pages pour voir les clés valides.',
        }
    ouvrir = args.get('ouvrir')
    if ouvrir is None:
        ouvrir = True
    return {
        'statut': 'ok',
        'key': page['key'],
        'titre': page['titre'],
        'url': page['url'],
        'ouvrir': bool(ouvrir),
        'suggestions': related_pages(page['key']),
    }


SUGGESTION_INTENTS = frozenset({'chat', 'open'})


def normalize_suggestions(raw_items, limit=3):
    """Puces de suite (G4) : 1 à 3, intent chat ou open. Rien n’est écrit."""
    cleaned = []
    for item in raw_items or []:
        if not isinstance(item, dict):
            continue
        label = (item.get('label') or item.get('titre') or item.get('nom') or '').strip()
        if not label:
            continue
        intent = (item.get('intent') or '').strip().lower()
        url = (item.get('url') or '').strip()
        if intent not in SUGGESTION_INTENTS:
            intent = 'open' if url else 'chat'
        if intent == 'open' and not url:
            intent = 'chat'
        value = (item.get('value') or label).strip()
        cleaned.append({
            'label': label[:80],
            'value': value[:200],
            'intent': intent,
            'url': url[:300],
        })
        if len(cleaned) >= limit:
            break
    return cleaned


def tool_proposer_actions(ctx, args):
    """Lecture seule : valide et renvoie jusqu’à 3 suggestions cliquables."""
    items = args.get('suggestions') or args.get('actions') or []
    if not isinstance(items, list):
        items = []
    suggestions = normalize_suggestions(items, limit=3)
    return {
        'statut': 'ok',
        'suggestions': suggestions,
        'nb': len(suggestions),
    }


TOOL_HANDLERS = {
    'chercher_en_base': tool_chercher_en_base,
    'get_effectifs': tool_effectifs,
    'rechercher_eleves': tool_rechercher_eleves,
    'rechercher_classes': tool_rechercher_classes,
    'ouvrir_classe': tool_ouvrir_classe,
    'rechercher_professeurs': tool_rechercher_professeurs,
    'get_affectations': tool_affectations,
    'rechercher_personnel': tool_rechercher_personnel,
    'get_notes_eleve': tool_notes_eleve,
    'get_emploi_du_temps': tool_emploi_du_temps,
    'get_presences': tool_presences,
    'get_sanctions': tool_sanctions,
    'get_annonces': tool_annonces,
    'creer_publier_annonce': tool_creer_publier_annonce,
    'get_periodes': tool_periodes,
    'get_comptabilite': tool_comptabilite,
    'get_parametres_comptabilite': tool_parametres_comptabilite,
    'get_structure_superieur': tool_structure_superieur,
    'lister_pages': tool_lister_pages,
    'ouvrir_page': tool_ouvrir_page,
    'proposer_actions': tool_proposer_actions,
    'get_notifications': tool_notifications,
    'get_preinscriptions': tool_preinscriptions,
    'get_liaisons': tool_liaisons,
    'get_examens': tool_examens,
    'get_annees': tool_annees,
    'get_salles': tool_salles,
    'get_matieres': tool_matieres,
    'get_caisse': tool_caisse,
    'get_volume_horaire': tool_volume_horaire,
}

from school_admin.services.assistant_emploi import (  # noqa: E402
    tool_ajouter_creneau_emploi,
    tool_creer_emploi_du_temps,
)

TOOL_HANDLERS['creer_emploi_du_temps'] = tool_creer_emploi_du_temps
TOOL_HANDLERS['ajouter_creneau_emploi'] = tool_ajouter_creneau_emploi

from school_admin.services.assistant_actions import (  # noqa: E402
    ACTION_SPECS,
    build_tool_schemas as build_action_tool_schemas,
)
import school_admin.services.assistant_staff  # noqa: E402,F401
import school_admin.services.assistant_dossiers  # noqa: E402,F401
from school_admin.services.assistant_pilotage import (  # noqa: E402
    VAGUE2_READ_HANDLERS,
    VAGUE2_READ_SCHEMA,
)
from school_admin.services.assistant_pedagogie import (  # noqa: E402
    VAGUE3_READ_HANDLERS,
    VAGUE3_READ_SCHEMA,
)
from school_admin.services.assistant_superieur import (  # noqa: E402
    VAGUE4_READ_HANDLERS,
    VAGUE4_READ_SCHEMA,
)
from school_admin.services.assistant_rh import (  # noqa: E402
    VAGUE5_READ_HANDLERS,
    VAGUE5_READ_SCHEMA,
)
from school_admin.services.assistant_examens import (  # noqa: E402
    VAGUE6_READ_HANDLERS,
    VAGUE6_READ_SCHEMA,
)

TOOL_HANDLERS.update(VAGUE2_READ_HANDLERS)
TOOL_HANDLERS.update(VAGUE3_READ_HANDLERS)
TOOL_HANDLERS.update(VAGUE4_READ_HANDLERS)
TOOL_HANDLERS.update(VAGUE5_READ_HANDLERS)
TOOL_HANDLERS.update(VAGUE6_READ_HANDLERS)

for _name, _spec in ACTION_SPECS.items():
    TOOL_HANDLERS[_name] = _spec.prepare


TOOLS_SCHEMA = [
    {
        'type': 'function',
        'function': {
            'name': 'chercher_en_base',
            'description': (
                'Cherche une donnée scolaire en base quand elle n’est pas déjà connue. '
                'À appeler dès qu’une question porte sur des chiffres, des listes ou '
                'un détail (filles, garçons, élèves, notes, absences, sanctions, '
                'affectations, classes, etc.). '
                'Si la donnée existe, elle est renvoyée. Sinon trouve=false.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'question': {
                        'type': 'string',
                        'description': 'La question ou la donnée à chercher',
                    },
                    'classe': {
                        'type': 'string',
                        'description': CLASSE_PARAM_DESCRIPTION,
                    },
                },
                'required': ['question'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_effectifs',
            'description': (
                'Effectifs de l’établissement ou d’une classe : nombre d’élèves, '
                'filles (sexe F), garçons (sexe M), classes, professeurs, personnel, '
                'capacité, places libres, et répartition par classe. '
                'À utiliser pour toute question sur les filles, les garçons '
                'ou le sexe des inscrits.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': {
                        'type': 'string',
                        'description': CLASSE_PARAM_DESCRIPTION,
                    },
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'rechercher_eleves',
            'description': 'Recherche des élèves ou étudiants par nom, prénom, matricule ou classe.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom, prénom ou matricule'},
                    'classe': {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'rechercher_classes',
            'description': 'Liste ou recherche les classes / promotions.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'rechercher_professeurs',
            'description': 'Recherche des professeurs par nom.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'rechercher_personnel',
            'description': 'Recherche du personnel administratif.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_notes_eleve',
            'description': 'Notes publiées et moyennes de période d’un élève ou étudiant.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': 'Nom, prénom ou matricule',
                    },
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_emploi_du_temps',
            'description': 'Emploi du temps actif d’une classe.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION},
                },
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'creer_emploi_du_temps',
            'description': (
                'Prépare la création de l’emploi du temps d’une classe. '
                'Ne crée rien tout de suite : une confirmation est obligatoire. '
                'À utiliser quand le directeur demande de créer un emploi du temps.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': {
                        'type': 'string',
                        'description': CLASSE_PARAM_DESCRIPTION,
                    },
                    'notes': {
                        'type': 'string',
                        'description': 'Note optionnelle sur l’emploi du temps',
                    },
                },
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ajouter_creneau_emploi',
            'description': (
                'Prépare un créneau (cours) dans l’emploi du temps d’une classe. '
                'Ne l’enregistre pas tout de suite : une confirmation est obligatoire. '
                'Si l’emploi du temps n’existe pas encore, il sera créé après confirmation. '
                'Jours : lundi à samedi. Heures au format HH:MM.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION},
                    'jour': {
                        'type': 'string',
                        'enum': [
                            'lundi',
                            'mardi',
                            'mercredi',
                            'jeudi',
                            'vendredi',
                            'samedi',
                            'dimanche',
                        ],
                    },
                    'heure_debut': {
                        'type': 'string',
                        'description': 'Heure de début, ex. 08:00',
                    },
                    'heure_fin': {
                        'type': 'string',
                        'description': 'Heure de fin, ex. 10:00',
                    },
                    'matiere': {'type': 'string', 'description': 'Nom de la matière'},
                    'professeur': {'type': 'string', 'description': 'Nom du professeur'},
                    'salle': {'type': 'string', 'description': 'Nom ou numéro de salle'},
                    'type_cours': {
                        'type': 'string',
                        'enum': [
                            'cours',
                            'td',
                            'tp',
                            'controle',
                            'examen',
                            'sport',
                            'pause',
                            'autre',
                        ],
                    },
                    'notes': {'type': 'string'},
                },
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_presences',
            'description': (
                'Présences / absences récentes. Avec query : détail d’un élève. '
                'Sans query : totaux de l’établissement.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                    'jours': {'type': 'integer', 'description': 'Nombre de jours (1-31), défaut 7'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_sanctions',
            'description': (
                'Sanctions disciplinaires de la session : nombre total, nombre d’élèves '
                'distincts sanctionnés, liste par élève, dernières sanctions. '
                'Avec query : historique d’un élève. À utiliser pour toute question '
                'du type « combien d’élèves ont des sanctions ».'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': 'Nom, prénom ou matricule d’un élève (optionnel)',
                    },
                    'classe': {
                        'type': 'string',
                        'description': CLASSE_PARAM_DESCRIPTION,
                    },
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_annonces',
            'description': 'Annonces publiées récemment.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'creer_publier_annonce',
            'description': (
                'Prépare une annonce officielle (titre, contenu, destinataires). '
                'Ne crée rien tout de suite : une confirmation du directeur est obligatoire. '
                'À utiliser quand le directeur demande de créer, rédiger ou publier une annonce.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'titre': {
                        'type': 'string',
                        'description': 'Titre court de l’annonce',
                    },
                    'contenu': {
                        'type': 'string',
                        'description': 'Texte complet de l’annonce',
                    },
                    'destinataires': {
                        'type': 'array',
                        'items': {
                            'type': 'string',
                            'enum': [
                                'tous',
                                'enseignants',
                                'parents',
                                'eleves',
                                'personnel_administratif',
                            ],
                        },
                        'description': 'Public visé. Défaut : tous.',
                    },
                    'publier': {
                        'type': 'boolean',
                        'description': (
                            'true pour publier après confirmation, '
                            'false pour un brouillon. Défaut : true.'
                        ),
                    },
                },
                'required': ['contenu'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_periodes',
            'description': (
                'Périodes scolaires (trimestres / semestres) et période active. '
                'En supérieur : inclut le niveau LMD de chaque semestre.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'niveau_lmd': {
                        'type': 'string',
                        'description': 'Filtre optionnel (L1, M1…) — supérieur uniquement.',
                    },
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_comptabilite',
            'description': (
                'Comptabilité élèves. Avec query : fiche enrichie '
                '(inscription, mensualités, annexes, dernier reçu, moratoire). '
                'Sans query : résumé des impayés. '
                'Préfère get_fiche_scolarite, get_bilan_scolarite ou get_impayes '
                'si la question est plus précise.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_parametres_comptabilite',
            'description': (
                'Liste les paramètres de scolarité (groupes, montants, frais annexes : '
                'tenue, carte, dossier, assurance, examen, transport, cantine, apport). '
                'Pour créer, utilise creer_parametres_comptabilite.'
            ),
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_structure_superieur',
            'description': (
                'Spécialités et modules LMD : crédits totaux, UE, semestres, '
                'classes liées. Uniquement en supérieur.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'lister_pages',
            'description': 'Liste les pages de l’espace directeur que tu peux ouvrir.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ouvrir_classe',
            'description': (
                'Ouvre la fiche d’une classe précise (ex. 6e A, CF L1 A). '
                'À utiliser dès que le directeur demande d’ouvrir, afficher '
                'ou aller dans une classe nommée.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': CLASSE_PARAM_DESCRIPTION,
                    },
                    'ouvrir': {
                        'type': 'boolean',
                        'description': 'true pour ouvrir la fiche tout de suite',
                    },
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ouvrir_page',
            'description': (
                'Ouvre une page de l’application (liste des classes, annonces, etc.). '
                'Pour une classe nommée, utilise ouvrir_classe. '
                'Clés : dashboard, etablissement, classes, ajouter_classe, salles, '
                'ajouter_salle, matieres, ajouter_matiere, modules, emplois_du_temps, '
                'pedagogie, professeurs, ajouter_professeur, personnel, ajouter_personnel, '
                'eleves, inscription_eleves, gestion_eleves, reinscription, notes, '
                'justifications_notes, presences, periodes, bulletins, config_moyennes, '
                'annonces, creer_annonce, examens, emploi_examens, comptabilite, '
                'bilan_comptable, parametres_comptabilite, administration, convocations, '
                'certificats, attestations_reussite, fiches_inscription, preinscriptions, '
                'liens_preinscription, liaisons, notifications, profil, annees, '
                'creer_annee, facturation, cartes_identite, configuration_horaires. '
                'Mettre ouvrir à true seulement si le directeur demande d’y aller.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'page_key': {
                        'type': 'string',
                        'description': 'Clé de la page, par exemple annonces ou eleves',
                    },
                    'ouvrir': {
                        'type': 'boolean',
                        'description': 'true pour ouvrir, false pour seulement suggérer',
                    },
                },
                'required': ['page_key'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_notifications',
            'description': 'Notifications du directeur (non lues et récentes).',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_preinscriptions',
            'description': 'Liste des préinscriptions (défaut : en attente).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'statut': {'type': 'string', 'description': 'en_attente, validee, rejetee'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_liaisons',
            'description': 'Demandes de liaison parent-élève.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'statut': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_examens',
            'description': (
                'Sessions d’examens de l’année consultée, avec le nombre de '
                'créneaux et les classes concernées.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom de session (optionnel)'},
                    'nom': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_annees',
            'description': 'Années scolaires de l’établissement.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_salles',
            'description': 'Salles de l’établissement.',
            'parameters': {
                'type': 'object',
                'properties': {'query': {'type': 'string'}},
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_matieres',
            'description': 'Matières de l’établissement.',
            'parameters': {
                'type': 'object',
                'properties': {'query': {'type': 'string'}},
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_caisse',
            'description': (
                'Caisse du mois : recettes (paiements), dépenses et solde. '
                'À utiliser pour toute question sur la caisse, les sorties ou le solde.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'mois': {'type': 'string', 'description': 'Mois au format YYYY-MM'},
                    'query': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_volume_horaire',
            'description': (
                'Volume horaire et paie vacataire d’un professeur : heures, montant, '
                'déjà payé ou non. Période : semaine, mois (défaut) ou année scolaire.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom du professeur'},
                    'professeur': {'type': 'string'},
                    'periode': {
                        'type': 'string',
                        'enum': ['semaine', 'mois', 'annee'],
                        'description': 'Défaut : mois',
                    },
                    'mois': {'type': 'string', 'description': 'YYYY-MM'},
                    'date': {'type': 'string', 'description': 'Jour de référence (semaine)'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_affectations',
            'description': (
                'Liste ou vérifie les affectations professeurs-classes-matières '
                'de l’année scolaire active. À utiliser pour « la liste des '
                'affectations », « qui enseigne en 6e A », « quelles classes '
                'a Diallo ». Ne crée ni ne supprime rien.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': 'Nom du professeur, ou laisse vide pour tout lister',
                    },
                    'classe': {
                        'type': 'string',
                        'description': 'Nom ou code de classe pour filtrer',
                    },
                    'professeur': {'type': 'string'},
                },
            },
        },
    },
]

TOOLS_SCHEMA.extend(VAGUE2_READ_SCHEMA)
TOOLS_SCHEMA.extend(VAGUE3_READ_SCHEMA)
TOOLS_SCHEMA.extend(VAGUE4_READ_SCHEMA)
TOOLS_SCHEMA.extend(VAGUE5_READ_SCHEMA)
TOOLS_SCHEMA.extend(VAGUE6_READ_SCHEMA)
TOOLS_SCHEMA.extend([
    {
        'type': 'function',
        'function': {
            'name': 'proposer_actions',
            'description': (
                'Affiche jusqu’à 3 propositions cliquables après une lecture utile '
                '(impayés, effectifs, notes, liste). N’écrit rien. '
                'Intent chat : le directeur envoie value à Gemini. '
                'Intent open : ouvrir url. '
                'Ne pas appeler pour un bonjour, ni pendant une confirmation d’écriture '
                '(la carte oui / modifier / annuler suffit). '
                'Ne pas énumérer ces puces à l’oral.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'suggestions': {
                        'type': 'array',
                        'maxItems': 3,
                        'items': {
                            'type': 'object',
                            'properties': {
                                'label': {
                                    'type': 'string',
                                    'description': 'Texte court du bouton',
                                },
                                'value': {
                                    'type': 'string',
                                    'description': 'Message envoyé si clic (intent chat)',
                                },
                                'intent': {
                                    'type': 'string',
                                    'enum': ['chat', 'open'],
                                },
                                'url': {
                                    'type': 'string',
                                    'description': 'URL si intent open',
                                },
                            },
                            'required': ['label'],
                        },
                    },
                },
                'required': ['suggestions'],
            },
        },
    },
])
TOOLS_SCHEMA.extend(build_action_tool_schemas())


def directeur_tools_schema(ctx):
    """Schéma exposé au LLM pour le persona directeur, filtré par type."""
    from school_admin.services.assistant_schema import tools_schema_for_context

    return tools_schema_for_context(ctx, TOOLS_SCHEMA)


def execute_tool(ctx, name, arguments):
    """Exécute un outil et renvoie un dict JSON-serializable."""
    if getattr(ctx, 'persona', 'directeur') == 'eleve':
        from school_admin.services.assistant_eleve_tools import execute_eleve_tool

        return execute_eleve_tool(ctx, name, arguments)
    if getattr(ctx, 'persona', 'directeur') == 'parent':
        from school_admin.services.assistant_parent_tools import execute_parent_tool

        return execute_parent_tool(ctx, name, arguments)
    if getattr(ctx, 'persona', 'directeur') == 'enseignant_primaire':
        from school_admin.services.assistant_enseignant_primaire_tools import (
            execute_enseignant_primaire_tool,
        )

        return execute_enseignant_primaire_tool(ctx, name, arguments)
    if getattr(ctx, 'persona', 'directeur') == 'enseignant':
        from school_admin.services.assistant_enseignant_secondaire_tools import (
            execute_enseignant_secondaire_tool,
        )

        return execute_enseignant_secondaire_tool(ctx, name, arguments)
    from school_admin.services.assistant_schema import (
        tool_permission_error,
        tool_permission_error_for_search,
    )

    denied = tool_permission_error(ctx, name)
    if denied:
        return denied
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return {'erreur': f'Outil inconnu : {name}'}
    try:
        args = arguments if isinstance(arguments, dict) else {}
        result = handler(ctx, args)
        if name == 'chercher_en_base' and isinstance(result, dict):
            search_denied = tool_permission_error_for_search(ctx, result.get('source'))
            if search_denied:
                return search_denied
        return result
    except Exception:
        logger.exception("Erreur outil assistant %s", name)
        return {'erreur': f'Impossible d’exécuter {name} pour le moment.'}


def dumps_tool_result(payload):
    return json.dumps(payload, ensure_ascii=False, default=str)
