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
    execute_tool,
)
from school_admin.services.gemini_context_cache import (
    cache_enabled,
    ensure_tools_cache,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3
LLM_TIMEOUT = 60.0
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
Tu aides pour l'administratif scolaire, et tu converses aussi de manière naturelle.

Réponds directement, comme dans une vraie discussion.
N'utilise jamais de formules toutes faites : « Je cherche ça », « Voici la réponse »,
« Je vais voir », « Un instant ».
Sois chaleureuse, claire, conversationnelle.
Si l'utilisateur change de sujet, suis-le tout de suite.
S'il discute (bonjour, comment ça va, merci), réponds comme un humain,
sans appeler d'outil.

Voix :
- Tes réponses seront lues à voix haute par la synthèse Gemini, en français naturel.
- Phrases fluides, comme à l'oral. N'ajoute pas de virgules artificielles.
- Cite les noms d'élèves, de professeurs et de lieux avec leur casse naturelle
  (Clé Jason, pas CLÉ JASON). Ne les mets jamais en capitales intégrales.
- Jamais de markdown : pas d'astérisques, pas de gras, pas de tableaux,
  pas de barres verticales, pas de tirets d'alignement, pas de crochets
  ni de listes à puces. Raconte tout en phrases orales, par exemple :
  « Vous avez 50 élèves, 25 filles et 25 garçons, répartis dans 5 classes. »
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
- Un contenu destiné à un champ ou une publication ne dépasse jamais 8000 caractères.
- Si la longueur demandée dépasse 8000 caractères, reste dans cette limite.

Actions :
- Avant de publier, créer, enregistrer ou appliquer un texte, présente le résultat
  et demande si c'est bon ou s'il faut modifier.
- Dès qu'une action est terminée, analyse le résultat de l'outil : réussite, échec
  ou annulation. Ne laisse jamais une action se conclure en silence.
- Confirme toujours clairement ce qui s'est passé (quoi, pour qui, si c'est ouvert
  ou publié). Une carte de confirmation visible est aussi affichée à l'utilisateur
  (verte si succès, rouge si échec, ambre si annulé).
- Ne dis jamais d'ouvrir un formulaire pour terminer une action : tout se fait
  à la voix. S'il manque un champ, pose UNE question, attends la réponse,
  puis rappelle le même outil avec tout ce que tu as déjà.

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
  En supérieur, creer_periode exige niveau_lmd (L1, M1…) et un semestre officiel.
- Absences : justifier_absence.
- Liaisons : approuver_liaison, rejeter_liaison, desapprouver_liaison.
- Préinscriptions : valider_preinscription, rejeter_preinscription,
  toggle_lien_preinscription.
- Bulletins : publier_bulletins, calculer_moyennes_classe, get_bulletin_eleve,
  imprimer_bulletins_classe, calculer_moyenne_annuelle.
- Pédagogie : get_notes_classe, get_moyennes_classe, get_eleves_difficulte,
  get_justifications_notes, traiter_justification, get_coefficients,
  configurer_coefficient, get_evaluations.
- Scolarité : enregistrer_paiement, get_fiche_scolarite, get_bilan_scolarite,
  get_impayes, ouvrir_recu, get_moratoires, verifier_statuts_paiement,
  synchroniser_remises_fratrie.
- Pilotage : get_statistiques_pilotage, get_taux_reussite, get_taux_presence,
  get_comparatif_periodes, get_repartition_cycles (collège+lycée / mixte).
- Paramètres de comptabilité : get_parametres_comptabilite pour lire,
  creer_parametres_comptabilite pour créer (nom, groupes comme 2nde / 1ère /
  Terminale, montants), modifier_parametres_comptabilite,
  supprimer_parametres_comptabilite. Ne te contente pas d’ouvrir la page.
- Examens : get_examens, creer_session_examen, supprimer_session_examen.
  Hors primaire : get_emploi_examens, get_notes_examen,
  modifier_session_examen, ajouter_creneau_examen, supprimer_creneau_examen.
