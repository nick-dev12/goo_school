"""
Client DeepSeek Flash (API compatible OpenAI) pour l'assistant vocal.
"""
import json
import logging
import re
import uuid

from asgiref.sync import sync_to_async
from django.conf import settings

from school_admin.services.assistant_tools import (
    TOOLS_SCHEMA,
    context_snapshot,
    dumps_tool_result,
    execute_tool,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3
DEEPSEEK_TIMEOUT = 45.0
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
Tu aides pour l'administratif scolaire, et tu converses aussi de manière naturelle.

Réponds directement, comme dans une vraie discussion.
N'utilise jamais de formules toutes faites : « Je cherche ça », « Voici la réponse »,
« Je vais voir », « Un instant ».
Sois chaleureuse, claire, conversationnelle.
Si l'utilisateur change de sujet, suis-le tout de suite.
S'il discute (bonjour, comment ça va, merci), réponds comme un humain,
sans appeler d'outil.

Voix :
- Tes réponses seront lues à voix haute.
- Phrases naturelles, avec des virgules pour respirer.
- Jamais de markdown, d'astérisques, de parenthèses, de crochets
  ni de listes à puces.
- Pas d'URL, pas de DSML.
- Écris les nombres en chiffres (110, 2026). Conserve noms, classes, matricules.

Outils :
- Appelle un outil seulement s'il faut une donnée ou une action réelle.
- Le contexte ne contient pas les chiffres ni les listes : ils sont en base.
- Si une donnée manque, cherche-la en base avant de répondre.
- Interdit : dire « je n'ai pas cette information » sans avoir cherché.
- Utilise seulement l'API d'outils. N'écris jamais les appels d'outils en texte.
- Les suggestions cliquables sont affichées à part : ne les énumère pas à l'oral.
- Ne propose pas de créer ce que tes outils ne savent pas créer.

Rédaction :
- Si on demande d'écrire (annonce, message, 2 paragraphes, N mots, un titre…),
  rédige toi-même à partir du sujet et du contexte. On n'a pas besoin de tout dicter.
- Un contenu destiné à un champ ou une publication ne dépasse jamais 2000 caractères.
- Si la longueur demandée dépasse 2000 caractères, reste dans cette limite.

Actions :
- Avant de publier, créer, enregistrer ou appliquer un texte, présente le résultat
  et demande si c'est bon ou s'il faut modifier.
- Dès qu'une action est terminée, analyse le résultat de l'outil : réussite, échec
  ou annulation. Ne laisse jamais une action se conclure en silence.
- Confirme toujours clairement ce qui s'est passé (quoi, pour qui, si c'est ouvert
  ou publié). Une carte de confirmation visible est aussi affichée à l'utilisateur
  (verte si succès, rouge si échec, ambre si annulé).

Annonces :
- S'il veut créer ou publier une annonce, appelle creer_publier_annonce avec ce que tu as.
- Destinataires : tous, enseignants, parents, eleves, personnel_administratif.
- Pour une annonce existante : publier_annonce, modifier_annonce,
  archiver_annonce, supprimer_annonce.

Emplois du temps :
- Pour créer un emploi du temps, appelle creer_emploi_du_temps avec la classe.
- Pour ajouter un cours ou un créneau, appelle ajouter_creneau_emploi
  (classe, jour, heure_debut HH:MM, heure_fin HH:MM, et si possible
  matiere, professeur, salle, type_cours).
- Dans classe, envoie seulement le nom, le code ou la filière
  (ex. « génie logiciel », « GL L1 A »), jamais la phrase entière.
- Ne crée rien tout de suite : une confirmation du directeur est obligatoire.
- S'il n'y a pas encore d'emploi du temps, le créneau le créera.
- Publier : publier_emploi_du_temps. Supprimer un créneau : supprimer_creneau_emploi.

Autres actions (toujours avec confirmation) :
- Années : creer_annee_scolaire, activer_annee_scolaire, desactiver_annee_scolaire,
  changer_session.
- Périodes : creer_periode, activer_periode, supprimer_periode.
- Absences : justifier_absence.
- Liaisons : approuver_liaison, rejeter_liaison, desapprouver_liaison.
- Préinscriptions : valider_preinscription, rejeter_preinscription,
  toggle_lien_preinscription.
- Bulletins : publier_bulletins, calculer_moyennes_classe.
- Scolarité : enregistrer_paiement.
- Examens : creer_session_examen, supprimer_session_examen.
- Structure : creer_classe, desactiver_classe, supprimer_classe, creer_salle,
  desactiver_salle, creer_matiere, desactiver_matiere.
- Documents : generer_document (type + élève).
- Formulaire complexe (inscrire un élève, ajouter un professeur) :
  ouvrir_page vers le formulaire.

