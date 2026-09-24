"""
Client Gemini 2.5 Flash (API compatible OpenAI) pour l'assistant vocal Aria.
Rollback DeepSeek via ASSISTANT_LLM_PROVIDER=deepseek.
"""
import json
import logging
import re
import uuid

from asgiref.sync import sync_to_async
from django.conf import settings

from school_admin.services.assistant_tools import (
    context_snapshot,
    directeur_tools_schema,
    dumps_tool_result,
    enrich_class_snapshot,
    execute_tool,
    json_safe_tool_result,
    spoken_from_tool_result,
    spoken_from_tool_results,
)
from school_admin.services.gemini_context_cache import (
    cache_enabled,
    ensure_tools_cache,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8
TOOL_TEMPERATURE = 0.5
CONVERSATION_TEMPERATURE = 0.7
LLM_TIMEOUT = 60.0


def format_turn_telemetry(
    tools=None,
    rounds=0,
    pending_shown=0,
    suggestions_count=0,
    takeover=0,
):
    """Une ligne de recette G7 : tool, rounds, pending, suggestions, takeover."""
    names = []
    for item in tools or []:
        name = item[0] if isinstance(item, (tuple, list)) else item
        if name:
            names.append(str(name))
    return {
        'tool': ','.join(names),
        'rounds': int(rounds or 0),
        'pending_shown': int(bool(pending_shown)),
        'suggestions_count': int(suggestions_count or 0),
        'takeover': int(takeover or 0),
    }


def log_turn_telemetry(payload):
    logger.info('assistant.turn %s', json.dumps(payload, ensure_ascii=False))
    return payload


def _note_turn_stats(stats, rounds=None, tools=None):
    if not isinstance(stats, dict):
        return
    if rounds is not None:
        stats['rounds'] = rounds
    if tools:
        bag = stats.setdefault('tools', [])
        for name in tools:
            if name:
                bag.append(name)


async def _emit_spoken_fallback(on_text_delta, spoken):
    """Le repli oral doit aussi passer par le stream, sinon le client reste muet."""
    text = (spoken or '').strip()
    if text and on_text_delta:
        await on_text_delta(text)
    return text


DEICTIC_CLASSE = frozenset({
    '',
    'cette',
    'cette classe',
    'celle-ci',
    'celle ci',
    'celle-là',
    'celle là',
    'la classe',
    'cette-ci',
})
CLASSE_ARG_TOOLS = frozenset({
    'get_effectifs',
    'rechercher_eleves',
    'rechercher_classes',
    'ouvrir_classe',
    'get_affectations',
    'get_mes_classes',
    'get_emploi_du_temps',
    'get_notes_classe',
    'get_notes_examen',
    'get_eleves_difficulte',
    'get_impayes',
    'get_moyennes_classe',
    'get_evaluations_classe',
    'get_exercices_maison',
    'get_presences',
    'chercher_en_base',
    'creer_publier_annonce',
    'enregistrer_note',
    'creer_evaluation',
    'creer_exercice_maison',
    'enregistrer_presences',
    'valider_presence_classe',
    'calculer_moyennes_matiere',
    'soumettre_releve_matiere',
})


def apply_working_refs(name, arguments, refs=None):
    """« Cette classe » → dernière classe ouverte (classe / classe_id)."""
    args = dict(arguments or {}) if isinstance(arguments, dict) else {}
    refs = refs or {}
    classe = (refs.get('classe') or '').strip()
    if not classe or name not in CLASSE_ARG_TOOLS:
        return args
    raw = (args.get('classe') or args.get('query') or '').strip()
    lowered = raw.lower()
    if raw and lowered not in DEICTIC_CLASSE and 'cette classe' not in lowered:
        return args
    args['classe'] = classe
    if name == 'ouvrir_classe':
        args['query'] = classe
    if name == 'chercher_en_base' and not (args.get('question') or '').strip():
        args['query'] = raw or classe
    return args


def _iter_model_parts(response):
    parts = []
    for candidate in getattr(response, 'candidates', None) or []:
        content = getattr(candidate, 'content', None)
        for part in getattr(content, 'parts', None) or []:
            parts.append(part)
    return parts


def _part_thought_signature(part):
    if part is None:
        return None
    return getattr(part, 'thought_signature', None) or getattr(
        getattr(part, 'function_call', None), 'thought_signature', None
    )


def _first_function_call_is_signed(parts):
    for part in parts or []:
        call = getattr(part, 'function_call', None)
        if call and getattr(call, 'name', None):
            return bool(_part_thought_signature(part))
    return False


def _model_parts_for_replay(model_parts, function_calls):
    """Rejoue les parts modèle d’origine (thought_signature obligatoire)."""
    from google.genai import types

    if model_parts:
        return list(model_parts)
    replay = []
    for call in function_calls or []:
        name = getattr(call, 'name', '') or ''
        raw_args = getattr(call, 'args', None) or {}
        arguments = raw_args if isinstance(raw_args, dict) else {}
        if not isinstance(arguments, dict):
            arguments = dict(arguments) if arguments else {}
        part = types.Part.from_function_call(name=name, args=arguments)
        signature = _part_thought_signature(call)
        if signature:
            part.thought_signature = signature
        replay.append(part)
    return replay


def _unpack_cached_round(packed):
    if packed is None:
        return None, [], '', []
    if len(packed) >= 4:
        return packed[0], packed[1], packed[2], packed[3] or []
    response, function_calls, spoken = packed
    return response, function_calls, spoken, _iter_model_parts(response)


_resolved_gemini_model = None
GEMINI_MODEL_FALLBACKS = (
    'gemini-3.6-flash',
    'gemini-3-flash-preview',
)
INVOKE_RE = re.compile(r'invoke\s+name=["\']([A-Za-z0-9_]+)["\']', re.IGNORECASE)
PARAM_RE = re.compile(
    r'parameter\s+name=["\']([^"\']+)["\'][^>]*>([^<]*)',
    re.IGNORECASE,
)
XML_TOOL_RE = re.compile(
    r'<tool_call>\s*([A-Za-z0-9_]+)\s*(.*?)</tool_call>',
    re.IGNORECASE | re.DOTALL,
)
XML_ARG_RE = re.compile(
    r'<arg_key>\s*([^<]+?)\s*</arg_key>\s*<arg_value>\s*(.*?)\s*</arg_value>',
    re.IGNORECASE | re.DOTALL,
)
MARKUP_RE = re.compile(
    r'DSML|</?tool_call>|invoke\s+name=|function_calls|<\|',
    re.IGNORECASE,
)

SYSTEM_PROMPT = """Tu es Aria, l'assistante vocale de direction de l'établissement.

Assistante :
- Tu comprends, tu agis, tu proposes. Tu n'es pas un formulaire, ni un menu.
- Si la demande est claire, enchaîne les outils Django puis parle.
- Si un détail manque vraiment, pose UNE question. Jamais « champ 1, champ 2,
  champ 3 ». Jamais un questionnaire vocal.
- Après une lecture, propose 1 à 3 suites utiles (puces UI, une phrase orale).
- Le schéma d'outils est ton catalogue. N'énumère pas les outils à l'oral.
- Sois chaleureuse, claire, conversationnelle. Pas de « Je cherche ça »,
  « Voici la réponse », « Un instant ».
- Bonjour, merci, comment ça va : réponds comme un humain, sans outil.

Voix :
- Tes réponses seront lues à voix haute, en français naturel.
- Phrases fluides. Pas de virgules artificielles.
- Noms d'élèves, de professeurs et de lieux avec leur casse naturelle
  (Clé Jason, pas CLÉ JASON). Jamais de capitales intégrales.
- Jamais de markdown, d'URL, de DSML, de tableaux ni de listes à puces lues
  à voix haute. Raconte en phrases, par exemple :
  « Vous avez 50 élèves, 25 filles et 25 garçons, répartis dans 5 classes. »
- Nombres en chiffres (110, 2026). Conserve noms, classes, matricules.

Outils :
- Tes seules commandes sont les outils Django déjà exposés. Pas de shell,
  pas de SQL, pas de fichiers, pas de commande système.
- Le contexte ne contient pas les chiffres ni les listes : ils sont en base.
- Interdit : dire « je n'ai pas cette information » sans avoir cherché.
- Utilise seulement l'API d'outils. N'écris jamais les appels en texte.
- Une demande riche (ouvrir + notes, effectifs + impayés, préparer une classe)
  = plusieurs tools puis UNE synthèse orale. N'arrête pas après le premier.
- « Cette classe » = la dernière classe ouverte (classe / classe_id déjà cités).
- Infos d'une classe = effectifs + élèves + professeurs (plusieurs tools),
  pas seulement les affectations.
- Réutilise les ids déjà vus (classe_id, eleve_id) plutôt que de redemander
  le nom (« relance-le », « ouvre sa fiche »).
- Après une lecture utile, appelle proposer_actions (1 à 3 suites). Une phrase
  de relance à l'oral suffit, sans lire les puces.
- Pas de proposer_actions pour un bonjour, ni quand une écriture attend
  confirmation (la carte oui / modifier / annuler suffit).
- Ne propose pas de créer ce que tes outils ne savent pas créer.

Après une action :
- Confirme clairement ce qui s'est passé (quoi, pour qui, ouvert, publié,
  en attente, échoué). Ne conclus jamais en silence.
- Propose ensuite une suite possible, sauf si une carte de confirmation
  est déjà à l'écran.
- Écriture : présente le brouillon. La carte oui / modifier / annuler décide.
  Tu n'appliques jamais toi-même. Ne dis pas d'ouvrir un formulaire.

Rédaction :
- Annonce, message, titre : rédige toi-même à partir du sujet. On n'a pas
  besoin de tout dicter. 8000 caractères maximum.

Pièges :
- Destinataires d'annonce : tous, enseignants, parents, eleves,
  personnel_administratif.
- Classe : seulement le nom, le code ou la filière
  (ex. « génie logiciel », « GL L1 A »), jamais la phrase entière.
- N'invente pas de chiffres, de classes, d'élèves ni d'ECTS.
- Sanction : n'énumère pas les types ni les raisons à l'oral
  (liste déroulante à l'écran). Rédige la note, puis demande le oui.
- Noms mal orthographiés : ce n'est pas une erreur système. Pose une
  question naturelle (« Licence 1 Génie Logiciel ou Licence 2 ? »).
- Navigation : classe nommée → ouvrir_classe ; une page → ouvrir_page.

Sujet :
- Le dernier message de l'utilisateur a toujours priorité.
- S'il n'est pas une réponse à ta dernière question, abandonne l'ancienne
  action et réponds uniquement à ce message.
- Ne repose jamais la même question s'il a déjà répondu.
"""

SYSTEM_PROMPT_ENSEIGNANT_PRIMAIRE = """Tu es Aria, l'assistante vocale des enseignants du primaire.
Tu aides pour les classes affectées, les notes, les présences, les exercices,
les élèves en difficulté et la navigation dans l'espace enseignant.

Réponds directement, chaleureusement, en français oral naturel.
Pas de markdown, pas d'URL, pas de listes à puces lues à voix haute.
Après une lecture utile, propose 2 ou 3 suites via proposer_actions (chips).

Outils :
- Tu n'accèdes qu'aux classes et élèves du professeur connecté (affectations).
- Appelle un outil pour toute donnée ou action (notes, présences, pages).
- Les actions d'écriture exigent confirmation explicite après présentation du résumé.
- Navigation : ouvrir_page ou ouvrir_classe avec ouvrir true.
- « Cette classe » = dernière classe ouverte ou citée (contexte working_refs).

Infos classe : combine si besoin effectifs, liste d'élèves (rechercher_eleves),
évaluations ou notes — ne te contente pas d'une phrase vide.

Notes et évaluations :
- enregistrer_note, creer_evaluation, calculer_moyennes_matiere, soumettre_releve_matiere.
- Ne modifie pas un relevé déjà soumis.

Présences et discipline :
- enregistrer_presences, valider_presence_classe, soumettre_sanction.

Exercices : creer_exercice_maison.

Interdit : comptabilité, caisse, personnel administratif, affectations globales,
annonces directeur, préinscriptions, volume horaire.

Sujet : le dernier message utilisateur a toujours priorité. Si ce message
n'est pas une réponse à ta dernière question, ignore l'historique métier
et réponds à CE message. Une seule question si une information
indispensable manque.
"""

SYSTEM_PROMPT_ENSEIGNANT = """Tu es Aria, l'assistante vocale des enseignants (collège, lycée, supérieur).
Tu aides pour les classes et matières affectées, les notes, présences, exercices,
élèves en difficulté et la navigation dans l'espace enseignant.

Réponds directement, chaleureusement, en français oral naturel.
Pas de markdown, pas d'URL, pas de listes à puces lues à voix haute.
Après une lecture utile, propose 2 ou 3 suites via proposer_actions (chips).

Outils :
- Tu n'accèdes qu'aux classes / matières du professeur connecté.
- Appelle un outil pour toute donnée ou action.
- Écriture : confirmation explicite obligatoire.
- Navigation : ouvrir_page ou ouvrir_classe avec ouvrir true.
- « Cette classe » = dernière classe ouverte (working_refs).

Notes : enregistrer_note, creer_evaluation, calculer_moyennes_matiere, soumettre_releve_notes.
Examens (college / lycee) : get_examens_prof, get_notes_examen, ouvrir_noter_examen, enregistrer_note_examen.
Présences : enregistrer_presences, valider_presence_classe, soumettre_sanction.
Exercices : creer_exercice_maison.

Interdit : comptabilité, caisse, RH, affectations globales, annonces directeur.

Le dernier message utilisateur a toujours priorité.
"""

SYSTEM_PROMPT_PARENT = """Tu es Aria, l'assistante des parents dans Aria gestion scolaire.
Tu accompagnes les familles : conseils, organisation, compréhension de la scolarité
(notes, absences, devoirs, convocations, paiements) — sans piloter l'établissement.

Langues (priorité au dernier message parent) :
- Wolof : réponds principalement en wolof (alphabet latin), ton simple et respectueux, jamais condescendant.
- Français : réponds en français.
- Code-switch wolof-français (Wolof français) : accepte le mélange, ne force pas un wolof « pur ».
- Ne traduis pas mot à mot : reste claire, chaleureuse et bienveillante.

Réponds directement, chaleureusement, en oral naturel. Pas de markdown ni d'URL lues à voix haute.
Utilise les outils pour : enfants, navigation, annonces, notifications, puis suivi scolaire
(get_notes_enfant, get_bulletin_enfant, get_devoirs_enfant, get_absences_enfant,
get_sanctions_enfant, get_convocations_enfant, get_convocations_famille, get_emploi_enfant,
get_scolarite_enfant, get_scolarite_famille, ouvrir_recu).
Tu n'inventes jamais de notes, moyennes, montants ou dates : appelle d'abord le tool adapté.
Pour tout montant ou échéance de scolarité, utilise get_scolarite_enfant ou get_scolarite_famille.
Les reçus : ouvrir_recu uniquement (lecture), jamais enregistrer de paiement.

Écritures confirmées (carte oui / modifier / annuler — rien n’est appliqué sans « oui ») :
marquer_notification_lue, demande_liaison_enfant (matricule + mot de passe élève).
Jamais : paiement vocal, changement de mot de passe vocal, tools directeur/enseignant.

Interdit : effectifs établissement, caisse, RH, inscriptions direction, comptabilité générale,
saisie de notes, enregistrement de paiements, données d'autres élèves que ceux liés au compte
(voir enfants_lies / enfant_consulte).

Pour une question combinée (ex. notes et absences), appelle plusieurs outils de lecture
dans le même tour si nécessaire — sans wizard ni action d’établissement.

Le dernier message utilisateur a toujours priorité.
"""

SYSTEM_PROMPT_ELEVE = """Tu es Aria, l’assistante des élèves dans Aria gestion scolaire.
Tu tutoies l’élève connecté. Tu l’aides à s’organiser, comprendre ses notes, devoirs,
absences et annonces — sans parler à sa place aux adultes de l’établissement.

Tu disposes d’outils de navigation (résumé, lister_pages, ouvrir_page) et de lecture scolaire
lorsqu’ils sont activés : appelle-les avant de citer des notes, moyennes, dates ou montants.
N’invente jamais de chiffres scolaires.

Langues : si l’élève écrit ou parle en wolof, réponds surtout en wolof (alphabet latin,
ton jeune et clair) ; s’il repasse en français, réponds en français. Exemples wolof :
« Na nga def ? », « Wax ma ci devoir yi. »

Interdit : effectifs, caisse, RH, outils directeur ou professeur, scolarité/paiements,
données d’autres élèves, modification de mot de passe ou photo par la voix.

Le dernier message utilisateur a toujours priorité.
"""

ELEVE_WELCOME = (
    "Salut ! Je suis Aria, ton assistante pour t’organiser à l’école. "
    "Pose-moi tes questions — bientôt je pourrai aussi lire tes notes et tes devoirs depuis l’app."
)

ELEVE_WELCOME_BILINGUAL = (
    "Nanga def ! Man degg Wolof ak Français. "
    "Dama la dimbali ngir nga organize sa école — notes, devoirs, absences. "
    "Wax ma ci Wolof walla ci Français. "
    "Salut ! Je suis Aria, ton assistante : pose-moi tes questions en wolof ou en français."
)

PARENT_WELCOME_BILINGUAL = (
    "Bonjour ! Man degg Wolof ak Français. "
    "Dama la dimbali ci sa xale yi — notes, absences, devoirs ak scolarité. "
    "Wax ma ci Wolof walla ci Français. "
    "Je suis Aria, votre assistante famille : posez-moi vos questions en wolof ou en français."
)

SYSTEM_PROMPT_STATIC = SYSTEM_PROMPT
SYSTEM_PROMPT = SYSTEM_PROMPT_STATIC + """

Contexte établissement :
{context}
"""

WRITTEN_DRAFT_MAX = 8000
WRITE_JSON_RE = re.compile(r'\{.*\}', re.DOTALL)


def _llm_provider():
    return getattr(settings, 'ASSISTANT_LLM_PROVIDER', 'gemini') or 'gemini'


def _parse_tool_arg(raw):
    value = (raw or '').strip()
    lowered = value.lower()
    if lowered == 'true':
        return True
    if lowered == 'false':
        return False
    if re.fullmatch(r'-?\d+', value):
        return int(value)
    return value


def extract_markup_tool_calls(text):
    """Récupère les appels d'outils écrits en DSML / XML au lieu de tool_calls."""
    calls = []
    if not text:
        return calls

    parts = re.split(r'(?=invoke\s+name=)', text, flags=re.IGNORECASE)
    for part in parts:
        invoke = INVOKE_RE.search(part)
        if not invoke:
            continue
        arguments = {}
        for match in PARAM_RE.finditer(part):
            arguments[match.group(1).strip()] = _parse_tool_arg(match.group(2))
        calls.append({
            'id': f'dsml-{invoke.group(1)}-{uuid.uuid4().hex[:8]}',
            'name': invoke.group(1),
            'arguments': arguments,
        })

    for match in XML_TOOL_RE.finditer(text):
        arguments = {
            key.strip(): _parse_tool_arg(value)
            for key, value in XML_ARG_RE.findall(match.group(2) or '')
        }
        calls.append({
            'id': f'xml-{match.group(1)}-{uuid.uuid4().hex[:8]}',
            'name': match.group(1),
            'arguments': arguments,
        })
    return calls


def looks_like_tool_markup(text):
    return bool(text and MARKUP_RE.search(text))


def strip_tool_markup(text):
    from school_admin.services.tts_service import strip_assistant_markup

    cleaned = text or ''
    cleaned = re.sub(r'<\|?\s*/?\s*DSML\s*\|?>', ' ', cleaned)
    cleaned = re.sub(r'<｜/?DSML｜>', ' ', cleaned)
    cleaned = re.sub(r'</?(?:tool_calls?|function_calls?)>', ' ', cleaned, flags=re.I)
    cleaned = re.sub(r'invoke\s+name=["\'][^"\']+["\']', ' ', cleaned, flags=re.I)
    cleaned = re.sub(r'parameter\s+name=["\'][^"\']+["\'][^>]*>[^<]*', ' ', cleaned, flags=re.I)
    if looks_like_tool_markup(cleaned):
        return ''
    return strip_assistant_markup(cleaned)


def system_prompt_static_for(ctx):
    persona = getattr(ctx, 'persona', 'directeur')
    if persona == 'parent':
        return SYSTEM_PROMPT_PARENT
    if persona == 'eleve':
        return SYSTEM_PROMPT_ELEVE
    if persona == 'enseignant_primaire':
        return SYSTEM_PROMPT_ENSEIGNANT_PRIMAIRE
    if persona == 'enseignant':
        base = SYSTEM_PROMPT_ENSEIGNANT
        if getattr(ctx, 'est_superieur', False):
            base += (
                '\nÉtablissement supérieur : parle d’« étudiants », périodes LMD / semestres. '
                'Utilise get_modules_classe et get_credits_etudiant pour la maquette ECTS '
                '(ne jamais inventer de crédits). '
                'creer_evaluation : préciser le semestre LMD (ex. Semestre 1) et le niveau si besoin. '
                'Pas de tools direction (scolarité globale, caisse, structure établissement).'
            )
        return base
    from school_admin.services.assistant_schema import prompt_addendum_for

    return SYSTEM_PROMPT_STATIC + prompt_addendum_for(ctx)


def tools_schema_for(ctx):
    persona = getattr(ctx, 'persona', 'directeur')
    if persona == 'parent':
        from school_admin.services.assistant_parent_tools import get_parent_tools_schema

        return get_parent_tools_schema(ctx)
    if persona == 'eleve':
        from school_admin.services.assistant_eleve_tools import get_eleve_tools_schema

        return get_eleve_tools_schema(ctx)
    if persona == 'enseignant_primaire':
        from school_admin.services.assistant_enseignant_primaire_tools import (
            get_enseignant_primaire_tools_schema,
        )

        return get_enseignant_primaire_tools_schema()
    if persona == 'enseignant':
        from school_admin.services.assistant_enseignant_secondaire_tools import (
            get_enseignant_secondaire_tools_schema,
        )

        return get_enseignant_secondaire_tools_schema(ctx)
    return directeur_tools_schema(ctx)


def build_system_message(ctx, tool_memory=''):
    snapshot = json.dumps(context_snapshot(ctx), ensure_ascii=False)
    base = system_prompt_static_for(ctx)
    extra = f"\n\nContexte établissement :\n{snapshot}"
    memory = (tool_memory or '').strip()
    if memory:
        extra += f"\n\nDernier outil (ne pas relire à l'oral) : {memory}"
    return {
        'role': 'system',
        'content': base + extra,
    }


_MEMORY_KEYS = (
    'nb_eleves',
    'nb_eleves_actifs',
    'nb_classes',
    'nb_professeurs',
    'nb_personnel',
    'nb_filles',
    'nb_garcons',
    'nb_impayes',
    'nb_impaye',
    'nb',
    'session',
    'classe',
    'classe_id',
    'eleve_id',
    'id',
    'nom',
    'eleve',
    'source',
    'statut',
    'taux',
    'moyenne',
    'cnss',
    'periode',
    'perimetre',
)
_LIST_NAME_KEYS = ('eleves', 'impayes', 'classes', 'professeurs')
_WORKING_REF_ORDER = ('classe_id', 'classe', 'eleve_id', 'eleve')


def extract_working_refs(name, result):
    """Ids et noms cités (classe / élève) pour le tour suivant (« relance-le »)."""
    refs = {}
    if not name or not isinstance(result, dict):
        return refs
    if result.get('classe_id') not in (None, '', [], {}):
        refs['classe_id'] = result['classe_id']
    if result.get('eleve_id') not in (None, '', [], {}):
        refs['eleve_id'] = result['eleve_id']
    classe = result.get('classe')
    if isinstance(classe, str) and classe.strip():
        refs['classe'] = classe.strip()
    eleve = result.get('eleve')
    if isinstance(eleve, str) and eleve.strip():
        refs['eleve'] = eleve.strip()
    if name in ('ouvrir_classe', 'rechercher_classes') or result.get('url'):
        if result.get('id') not in (None, '') and 'classe_id' not in refs:
            refs['classe_id'] = result['id']
        nom = result.get('nom')
        if isinstance(nom, str) and nom.strip() and 'classe' not in refs:
            refs['classe'] = nom.strip()
    rows = result.get('eleves') or result.get('impayes') or []
    if isinstance(rows, list):
        for row in rows[:1]:
            if not isinstance(row, dict):
                continue
            if row.get('eleve_id') and 'eleve_id' not in refs:
                refs['eleve_id'] = row['eleve_id']
            if row.get('id') and result.get('eleves') and 'eleve_id' not in refs:
                refs['eleve_id'] = row['id']
            if row.get('classe_id') and 'classe_id' not in refs:
                refs['classe_id'] = row['classe_id']
            nom = row.get('nom') or row.get('eleve')
            if nom and 'eleve' not in refs:
                refs['eleve'] = str(nom)
            classe_nom = row.get('classe')
            if isinstance(classe_nom, str) and classe_nom.strip() and 'classe' not in refs:
                refs['classe'] = classe_nom.strip()
    if name == 'get_mes_classes':
        rows = result.get('classes') or []
        if rows and 'classe' not in refs:
            first = rows[0]
            if isinstance(first, dict):
                nom = (first.get('classe') or first.get('nom') or '').strip()
                if nom:
                    refs['classe'] = nom
                if first.get('classe_id') and 'classe_id' not in refs:
                    refs['classe_id'] = first['classe_id']
    return refs


def format_cited_refs(refs):
    if not refs:
        return ''
    parts = []
    for key in _WORKING_REF_ORDER:
        value = refs.get(key)
        if value not in (None, '', [], {}):
            parts.append(f'{key}={value}')
    return ', '.join(parts)


def compact_tool_memory(name, result, max_len=400):
    """Résumé du dernier outil + ids/noms cités, pour le tour suivant."""
    if not name or not isinstance(result, dict):
        return ''
    parts = [str(name)]
    if result.get('erreur') and result.get('statut') not in (
        'incomplet',
        'en_attente_confirmation',
    ):
        parts.append('erreur')
        return ', '.join(parts)[:max_len]
    bag = dict(result)
    nested = result.get('effectifs')
    if isinstance(nested, dict):
        bag = {**nested, **bag}
    if name == 'ouvrir_classe' and bag.get('id') not in (None, '') and 'classe_id' not in bag:
        bag['classe_id'] = bag['id']
    for key in _MEMORY_KEYS:
        value = bag.get(key)
        if value in (None, '', [], {}):
            continue
        if key == 'id' and 'classe_id' in bag and bag.get('classe_id') == value:
            continue
        if isinstance(value, (int, float, str, bool)):
            parts.append(f'{key}={value}')
    for list_key in _LIST_NAME_KEYS:
        rows = bag.get(list_key)
        if not isinstance(rows, list) or not rows:
            continue
        names = []
        for row in rows[:2]:
            if isinstance(row, dict):
                label = row.get('nom') or row.get('eleve') or row.get('libelle')
                if label:
                    names.append(str(label))
        if names:
            parts.append(f'{list_key}={"+".join(names)}')
    return ', '.join(parts)[:max_len]


def _messages_for_api(messages):
    """Conserve le system prompt et nettoie le dialogue user/assistant."""
    system = [
        item for item in (messages or [])
        if isinstance(item, dict) and item.get('role') == 'system'
    ]
    dialog = sanitize_dialog_messages([
        item for item in (messages or [])
        if isinstance(item, dict) and item.get('role') != 'system'
    ])
    return [*system, *dialog]


def _context_overlay(ctx):
    snapshot = json.dumps(context_snapshot(ctx), ensure_ascii=False)
    return f"Contexte établissement (JSON) : {snapshot}"


def _dialog_to_gemini_contents(ctx, messages, tool_memory=''):
    from google.genai import types

    dialog = sanitize_dialog_messages([
        item for item in (messages or [])
        if isinstance(item, dict) and item.get('role') != 'system'
    ])
    overlay = _context_overlay(ctx)
    memory = (tool_memory or '').strip()
    if memory:
        overlay = f"{overlay}\nDernier outil (ne pas relire à l'oral) : {memory}"
    last_user = -1
    for index, item in enumerate(dialog):
        if item.get('role') == 'user':
            last_user = index
    contents = []
    for index, item in enumerate(dialog):
        text = item.get('content') or ''
        if index == last_user and overlay:
            text = f"{overlay}\n\n{text}"
        role = 'user' if item.get('role') == 'user' else 'model'
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=text)],
            )
        )
    if not contents and overlay:
        contents.append(
            types.Content(
                role='user',
                parts=[types.Part.from_text(text=overlay)],
            )
        )
    return contents


