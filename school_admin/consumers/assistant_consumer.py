"""
WebSocket de l'assistant vocal directeur : Gemini LLM + TTS Gemini phrase par phrase.
"""
import asyncio
import base64
import json
import logging
import re

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from school_admin.services.assistant_emploi import (
    apply_creneau_draft,
    apply_emploi_du_temps_draft,
    choices_for_emploi,
)
from school_admin.services.assistant_actions import (
    ACTION_SPECS,
    GUIDED_ACTIONS,
    choices_for_action,
    default_prompt,
    is_action_ready,
)
from school_admin.services.assistant_enseignant_actions import (
    ENSEIGNANT_ACTION_SPECS,
    choices_for_enseignant_action,
    get_enseignant_action,
)
from school_admin.services.assistant_enseignant_secondaire_actions import (
    ENSEIGNANT_SECONDAIRE_ACTION_SPECS,
    choices_for_enseignant_secondaire_action,
    get_enseignant_secondaire_action,
)
from school_admin.services.assistant_intents import (
    is_navigation_only,
    resolve_open_intent,
)
from school_admin.services.assistant_search import (
    choices_from_class_lookup,
    is_lookup_clarification,
)
from school_admin.services.gemini_assistant_service import (
    build_system_message,
    compact_tool_memory,
    extract_working_refs,
    format_cited_refs,
    format_turn_telemetry,
    log_turn_telemetry,
    run_assistant_turn,
    sanitize_dialog_messages,
)
from school_admin.services.assistant_tools import (
    normalize_suggestions,
    spoken_from_tool_result,
    spoken_from_tool_results,
    suggestions_after_read,
)
from school_admin.services.tts_service import strip_assistant_markup, synthesize_audio

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 24
MAX_QUESTION_LENGTH = 8000
MAX_TTS_SEGMENT_CHARS = 150
MIN_TTS_CLAUSE_CHARS = 120
SENTENCE_RE = re.compile(r'(.+?(?:[.!?…]|\n)+)\s*', re.DOTALL)
CLAUSE_RE = re.compile(r'(.{120,}?[,;:])\s+')
AFFIRM_RE = re.compile(
    r'^\s*(oui|ouais|ok|okay|yes|d[\'’ ]?accord|je confirme|confirme[rz]?|'
    r'vas[- ]y|publie[rz]?|c[\'’ ]est bon|cest bon|parfait|go|valide[rz]?|'
    r'tu peux publier|c[\'’ ]est ok|nickel|volontiers|bien[ -]?s[uû]r|'
    r'allez[- ]y|daccords?|c[\'’ ]est parfait|c[\'’ ]est valid[ée])\b',
    re.IGNORECASE,
)
CANCEL_RE = re.compile(
    r'^\s*(non|annule[rz]?|stop|laisse tomber|pas maintenant|cancel|'
    r'oublie|n[\'’]y pense plus)([\s,!.].*)?$',
    re.IGNORECASE,
)
MODIFY_RE = re.compile(
    r'\b(modifi(?:er|e)[rz]?|change[rz]?|corrige[rz]?|ajuste[rz]?|'
    r'plut[oô]t|ajoute[rz]?|enl[eè]ve[rz]?|retire[rz]?|'
    r'pas\s+(?:ça|cela|bon)|plus (?:court|long))\b',
    re.IGNORECASE,
)
PENDING_MODIFY_RE = re.compile(
    r'(?:je\s+veux\s+|on\s+peut\s+|peux[- ]tu\s+)?'
    r'(?:modifi(?:er|e)[rz]?|corrige[rz]?|ajuste[rz]?)\b'
    r'|(?:change[rz]?)\s+(?:le|la|les|un|une|ce|cet|cette)\b',
    re.IGNORECASE,
)
_ALLOWED_WHEN_CANCELLED = frozenset({'done', 'error', 'pong'})


def is_affirmative(text):
    raw = (text or '').strip()
    if not raw:
        return False
    if MODIFY_RE.search(raw):
        return False
    return bool(AFFIRM_RE.match(raw))


def is_cancel(text):
    raw = (text or '').strip()
    if not raw:
        return False
    if is_affirmative(raw):
        return False
    return bool(CANCEL_RE.match(raw))


def wants_modify(text):
    return bool(MODIFY_RE.search(text or ''))


def is_pending_modify(text):
    """G2 : « modifier / change le… » garde la carte. Pas « ajoute » ni un nouveau sujet."""
    raw = (text or '').strip()
    if not raw or is_affirmative(raw) or is_cancel(raw):
        return False
    return bool(PENDING_MODIFY_RE.search(raw))


class SentenceAssembler:
    """Découpe un flux de tokens en segments TTS d’environ 120–150 caractères."""

    def __init__(self, max_chars=MAX_TTS_SEGMENT_CHARS, min_clause=MIN_TTS_CLAUSE_CHARS):
        self.buffer = ''
        self.max_chars = max_chars
        self.min_clause = min_clause

    def feed(self, delta):
        self.buffer += delta or ''
        sentences = []
        while True:
            match = SENTENCE_RE.match(self.buffer)
            if not match and len(self.buffer) >= self.min_clause:
                match = CLAUSE_RE.match(self.buffer)
            if match:
                sentence = match.group(1).strip()
                self.buffer = self.buffer[match.end():]
                if sentence:
                    sentences.extend(self._split_long(sentence))
                continue
            forced = self._force_cut()
            if not forced:
                break
            sentences.append(forced)
        return sentences

    def _force_cut(self):
        if len(self.buffer) < self.max_chars:
            return ''
        cut = self.buffer.rfind(' ', 0, self.max_chars)
        if cut < 40:
            cut = self.max_chars
        sentence = self.buffer[:cut].strip()
        self.buffer = self.buffer[cut:].lstrip()
        return sentence

    def _split_long(self, sentence):
        if len(sentence) <= self.max_chars:
            return [sentence]
        parts = []
        rest = sentence
        while len(rest) > self.max_chars:
            cut = rest.rfind(' ', 0, self.max_chars)
            if cut < 40:
                cut = self.max_chars
            parts.append(rest[:cut].strip())
            rest = rest[cut:].lstrip()
        if rest:
            parts.append(rest)
        return [part for part in parts if part]

    def flush(self):
        leftover = self.buffer.strip()
        self.buffer = ''
        return leftover