Recherche et fautes :
- Les noms peuvent être mal orthographiés ou incomplets.
- Si un outil renvoie trouve=false ou suggestions_possibles,
  ce n'est pas une erreur système. Pose une question naturelle,
  par exemple : « Vous voulez Licence 1 Génie Logiciel ou Licence 2 ? »
- Ne dis jamais « action échouée » ni « aucune classe trouvée ».

Navigation :
- Classe nommée (6e A, CF L1 A…) : ouvrir_classe, ouvrir true.
- Une page : ouvrir_page, ouvrir true.

Sujet :
- Le dernier message de l'utilisateur a toujours priorité.
- S'il change de sujet ou pose une question sans rapport avec l'échange
  précédent, abandonne l'ancienne action et réponds uniquement au nouveau message.
- Ne ramène pas la conversation sur le sujet d'avant.

Contexte établissement :
{context}
"""

WRITTEN_DRAFT_MAX = 2000
WRITE_JSON_RE = re.compile(r'\{.*\}', re.DOTALL)


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
    cleaned = text or ''
    cleaned = re.sub(r'<\|?\s*/?\s*DSML\s*\|?>', ' ', cleaned)
    cleaned = re.sub(r'<｜/?DSML｜>', ' ', cleaned)
    cleaned = re.sub(r'</?(?:tool_calls?|function_calls?)>', ' ', cleaned, flags=re.I)
    cleaned = re.sub(r'invoke\s+name=["\'][^"\']+["\']', ' ', cleaned, flags=re.I)
    cleaned = re.sub(r'parameter\s+name=["\'][^"\']+["\'][^>]*>[^<]*', ' ', cleaned, flags=re.I)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if looks_like_tool_markup(cleaned):
        return ''
    return cleaned


def build_system_message(ctx):
    snapshot = json.dumps(context_snapshot(ctx), ensure_ascii=False)
    return {
        'role': 'system',
        'content': SYSTEM_PROMPT.format(context=snapshot),
    }


def _get_client():
    from openai import AsyncOpenAI

    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or ''
    if not api_key:
        raise RuntimeError('Clé API DeepSeek manquante. Configurez DEEPSEEK_API_KEY.')
    return AsyncOpenAI(
        api_key=api_key,
        base_url=getattr(settings, 'DEEPSEEK_API_BASE_URL', 'https://api.deepseek.com'),
        timeout=DEEPSEEK_TIMEOUT,
    )


def _model_name():
    return getattr(settings, 'DEEPSEEK_MODEL', 'deepseek-flash') or 'deepseek-flash'


def _extract_reasoning_content(message):
    """DeepSeek (mode thinking) exige le renvoi du reasoning_content au tour suivant."""
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


def _assistant_message_dict(message, content=None, tool_calls=None):
    """Construit le message assistant à renvoyer à l’API (reasoning + tool_calls)."""
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
    stream = await client.chat.completions.create(
        model=_model_name(),
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


async def run_assistant_turn(
    ctx,
    messages,
    on_status=None,
    on_text_delta=None,
    on_tool_result=None,
    use_tools=True,
):
    """
    Exécute un tour : outils en auto si besoin, puis stream du texte oral.

    Retourne (messages_enrichis, texte_final).
    """
    client = _get_client()
    working = list(messages)
    used_tools = False
    extra = {}
    if use_tools:
        extra = {'tools': TOOLS_SCHEMA, 'tool_choice': 'auto'}

    for _round in range(MAX_TOOL_ROUNDS):
        if on_status:
            await on_status('searching' if used_tools or _round == 0 else 'speaking')
        response = await client.chat.completions.create(
            model=_model_name(),
            messages=working,
            **extra,
        )
        message = response.choices[0].message
        tool_calls = _extract_tool_calls(message)
        if not tool_calls:
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

        used_tools = True
        working.append(_assistant_message_dict(message, tool_calls=tool_calls))
        for call in tool_calls:
            result = await sync_to_async(execute_tool, thread_sensitive=True)(
                ctx, call['name'], call['arguments']
            )
            if on_tool_result:
                await on_tool_result(call['name'], call['arguments'], result)
            working.append({
                'role': 'tool',
                'tool_call_id': call['id'],
                'content': dumps_tool_result(result),
            })

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
    Le contenu est limité à 2000 caractères.
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
    response = await client.chat.completions.create(
        model=_model_name(),
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
    DeepSeek décide si le message continue l'action en cours ou change de sujet.
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
    response = await client.chat.completions.create(
        model=_model_name(),
        messages=[
            {
                'role': 'system',
                'content': (
                    "Tu classifies le dernier message. "
                    "Réponds uniquement en JSON : "
                    '{"intent":"continue"} ou {"intent":"switch"}. '
                    "continue = il répond à l'action en cours "
                    "(oui, modifier, destinataires, nom de classe, détail du brouillon). "
                    "switch = nouvelle question ou nouvelle action, sans rapport."
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
    response = await client.chat.completions.create(
        model=_model_name(),
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