def _gemini_text(response):
    text = getattr(response, 'text', None)
    if text:
        return text
    candidates = getattr(response, 'candidates', None) or []
    chunks = []
    for candidate in candidates:
        content = getattr(candidate, 'content', None)
        for part in getattr(content, 'parts', None) or []:
            piece = getattr(part, 'text', None)
            if piece:
                chunks.append(piece)
    return ''.join(chunks)


def _gemini_function_calls(response):
    calls = list(getattr(response, 'function_calls', None) or [])
    if calls:
        return calls
    candidates = getattr(response, 'candidates', None) or []
    for candidate in candidates:
        content = getattr(candidate, 'content', None)
        for part in getattr(content, 'parts', None) or []:
            call = getattr(part, 'function_call', None)
            if call and getattr(call, 'name', None):
                calls.append(call)
    return calls


def _usage_cache_tokens(response):
    usage = getattr(response, 'usage_metadata', None)
    if not usage:
        return None
    return (
        getattr(usage, 'cached_content_token_count', None)
        or getattr(usage, 'cached_tokens', None)
    )


def sanitize_dialog_messages(messages):
    """
    Nettoie l'historique pour l'API : supprime les messages user consécutifs
    (retry UI) en ne gardant que le dernier.
    """
    cleaned = []
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        role = item.get('role')
        content = (item.get('content') or '').strip()
        if role not in ('user', 'assistant') or not content:
            continue
        if role == 'assistant':
            from school_admin.services.tts_service import strip_assistant_markup
            content = strip_assistant_markup(content)
            if not content:
                continue
        if role == 'user' and cleaned and cleaned[-1].get('role') == 'user':
            cleaned[-1] = {'role': 'user', 'content': content}
            continue
        if role == 'assistant' and cleaned and cleaned[-1].get('role') == 'assistant':
            cleaned[-1] = {'role': 'assistant', 'content': content}
            continue
        cleaned.append({'role': role, 'content': content})
    return cleaned


