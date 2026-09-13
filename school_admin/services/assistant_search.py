"""
Recherche floue pour l’assistant vocal.

Tolère fautes (logicier → logiciel), accents et phrases bruitées
(« creee pour genie logicier » → génie logiciel).
"""
import logging
import re
import unicodedata
from difflib import SequenceMatcher

from django.db.models import Q

logger = logging.getLogger(__name__)

UNIQUE_THRESHOLD = 0.72
SUGGEST_THRESHOLD = 0.42
WEAK_THRESHOLD = 0.32
MIN_GAP = 0.10
MAX_SUGGESTIONS = 5

CLASSE_PARAM_DESCRIPTION = (
    'Nom court, code, sigle ou filière seulement. '
    'Exemples : « GL L1 A », « génie logiciel », « licence 1 ». '
    'Ne jamais recopier la phrase entière '
    '(pas « crée l’emploi du temps de… »). '
    'Si le nom est mal orthographié, envoie-le tel quel : '
    'la recherche corrige les fautes.'
)

CLASS_NOISE_RES = (
    re.compile(
        r"\b(?:cr[éeè]{1,4}[erz]?|ajout(?:e[rz]?|er)|pr[ée]pare[rz]?|"
        r"ouvre[rz]?|afficher?|montre[rz]?|lance[rz]?|g[ée]n[èe]re[rz]?|"
        r"fais|faire|va[sz]?|aller|donne[rz]?)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:emploi(?:s)?\s+du\s+temps|emplois?\s+du\s+temp|edt)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:classe|promotion|fili[eè]re|d[ée]partement|sp[ée]cialit[ée])s?\b",
        re.I,
    ),
    re.compile(r"\b(?:pour|dans|avec|vers|sur|chez)\b", re.I),
)

STOPWORDS = {
    'le', 'la', 'les', 'un', 'une', 'des', 'du', 'de', 'd', 'l',
    'et', 'ou', 'au', 'aux', 'en', 'ce', 'cet', 'cette',
}


