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
    enrich_creneau_draft,
    enrich_emploi_draft,
    next_creneau_prompt,
    next_emploi_prompt,
    _classe_choices,
)
from school_admin.services.assistant_actions import (
    ACTION_SPECS,
    choices_for_action,
    default_prompt,
    is_action_ready,
)
from school_admin.services.assistant_intents import (
    ANNONCE_CREATE_RE,
    CRENEAU_ADD_RE,
    annonce_field_request,
    decide_pending_reply,
    extract_creneau_draft,
    extract_emploi_draft,
    infer_destinataires,
    is_small_talk,
    is_vague_annonce_modify,
    resolve_action_intent,
    resolve_annonce_intent,
    resolve_emploi_intent,
    resolve_open_intent,
)
from school_admin.services.assistant_search import (
    choices_from_class_lookup,
    is_lookup_clarification,
)
from school_admin.services.gemini_assistant_service import (
    WRITTEN_DRAFT_MAX,
    build_system_message,
    classify_pending_intent,
    generate_written_draft,
    run_assistant_turn,
    sanitize_dialog_messages,
)
from school_admin.services.tts_service import strip_assistant_markup, synthesize_audio

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 24
MAX_QUESTION_LENGTH = 8000
SENTENCE_RE = re.compile(r'(.+?(?:[.!?…]|\n)+)\s*', re.DOTALL)
CLAUSE_RE = re.compile(r'(.{40,}?[,;:])\s+')
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
WRITE_SPEC_RE = re.compile(
    r'(\d+\s*(?:mots?|paragraphes?)|en\s+\d+\s+paragraphes?|'
    r'r[ée]dige[rz]?|ecris|écris|un titre|deux paragraphes|'
    r'plus (?:court|long))',
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


class SentenceAssembler:
    """Découpe un flux de tokens en phrases prêtes pour le TTS."""

    def __init__(self):
        self.buffer = ''

    def feed(self, delta):
        self.buffer += delta or ''
        sentences = []
        while True:
            match = SENTENCE_RE.match(self.buffer)
            if not match and len(self.buffer) >= 70:
                match = CLAUSE_RE.match(self.buffer)
            if not match:
                break
            sentence = match.group(1).strip()
            self.buffer = self.buffer[match.end():]
            if sentence:
                sentences.append(sentence)
        return sentences

    def flush(self):
        leftover = self.buffer.strip()
        self.buffer = ''
        return leftover


class AssistantConsumer(AsyncWebsocketConsumer):
    """Canal privé directeur / personnel administratif."""

    async def connect(self):
        self.etablissement = None
        self.personnel = None
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
        allowed = await self._resolve_etablissement()
        if not allowed:
            await self.close(code=4401)
            return
        await self.accept()
        await self._load_pending()
        await self._send_json({
            'type': 'connection.established',
            'etablissement': getattr(self.etablissement, 'nom', ''),
        })
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

        await self._launch_turn(lambda: self._execute_user_message(question))

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

    async def _execute_user_message(self, question):
        await self._send_working_ack(question)
        await self._ensure_pending_loaded()
        if await self._route_pending_reply(question):
            return
        if self.pending_action:
            await self._clear_pending(silent=True)
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
                await self._send_json({
                    'type': 'error',
                    'message': str(exc),
                })
                await self._send_json({'type': 'done'})
            except Exception:
                logger.exception("Erreur assistant vocal")
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
        await self._cancel_opener()
        pending = dict(self.pending_action) if isinstance(self.pending_action, dict) else None
        self._opener_task = asyncio.create_task(self._prepare_opening(question, pending))
        self._opener_emit_task = asyncio.create_task(self._emit_opening())

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
                await self._send_choices(choices)

    async def _handle_local_intent(self, question, ctx):
        draft = resolve_annonce_intent(question)
        if draft is not None:
            await self._start_annonce_guidee(question, draft)
            return True
        emploi = resolve_emploi_intent(question)
        if emploi is not None:
            if emploi.get('action') == 'ajouter_creneau_emploi':
                await self._start_creneau_guidee(question, emploi)
            else:
                await self._start_emploi_guidee(question, emploi)
            return True
        action_intent = resolve_action_intent(question)
        if action_intent:
            name, args = action_intent
            result = await self._execute_tool(ctx, name, args)
            await self._start_generic_action(name, question, result)
            return True
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
            spoken = f"J’ouvre la classe {result.get('nom') or args.get('query')}."
        else:
            spoken = f"J’ouvre {result.get('titre') or 'cette page'}."
        await self._speak_and_finish(user_text=question, spoken=spoken)
        return True

    async def _handle_chat(self, question):
        ctx = await self._build_context()
        if await self._handle_local_intent(question, ctx):
            return

        dialog = sanitize_dialog_messages(self.history)
        dialog.append({'role': 'user', 'content': question})
        dialog = sanitize_dialog_messages(dialog)
        messages = [build_system_message(ctx), *dialog]

        assembler = SentenceAssembler()
        pending_tts = []

        async def on_status(phase):
            await self._send_json({'type': 'status', 'phase': phase})

        async def on_text_delta(delta):
            if self._cancel_requested:
                return
            clean = strip_assistant_markup(delta)
            if not clean:
                return
            await self._send_json({'type': 'text_delta', 'text': clean})
            for sentence in assembler.feed(clean):
                pending_tts.append(
                    (sentence, self._track_tts(asyncio.create_task(synthesize_audio(sentence))))
                )

        takeover = {'annonce': False, 'emploi': False, 'creneau': False, 'generic': False}

        async def on_tool_result(name, _arguments, result):
            if not isinstance(result, dict):
                return
            if name in ACTION_SPECS:
                if result.get('erreur') and result.get('statut') not in (
                    'incomplet',
                    'en_attente_confirmation',
                ):
                    await self._send_action_result(
                        'error',
                        'Action échouée',
                        result['erreur'],
                    )
                    return
                takeover['generic'] = True
                await self._start_generic_action(name, question, result)
                return
            if name == 'creer_publier_annonce':
                if result.get('erreur'):
                    await self._send_action_result(
                        'error',
                        'Action échouée',
                        result['erreur'],
                    )
                    return
                takeover['annonce'] = True
                await self._start_annonce_guidee(question, result)
                return
            if name == 'creer_emploi_du_temps':
                if is_lookup_clarification(result):
                    self._followup_choices = choices_from_class_lookup(result)
                    return
                if result.get('erreur'):
                    await self._send_action_result(
                        'error',
                        'Action échouée',
                        result['erreur'],
                    )
                    return
                takeover['emploi'] = True
                await self._start_emploi_guidee(question, result)
                return
            if name == 'ajouter_creneau_emploi':
                if is_lookup_clarification(result):
                    self._followup_choices = choices_from_class_lookup(result)
                    return
                if result.get('erreur'):
                    await self._send_action_result(
                        'error',
                        'Action échouée',
                        result['erreur'],
                    )
                    return
                takeover['creneau'] = True
                await self._start_creneau_guidee(question, result)
                return
            if name in ('ouvrir_page', 'ouvrir_classe'):
                await self._dispatch_navigation(name, result)

        try:
            _working, spoken = await run_assistant_turn(
                ctx,
                messages,
                on_status=on_status,
                on_text_delta=on_text_delta,
                on_tool_result=on_tool_result,
                use_tools=not is_small_talk(question),
            )
        except RuntimeError as exc:
            await self._cancel_opener()
            await self._send_json({'type': 'error', 'message': str(exc)})
            await self._send_json({'type': 'done'})
            return

        if self._cancel_requested:
            await self._cancel_tts_tasks()
            return

        if takeover['annonce'] or takeover['emploi'] or takeover['creneau'] or takeover['generic']:
            return

        leftover = assembler.flush()
        if leftover:
            pending_tts.append(
                (leftover, self._track_tts(asyncio.create_task(synthesize_audio(leftover))))
            )

        await self._flush_tts_queue(pending_tts)
        if self._cancel_requested:
            return

        if spoken:
            self.history.append({'role': 'user', 'content': question})
            self.history.append({'role': 'assistant', 'content': spoken})
            overflow = len(self.history) - MAX_HISTORY_MESSAGES
            if overflow > 0:
                self.history = self.history[overflow:]
            await self._send_choices(
                self._followup_choices or self._infer_choices(spoken)
            )
            self._followup_choices = []
        elif not leftover and not pending_tts:
            await self._send_json({
                'type': 'error',
                'message': "Je n’ai reçu aucune réponse de l’assistant.",
            })

            await self._send_json({'type': 'done'})

    async def _handle_stt(self, payload):
        from school_admin.services.stt_service import transcribe_pcm16

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

        text = await transcribe_pcm16(audio_bytes)
        await self._send_json({
            'type': 'transcript',
            'text': text,
        })

    async def _emit_sentence(self, sentence, index, audio=None, audio_mime='audio/wav'):
        if audio is None:
            audio, audio_mime = await synthesize_audio(sentence)
        if not audio_mime:
            audio_mime = 'audio/wav'
        payload = {
            'type': 'audio_sentence',
            'index': index,
            'text': sentence,
            'audio_mime': audio_mime,
            'audio_base64': base64.b64encode(audio).decode('ascii') if audio else '',
        }
        await self._send_json(payload)

    async def _flush_tts_queue(self, pending_tts):
        if self._cancel_requested:
            await self._cancel_tts_tasks()
            return
        await self._emit_opening()
        start = self._tts_index
        for offset, (sentence, task) in enumerate(pending_tts):
            if self._cancel_requested:
                await self._cancel_tts_tasks()
                return
            audio = b''
            mime = 'audio/wav'
            try:
                audio, mime = await task
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Échec TTS phrase.")
            if self._cancel_requested:
                return
            await self._emit_sentence(
                sentence,
                start + offset,
                audio=audio or b'',
                audio_mime=mime or 'audio/wav',
            )
        self._tts_index = start + len(pending_tts)

    async def _send_json(self, payload):
        if self._cancel_requested and payload.get('type') not in _ALLOWED_WHEN_CANCELLED:
            return
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
            return True
        if isinstance(user, PersonnelAdministratif):
            personnel = PersonnelAdministratif.objects.select_related('etablissement').get(
                pk=user.pk
            )
            self.etablissement = personnel.etablissement
            self.personnel = personnel
            return bool(self.etablissement)
        return False

    @database_sync_to_async
    def _build_context(self):
        from school_admin.services.assistant_tools import build_assistant_context

        session_store = self.scope.get('session') or {}
        return build_assistant_context(
            self.etablissement,
            session_store,
            personnel=self.personnel,
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

    async def _send_annonce_form_fill(self):
        draft = (self.pending_action or {}).get('draft') or {}
        await self._send_json({
            'type': 'form.fill',
            'form': 'annonce',
            'titre': draft.get('titre') or '',
            'contenu': draft.get('contenu') or '',
            'destinataires': draft.get('destinataires') or [],
        })

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
        elif name in ACTION_SPECS:
            draft = self.pending_action.get('draft') or {}
            await self._send_generic_pending_ui(name, draft)
            await self._send_choices(choices_for_action(name, draft))

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

    async def _route_pending_reply(self, question):
        await self._ensure_pending_loaded()
        pending = self.pending_action
        if not pending:
            return False
        name = pending.get('name')
        if is_cancel(question):
            await self._run_guarded(self._cancel_pending)
            return True
        if name in ('annonce_guidee', 'creer_publier_annonce'):
            field = annonce_field_request(question)
            vague = is_vague_annonce_modify(question)
            edit_open = bool((pending.get('draft') or {}).get('edit_field'))
            if (
                is_affirmative(question)
                and self._annonce_ready()
                and not field
                and not vague
                and not edit_open
            ):
                await self._run_guarded(self._confirm_pending)
                return True
            if field or vague:
                await self._run_guarded(lambda: self._continue_annonce_guidee(question))
                return True
        elif name in ('creer_emploi_du_temps', 'ajouter_creneau_emploi'):
            if is_affirmative(question) and self._emploi_action_ready():
                await self._run_guarded(self._confirm_pending)
                return True
            await self._run_guarded(lambda: self._continue_emploi_guidee(question))
            return True
        elif name in ACTION_SPECS:
            if is_affirmative(question) and is_action_ready(pending.get('draft') or {}):
                await self._run_guarded(self._confirm_pending)
                return True
            decision = decide_pending_reply(question, pending)
            if decision == 'switch':
                await self._clear_pending(silent=True)
                return False
            await self._run_guarded(lambda: self._continue_generic_action(question))
            return True
        elif is_affirmative(question):
            await self._run_guarded(self._confirm_pending)
            return True

        decision = decide_pending_reply(question, pending)
        if decision == 'ask':
            try:
                decision = await classify_pending_intent(pending, question)
            except Exception:
                logger.exception("Classification de sujet Aria")
                decision = 'switch'
        if decision == 'switch':
            await self._clear_pending(silent=True)
            return False

        if name == 'choisir_classe':
            await self._run_guarded(lambda: self._open_classe_from_reply(question))
            return True
        if name in ('annonce_guidee', 'creer_publier_annonce'):
            await self._run_guarded(lambda: self._continue_annonce_guidee(question))
            return True
        if name in ('creer_emploi_du_temps', 'ajouter_creneau_emploi'):
            await self._run_guarded(lambda: self._continue_emploi_guidee(question))
            return True
        if name in ACTION_SPECS:
            await self._run_guarded(lambda: self._continue_generic_action(question))
            return True
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
        from school_admin.services.assistant_tools import list_classe_choices

        return list_classe_choices(ctx)

    async def _open_classe_from_reply(self, question):
        ctx = await self._build_context()
        result = await self._execute_tool(
            ctx, 'ouvrir_classe', {'query': question, 'ouvrir': True}
        )
        await self._dispatch_navigation('ouvrir_classe', result)
        if is_lookup_clarification(result):
            spoken = "Je n’ai pas trouvé la classe exacte. Voici les plus proches."
            if result.get('statut') == 'plusieurs':
                spoken = "Plusieurs classes correspondent. Laquelle voulez-vous ?"
            choices = choices_from_class_lookup(result, intent='open')
            await self._speak_and_finish(user_text=question, spoken=spoken, choices=choices)
            return
        self.pending_action = None
        await self._persist_pending()
        spoken = f"J’ouvre la classe {result.get('nom') or question}."
        await self._speak_and_finish(user_text=question, spoken=spoken)

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

    def _choices_for_annonce_fields(self):
        return [
            {'label': 'Le titre', 'value': 'Modifie le titre.', 'intent': 'chat'},
            {'label': 'Le texte', 'value': 'Modifie le texte.', 'intent': 'chat'},
            {'label': 'Les destinataires', 'value': 'Change les destinataires.', 'intent': 'chat'},
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
        if self.pending_action and self.pending_action.get('name') in ACTION_SPECS:
            draft = self.pending_action.get('draft') or {}
            if is_action_ready(draft):
                return choices_for_action(self.pending_action['name'], draft)
            return []
        if self.pending_action and self.pending_action.get('name') == 'choisir_classe':
            return self.pending_action.get('choices') or []
        if self.pending_action:
            return []
        text = spoken or ''
        if self.pending_action and re.search(
            r"c['’ ]est bon|je publie|confirme|valider|avant publication",
            text,
            re.I,
        ):
            return []
        if re.search(r'\?$', text.strip()) and re.search(
            r'\b(?:souhaitez[- ]vous|voulez[- ]vous|c["’]est bon)\b',
            text,
            re.I,
        ):
            return [
                {'label': 'Oui', 'value': 'Oui.', 'intent': 'chat'},
                {'label': 'Non', 'value': 'Non.', 'intent': 'chat'},
            ]
        return []

    def _next_annonce_prompt(self):
        draft = (self.pending_action or {}).get('draft') or {}
        if not draft.get('titre') and not draft.get('contenu'):
            return "Sur quel sujet souhaitez-vous communiquer ?"
        if not draft.get('contenu'):
            return "Quel message souhaitez-vous faire passer ?"
        if not draft.get('destinataires'):
            return (
                "Qui doit recevoir cette annonce : tout le monde, les enseignants, "
                "les parents ou les élèves ?"
            )
        from school_admin.services.assistant_tools import _destinataires_libelle

        dest = _destinataires_libelle(draft.get('destinataires') or ['tous'])
        return (
            f"Voici le projet. Titre : {draft.get('titre')}. "
            f"Destinataires : {dest}. "
            "C’est bon, ou souhaitez-vous modifier quelque chose avant publication ?"
        )

    def _needs_written_draft(self, text, draft):
        if is_affirmative(text) or is_cancel(text):
            return False
        if is_vague_annonce_modify(text) or annonce_field_request(text):
            return False
        if WRITE_SPEC_RE.search(text or ''):
            return True
        if wants_modify(text) and (draft.get('contenu') or draft.get('titre')):
            return True
        if not draft.get('contenu') and len((text or '').strip()) < 90:
            return True
        return False

    async def _fill_annonce_from_instruction(self, question, draft):
        ctx = await self._build_context()
        generated = await generate_written_draft(ctx, question, current=draft)
        if generated.get('titre'):
            draft['titre'] = generated['titre'][:255]
        if generated.get('contenu'):
            draft['contenu'] = generated['contenu'][:WRITTEN_DRAFT_MAX]
        return draft

    async def _start_annonce_guidee(self, question, draft=None):
        from django.urls import reverse

        data = draft or {}
        current = {
            'titre': (data.get('titre') or '').strip()[:255],
            'contenu': (data.get('contenu') or '').strip()[:WRITTEN_DRAFT_MAX],
            'destinataires': data.get('destinataires'),
            'publier': True,
        }
        leftover_topic = ANNONCE_CREATE_RE.sub('', question or '').strip(' .!?:,')
        should_draft = bool(
            current['titre']
            or current['contenu']
            or len(leftover_topic) > 8
            or WRITE_SPEC_RE.search(question or '')
        )
        if should_draft and (
            not current['titre'] or not current['contenu'] or WRITE_SPEC_RE.search(question or '')
        ):
            try:
                current = await self._fill_annonce_from_instruction(question, current)
            except Exception:
                logger.exception("Impossible de rédiger le brouillon d’annonce.")
        if current.get('titre') and current.get('contenu') and not current.get('destinataires'):
            current['destinataires'] = ['tous']
        self.pending_action = {
            'name': 'annonce_guidee',
            'draft': current,
        }
        await self._send_json({
            'type': 'navigate',
            'url': reverse('directeur:creer_annonce'),
            'titre': 'Créer une annonce',
            'immediate': True,
        })
        await self._send_annonce_form_fill()
        if self._annonce_ready():
            await self._set_pending(self.pending_action['draft'])
            self.pending_action['name'] = 'annonce_guidee'
        await self._persist_pending()
        spoken = "J’ouvre le formulaire d’annonce. " + self._next_annonce_prompt()
        await self._speak_and_finish(
            user_text=question,
            spoken=spoken,
            choices=self._choices_for_annonce(),
        )

    async def _continue_annonce_guidee(self, question):
        draft = dict((self.pending_action or {}).get('draft') or {})
        text = (question or '').strip()
        field = annonce_field_request(text)
        if is_vague_annonce_modify(text) and not field:
            await self._speak_and_finish(
                user_text=question,
                spoken="Que souhaitez-vous modifier : le titre, le texte ou les destinataires ?",
                choices=self._choices_for_annonce_fields(),
            )
            return
        if field:
            draft['edit_field'] = field
            if field == 'destinataires':
                draft['destinataires'] = None
                draft['destinataires_libelle'] = ''
            self.pending_action['draft'] = draft
            await self._persist_pending()
            if field == 'titre':
                spoken = "Quel nouveau titre souhaitez-vous ?"
                choices = []
            elif field == 'contenu':
                spoken = (
                    "Quel nouveau texte souhaitez-vous ? Indiquez aussi le format "
                    "si besoin, par exemple deux paragraphes."
                )
                choices = []
            else:
                spoken = "Qui doit recevoir cette annonce ?"
                choices = self._choices_for_annonce()
            await self._speak_and_finish(
                user_text=question,
                spoken=spoken,
                choices=choices,
            )
            return

        focus = draft.get('edit_field')
        dests = infer_destinataires(text)
        if focus == 'titre':
            if self._needs_written_draft(text, draft):
                try:
                    generated = await self._fill_annonce_from_instruction(text, draft)
                    draft['titre'] = (generated.get('titre') or text)[:255]
                except Exception:
                    logger.exception("Impossible d’ajuster le titre d’annonce.")
                    draft['titre'] = text[:255]
            else:
                draft['titre'] = text[:255]
            draft.pop('edit_field', None)
        elif focus == 'contenu':
            if self._needs_written_draft(text, draft):
                try:
                    draft = await self._fill_annonce_from_instruction(text, draft)
                except Exception:
                    logger.exception("Impossible d’ajuster le texte d’annonce.")
                    draft['contenu'] = text[:WRITTEN_DRAFT_MAX]
            else:
                draft['contenu'] = text[:WRITTEN_DRAFT_MAX]
            draft.pop('edit_field', None)
        elif dests and (
            focus == 'destinataires'
            or not draft.get('destinataires')
            or 'destinataire' in text.lower()
        ):
            draft['destinataires'] = dests
            draft.pop('edit_field', None)
        elif focus == 'destinataires':
            await self._speak_and_finish(
                user_text=question,
                spoken="Qui doit recevoir cette annonce : tout le monde, les enseignants, les parents ou les élèves ?",
                choices=self._choices_for_annonce(),
            )
            return
        elif self._needs_written_draft(text, draft):
            try:
                draft = await self._fill_annonce_from_instruction(text, draft)
            except Exception:
                logger.exception("Impossible d’ajuster le brouillon d’annonce.")
                if not draft.get('contenu'):
                    draft['contenu'] = text[:WRITTEN_DRAFT_MAX]
                elif not draft.get('titre'):
                    draft['titre'] = text[:255]
        elif not draft.get('titre'):
            draft['titre'] = text[:255]
        elif not draft.get('contenu'):
            draft['contenu'] = text[:WRITTEN_DRAFT_MAX]
        elif not draft.get('destinataires'):
            draft['destinataires'] = dests or ['tous']
        elif self._annonce_ready():
            if len(text) <= 80:
                draft['titre'] = text[:255]
            else:
                draft['contenu'] = text[:WRITTEN_DRAFT_MAX]
        if draft.get('contenu'):
            draft['contenu'] = draft['contenu'][:WRITTEN_DRAFT_MAX]
        self.pending_action['draft'] = draft
        await self._send_annonce_form_fill()
        if self._annonce_ready():
            await self._set_pending(draft)
            self.pending_action['name'] = 'annonce_guidee'
        await self._persist_pending()
        await self._speak_and_finish(
            user_text=question,
            spoken=self._next_annonce_prompt(),
            choices=self._choices_for_annonce(),
        )

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
        await self._send_json({
            'type': 'action.pending',
            'action': name,
            'titre': draft.get('nom') or draft.get('resume') or name.replace('_', ' '),
            'contenu': default_prompt(draft),
            'destructive': bool(draft.get('destructive')),
            'choices': choices_for_action(name, draft),
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

    async def _navigate_emploi(self, url, titre):
        if not url:
            return
        await self._send_json({
            'type': 'navigate',
            'url': url,
            'titre': titre or 'Emploi du temps',
        })

    async def _start_emploi_guidee(self, question, draft=None):
        ctx = await self._build_context()
        data = await database_sync_to_async(enrich_emploi_draft)(ctx, draft or {})
        if data.get('suggestions_possibles') or data.get('plusieurs_classes'):
            data['choices'] = choices_from_class_lookup(data)
        elif not data.get('classe') and data.get('statut') == 'incomplet':
            data['choices'] = await database_sync_to_async(_classe_choices)(ctx)
        self.pending_action = {
            'name': 'creer_emploi_du_temps',
            'draft': data,
        }
        await self._persist_pending()
        if data.get('url'):
            await self._navigate_emploi(data['url'], data.get('classe'))
        spoken = next_emploi_prompt(data)
        choices = data.get('choices') or self._choices_for_emploi_action()
        await self._speak_and_finish(user_text=question, spoken=spoken, choices=choices)

    async def _start_creneau_guidee(self, question, draft=None):
        ctx = await self._build_context()
        data = await database_sync_to_async(enrich_creneau_draft)(ctx, draft or {})
        if data.get('suggestions_possibles') or data.get('plusieurs_classes'):
            data['choices'] = choices_from_class_lookup(data)
        elif not data.get('classe') and data.get('statut') == 'incomplet':
            data['choices'] = await database_sync_to_async(_classe_choices)(ctx)
        self.pending_action = {
            'name': 'ajouter_creneau_emploi',
            'draft': data,
        }
        await self._persist_pending()
        if data.get('url'):
            await self._navigate_emploi(data['url'], data.get('classe'))
        spoken = next_creneau_prompt(data)
        choices = data.get('choices') or self._choices_for_emploi_action()
        await self._speak_and_finish(user_text=question, spoken=spoken, choices=choices)

    async def _continue_emploi_guidee(self, question):
        pending = self.pending_action or {}
        name = pending.get('name')
        draft = dict(pending.get('draft') or {})
        text = (question or '').strip()
        if name == 'creer_emploi_du_temps' and (
            CRENEAU_ADD_RE.search(text) or re.search(r'cr[ée]neau|cours', text, re.I)
        ):
            merged = extract_creneau_draft(text)
            if draft.get('classe') and not merged.get('classe'):
                merged['classe'] = draft['classe']
            await self._start_creneau_guidee(question, merged)
            return
        extracted = (
            extract_creneau_draft(text)
            if name == 'ajouter_creneau_emploi'
            else extract_emploi_draft(text)
        )
        for key, value in extracted.items():
            if key == 'action' or not value:
                continue
            if wants_modify(text) or not draft.get(key):
                draft[key] = value
                if key == 'matiere':
                    draft.pop('matiere_introuvable', None)
                    draft.pop('matiere_id', None)
                if key == 'professeur':
                    draft.pop('professeur_introuvable', None)
                    draft.pop('professeur_id', None)
                if key == 'salle':
                    draft.pop('salle_introuvable', None)
                    draft.pop('salle_id', None)
        if (
            not draft.get('classe')
            and not extracted.get('jour')
            and not extracted.get('heure_debut')
            and not is_affirmative(text)
            and not is_cancel(text)
            and not wants_modify(text)
            and len(text) <= 40
        ):
            draft['classe'] = text
        if name == 'ajouter_creneau_emploi':
            await self._start_creneau_guidee(question, draft)
        else:
            await self._start_emploi_guidee(question, draft)

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
            if name == 'ajouter_creneau_emploi':
                await self._start_creneau_guidee('Confirmer', result)
            else:
                await self._start_emploi_guidee('Confirmer', result)
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

    async def _start_generic_action(self, name, question, result):
        data = dict(result or {})
        if data.get('erreur') and data.get('statut') not in (
            'incomplet',
            'en_attente_confirmation',
        ):
            await self._clear_pending(silent=True)
            await self._send_action_result('error', 'Action échouée', data['erreur'])
            await self._speak_and_finish(user_text=question, spoken=data['erreur'])
            return
        self.pending_action = {'name': name, 'draft': data}
        await self._persist_pending()
        if data.get('url') and data.get('ouvrir'):
            await self._send_json({
                'type': 'navigate',
                'url': data['url'],
                'titre': data.get('resume') or data.get('nom') or '',
            })
        spoken = data.get('message') or default_prompt(data)
        if data.get('auto_appliquer') and data.get('statut') == 'en_attente_confirmation':
            await self._confirm_generic_action()
            return
        if data.get('statut') == 'en_attente_confirmation':
            spoken = default_prompt(data)
        elif data.get('statut') == 'ok' and not data.get('erreur'):
            await self._clear_pending(silent=True)
            await self._send_action_result(
                'success',
                'Action réalisée',
                data.get('message') or 'C’est déjà fait.',
                url=data.get('url'),
            )
            spoken = data.get('message') or spoken
            await self._speak_and_finish(user_text=question, spoken=spoken)
            return
        choices = choices_for_action(name, data)
        if is_action_ready(data):
            await self._send_generic_pending_ui(name, data)
        await self._speak_and_finish(user_text=question, spoken=spoken, choices=choices)

    async def _continue_generic_action(self, question):
        pending = self.pending_action or {}
        name = pending.get('name')
        draft = dict(pending.get('draft') or {})
        text = (question or '').strip()
        if is_affirmative(text) and is_action_ready(draft):
            await self._confirm_generic_action()
            return
        manquants = list(draft.get('manquants') or [])
        if manquants:
            draft[manquants[0]] = text
        else:
            draft['query'] = text
        other = resolve_action_intent(text)
        if other and other[0] == name:
            draft.update(other[1])
        result = await self._execute_tool(await self._build_context(), name, draft)
        await self._start_generic_action(name, question, result)

    async def _confirm_generic_action(self):
        pending = self.pending_action or {}
        name = pending.get('name')
        draft = dict(pending.get('draft') or {})
        spec = ACTION_SPECS.get(name)
        if not spec or not spec.apply:
            await self._send_action_result(
                'error',
                'Action échouée',
                'Aucune action n’était en attente de confirmation.',
            )
            await self._send_json({'type': 'done'})
            return
        if not is_action_ready(draft):
            await self._continue_generic_action('Confirmer')
            return
        ctx = await self._build_context()
        result = await database_sync_to_async(spec.apply)(ctx, draft)
        if result.get('statut') == 'incomplet' or (
            result.get('erreur') and result.get('manquants')
        ):
            await self._start_generic_action(name, 'Confirmer', result)
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
        if pending and pending.get('name') in ACTION_SPECS:
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

    async def _speak_and_finish(self, user_text, spoken, choices=None):
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
        pending_tts = [
            (sentence, self._track_tts(asyncio.create_task(synthesize_audio(sentence))))
            for sentence in sentences
        ]
        await self._flush_tts_queue(pending_tts)
        if self._cancel_requested:
            return
        if spoken:
            self.history.append({'role': 'user', 'content': user_text})
            self.history.append({'role': 'assistant', 'content': spoken})
            overflow = len(self.history) - MAX_HISTORY_MESSAGES
            if overflow > 0:
                self.history = self.history[overflow:]
        await self._send_choices(choices if choices is not None else self._infer_choices(spoken))
        await self._send_json({'type': 'done'})

    @database_sync_to_async
    def _apply_annonce(self, ctx, draft):
        from school_admin.services.assistant_tools import apply_annonce_draft

        return apply_annonce_draft(ctx, draft)