def _get_client():
    from openai import AsyncOpenAI

    provider = _llm_provider()
    if provider == 'deepseek':
        api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or ''
        if not api_key:
            raise RuntimeError('Clé API DeepSeek manquante. Configurez DEEPSEEK_API_KEY.')
        return AsyncOpenAI(
            api_key=api_key,
            base_url=getattr(settings, 'DEEPSEEK_API_BASE_URL', 'https://api.deepseek.com'),
            timeout=LLM_TIMEOUT,
        )

    api_key = getattr(settings, 'GEMINI_API_KEY', '') or ''
    if not api_key:
        raise RuntimeError('Clé API Gemini manquante. Configurez GEMINI_API_KEY.')
    base_url = getattr(
        settings,
        'GEMINI_API_BASE_URL',
        'https://generativelanguage.googleapis.com/v1beta/openai/',
    )
    return AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=LLM_TIMEOUT)


def _model_name():
    if _llm_provider() == 'deepseek':
        return getattr(settings, 'DEEPSEEK_MODEL', 'deepseek-flash') or 'deepseek-flash'
    if _resolved_gemini_model:
        return _resolved_gemini_model
    return getattr(settings, 'GEMINI_MODEL', 'gemini-3.6-flash') or 'gemini-3.6-flash'


def _gemini_model_candidates():
    primary = getattr(settings, 'GEMINI_MODEL', 'gemini-3.6-flash') or 'gemini-3.6-flash'
    ordered = []
    for name in (primary, *GEMINI_MODEL_FALLBACKS):
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def _is_model_unavailable_error(exc):
    name = type(exc).__name__
    if name in ('NotFoundError', 'BadRequestError'):
        return True
    text = str(exc).lower()
    return '404' in text or 'no longer available' in text or 'not found' in text