class AssistantConsumer(AsyncWebsocketConsumer):
    """Canal privé directeur / personnel / enseignant / parent."""

    async def connect(self):
        self.etablissement = None
        self.personnel = None
        self.professeur = None
        self.parent = None
        self.eleve = None
        self.persona = 'directeur'
        self.history = []
        self.pending_action = None
        self._busy = False
        self._turn_task = None
        self._tts_tasks = []
        self._cancel_requested = False
        self._cancel_notified = False
        self._opener_task = None
        self._opener_emit_task = None
        self._opener_emitted = False
        self._opener_lock = asyncio.Lock()
        self._tts_index = 0
        self._followup_choices = []
        self._followup_suggestions = []
        self._socket_fresh = True
        self._last_tool_memory = ''
        self._working_refs = {}
        self._turn_has_output = False
        self._parent_lang_pref = 'auto'
        self._parent_user_turn_lang = 'fr'
        self._turn_stats = {
            'tools': [],
            'rounds': 0,
            'pending_shown': 0,
            'suggestions_count': 0,
            'takeover': 0,
        }
        allowed = await self._resolve_etablissement()
        if not allowed:
            await self.close(code=4401)
            return
        await self.accept()
        await self._load_pending()
        await self._send_json({
            'type': 'connection.established',
            'etablissement': getattr(self.etablissement, 'nom', ''),
            'persona': getattr(self, 'persona', 'directeur'),
        })
        if getattr(self, 'persona', '') == 'parent':
            await self._send_parent_welcome()
        elif getattr(self, 'persona', '') == 'eleve':
            await self._send_eleve_welcome()
        await self._restore_pending_ui()

    async def disconnect(self, close_code):
        await self._stop_current(notify=False)
        await self._cancel_opener()
        self.history = []
        # Ne pas effacer aria_pending en session : une reconnexion WebSocket doit
        # pouvoir reprendre l’action en attente de confirmation.
        self.pending_action = None

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await self._send_json({'type': 'error', 'message': 'Message invalide.'})
            return

        kind = payload.get('type')
        if kind == 'ping':
            await self._send_json({'type': 'pong'})
            return
        if kind == 'stt':
            await self._handle_stt(payload)
            return
        if kind == 'set_lang_pref':
            await self._handle_set_lang_pref(payload)
            return
        if kind == 'restore_history':
            self._restore_history(payload.get('messages') or [])
            return
        if kind in ('stop', 'cancel_turn'):
            await self._stop_current(notify=True)
            return
        if kind == 'confirm_action':
            await self._launch_turn(lambda: self._confirm_from_ui(payload))
            return
        if kind == 'cancel_action':
            await self._launch_turn(self._cancel_from_ui)
            return
        if kind == 'choice':
            await self._launch_turn(lambda: self._handle_choice_payload(payload))
            return
        if kind != 'chat':
            await self._send_json({'type': 'error', 'message': 'Type de message inconnu.'})
            return

        question = (payload.get('text') or '').strip()
        if not question:
            await self._send_json({'type': 'error', 'message': 'Votre question est vide.'})
            return
        if len(question) > MAX_QUESTION_LENGTH:
            await self._send_json({
                'type': 'error',
                'message': f'Question trop longue (maximum {MAX_QUESTION_LENGTH} caractères).',
            })
            return

        lang_pref = payload.get('lang_pref')
        await self._launch_turn(lambda: self._execute_user_message(question, lang_pref))

    async def _confirm_from_ui(self, payload):
        await self._send_working_ack('Oui, publier.')
        await self._ensure_pending_loaded()
        if payload.get('publier') is True and self.pending_action:
            self.pending_action.setdefault('draft', {})['publier'] = True
        await self._confirm_pending()

    async def _cancel_from_ui(self):
        await self._send_working_ack('Annuler.')
        await self._ensure_pending_loaded()
        await self._cancel_pending()

    async def _execute_user_message(self, question, lang_pref=None):
        if self._is_parent():
            from school_admin.services.assistant_parent_language import (
                normalize_lang_preference,
                resolve_user_turn_language,
            )

            if lang_pref:
                await self._save_parent_lang_pref(lang_pref)
            self._parent_lang_pref = await self._load_parent_lang_pref()
            if lang_pref:
                self._parent_lang_pref = normalize_lang_preference(lang_pref)
            self._parent_user_turn_lang = resolve_user_turn_language(
                question,
                self._parent_lang_pref,
            )
        await self._send_working_ack(question)
        await self._ensure_pending_loaded()
        if self._socket_fresh:
            self._socket_fresh = False
            if self.pending_action and not (
                is_affirmative(question)
                or is_cancel(question)
                or is_pending_modify(question)
            ):
                await self._clear_pending(silent=True)
        if await self._route_pending_reply(question):
            return
        await self._handle_chat(question)

    async def _cancel_tts_tasks(self):
        tasks = [task for task in self._tts_tasks if task and not task.done()]
        self._tts_tasks = []
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _track_tts(self, task):
        self._tts_tasks.append(task)
        return task

    async def _stop_current(self, notify=True):
        self._cancel_requested = True
        await self._cancel_opener()
        await self._cancel_tts_tasks()
        task = self._turn_task
        current = asyncio.current_task()
        if task is not None and task is not current and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._turn_task = None
        self._busy = False
        if notify and not self._cancel_notified:
            self._cancel_notified = True
            try:
                await self._send_json({'type': 'done', 'cancelled': True})
            except Exception:
                pass

    async def _launch_turn(self, handler):
        if self._turn_task and not self._turn_task.done():
            await self._stop_current(notify=True)

        async def runner():
            self._cancel_requested = False
            self._cancel_notified = False
            self._busy = True
            self._turn_has_output = False
            self._reset_turn_stats()
            try:
                await handler()
            except asyncio.CancelledError:
                await self._cancel_tts_tasks()
                if not self._cancel_notified:
                    self._cancel_notified = True
                    try:
                        await self._send_json({'type': 'done', 'cancelled': True})
                    except Exception:
                        pass
                raise
            except RuntimeError as exc:
                logger.warning("Assistant vocal : %s", exc)
                if self._turn_has_output:
                    await self._send_json({'type': 'done'})
                else:
                    await self._send_json({
                        'type': 'error',
                        'message': str(exc),
                    })
                    await self._send_json({'type': 'done'})
            except Exception:
                logger.exception("Erreur assistant vocal")
                if self._turn_has_output:
                    await self._send_json({'type': 'done'})
                else:
                    await self._send_json({
                        'type': 'error',
                        'message': "Je n’ai pas pu répondre pour le moment. Réessayez dans un instant.",
                    })
                    await self._send_json({'type': 'done'})
            finally:
                self._busy = False
                if self._turn_task is asyncio.current_task():
                    self._turn_task = None

        self._turn_task = asyncio.create_task(runner())

    async def _send_working_ack(self, question):
        await self._cancel_opener()
        await self._send_json({'type': 'status', 'phase': 'working'})

    async def _cancel_opener(self):
        task = self._opener_task
        emit_task = self._opener_emit_task
        self._opener_task = None
        self._opener_emit_task = None
        self._opener_emitted = False
        self._tts_index = 0
        for pending in (task, emit_task):
            if pending and not pending.done():
                pending.cancel()
                try:
                    await pending
                except (asyncio.CancelledError, Exception):
                    pass

    async def _start_opening(self, question):
        # Vague D : une seule file (réponse). Pas d’amorce vocale en parallèle.
        del question
        await self._cancel_opener()

    async def _prepare_opening(self, question, pending):
        try:
            text = await generate_opening_line(question, pending)
        except Exception:
            logger.exception("Amorce Aria")
            text = ''
        if not text:
            return '', b'', 'audio/wav'
        audio = b''
        mime = 'audio/wav'
        try:
            audio, mime = await synthesize_audio(text)
        except Exception:
            logger.exception("TTS amorce Aria")
        if not mime:
            mime = 'audio/wav'
        return text, audio or b'', mime

    async def _emit_opening(self):
        if self._opener_emitted:
            return
        task = self._opener_task
        if not task:
            return
        async with self._opener_lock:
            if self._opener_emitted:
                return
            try:
                text, audio, mime = await task
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Amorce Aria")
                return
            if self._opener_emitted or not text:
                return
            self._opener_emitted = True
            await self._emit_sentence(text, 0, audio=audio, audio_mime=mime)
            self._tts_index = 1

    async def _send_action_result(self, status, title, message, **extra):
        """Confirmation visible obligatoire après chaque action terminée."""
        payload = {
            'type': 'action.result',
            'status': status,
            'title': title,
            'message': message,
        }
        payload.update({key: value for key, value in extra.items() if value not in (None, '')})
        await self._send_json(payload)

    async def _dispatch_navigation(self, name, result):
        if not isinstance(result, dict):
            return
        if result.get('erreur') and not is_lookup_clarification(result):
            await self._send_action_result(
                'error',
                'Action échouée',
                result['erreur'],
            )
        elif result.get('url') and result.get('ouvrir'):
            titre = result.get('titre') or result.get('nom') or 'cet écran'
            label = 'classe' if name == 'ouvrir_classe' else 'page'
            await self._send_action_result(
                'success',
                'Action réalisée',
                f"La {label} {titre} a bien été ouverte.",
                url=result.get('url'),
            )
        if result.get('url') and result.get('ouvrir'):
            await self._send_json({
                'type': 'navigate',
                'url': result['url'],
                'titre': result.get('titre') or result.get('nom') or '',
            })
        suggestions = result.get('suggestions') or []
        if suggestions or (name == 'ouvrir_classe' and not result.get('ouvrir')):
            items = list(suggestions)
            if result.get('url') and not result.get('ouvrir'):
                items.insert(0, {
                    'titre': result.get('titre') or result.get('nom'),
                    'url': result.get('url'),
                })
            choices = [
                {
                    'label': item.get('titre') or item.get('nom') or '',
                    'value': f"Ouvre {item.get('titre') or item.get('nom')}",
                    'url': item.get('url'),
                    'intent': 'open',
                }
                for item in items
                if item.get('titre') or item.get('nom')
            ]
            if choices:
                await self._send_suggestions(choices)

    def _is_enseignant_primaire(self):
        return getattr(self, 'persona', 'directeur') == 'enseignant_primaire'

    def _is_enseignant_secondaire(self):
        return getattr(self, 'persona', 'directeur') == 'enseignant'

    def _pending_action_names(self):
        if self._is_parent():
            from school_admin.services.assistant_parent_actions import PARENT_ACTION_SPECS

            return PARENT_ACTION_SPECS
        if self._is_enseignant_primaire():
            return ENSEIGNANT_ACTION_SPECS
        if self._is_enseignant_secondaire():
            return ENSEIGNANT_SECONDAIRE_ACTION_SPECS
        return ACTION_SPECS

    def _action_spec(self, name):
        if self._is_parent():
            from school_admin.services.assistant_parent_actions import get_parent_action

            return get_parent_action(name)
        if self._is_enseignant_primaire():
            return get_enseignant_action(name) or ACTION_SPECS.get(name)
        if self._is_enseignant_secondaire():
            return get_enseignant_secondaire_action(name) or ACTION_SPECS.get(name)
        return ACTION_SPECS.get(name)

    def _choices_for_pending_action(self, name, draft):
        if self._is_parent():
            from school_admin.services.assistant_parent_actions import choices_for_parent_action

            return choices_for_parent_action(name, draft)
        if self._is_enseignant_primaire() and name in ENSEIGNANT_ACTION_SPECS:
            return choices_for_enseignant_action(name, draft)
        if self._is_enseignant_secondaire() and name in ENSEIGNANT_SECONDAIRE_ACTION_SPECS:
            return choices_for_enseignant_secondaire_action(name, draft)
        return choices_for_action(name, draft)

    def _is_write_tool_name(self, name):
        if self._is_parent():
            from school_admin.services.assistant_parent_actions import is_parent_write_action

            return is_parent_write_action(name)
        return name in self._pending_action_names() or name in GUIDED_ACTIONS

    async def _on_live_tool_result(self, name, result):
        """Carte / nav si besoin, mais ne jamais arrêter Gemini (G1)."""
        if self._is_parent():
            if isinstance(result, dict):
                refs = getattr(self, '_working_refs', None)
                if refs is None:
                    self._working_refs = {}
                self._working_refs.update(extract_working_refs(name, result))
                self._last_tool_memory = compact_tool_memory(name, result)
            if name in ('ouvrir_page', 'ouvrir_recu', 'select_enfant'):
                await self._dispatch_navigation(name, result)
            elif self._is_write_tool_name(name):
                await self._remember_write_pending(name, result)
            return False
        if isinstance(result, dict):
            refs = getattr(self, '_working_refs', None)
            if refs is None:
                self._working_refs = {}
            self._working_refs.update(extract_working_refs(name, result))
            self._last_tool_memory = compact_tool_memory(name, result)
        if not isinstance(result, dict):
            return False
        if name == 'proposer_actions':
            items = (result or {}).get('suggestions') or []
            if items and not (
                self.pending_action and self._pending_is_ready()
            ):
                self._followup_suggestions = normalize_suggestions(items)
            return False
        if name in ('ouvrir_page', 'ouvrir_classe'):
            await self._dispatch_navigation(name, result)
            return False
        if self._is_write_tool_name(name):
            await self._remember_write_pending(name, result)
        return False

    async def _remember_write_pending(self, name, result):
        """Persiste le brouillon + carte de confirmation. Ne parle pas, n'applique pas."""
        data = dict(result or {})
        statut = data.get('statut')
        hard_error = bool(data.get('erreur')) and statut not in (
            'incomplet',
            'en_attente_confirmation',
            'plusieurs',
            'introuvable',
        )
        if hard_error:
            await self._send_action_result('error', 'Action échouée', data['erreur'])
            return False
        if statut == 'ok' and not data.get('erreur'):
            await self._clear_pending(silent=True)
            await self._send_action_result(
                'success',
                'Action réalisée',
                data.get('message') or 'C’est déjà fait.',
                url=data.get('url'),
            )
            return False

        self.pending_action = {'name': name, 'draft': data}
        await self._persist_pending()

        if data.get('url') and (
            data.get('ouvrir')
            or name in ('creer_emploi_du_temps', 'ajouter_creneau_emploi')
        ):
            await self._send_json({
                'type': 'navigate',
                'url': data['url'],
                'titre': data.get('resume') or data.get('nom') or data.get('classe') or '',
            })

        if statut == 'en_attente_confirmation' and is_action_ready(data):
            if name in ('creer_publier_annonce', 'annonce_guidee'):
                await self._set_pending(data)
            else:
                await self._send_generic_pending_ui(name, data)
            return False

        choices = self._choices_for_pending_action(name, data)
        if not choices and (
            is_lookup_clarification(data)
            or data.get('suggestions_possibles')
            or data.get('plusieurs_classes')
        ):
            choices = choices_from_class_lookup(data)
        if choices:
            self._followup_choices = choices
        return False

    async def _handle_local_intent(self, question, ctx):
        if getattr(ctx, 'persona', '') in ('parent', 'eleve'):
            return False
        if not is_navigation_only(question):
            return False
        intent = resolve_open_intent(question)
        if not intent:
            return False
        name, args = intent
        if name == 'choisir_classe':
            await self._offer_classe_choices(question)
            return True
        result = await self._execute_tool(ctx, name, args)
        await self._dispatch_navigation(name, result)
        if is_lookup_clarification(result):
            spoken = (
                result.get('message')
                and "Je n’ai pas trouvé la classe exacte. Voici les plus proches."
                or "Je n’ai pas trouvé la classe exacte. Laquelle voulez-vous ?"
            )
            if result.get('statut') == 'plusieurs':
                spoken = "Plusieurs classes correspondent. Laquelle voulez-vous ?"
        elif result.get('erreur'):
            spoken = result['erreur']
        elif name == 'ouvrir_classe':
            spoken = spoken_from_tool_result(name, result, ctx=ctx) or (
                f"J’ouvre la classe {result.get('nom') or args.get('query')}."
            )
            if isinstance(result, dict):
                if getattr(self, '_working_refs', None) is None:
                    self._working_refs = {}
                self._working_refs.update(extract_working_refs(name, result))
        else:
            spoken = result.get('message') or f"J’ouvre {result.get('titre') or 'cette page'}."
        sugg = (
            suggestions_after_read(
                [(name, result)],
                getattr(self, '_working_refs', None),
                ctx=ctx,
            )
            if name == 'ouvrir_classe' and isinstance(result, dict)
            else None
        )
        await self._speak_and_finish(
            user_text=question,
            spoken=spoken,
            suggestions=sugg,
        )
        return True

    async def _handle_chat(self, question):
        ctx = await self._build_context()
        if await self._handle_local_intent(question, ctx):
            return

        dialog = sanitize_dialog_messages(self.history)
        dialog.append({'role': 'user', 'content': question})
        dialog = sanitize_dialog_messages(dialog)
        messages = [
            build_system_message(ctx, tool_memory=self._tool_memory_for_turn()),
            *dialog,
        ]

        assembler = SentenceAssembler()
        pending_sentences = []

        async def on_status(phase):
            await self._send_json({'type': 'status', 'phase': phase})

        async def on_text_delta(delta):
            if self._cancel_requested:
                return
            clean = strip_assistant_markup(delta)
            if not clean:
                return
            await self._send_json({'type': 'text_delta', 'text': clean})
            pending_sentences.extend(assembler.feed(clean))

        last_tool_results = []
        turn_stats = getattr(self, '_turn_stats', None)
        if turn_stats is None:
            self._reset_turn_stats()
            turn_stats = self._turn_stats

        async def on_tool_result(name, _arguments, result):
            if isinstance(result, dict):
                last_tool_results.append((name, result))
            should_stop = await self._on_live_tool_result(name, result)
            if should_stop:
                turn_stats['takeover'] = turn_stats.get('takeover', 0) + 1
            return should_stop

        use_tools = True
        try:
            _working, spoken = await run_assistant_turn(
                ctx,
                messages,
                on_status=on_status,
                on_text_delta=on_text_delta,
                on_tool_result=on_tool_result,
                use_tools=use_tools,
                tool_memory=self._tool_memory_for_turn(),
                turn_stats=turn_stats,
                working_refs=getattr(self, '_working_refs', None) or {},
            )
        except Exception:
            logger.exception("Tour Gemini après outil")
            spoken = spoken_from_tool_results(last_tool_results, ctx=ctx)
            if spoken:
                await self._send_json({'type': 'text_delta', 'text': spoken})
                pending_sentences.append(spoken)
                await self._flush_tts_queue(pending_sentences)
                fallback_sugg = suggestions_after_read(
                    last_tool_results,
                    getattr(self, '_working_refs', None),
                    ctx=ctx,
                )
                if fallback_sugg and not (
                    self.pending_action and self._pending_is_ready()
                ):
                    await self._send_suggestions(fallback_sugg)
                if last_tool_results and not turn_stats.get('tools'):
                    turn_stats['tools'] = [name for name, _result in last_tool_results]
                self._log_turn_stats()
                await self._send_json({'type': 'done'})
                return
            await self._cancel_opener()
            if last_tool_results or turn_stats.get('pending_shown'):
                spoken = (
                    "J’ai préparé l’action. C’est bon ?"
                    if turn_stats.get('pending_shown')
                    else "J’ai les informations. Que souhaitez-vous que je fasse ?"
                )
                await self._send_json({'type': 'text_delta', 'text': spoken})
                pending_sentences.append(spoken)
                await self._flush_tts_queue(pending_sentences)
                if last_tool_results and not turn_stats.get('tools'):
                    turn_stats['tools'] = [name for name, _result in last_tool_results]
                self._log_turn_stats()
                await self._send_json({'type': 'done'})
                return
            if not self._turn_has_output:
                await self._send_json({
                    'type': 'error',
                    'message': "Je n’ai pas pu répondre pour le moment. Réessayez dans un instant.",
                })
            self._log_turn_stats()
            await self._send_json({'type': 'done'})
            return

        if self._cancel_requested:
            await self._cancel_tts_tasks()
            return

        leftover = assembler.flush()
        if leftover:
            pending_sentences.append(leftover)

        if last_tool_results:
            refs = getattr(self, '_working_refs', None)
            if refs is None:
                self._working_refs = {}
            for tool_name, tool_result in last_tool_results:
                if isinstance(tool_result, dict):
                    self._working_refs.update(extract_working_refs(tool_name, tool_result))
            self._last_tool_memory = compact_tool_memory(*last_tool_results[-1])
        if spoken and not leftover and not pending_sentences:
            await self._send_json({'type': 'text_delta', 'text': spoken})
            pending_sentences.append(spoken)
        elif not spoken and not leftover and last_tool_results:
            spoken = spoken_from_tool_results(last_tool_results, ctx=ctx)
            if spoken:
                await self._send_json({'type': 'text_delta', 'text': spoken})
                pending_sentences.append(spoken)

        if not spoken and not leftover and not pending_sentences and (
            last_tool_results or turn_stats.get('pending_shown')
        ):
            spoken = (
                "J’ai préparé l’action. C’est bon ?"
                if turn_stats.get('pending_shown')
                else "J’ai les informations. Que souhaitez-vous que je fasse ?"
            )
            await self._send_json({'type': 'text_delta', 'text': spoken})
            pending_sentences.append(spoken)

        await self._flush_tts_queue(pending_sentences)
        if self._cancel_requested:
            return

        if spoken:
            self.history.append({'role': 'user', 'content': question})
            self.history.append({'role': 'assistant', 'content': spoken})
            overflow = len(self.history) - MAX_HISTORY_MESSAGES
            if overflow > 0:
                self.history = self.history[overflow:]
            if self._followup_choices:
                await self._send_choices(self._followup_choices)
            elif self._followup_suggestions:
                await self._send_suggestions(self._followup_suggestions)
            elif last_tool_results and not (
                self.pending_action and self._pending_is_ready()
            ):
                fallback_sugg = suggestions_after_read(
                    last_tool_results,
                    getattr(self, '_working_refs', None),
                    ctx=ctx,
                )
                if fallback_sugg:
                    await self._send_suggestions(fallback_sugg)
                else:
                    await self._send_choices(self._infer_choices(spoken))
            else:
                await self._send_choices(self._infer_choices(spoken))
            self._followup_choices = []
            self._followup_suggestions = []
        elif not leftover and not pending_sentences:
            await self._send_json({
                'type': 'error',
                'message': "Je n’ai reçu aucune réponse de l’assistant.",
            })

        if last_tool_results and not turn_stats.get('tools'):
            turn_stats['tools'] = [name for name, _result in last_tool_results]
        self._log_turn_stats()
        await self._send_json({'type': 'done'})

    async def _handle_stt(self, payload):
        from school_admin.services.stt_service import transcribe_pcm16, transcribe_pcm16_multi

        raw = payload.get('audio_base64') or ''
        try:
            audio_bytes = base64.b64decode(raw)
        except Exception:
            await self._send_json({
                'type': 'transcript',
                'text': '',
                'error': 'Audio invalide.',
            })
            return

        if self._is_parent():
            from school_admin.services.assistant_parent_language import (
                STT_WOLOF_WEAK_MESSAGE,
                normalize_lang_preference,
                pick_best_stt_transcript,
                stt_language_order,
            )

            pref = normalize_lang_preference(
                payload.get('lang_pref') or await self._load_parent_lang_pref()
            )
            if payload.get('lang_pref'):
                await self._save_parent_lang_pref(pref)
            self._parent_lang_pref = pref
            order = stt_language_order(pref)
            if len(order) > 1:
                candidates = await transcribe_pcm16_multi(audio_bytes, order)
            else:
                candidates = {
                    order[0]: await transcribe_pcm16(audio_bytes, order[0]),
                }
            text, locale, weak = pick_best_stt_transcript(candidates)
            prefer_wolof = pref == 'wo' or (
                pref == 'auto' and locale.startswith('wo')
            )
            response = {
                'type': 'transcript',
                'text': text,
                'stt_locale': locale,
            }
            if weak and prefer_wolof:
                response['stt_weak'] = True
                response['fallback_message'] = STT_WOLOF_WEAK_MESSAGE
                if not text:
                    response['text'] = ''
            await self._send_json(response)
            return

        text = await transcribe_pcm16(audio_bytes)
        await self._send_json({
            'type': 'transcript',
            'text': text,
        })

    def _parent_tts_language(self, sentence):
        if not self._is_parent():
            return None
        from school_admin.services.assistant_parent_language import resolve_tts_language

        lang = resolve_tts_language(
            sentence or '',
            user_turn_language=getattr(self, '_parent_user_turn_lang', 'fr'),
            preference=getattr(self, '_parent_lang_pref', 'auto'),
        )
        return lang if lang == 'wo' else None

    async def _emit_sentence(self, sentence, index, audio=None, audio_mime='audio/wav'):
        if audio is None:
            tts_lang = self._parent_tts_language(sentence)
            if tts_lang:
                audio, audio_mime = await synthesize_audio(sentence, language=tts_lang)
            else:
                audio, audio_mime = await synthesize_audio(sentence)
        if not audio_mime:
            audio_mime = 'audio/wav'
        voice_failed = not audio
        payload = {
            'type': 'audio_sentence',
            'index': index,
            'text': sentence,
            'audio_mime': audio_mime,
            'audio_base64': base64.b64encode(audio).decode('ascii') if audio else '',
            'voice_failed': voice_failed,
        }
        await self._send_json(payload)

    async def _flush_tts_queue(self, sentences):
        if self._cancel_requested:
            await self._cancel_tts_tasks()
            return
        start = self._tts_index
        for offset, sentence in enumerate(sentences):
            if self._cancel_requested:
                await self._cancel_tts_tasks()
                return
            audio = b''
            mime = 'audio/wav'
            tts_lang = self._parent_tts_language(sentence)
            if tts_lang:
                synth = synthesize_audio(sentence, language=tts_lang)
            else:
                synth = synthesize_audio(sentence)
            task = self._track_tts(asyncio.create_task(synth))
            try:
                audio, mime = await task
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Échec TTS phrase.")
            if self._cancel_requested:
                return
            if not audio:
                logger.warning(
                    "TTS vide après repli, phrase %s : %s",
                    start + offset,
                    (sentence or '')[:80],
                )
            # audio=None relancerait une 2e synthèse : on transmet le résultat tel quel.
            await self._emit_sentence(
                sentence,
                start + offset,
                audio=audio if audio else b'',
                audio_mime=mime or 'audio/wav',
            )
        self._tts_index = start + len(sentences)

    async def _send_json(self, payload):
        if self._cancel_requested and payload.get('type') not in _ALLOWED_WHEN_CANCELLED:
            return
        kind = payload.get('type')
        if kind in (
            'audio_sentence',
            'text_delta',
            'action.result',
            'action.done',
            'suggestions',
        ):
            self._turn_has_output = True
        await self.send(text_data=json.dumps(payload, ensure_ascii=False))

    @database_sync_to_async
    def _resolve_etablissement(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            return False

        from school_admin.model.etablissement_model import Etablissement
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif

        if isinstance(user, Etablissement):
            self.etablissement = Etablissement.objects.get(pk=user.pk)
            self.personnel = None
            self.professeur = None
            self.persona = 'directeur'
            return True
        if isinstance(user, PersonnelAdministratif):
            personnel = PersonnelAdministratif.objects.select_related('etablissement').get(
                pk=user.pk
            )
            self.etablissement = personnel.etablissement
            self.personnel = personnel
            self.persona = 'directeur'
            return bool(self.etablissement)

        from school_admin.model.professeur_model import Professeur

        if isinstance(user, Professeur):
            from school_admin.services.assistant_prof_persona import (
                resolve_professeur_assistant_persona,
            )

            prof = Professeur.objects.select_related('etablissement').get(pk=user.pk)
            persona = resolve_professeur_assistant_persona(prof)
            if not persona:
                return False
            self.etablissement = prof.etablissement
            self.professeur = prof
            self.personnel = None
            self.persona = persona
            return True

        from school_admin.model.parent_model import Parent

        if isinstance(user, Parent):
            par = Parent.objects.select_related('etablissement').get(pk=user.pk)
            if not par.actif:
                return False
            self.parent = par
            self.etablissement = par.etablissement
            self.personnel = None
            self.professeur = None
            self.persona = 'parent'
            return bool(self.etablissement)

        from school_admin.model.eleve_model import Eleve

        if isinstance(user, Eleve):
            el = Eleve.objects.select_related('etablissement', 'classe').get(pk=user.pk)
            if not el.actif:
                return False
            self.eleve = el
            self.etablissement = el.etablissement
            self.personnel = None
            self.professeur = None
            self.parent = None
            self.persona = 'eleve'
            return bool(self.etablissement)

        return False

    async def _send_eleve_welcome(self):
        from school_admin.services.gemini_assistant_service import ELEVE_WELCOME

        text = ELEVE_WELCOME
        await self._send_json({
            'type': 'assistant.welcome',
            'text': text,
            'persona': 'eleve',
        })
        try:
            audio, mime = await synthesize_audio(text)
        except Exception:
            logger.exception('TTS accueil élève')
            audio, mime = b'', 'audio/wav'
        if text:
            await self._emit_sentence(text, 0, audio=audio or b'', audio_mime=mime or 'audio/wav')

    async def _send_parent_welcome(self):
        from school_admin.services.gemini_assistant_service import PARENT_WELCOME_BILINGUAL

        text = PARENT_WELCOME_BILINGUAL
        await self._send_json({
            'type': 'assistant.welcome',
            'text': text,
            'persona': 'parent',
        })
        try:
            audio, mime = await synthesize_audio(text)
        except Exception:
            logger.exception('TTS accueil parent')
            audio, mime = b'', 'audio/wav'
        if text:
            await self._emit_sentence(text, 0, audio=audio or b'', audio_mime=mime or 'audio/wav')

    def _is_parent(self):
        return getattr(self, 'persona', 'directeur') == 'parent'

    def _is_eleve(self):
        return getattr(self, 'persona', 'directeur') == 'eleve'

    async def _handle_set_lang_pref(self, payload):
        if not self._is_parent():
            await self._send_json({
                'type': 'error',
                'message': 'Préférence langue réservée au parcours parent.',
            })
            return
        from school_admin.services.assistant_parent_language import normalize_lang_preference

        pref = normalize_lang_preference(payload.get('value'))
        await self._save_parent_lang_pref(pref)
        self._parent_lang_pref = pref
        await self._send_json({'type': 'lang_pref', 'value': pref})

    @database_sync_to_async
    def _load_parent_lang_pref(self):
        from school_admin.services.assistant_parent_language import (
            SESSION_LANG_KEY,
            normalize_lang_preference,
        )

        session = self.scope.get('session') or {}
        return normalize_lang_preference(session.get(SESSION_LANG_KEY, 'auto'))

    @database_sync_to_async
    def _save_parent_lang_pref(self, pref):
        from school_admin.services.assistant_parent_language import (
            SESSION_LANG_KEY,
            normalize_lang_preference,
        )

        session = self.scope.get('session')
        if session is None:
            return
        session[SESSION_LANG_KEY] = normalize_lang_preference(pref)
        if not hasattr(session, 'save'):
            return
        try:
            session.save()
        except Exception:
            logger.exception('Impossible de sauvegarder aria_parent_lang en session.')

    @database_sync_to_async
    def _build_context(self):
        from school_admin.services.assistant_tools import build_assistant_context

        session_store = self.scope.get('session')
        if session_store is None:
            session_store = {}
        return build_assistant_context(
            self.etablissement,
            session_store,
            personnel=self.personnel,
            professeur=self.professeur,
            parent=self.parent,
            eleve=self.eleve,
            persona=self.persona,
        )

    @database_sync_to_async
    def _execute_tool(self, ctx, name, arguments):
        from school_admin.services.assistant_tools import execute_tool

        return execute_tool(ctx, name, arguments)

    async def _run_guarded(self, handler):
        if self._busy and self._turn_task is asyncio.current_task():
            try:
                await handler()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Erreur action assistant")
                if not self._turn_has_output:
                    await self._send_action_result(
                        'error',
                        'Action échouée',
                        "Je n’ai pas pu exécuter cette action. Réessayez.",
                    )
                    await self._send_json({
                        'type': 'error',
                        'message': "Je n’ai pas pu exécuter cette action. Réessayez.",
                    })
                await self._send_json({'type': 'done'})
            return
        await self._launch_turn(handler)

    def _restore_history(self, messages):
        cleaned = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = item.get('role')
            content = (item.get('content') or '').strip()
            if role in ('user', 'assistant') and content:
                cleaned.append({'role': role, 'content': content[:2000]})
        cleaned = sanitize_dialog_messages(cleaned)
        overflow = len(cleaned) - MAX_HISTORY_MESSAGES
        self.history = cleaned[overflow:] if overflow > 0 else cleaned

    def _annonce_ready(self):
        draft = (self.pending_action or {}).get('draft') or {}
        return bool(draft.get('titre') and draft.get('contenu') and draft.get('destinataires'))

    async def _send_choices(self, choices):
        cleaned = []
        widget = 'buttons'
        placeholder = ''
        for item in choices or []:
            if not isinstance(item, dict):
                continue
            label = (item.get('label') or item.get('titre') or '').strip()
            if not label:
                continue
            if (item.get('widget') or '') == 'select':
                widget = 'select'
            if item.get('placeholder') and not placeholder:
                placeholder = item.get('placeholder')
            cleaned.append({
                'label': label[:80],
                'value': (item.get('value') or label)[:200],
                'intent': item.get('intent') or 'chat',
                'url': item.get('url') or '',
                'widget': item.get('widget') or '',
                'placeholder': item.get('placeholder') or '',
            })
        if not cleaned:
            return
        payload = {
            'type': 'choices',
            'widget': widget,
            'placeholder': placeholder,
            'choices': cleaned if widget == 'select' else cleaned[:5],
        }
        await self._send_json(payload)

    async def _send_suggestions(self, items):
        cleaned = normalize_suggestions(items, limit=3)
        if not cleaned:
            return
        stats = getattr(self, '_turn_stats', None)
        if stats is None:
            self._reset_turn_stats()
            stats = self._turn_stats
        stats['suggestions_count'] = len(cleaned)
        await self._send_json({
            'type': 'suggestions',
            'items': cleaned,
        })

    async def _restore_pending_ui(self):
        if not self.pending_action:
            return
        name = self.pending_action.get('name')
        if name in ('annonce_guidee', 'creer_publier_annonce') and self._annonce_ready():
            draft = self.pending_action.get('draft') or {}
            await self._send_json({
                'type': 'action.pending',
                'action': 'creer_publier_annonce',
                'titre': draft.get('titre') or '',
                'contenu': draft.get('contenu') or '',
                'destinataires_libelle': draft.get('destinataires_libelle') or 'Tous',
                'publier': bool(draft.get('publier', True)),
            })
            await self._send_choices(self._choices_for_annonce())
        elif name in ('creer_emploi_du_temps', 'ajouter_creneau_emploi'):
            await self._send_choices(self._choices_for_emploi_action())
        elif name == 'choisir_classe':
            await self._send_choices(self.pending_action.get('choices') or [])
        elif name in self._pending_action_names():
            draft = self.pending_action.get('draft') or {}
            await self._send_generic_pending_ui(name, draft)
            await self._send_choices(self._choices_for_pending_action(name, draft))

    async def _handle_choice_payload(self, payload):
        intent = (payload.get('intent') or 'chat').strip()
        value = (payload.get('value') or payload.get('label') or '').strip()
        if intent == 'open' and payload.get('url'):
            await self._send_working_ack(value or 'Ouvre cette page.')
        elif intent not in ('cancel',):
            await self._send_working_ack(value)
        if intent == 'confirm':
            await self._ensure_pending_loaded()
            if payload.get('publier') is True and self.pending_action:
                self.pending_action.setdefault('draft', {})['publier'] = True
            await self._run_guarded(self._confirm_pending)
            return
        if intent == 'cancel':
            await self._ensure_pending_loaded()
            await self._run_guarded(self._cancel_pending)
            return
        if intent == 'open' and payload.get('url'):
            opened = (payload.get('label') or value).strip()
            lowered = opened.lower()
            if lowered.startswith('ouvre '):
                opened = opened[6:].strip()
            if opened.lower().startswith('la classe '):
                opened = opened[10:].strip()
            await self._send_action_result(
                'success',
                'Action réalisée',
                f"{opened} a bien été ouverte.",
                url=payload['url'],
            )
            await self._send_json({
                'type': 'navigate',
                'url': payload['url'],
                'titre': value,
                'immediate': True,
            })
            await self._clear_pending(silent=True)
            await self._speak_and_finish(user_text=value, spoken=f"J’ouvre {value}.")
            return
        if not value:
            await self._send_action_result(
                'error',
                'Action échouée',
                'Ce choix n’est pas valide.',
            )
            await self._send_json({'type': 'error', 'message': 'Choix invalide.'})
            return
        if await self._route_pending_reply(value):
            return
        await self._handle_chat(value)

    def _pending_is_ready(self):
        pending = self.pending_action or {}
        name = pending.get('name')
        draft = pending.get('draft') or {}
        if name in ('annonce_guidee', 'creer_publier_annonce'):
            return self._annonce_ready()
        if name in ('creer_emploi_du_temps', 'ajouter_creneau_emploi'):
            return self._emploi_action_ready()
        return is_action_ready(draft)

    def _tool_memory_for_turn(self):
        parts = []
        if self._last_tool_memory:
            parts.append(self._last_tool_memory)
        cited = format_cited_refs(getattr(self, '_working_refs', {}) or {})
        if cited:
            parts.append(f'Réfs citées (réutilise pour relancer/ouvrir) : {cited}')
        pending = self.pending_action
        if pending and pending.get('name'):
            compact = compact_tool_memory(pending['name'], pending.get('draft') or {})
            parts.append(
                "Action en attente de confirmation (rien n’est écrit) : "
                f"{compact or pending['name']}. "
                "S’il demande de modifier, rappelle le même outil avec le brouillon ajusté."
            )
        return ' | '.join(parts)

    def _reset_turn_stats(self):
        self._turn_stats = {
            'tools': [],
            'rounds': 0,
            'pending_shown': 0,
            'suggestions_count': 0,
            'takeover': 0,
        }

    def _log_turn_stats(self):
        stats = getattr(self, '_turn_stats', None) or {}
        payload = format_turn_telemetry(
            tools=stats.get('tools') or [],
            rounds=stats.get('rounds') or 0,
            pending_shown=stats.get('pending_shown') or 0,
            suggestions_count=stats.get('suggestions_count') or 0,
            takeover=stats.get('takeover') or 0,
        )
        log_turn_telemetry(payload)
        return payload

    def _mark_pending_shown(self):
        stats = getattr(self, '_turn_stats', None)
        if stats is None:
            self._reset_turn_stats()
            stats = self._turn_stats
        stats['pending_shown'] = 1

    async def _route_pending_reply(self, question):
        """G2 : seuls oui / modifier / annuler consomment le pending."""
        await self._ensure_pending_loaded()
        pending = self.pending_action
        if not pending:
            return False
        if is_cancel(question):
            await self._run_guarded(self._cancel_pending)
            return True
        if is_affirmative(question):
            if self._pending_is_ready():
                await self._run_guarded(self._confirm_pending)
                return True
            return False
        if is_pending_modify(question):
            return False
        await self._clear_pending(silent=True)
        return False

    async def _offer_classe_choices(self, question):
        ctx = await self._build_context()
        choices = await database_sync_to_async(self._classe_choice_items)(ctx)
        self.pending_action = {
            'name': 'choisir_classe',
            'choices': choices,
        }
        await self._persist_pending()
        if choices:
            spoken = "Quelle classe voulez-vous ouvrir ? Choisissez-en une, ou dites-moi son nom."
        else:
            spoken = "Je ne trouve aucune classe active pour le moment."
            await self._send_action_result(
                'error',
                'Action échouée',
                spoken,
            )
        await self._speak_and_finish(user_text=question, spoken=spoken, choices=choices)

    def _classe_choice_items(self, ctx):
        if self._is_enseignant_primaire() or self._is_enseignant_secondaire():
            from django.urls import reverse
            from school_admin.services.assistant_enseignant_scope import affectations_qs

            route = (
                'enseignant_primaire:detail_classe'
                if self._is_enseignant_primaire()
                else 'enseignant:detail_classe'
            )
            items = []
            seen = set()
            for aff in affectations_qs(ctx)[:12]:
                if aff.classe_id in seen:
                    continue
                seen.add(aff.classe_id)
                label = aff.classe.nom
                if self._is_enseignant_secondaire() and getattr(aff, 'matiere_id', None):
                    mat = getattr(aff.matiere, 'nom', None)
                    if mat:
                        label = f'{aff.classe.nom} ({mat})'
                items.append({
                    'label': label,
                    'value': f'Ouvre la classe {aff.classe.nom}',
                    'url': reverse(route, args=[aff.classe_id]),
                    'intent': 'open',
                })
            return items[:8]
        from school_admin.services.assistant_tools import list_classe_choices

        return list_classe_choices(ctx)

    def _choices_for_annonce(self):
        draft = (self.pending_action or {}).get('draft') or {}
        focus = draft.get('edit_field')
        if focus in ('titre', 'contenu'):
            return []
        if not draft.get('titre') and not draft.get('contenu'):
            return []
        if not draft.get('contenu'):
            return []
        if focus == 'destinataires' or not draft.get('destinataires'):
            return [
                {'label': 'Tout le monde', 'value': 'tout le monde', 'intent': 'chat'},
                {'label': 'Enseignants', 'value': 'les enseignants', 'intent': 'chat'},
                {'label': 'Parents', 'value': 'les parents', 'intent': 'chat'},
                {'label': 'Élèves', 'value': 'les élèves', 'intent': 'chat'},
            ]
        return [
            {'label': 'Oui, publier', 'value': 'Oui, c’est bon.', 'intent': 'confirm'},
            {'label': 'Modifier', 'value': 'Je veux modifier.', 'intent': 'modify'},
            {'label': 'Annuler', 'value': 'Annuler.', 'intent': 'cancel'},
        ]

    def _infer_choices(self, spoken):
        if self.pending_action and self.pending_action.get('name') == 'annonce_guidee':
            return self._choices_for_annonce()
        if self.pending_action and self.pending_action.get('name') in (
            'creer_emploi_du_temps',
            'ajouter_creneau_emploi',
        ):
            return self._choices_for_emploi_action()
        if self.pending_action and self.pending_action.get('name') in self._pending_action_names():
            draft = self.pending_action.get('draft') or {}
            if is_action_ready(draft):
                return self._choices_for_pending_action(self.pending_action['name'], draft)
            return []
        if self.pending_action and self.pending_action.get('name') == 'choisir_classe':
            return self.pending_action.get('choices') or []
        return []

    async def _set_pending(self, draft):
        from school_admin.services.assistant_tools import _destinataires_libelle

        name = (self.pending_action or {}).get('name') or 'creer_publier_annonce'
        draft = dict(draft or {})
        if draft.get('destinataires') and not draft.get('destinataires_libelle'):
            draft['destinataires_libelle'] = _destinataires_libelle(draft['destinataires'])
        self.pending_action = {
            'name': name,
            'draft': draft,
        }
        self._mark_pending_shown()
        await self._send_json({
            'type': 'action.pending',
            'action': 'creer_publier_annonce',
            'titre': draft.get('titre') or '',
            'contenu': draft.get('contenu') or '',
            'destinataires_libelle': draft.get('destinataires_libelle') or 'Tous',
            'publier': bool(draft.get('publier', True)),
            'choices': self._choices_for_annonce(),
        })
        await self._persist_pending()

    async def _persist_pending(self):
        session = self.scope.get('session')
        if session is None:
            return
        try:
            session['aria_pending'] = self.pending_action
            if hasattr(session, 'asave'):
                await session.asave()
            else:
                await database_sync_to_async(session.save)()
        except Exception:
            logger.exception("Impossible d’enregistrer l’action Aria en session.")

    async def _load_pending(self):
        session = self.scope.get('session')
        if session is None:
            return
        pending = session.get('aria_pending')
        if isinstance(pending, dict) and pending.get('name'):
            self.pending_action = pending

    async def _ensure_pending_loaded(self):
        if self.pending_action:
            return True
        await self._load_pending()
        return bool(self.pending_action)

    async def _send_generic_pending_ui(self, name, draft):
        draft = dict(draft or {})
        self._mark_pending_shown()
        await self._send_json({
            'type': 'action.pending',
            'action': name,
            'titre': draft.get('nom') or draft.get('resume') or name.replace('_', ' '),
            'contenu': default_prompt(draft),
            'destructive': bool(draft.get('destructive')),
            'choices': self._choices_for_pending_action(name, draft),
        })

    async def _clear_pending(self, silent=False):
        if not self.pending_action:
            return
        self.pending_action = None
        await self._persist_pending()
        if not silent:
            await self._send_json({'type': 'action.cancelled'})

    async def _cancel_pending(self):
        await self._ensure_pending_loaded()
        if not self.pending_action:
            await self._send_action_result(
                'error',
                'Action échouée',
                'Aucune action n’était en attente de confirmation.',
            )
            await self._send_json({'type': 'done'})
            return
        was_annonce = self.pending_action.get('name') in (
            'annonce_guidee',
            'creer_publier_annonce',
        )
        await self._clear_pending(silent=True)
        spoken = (
            "D’accord, je n’ai rien publié."
            if was_annonce
            else "D’accord, j’annule."
        )
        await self._send_action_result(
            'cancelled',
            'Action annulée',
            spoken,
        )
        await self._speak_and_finish(user_text='Annuler', spoken=spoken)

    def _emploi_action_ready(self):
        pending = self.pending_action or {}
        name = pending.get('name')
        draft = pending.get('draft') or {}
        if name == 'creer_emploi_du_temps':
            return bool(draft.get('classe_id'))
        if name == 'ajouter_creneau_emploi':
            return bool(
                (draft.get('classe_id') or draft.get('classe'))
                and draft.get('jour')
                and draft.get('heure_debut')
                and draft.get('heure_fin')
                and not draft.get('matiere_introuvable')
                and not draft.get('professeur_introuvable')
                and not draft.get('salle_introuvable')
            )
        return False

    def _choices_for_emploi_action(self):
        pending = self.pending_action or {}
        return choices_for_emploi(pending.get('draft') or {}, pending.get('name'))

    async def _confirm_emploi_action(self):
        pending = self.pending_action or {}
        name = pending.get('name')
        draft = dict(pending.get('draft') or {})
        ctx = await self._build_context()
        if name == 'ajouter_creneau_emploi':
            result = await database_sync_to_async(apply_creneau_draft)(ctx, draft)
        else:
            result = await database_sync_to_async(apply_emploi_du_temps_draft)(ctx, draft)
        if is_lookup_clarification(result) or (
            result.get('statut') in ('incomplet', 'plusieurs', 'introuvable')
            and not (
                result.get('emploi_id')
                or result.get('creneau_id')
                or result.get('cree')
            )
        ):
            self.pending_action = {'name': name, 'draft': result}
            await self._persist_pending()
            spoken = result.get('message') or default_prompt(result)
            await self._speak_and_finish(user_text='Confirmer', spoken=spoken)
            return
        self.pending_action = None
        await self._persist_pending()
        if result.get('erreur'):
            await self._send_action_result(
                'error',
                'Action échouée',
                result['erreur'],
            )
            await self._speak_and_finish(user_text='Confirmer', spoken=result['erreur'])
            return
        url = result.get('url') or ''
        message = result.get('message') or 'Action réalisée.'
        if name == 'ajouter_creneau_emploi':
            spoken = f"C’est fait. {message} J’ouvre l’emploi du temps."
        elif result.get('deja_existant'):
            spoken = f"{message} J’ouvre la grille."
        else:
            spoken = f"C’est fait. {message} J’ouvre la grille."
        await self._send_action_result(
            'success',
            'Action réalisée',
            message,
            url=url,
        )
        await self._send_json({
            'type': 'action.done',
            'action': name,
            'id': result.get('emploi_id') or result.get('creneau_id'),
            'message': message,
            'url': url,
        })
        await self._speak_and_finish(user_text='Confirmer', spoken=spoken)

    async def _confirm_generic_action(self):
        pending = self.pending_action or {}
        name = pending.get('name')
        draft = dict(pending.get('draft') or {})
        spec = self._action_spec(name)
        if not spec or not spec.apply:
            await self._send_action_result(
                'error',
                'Action échouée',
                'Aucune action n’était en attente de confirmation.',
            )
            await self._send_json({'type': 'done'})
            return
        if not is_action_ready(draft):
            spoken = default_prompt(draft) or "Il me manque encore des informations."
            await self._speak_and_finish(user_text='Confirmer', spoken=spoken)
            return
        ctx = await self._build_context()
        result = await database_sync_to_async(spec.apply)(ctx, draft)
        if result.get('statut') == 'incomplet' or (
            result.get('erreur') and result.get('manquants')
        ):
            self.pending_action = {'name': name, 'draft': result}
            await self._persist_pending()
            spoken = result.get('message') or default_prompt(result)
            await self._speak_and_finish(user_text='Confirmer', spoken=spoken)
            return
        self.pending_action = None
        await self._persist_pending()
        if result.get('erreur'):
            await self._send_action_result('error', 'Action échouée', result['erreur'])
            await self._speak_and_finish(user_text='Confirmer', spoken=result['erreur'])
            return
        url = result.get('url') or ''
        message = result.get('message') or 'Action réalisée.'
        await self._send_action_result('success', 'Action réalisée', message, url=url)
        await self._send_json({
            'type': 'action.done',
            'action': name,
            'id': result.get('id'),
            'message': message,
            'url': url,
        })
        if url:
            await self._send_json({
                'type': 'navigate',
                'url': url,
                'titre': result.get('nom') or result.get('titre') or '',
            })
        spoken = f"C’est fait. {message}"
        await self._speak_and_finish(user_text='Confirmer', spoken=spoken)

    async def _confirm_pending(self):
        await self._ensure_pending_loaded()
        pending = self.pending_action
        if pending and pending.get('name') in self._pending_action_names():
            await self._confirm_generic_action()
            return
        if pending and pending.get('name') in (
            'creer_emploi_du_temps',
            'ajouter_creneau_emploi',
        ):
            await self._confirm_emploi_action()
            return
        if not pending or pending.get('name') not in (
            'creer_publier_annonce',
            'annonce_guidee',
        ):
            await self._send_action_result(
                'error',
                'Action échouée',
                'Aucune action n’était en attente de confirmation.',
            )
            await self._send_json({'type': 'done'})
            return

        ctx = await self._build_context()
        draft = dict(pending['draft'])
        draft['publier'] = True
        result = await self._apply_annonce(ctx, draft)
        self.pending_action = None
        await self._persist_pending()
        if result.get('erreur'):
            await self._send_action_result(
                'error',
                'Action échouée',
                result['erreur'],
            )
            await self._speak_and_finish(
                user_text='Confirmer',
                spoken=result['erreur'],
            )
            return

        titre = result.get('titre') or 'cette annonce'
        dest = result.get('destinataires_libelle') or 'tous'
        detail_url = result.get('url') or '/directeur/annonces/'
        if result.get('publiee'):
            spoken = f"C’est fait. L’annonce {titre} a été publiée pour {dest}. J’ouvre son détail."
            success = f"Annonce publiée avec succès : {titre}."
        else:
            spoken = f"C’est fait. L’annonce {titre} a été enregistrée en brouillon. J’ouvre son détail."
            success = f"Annonce enregistrée en brouillon : {titre}."
        await self._send_action_result(
            'success',
            'Action réalisée',
            success,
            url=detail_url,
        )
        await self._send_json({
            'type': 'action.done',
            'action': 'creer_publier_annonce',
            'id': result.get('id'),
            'titre': result.get('titre'),
            'publiee': result.get('publiee'),
            'message': success,
            'url': detail_url,
        })
        await self._send_json({
            'type': 'navigate',
            'url': detail_url,
            'titre': titre,
        })
        await self._speak_and_finish(user_text='Confirmer', spoken=spoken)

    async def _speak_and_finish(self, user_text, spoken, choices=None, suggestions=None):
        if self._cancel_requested:
            return
        spoken = strip_assistant_markup(spoken or '')
        await self._send_json({'type': 'status', 'phase': 'speaking'})
        if spoken:
            await self._send_json({'type': 'text_delta', 'text': spoken})
        assembler = SentenceAssembler()
        sentences = list(assembler.feed(spoken or ''))
        leftover = assembler.flush()
        if leftover:
            sentences.append(leftover)
        try:
            await self._flush_tts_queue(sentences)
        except Exception:
            logger.exception("TTS après action — le texte a déjà été envoyé")
        if self._cancel_requested:
            return
        if spoken:
            self.history.append({'role': 'user', 'content': user_text})
            self.history.append({'role': 'assistant', 'content': spoken})
            overflow = len(self.history) - MAX_HISTORY_MESSAGES
            if overflow > 0:
                self.history = self.history[overflow:]
        if suggestions:
            await self._send_suggestions(suggestions)
        else:
            await self._send_choices(choices if choices is not None else self._infer_choices(spoken))
        await self._send_json({'type': 'done'})

    @database_sync_to_async
    def _apply_annonce(self, ctx, draft):
        from school_admin.services.assistant_tools import apply_annonce_draft

        return apply_annonce_draft(ctx, draft)