- Structure : creer_classe, modifier_classe, desactiver_classe, supprimer_classe,
  creer_salle, modifier_salle, desactiver_salle, creer_matiere, desactiver_matiere,
  creer_filiere, modifier_filiere, supprimer_filiere, creer_module, supprimer_module.
  En supérieur : get_ects_etudiant, get_ects_classe, get_modules_classe,
  affecter_module_classe, fixer_credits_module, get_releve_ects,
  get_structure_superieur (crédits, UE, semestre). N’invente pas d’ECTS.
- Élèves : inscrire_eleve, modifier_eleve, reinscrire_eleve, activer_eleve,
  desactiver_eleve, donner_sanction. Pour une sanction, appelle donner_sanction
  avec le ou les noms (sépare-les par « et »). Ne cite jamais la liste des types
  ni des raisons à l’oral : le chat affiche une liste déroulante. Demande seulement
  le type, puis la raison, puis la gravité. Ensuite rédige la note toi-même et
  enregistre. Plusieurs élèves peuvent recevoir la même sanction en un seul appel.
- Sanctions (lecture) : get_sanctions ou chercher_en_base pour compter les élèves
  sanctionnés, lister les sanctions de la session, ou le dossier d'un élève nommé.
  Pour « combien d'élèves ont des sanctions », interroge toujours la base avant
  de répondre ; ne dis jamais qu'il n'y a pas de liste globale sans avoir appelé l'outil.
- Professeurs : creer_professeur, modifier_professeur, desactiver_professeur,
  enregistrer_absence_professeur.
- Affectations : get_affectations pour lister ou vérifier (année active).
  Pour affecter ou retirer : affecter_professeur avec le professeur, la classe,
  la matière hors primaire, et action add ou remove. N'utilise jamais
  affecter_professeur pour une simple liste.
- Personnel : creer_personnel, modifier_personnel, desactiver_personnel.
- Caisse : get_caisse pour lire, ajouter_depense, supprimer_depense.
- RH : get_dossier_employe, modifier_dossier_employe, get_absences_professeur,
  supprimer_absence_professeur, ouvrir_fiche_paie (vacataire déjà payé).
  Pas de bulletin de paie permanent.
- Paie vacataire : get_volume_horaire (semaine / mois / année), marquer_paie.
- Moratoires : creer_moratoire, payer_echeance_moratoire, relancer_impaye.
- Moyennes : configurer_moyennes (classique 50/50, exigeante 40/60, continu 60/40,
  spéciale 30/70), configurer_standards (moyenne de passage),
  configurer_visibilite_bulletins.
- Documents : generer_document (type + élève).

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
- Le dernier message de l'utilisateur a toujours priorité, même s'il coupe
  une réponse ou change de sujet.
- Si le dernier message n'est pas une réponse à la question que TU viens
  de poser, ignore l'historique métier et réponds à CE message.
- S'il change de sujet, pose une question sans rapport, ou envoie une nouvelle
  consigne, abandonne l'ancienne action et réponds uniquement à ce message.
- Ne ramène pas la conversation sur le sujet d'avant.
- Ne repose jamais la même question de clarification s'il a déjà répondu
  (titre, texte, destinataires, oui/non, un nom, un choix).
- Tu es autonome : déduis le contexte, rédige, propose. Pose UNE question
  seulement si une information indispensable manque vraiment.
"""

SYSTEM_PROMPT_ENSEIGNANT_PRIMAIRE = """Tu es Aria, l'assistante vocale des enseignants du primaire.
Tu aides pour les classes affectées, les notes, les présences, les exercices,
les élèves en difficulté et la navigation dans l'espace enseignant.

Réponds directement, chaleureusement, en français oral naturel.
Pas de markdown, pas d'URL, pas de listes à puces lues à voix haute.

Outils :
- Tu n'accèdes qu'aux classes et élèves du professeur connecté.
- Appelle un outil pour toute donnée ou action (notes, présences, pages).
- Les actions d'écriture exigent confirmation explicite après présentation du résumé.
- Navigation : ouvrir_page ou ouvrir_classe avec ouvrir true.

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
    if persona == 'enseignant_primaire':
        return SYSTEM_PROMPT_ENSEIGNANT_PRIMAIRE
    from school_admin.services.assistant_schema import prompt_addendum_for

    return SYSTEM_PROMPT_STATIC + prompt_addendum_for(ctx)