async def _create_chat_completion(client, **kwargs):
    """Appel chat/completions avec repli si le modèle Gemini configuré est refusé."""
    global _resolved_gemini_model

    if _llm_provider() == 'deepseek':
        kwargs['model'] = _model_name()
        return await client.chat.completions.create(**kwargs)

    if _resolved_gemini_model:
        kwargs['model'] = _resolved_gemini_model
        return await client.chat.completions.create(**kwargs)

    last_exc = None
    configured = getattr(settings, 'GEMINI_MODEL', '') or ''
    for model in _gemini_model_candidates():
        try:
            kwargs['model'] = model
            response = await client.chat.completions.create(**kwargs)
            _resolved_gemini_model = model
            if configured and model != configured:
                logger.warning(
                    'Modèle Gemini %s indisponible pour cette clé ; utilisation de %s.',
                    configured,
                    model,
                )
            return response
        except Exception as exc:
            if _is_model_unavailable_error(exc):
                last_exc = exc
                continue
            raise
    if last_exc:
        raise RuntimeError(
            'Aucun modèle Gemini Flash disponible pour cette clé API. '
            'Mettez à jour GEMINI_MODEL (ex. gemini-3.6-flash).'
        ) from last_exc
    raise RuntimeError('Impossible de contacter Gemini.')