def fold_text(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def clean_class_query(query):
    """Retire le bruit autour du nom de classe / filière."""
    text = (query or '').strip().rstrip('.!?…')
    text = re.sub(r"l['’]", ' ', text, flags=re.I)
    for pattern in CLASS_NOISE_RES:
        text = pattern.sub(' ', text)
    text = re.sub(r'\s+', ' ', text).strip(' .,;:!?-')
    tokens = [token for token in text.split() if fold_text(token) not in STOPWORDS]
    cleaned = ' '.join(tokens).strip()
    return cleaned or (query or '').strip()


def token_similarity(query, haystack):
    """Score 0–1 : chaque mot de la requête vs le meilleur mot cible."""
    q_tokens = [token for token in fold_text(query).split() if token not in STOPWORDS]
    h_tokens = fold_text(haystack).split()
    if not q_tokens or not h_tokens:
        return 0.0
    scores = []
    for query_token in q_tokens:
        best = 0.0
        for hay_token in h_tokens:
            if query_token == hay_token:
                best = 1.0
                break
            if query_token in hay_token or hay_token in query_token:
                best = max(best, 0.88)
            best = max(best, SequenceMatcher(None, query_token, hay_token).ratio())
        scores.append(best)
    compact_q = fold_text(query).replace(' ', '')
    compact_h = fold_text(haystack).replace(' ', '')
    compact = 1.0 if compact_q and compact_q == compact_h else 0.0
    if compact_q and compact_q in compact_h:
        compact = max(compact, 0.9)
    whole = SequenceMatcher(None, fold_text(query), fold_text(haystack)).ratio()
    return max(sum(scores) / len(scores), whole, compact)


def pick_unique(objects, query, haystack_fn, unique_threshold=UNIQUE_THRESHOLD):
    """Retourne l’objet le plus proche s’il est nettement devant, sinon None."""
    scored = []
    for obj in objects:
        scored.append((token_similarity(query, haystack_fn(obj)), obj))
    scored.sort(key=lambda item: -item[0])
    if not scored:
        return None
    best_score, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if best_score >= unique_threshold and (best_score - second) >= MIN_GAP:
        return best
    return None


def is_lookup_clarification(result):
    """True si le résultat demande une précision, pas une erreur système."""
    if not isinstance(result, dict):
        return False
    if result.get('statut') in ('incomplet', 'plusieurs', 'introuvable'):
        return True
    if result.get('trouve') is False:
        return True
    if result.get('plusieurs_classes'):
        return True
    if result.get('suggestions_possibles') or result.get('suggestions'):
        return True
    return False


def _classe_haystack(classe):
    department = classe.department
    parts = [
        classe.nom or '',
        classe.code_classe or '',
        classe.niveau_lmd or '',
        classe.niveau_libelle or '',
        classe.description or '',
    ]
    if hasattr(classe, 'get_niveau_display'):
        parts.append(classe.get_niveau_display() or '')
    if department is not None:
        parts.extend([
            department.nom or '',
            department.sigle or '',
            department.mention or '',
            department.domaine or '',
        ])
    level = getattr(classe, 'academic_level', None)
    if level is not None:
        parts.extend([level.nom or '', level.code or ''])
    return ' '.join(parts)


def _trigram_candidates(qs, query, limit=8):
    try:
        from django.contrib.postgres.search import TrigramSimilarity
        from django.db.models.functions import Greatest
    except ImportError:
        return []
    try:
        return list(
            qs.annotate(
                _aria_sim=Greatest(
                    TrigramSimilarity('nom', query),
                    TrigramSimilarity('code_classe', query),
                    TrigramSimilarity('department__nom', query),
                    TrigramSimilarity('department__sigle', query),
                )
            )
            .filter(_aria_sim__gte=0.18)
            .order_by('-_aria_sim')[:limit]
        )
    except Exception:
        logger.debug("Recherche trigram indisponible", exc_info=True)
        return []


def _sql_loose_filter(qs, query):
    tokens = [token for token in fold_text(query).split() if token not in STOPWORDS]
    filters = (
        Q(nom__icontains=query)
        | Q(code_classe__icontains=query)
        | Q(description__icontains=query)
        | Q(niveau_lmd__icontains=query)
        | Q(niveau_libelle__icontains=query)
        | Q(department__nom__icontains=query)
        | Q(department__sigle__icontains=query)
        | Q(department__mention__icontains=query)
    )
    for token in tokens:
        if len(token) < 2:
            continue
        filters |= (
            Q(nom__icontains=token)
            | Q(code_classe__icontains=token)
            | Q(department__nom__icontains=token)
            | Q(department__sigle__icontains=token)
            | Q(department__mention__icontains=token)
            | Q(niveau_lmd__icontains=token)
        )
    return qs.filter(filters)


def _unique_payload(ctx, classe, query, cleaned, score=1.0):
    from school_admin.services.assistant_tools import _classe_item

    item = _classe_item(ctx, classe)
    item.update({
        'statut': 'ok',
        'trouve': True,
        'query': query,
        'query_normalisee': cleaned,
        'similarite': round(score, 2),
        'titre': classe.nom,
    })
    return item


def search_classes(ctx, query, limit=MAX_SUGGESTIONS):
    """
    Cherche une classe par nom, code, sigle, filière, niveau.

    Retours possibles :
    - statut=ok + id : correspondance unique
    - statut=plusieurs : plusieurs proches (suggestions_possibles)
    - statut=introuvable : rien de suffisamment proche
    Jamais de clé « erreur » pour un simple raté de nom.
    """
    from school_admin.services.assistant_tools import _classe_item, _classes_qs

    raw = (query or '').strip()
    cleaned = clean_class_query(raw)
    if not cleaned:
        return {
            'trouve': False,
            'statut': 'incomplet',
            'ouvrir': False,
            'manquants': ['classe'],
            'query': raw,
            'query_normalisee': '',
            'suggestions_possibles': [],
            'suggestions': [],
            'classes': [],
            'message': 'Demande le nom de la classe, du code ou de la filière.',
        }

    qs = _classes_qs(ctx).select_related('department', 'academic_level')
    exact = list(
        qs.filter(
            Q(nom__iexact=cleaned)
            | Q(code_classe__iexact=cleaned)
            | Q(department__sigle__iexact=cleaned)
        )[:limit]
    )
    if len(exact) == 1:
        return _unique_payload(ctx, exact[0], raw, cleaned, score=1.0)

    candidates = {}
    for classe in exact:
        candidates[classe.id] = classe
    for classe in _sql_loose_filter(qs, cleaned)[:40]:
        candidates[classe.id] = classe
    for classe in _trigram_candidates(qs, cleaned):
        candidates[classe.id] = classe
    if len(candidates) < 4:
        for classe in qs:
            candidates[classe.id] = classe

    scored = []
    for classe in candidates.values():
        score = token_similarity(cleaned, _classe_haystack(classe))
        scored.append((score, classe))
    scored.sort(key=lambda item: -item[0])

    strong = [(score, classe) for score, classe in scored if score >= SUGGEST_THRESHOLD]
    if not strong and scored and scored[0][0] >= WEAK_THRESHOLD:
        strong = scored[:limit]

    if not strong:
        return {
            'trouve': False,
            'statut': 'introuvable',
            'ouvrir': False,
            'query': raw,
            'query_normalisee': cleaned,
            'suggestions_possibles': [],
            'suggestions': [],
            'classes': [],
            'message': (
                f"Aucune classe proche de « {cleaned} ». "
                "Demande une précision à l’oral, sans parler d’erreur système."
            ),
        }

    best_score, best = strong[0]
    second = strong[1][0] if len(strong) > 1 else 0.0
    if best_score >= UNIQUE_THRESHOLD and (best_score - second) >= MIN_GAP:
        return _unique_payload(ctx, best, raw, cleaned, score=best_score)

    items = []
    for score, classe in strong[:limit]:
        item = _classe_item(ctx, classe)
        item['similarite'] = round(score, 2)
        items.append(item)

    return {
        'trouve': False,
        'statut': 'plusieurs',
        'ouvrir': False,
        'query': raw,
        'query_normalisee': cleaned,
        'classes': items,
        'suggestions': [
            {'titre': item['nom'], 'url': item.get('url')}
            for item in items
        ],
        'suggestions_possibles': [
            {
                'nom': item['nom'],
                'id': item['id'],
                'libelle': item.get('libelle') or item['nom'],
                'departement': item.get('departement'),
                'sigle': item.get('sigle'),
                'niveau_lmd': item.get('niveau_lmd'),
                'similarite': item.get('similarite'),
            }
            for item in items
        ],
        'message': (
            f"Aucune classe exacte pour « {cleaned} ». "
            "Propose à l’oral les suggestions_possibles et demande de choisir."
        ),
    }


def find_classe(ctx, query):
    """Objet Classe si une seule correspondance fiable, sinon None."""
    from school_admin.model.classe_model import Classe

    result = search_classes(ctx, query)
    classe_id = result.get('id') if result.get('statut') == 'ok' else None
    if not classe_id:
        return None
    return Classe.objects.filter(
        pk=classe_id,
        etablissement=ctx.etablissement,
        actif=True,
    ).first()


def choices_from_class_lookup(result, intent='chat'):
    """Boutons cliquables à partir d’un résultat de recherche de classe."""
    if not isinstance(result, dict):
        return []
    rows = (
        result.get('suggestions_possibles')
        or result.get('classes')
        or result.get('suggestions')
        or []
    )
    choices = []
    for item in rows[:MAX_SUGGESTIONS]:
        if not isinstance(item, dict):
            continue
        label = (
            item.get('libelle')
            or item.get('nom')
            or item.get('titre')
            or item.get('label')
            or ''
        ).strip()
        if not label:
            continue
        choice = {
            'label': label,
            'value': item.get('nom') or item.get('titre') or label,
            'intent': intent,
        }
        if item.get('url') and intent == 'open':
            choice['url'] = item['url']
        choices.append(choice)
    return choices