def tools_schema_for(ctx):
    persona = getattr(ctx, 'persona', 'directeur')
    if persona == 'enseignant_primaire':
        from school_admin.services.assistant_enseignant_primaire_tools import (
            get_enseignant_primaire_tools_schema,
        )

        return get_enseignant_primaire_tools_schema()
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
    'session',
    'classe',
    'nom',
    'source',
    'statut',
    'taux',
    'moyenne',
    'cnss',
    'periode',
)


def compact_tool_memory(name, result, max_len=280):
    """Résumé chiffré du dernier outil, pour le tour suivant seulement."""
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
    for key in _MEMORY_KEYS:
        value = bag.get(key)
        if value in (None, '', [], {}):
            continue
        if isinstance(value, (int, float, str, bool)):
            parts.append(f'{key}={value}')
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
    last_chunk = None
    try:
        stream = await client.aio.models.generate_content_stream(
            model=cache_model,
            contents=contents,
            config=config,
        )
        async for chunk in stream:
            last_chunk = chunk
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
        function_calls = _gemini_function_calls(response)
        spoken = strip_tool_markup(_gemini_text(response) or '')
        if not function_calls and spoken and on_text_delta:
            await on_text_delta(spoken)
        return response, function_calls, spoken

    spoken = '' if function_calls else strip_tool_markup(''.join(spoken_parts))
    return last_chunk, function_calls, spoken


async def _run_assistant_turn_cached(
    ctx,
    messages,
    on_status=None,
    on_text_delta=None,
    on_tool_result=None,
    tool_memory='',
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
        profile=schema_profile(ctx) if persona == 'directeur' else None,
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
    temperature = 0.5

    for _round in range(MAX_TOOL_ROUNDS):
        if on_status:
            await on_status('searching' if used_tools or _round == 0 else 'speaking')
        try:
            response, function_calls, spoken = await _stream_cached_round(
                client,
                cache_model,
                cache_name,
                contents,
                temperature,
                on_text_delta,
            )
        except Exception as exc:
            name = type(exc).__name__
            if 'Timeout' in name or 'timeout' in str(exc).lower():
                raise RuntimeError(
                    'Le service de réponse met trop longtemps. Réessayez dans un instant.'
                ) from exc
            logger.warning('Tour Gemini avec cache échoué, repli sans cache : %s', exc)
            return None

        cached_tokens = _usage_cache_tokens(response)
        if cached_tokens:
            logger.info('Gemini cache hit : %s tokens lus depuis le cache.', cached_tokens)

        if not function_calls:
            return messages, spoken

        used_tools = True
        model_parts = []
        response_parts = []
        for call in function_calls:
            name = getattr(call, 'name', '') or ''
            raw_args = getattr(call, 'args', None) or {}
            arguments = raw_args if isinstance(raw_args, dict) else {}
            model_parts.append(
                types.Part.from_function_call(name=name, args=arguments)
            )
            result = await sync_to_async(execute_tool, thread_sensitive=True)(
                ctx, name, arguments
            )
            if on_tool_result:
                await on_tool_result(name, arguments, result)
            response_parts.append(
                types.Part.from_function_response(name=name, response=result)
            )
        contents.append(types.Content(role='model', parts=model_parts))
        contents.append(types.Content(role='user', parts=response_parts))

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
        )
        if cached_result is not None:
            return cached_result

    client = _get_client()
    working = _messages_for_api(messages)
    used_tools = False
    extra = {'temperature': 0.5 if use_tools else 0.7}
    schema = tools_schema_for(ctx) if use_tools else None
    if use_tools:
        extra['tools'] = schema
        extra['tool_choice'] = 'auto'

    for _round in range(MAX_TOOL_ROUNDS):
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
        working.append(_assistant_message_for_api(message, tool_calls=tool_calls))
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