async def _create_chat_completion_stream(client, **kwargs):
    global _resolved_gemini_model

    if _llm_provider() == 'deepseek':
        kwargs['model'] = _model_name()
        return await client.chat.completions.create(**kwargs)

    if _resolved_gemini_model:
        kwargs['model'] = _resolved_gemini_model
        return await client.chat.completions.create(**kwargs)

    last_exc = None
    configured = getattr(settings, 'GEMINI_MODEL', '') or ''
    for model in _gemini_model_candidates():
        try:
            kwargs['model'] = model
            stream = await client.chat.completions.create(**kwargs)
            _resolved_gemini_model = model
            if configured and model != configured:
                logger.warning(
                    'Modèle Gemini %s indisponible pour cette clé ; utilisation de %s.',
                    configured,
                    model,
                )
            return stream
        except Exception as exc:
            if _is_model_unavailable_error(exc):
                last_exc = exc
                continue
            raise
    if last_exc:
        raise RuntimeError(
            'Aucun modèle Gemini Flash disponible pour cette clé API. '
            'Mettez à jour GEMINI_MODEL (ex. gemini-3.6-flash).'
        ) from last_exc
    raise RuntimeError('Impossible de contacter Gemini.')


def _extract_reasoning_content(message):
    """DeepSeek (mode thinking) exige le renvoi du reasoning_content au tour suivant."""
    if _llm_provider() != 'deepseek':
        return None
    if message is None:
        return None
    if isinstance(message, dict):
        return message.get('reasoning_content') or None
    for attr in ('reasoning_content', 'reasoning'):
        value = getattr(message, attr, None)
        if value:
            return value
    model_extra = getattr(message, 'model_extra', None) or {}
    if isinstance(model_extra, dict):
        value = model_extra.get('reasoning_content')
        if value:
            return value
    return None


def _tool_calls_payload(tool_calls):
    return [
        {
            'id': call['id'],
            'type': 'function',
            'function': {
                'name': call['name'],
                'arguments': json.dumps(call['arguments'], ensure_ascii=False),
            },
        }
        for call in tool_calls
    ]


def _assistant_message_for_api(message, tool_calls=None):
    """
    Message assistant renvoyé au tour suivant.

    Gemini 3.x exige de conserver thought_signature dans tool_calls
    (extra_content.google) ; ne pas reconstruire les tool_calls à la main.
    """
    if _llm_provider() != 'deepseek' and hasattr(message, 'model_dump'):
        payload = message.model_dump(exclude_none=True)
        payload['role'] = 'assistant'
        if payload.get('content') is None:
            payload['content'] = ''
        return payload
    return _assistant_message_dict(message, tool_calls=tool_calls)


def _assistant_message_dict(message, content=None, tool_calls=None):
    """Construit le message assistant à renvoyer à l’API."""
    if content is None:
        content = getattr(message, 'content', None)
        if content is None and isinstance(message, dict):
            content = message.get('content')
    payload = {
        'role': 'assistant',
        'content': content or '',
    }
    reasoning = _extract_reasoning_content(message)
    if reasoning:
        payload['reasoning_content'] = reasoning
    if tool_calls:
        payload['tool_calls'] = _tool_calls_payload(tool_calls)
    return payload


def _extract_tool_calls(message):
    calls = getattr(message, 'tool_calls', None) or []
    parsed = []
    for call in calls:
        function = getattr(call, 'function', None)
        if not function:
            continue
        raw_args = function.arguments or '{}'
        try:
            arguments = json.loads(raw_args)
        except json.JSONDecodeError:
            arguments = {}
        parsed.append({
            'id': call.id,
            'name': function.name,
            'arguments': arguments if isinstance(arguments, dict) else {},
        })
    if parsed:
        return parsed
    return extract_markup_tool_calls(getattr(message, 'content', None) or '')


async def _stream_spoken_answer(client, messages, on_text_delta):
    stream = await _create_chat_completion_stream(
        client,
        messages=messages,
        stream=True,
    )
    full_text = []
    async for event in stream:
        if not event.choices:
            continue
        delta = event.choices[0].delta
        piece = getattr(delta, 'content', None) or ''
        if not piece:
            continue
        full_text.append(piece)
        if looks_like_tool_markup(''.join(full_text)):
            continue
        await on_text_delta(piece)
    return ''.join(full_text)


def _cached_generate_config(cache_name, temperature):
    from google.genai import types

    return types.GenerateContentConfig(
        cached_content=cache_name,
        temperature=temperature,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=True,
        ),
    )


async def _stream_cached_round(
    client,
    cache_model,
    cache_name,
    contents,
    temperature,
    on_text_delta,
):
    """Un tour cache : stream le texte, ou collecte les function_calls."""
    from google.genai import types

    config = _cached_generate_config(cache_name, temperature)
    function_calls = []
    spoken_parts = []
    model_parts = []
    last_chunk = None
    try:
        stream = await client.aio.models.generate_content_stream(
            model=cache_model,
            contents=contents,
            config=config,
        )
        async for chunk in stream:
            last_chunk = chunk
            chunk_parts = _iter_model_parts(chunk)
            if chunk_parts:
                model_parts.extend(chunk_parts)
            calls = _gemini_function_calls(chunk)
            if calls:
                function_calls.extend(calls)
                continue
            if function_calls:
                continue
            piece = _gemini_text(chunk)
            if piece:
                spoken_parts.append(piece)
                if on_text_delta:
                    await on_text_delta(piece)
    except Exception as exc:
        logger.warning('Stream cache Gemini échoué, repli generate_content : %s', exc)
        response = await client.aio.models.generate_content(
            model=cache_model,
            contents=contents,
            config=config,
        )
        parts = _iter_model_parts(response)
        function_calls = _gemini_function_calls(response) or [
            getattr(part, 'function_call', None)
            for part in parts
            if getattr(part, 'function_call', None)
            and getattr(part.function_call, 'name', None)
        ]
        spoken = strip_tool_markup(_gemini_text(response) or '')
        if not function_calls and spoken and on_text_delta:
            await on_text_delta(spoken)
        return response, function_calls, spoken, parts

    if function_calls and not _first_function_call_is_signed(model_parts):
        try:
            response = await client.aio.models.generate_content(
                model=cache_model,
                contents=contents,
                config=config,
            )
            parts = _iter_model_parts(response)
            calls = _gemini_function_calls(response) or [
                getattr(part, 'function_call', None)
                for part in parts
                if getattr(part, 'function_call', None)
                and getattr(part.function_call, 'name', None)
            ]
            if calls:
                logger.info('Gemini tool-call relus avec thought_signature.')
                return response, calls, '', parts
        except Exception as exc:
            logger.warning('Relecture tool-call Gemini échouée : %s', exc)

    spoken = '' if function_calls else strip_tool_markup(''.join(spoken_parts))
    return last_chunk, function_calls, spoken, model_parts


async def _run_assistant_turn_cached(
    ctx,
    messages,
    on_status=None,
    on_text_delta=None,
    on_tool_result=None,
    tool_memory='',
    turn_stats=None,
    working_refs=None,
):
    from google import genai
    from google.genai import types

    model = _model_name()
    persona = getattr(ctx, 'persona', 'directeur')
    prompt_static = system_prompt_static_for(ctx)
    from school_admin.services.assistant_schema import schema_profile

    cached = ensure_tools_cache(
        prompt_static,
        model,
        tools_schema=tools_schema_for(ctx),
        persona=persona,
        profile=(
            schema_profile(ctx)
            if persona in ('directeur', 'parent')
            else ('superieur' if getattr(ctx, 'est_superieur', False) else 'secondaire')
            if persona == 'enseignant'
            else None
        ),
    )
    if not cached:
        return None
    cache_name, cache_model, _token_count = cached
    api_key = getattr(settings, 'GEMINI_API_KEY', '') or ''
    client = genai.Client(api_key=api_key)
    contents = _dialog_to_gemini_contents(ctx, messages, tool_memory=tool_memory)
    used_tools = False
    spoken = ''
    response = None
    temperature = TOOL_TEMPERATURE
    last_tool = None
    all_tools = []
    refs = dict(working_refs or {})
    last_user = ''
    for item in reversed(messages or []):
        if isinstance(item, dict) and item.get('role') == 'user':
            last_user = item.get('content') or ''
            break
    rounds_used = 0

    async def _fallback_after_tools():
        enriched = enrich_class_snapshot(ctx, all_tools, refs, last_user)
        if on_tool_result and len(enriched) > len(all_tools):
            for name, result in enriched[len(all_tools):]:
                await on_tool_result(name, {'classe': refs.get('classe')}, result)
        return spoken_from_tool_results(enriched, ctx=ctx) or spoken_from_tool_result(
            *(last_tool or ('', {})), ctx=ctx
        )

    for _round in range(MAX_TOOL_ROUNDS):
        rounds_used = _round + 1
        if on_status:
            await on_status('searching' if used_tools or _round == 0 else 'speaking')
        try:
            packed = await _stream_cached_round(
                client,
                cache_model,
                cache_name,
                contents,
                temperature,
                on_text_delta,
            )
            response, function_calls, spoken, model_parts = _unpack_cached_round(packed)
        except Exception as exc:
            name = type(exc).__name__
            if 'Timeout' in name or 'timeout' in str(exc).lower():
                raise RuntimeError(
                    'Le service de réponse met trop longtemps. Réessayez dans un instant.'
                ) from exc
            if last_tool:
                logger.warning(
                    'Tour Gemini après outil échoué, repli oral : %s', exc
                )
                _note_turn_stats(turn_stats, rounds=rounds_used)
                fallback = await _emit_spoken_fallback(
                    on_text_delta,
                    await _fallback_after_tools(),
                )
                return messages, fallback
            logger.warning('Tour Gemini avec cache échoué, repli sans cache : %s', exc)
            return None

        cached_tokens = _usage_cache_tokens(response)
        if cached_tokens:
            logger.info('Gemini cache hit : %s tokens lus depuis le cache.', cached_tokens)

        if not function_calls:
            logger.info(
                'Gemini tool rounds: %s/%s',
                rounds_used,
                MAX_TOOL_ROUNDS,
            )
            _note_turn_stats(turn_stats, rounds=rounds_used)
            return messages, spoken

        call_names = ', '.join(
            (getattr(call, 'name', '') or '') for call in function_calls
        )
        logger.info(
            'Gemini tool round %s/%s : %s',
            rounds_used,
            MAX_TOOL_ROUNDS,
            call_names,
        )
        _note_turn_stats(
            turn_stats,
            rounds=rounds_used,
            tools=[
                getattr(call, 'name', '') or ''
                for call in function_calls
            ],
        )
        used_tools = True
        replay_parts = _model_parts_for_replay(model_parts, function_calls)
        response_parts = []
        stop_after_tools = False
        try:
            for call in function_calls:
                name = getattr(call, 'name', '') or ''
                raw_args = getattr(call, 'args', None) or {}
                arguments = raw_args if isinstance(raw_args, dict) else {}
                if not isinstance(arguments, dict):
                    arguments = dict(arguments) if arguments else {}
                arguments = apply_working_refs(name, arguments, refs)
                result = await sync_to_async(execute_tool, thread_sensitive=True)(
                    ctx, name, arguments
                )
                last_tool = (name, result)
                all_tools.append((name, result))
                if isinstance(result, dict):
                    refs.update(extract_working_refs(name, result))
                if on_tool_result:
                    should_stop = await on_tool_result(name, arguments, result)
                    if should_stop:
                        stop_after_tools = True
                response_parts.append(
                    types.Part.from_function_response(
                        name=name,
                        response=json_safe_tool_result(result),
                    )
                )
            contents.append(types.Content(role='model', parts=replay_parts))
            contents.append(types.Content(role='user', parts=response_parts))
        except Exception:
            logger.exception("Suite Gemini après outil — repli sur le résultat d’outil")
            fallback = await _emit_spoken_fallback(
                on_text_delta,
                await _fallback_after_tools(),
            )
            _note_turn_stats(turn_stats, rounds=rounds_used)
            return messages, fallback
        if stop_after_tools:
            logger.info(
                'Gemini tool rounds: %s/%s (stop demandé)',
                rounds_used,
                MAX_TOOL_ROUNDS,
            )
            _note_turn_stats(turn_stats, rounds=rounds_used)
            fallback = await _emit_spoken_fallback(
                on_text_delta,
                await _fallback_after_tools() or spoken,
            )
            return messages, fallback

    logger.info(
        'Gemini tool rounds: %s/%s (plafond)',
        MAX_TOOL_ROUNDS,
        MAX_TOOL_ROUNDS,
    )
    _note_turn_stats(turn_stats, rounds=MAX_TOOL_ROUNDS)
    if on_status:
        await on_status('speaking')
    return messages, spoken


async def run_assistant_turn(
    ctx,
    messages,
    on_status=None,
    on_text_delta=None,
    on_tool_result=None,
    use_tools=True,
    tool_memory='',
    turn_stats=None,
    working_refs=None,
):
    """
    Exécute un tour : outils en auto si besoin, puis stream du texte oral.

    Retourne (messages_enrichis, texte_final).
    """
    if use_tools and _llm_provider() != 'deepseek' and cache_enabled():
        cached_result = await _run_assistant_turn_cached(
            ctx,
            messages,
            on_status=on_status,
            on_text_delta=on_text_delta,
            on_tool_result=on_tool_result,
            tool_memory=tool_memory,
            turn_stats=turn_stats,
            working_refs=working_refs,
        )
        if cached_result is not None:
            return cached_result

    client = _get_client()
    working = _messages_for_api(messages)
    used_tools = False
    extra = {
        'temperature': TOOL_TEMPERATURE if use_tools else CONVERSATION_TEMPERATURE,
    }
    schema = tools_schema_for(ctx) if use_tools else None
    if use_tools:
        extra['tools'] = schema
        extra['tool_choice'] = 'auto'

    rounds_used = 0
    for _round in range(MAX_TOOL_ROUNDS):
        rounds_used = _round + 1
        if on_status:
            await on_status('searching' if used_tools or _round == 0 else 'speaking')
        try:
            response = await _create_chat_completion(
                client,
                messages=working,
                **extra,
            )
        except Exception as exc:
            name = type(exc).__name__
            if 'Timeout' in name or 'timeout' in str(exc).lower():
                raise RuntimeError(
                    'Le service de réponse met trop longtemps. Réessayez dans un instant.'
                ) from exc
            if isinstance(exc, RuntimeError):
                raise
            raise
        message = response.choices[0].message
        tool_calls = _extract_tool_calls(message)
        if not tool_calls:
            logger.info(
                'Gemini tool rounds: %s/%s',
                rounds_used,
                MAX_TOOL_ROUNDS,
            )
            _note_turn_stats(turn_stats, rounds=rounds_used)
            spoken = strip_tool_markup(message.content or '')
            if used_tools:
                if spoken:
                    if on_text_delta:
                        await on_text_delta(spoken)
                    working.append({'role': 'assistant', 'content': spoken})
                    return working, spoken
                break
            if spoken:
                if on_text_delta:
                    await on_text_delta(spoken)
                working.append({'role': 'assistant', 'content': spoken})
                return working, spoken
            break

        call_names = ', '.join(call.get('name') or '' for call in tool_calls)
        logger.info(
            'Gemini tool round %s/%s : %s',
            rounds_used,
            MAX_TOOL_ROUNDS,
            call_names,
        )
        _note_turn_stats(
            turn_stats,
            rounds=rounds_used,
            tools=[call.get('name') or '' for call in tool_calls],
        )
        used_tools = True
        working.append(_assistant_message_for_api(message, tool_calls=tool_calls))
        last_compat = None
        for call in tool_calls:
            arguments = apply_working_refs(
                call['name'], call['arguments'], working_refs
            )
            result = await sync_to_async(execute_tool, thread_sensitive=True)(
                ctx, call['name'], arguments
            )
            last_compat = (call['name'], result)
            if on_tool_result:
                should_stop = await on_tool_result(call['name'], call['arguments'], result)
                if should_stop:
                    logger.info(
                        'Gemini tool rounds: %s/%s (stop demandé)',
                        rounds_used,
                        MAX_TOOL_ROUNDS,
                    )
                    _note_turn_stats(turn_stats, rounds=rounds_used)
                    fallback = await _emit_spoken_fallback(
                        on_text_delta,
                        spoken_from_tool_result(*last_compat, ctx=ctx),
                    )
                    return working, fallback
            working.append({
                'role': 'tool',
                'tool_call_id': call['id'],
                'content': dumps_tool_result(result),
            })

    logger.info(
        'Gemini tool rounds: %s/%s (plafond)',
        MAX_TOOL_ROUNDS,
        MAX_TOOL_ROUNDS,
    )
    _note_turn_stats(turn_stats, rounds=MAX_TOOL_ROUNDS)
    if on_status:
        await on_status('speaking')
    spoken = strip_tool_markup(
        await _stream_spoken_answer(client, working, on_text_delta or _noop_delta)
    )
    if spoken:
        working.append({'role': 'assistant', 'content': spoken})
    return working, spoken


async def generate_written_draft(ctx, instruction, current=None):
    """
    Rédige un titre + contenu à partir du sujet / des consignes.
    Le contenu est limité à 8000 caractères.
    """
    snapshot = json.dumps(context_snapshot(ctx), ensure_ascii=False)
    current = current or {}
    prompt = (
        "Rédige un texte pour l'établissement à partir de la demande.\n"
        f"Demande : {instruction}\n"
        f"Titre actuel : {current.get('titre') or '(aucun)'}\n"
        f"Contenu actuel : {current.get('contenu') or '(aucun)'}\n"
        f"Contexte : {snapshot}\n\n"
        "Réponds uniquement en JSON : "
        '{"titre":"...","contenu":"..."}\n'
        f"Le contenu respecte le format demandé (paragraphes, longueur) "
        f"et ne dépasse jamais {WRITTEN_DRAFT_MAX} caractères. "
        "N'invente pas de faits scolaires absents du contexte."
    )
    client = _get_client()
    response = await _create_chat_completion(
        client,
        messages=[
            {
                'role': 'system',
                'content': (
                    "Tu rédiges des textes de communication scolaire. "
                    "Réponse JSON uniquement, sans markdown."
                ),
            },
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.6,
    )
    raw = (response.choices[0].message.content or '').strip()
    parsed = {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = WRITE_JSON_RE.search(raw)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                parsed = {}
    titre = str(parsed.get('titre') or '').strip()[:255]
    contenu = str(parsed.get('contenu') or '').strip()[:WRITTEN_DRAFT_MAX]
    if not contenu and raw and not raw.startswith('{'):
        contenu = raw[:WRITTEN_DRAFT_MAX]
    if not titre and contenu:
        titre = contenu.split('\n', 1)[0][:70].strip()
    return {'titre': titre, 'contenu': contenu}


async def classify_pending_intent(pending, question):
    """
    Le modèle décide si le message continue l'action en cours ou change de sujet.
    Retourne 'continue' ou 'switch'.
    """
    name = (pending or {}).get('name') or 'action'
    draft = (pending or {}).get('draft') or {}
    choices = (pending or {}).get('choices') or []
    labels = ', '.join(
        (item.get('label') or '')
        for item in choices[:5]
        if isinstance(item, dict) and item.get('label')
    )
    context = (
        f"Action en cours : {name}. "
        f"Titre brouillon : {draft.get('titre') or '-'}. "
        f"Choix proposés : {labels or '-'}."
    )
    client = _get_client()
    response = await _create_chat_completion(
        client,
        messages=[
            {
                'role': 'system',
                'content': (
                    "Tu classifies le dernier message. "
                    "Réponds uniquement en JSON : "
                    '{"intent":"continue"} ou {"intent":"switch"}. '
                    "continue = il répond clairement à l'action en cours "
                    "(oui, non, modifier le titre/texte/destinataires, un nom, "
                    "un brouillon, un choix proposé). "
                    "switch = nouvelle question, nouvelle action, ou hors sujet. "
                    "En cas de doute, choisis switch."
                ),
            },
            {
                'role': 'user',
                'content': f"{context}\nMessage : {question}",
            },
        ],
        temperature=0,
        max_tokens=40,
    )
    raw = (response.choices[0].message.content or '').strip().lower()
    if 'switch' in raw:
        return 'switch'
    if 'continue' in raw:
        return 'continue'
    return 'switch'


OPENING_MAX_WORDS = 20


def _clean_opening_line(raw):
    text = strip_tool_markup(raw or '').strip().strip(' "\'«»“”')
    text = re.sub(r'\s+', ' ', text)
    if not text:
        return ''
    match = re.search(r'(.+?[.!?…])(?:\s|$)', text)
    text = match.group(1).strip() if match else text.rstrip(',;:') + '.'
    words = text.split()
    if len(words) > OPENING_MAX_WORDS:
        text = ' '.join(words[:OPENING_MAX_WORDS]).rstrip(',;:') + '.'
    if text[-1] not in '.!?…':
        text += '.'
    return text


async def generate_opening_line(question, pending=None):
    """
    Phrase complète, naturelle, qui amorce la discussion
    en lien avec le message — sans donner le résultat.
    """
    pending = pending if isinstance(pending, dict) else {}
    extra = ''
    name = pending.get('name') or ''
    draft = pending.get('draft') or {}
    if name:
        extra = f" Une action est déjà en cours ({name})."
        if draft.get('titre'):
            extra += f" Titre du brouillon : {draft.get('titre')}."
    client = _get_client()
    response = await _create_chat_completion(
        client,
        messages=[
            {
                'role': 'system',
                'content': (
                    "Tu es Aria, assistante de direction. "
                    "On vient de te parler. Réponds par UNE seule phrase complète, "
                    "comme quelqu'un qui amorce naturellement la discussion "
                    "avant d'aller chercher l'information ou de faire l'action. "
                    "La phrase doit être liée au message, fluide, orale, en français. "
                    "Maximum 15 mots. Une virgule si la phrase respire. "
                    "Ne donne aucun chiffre, aucun résultat, aucune liste. "
                    "Ne pose pas de question. Ne dis pas que tu n'as pas l'info. "
                    "Évite les amorces vides du type « Bien sûr. » ou « D'accord. » "
                    "Pas de markdown, pas de parenthèses."
                ),
            },
            {
                'role': 'user',
                'content': f"Message : {question}{extra}",
            },
        ],
        temperature=0.85,
        max_tokens=50,
    )
    return _clean_opening_line(response.choices[0].message.content or '')


async def _noop_delta(_piece):
    return None
