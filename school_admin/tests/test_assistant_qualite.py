"""
Qualité assistant — Vagues A+B (voix, sujet) et C+D (Gemini, polish).
"""
import asyncio
from unittest.mock import AsyncMock, patch

from django.test import SimpleTestCase

from school_admin.consumers.assistant_consumer import (
    MAX_TTS_SEGMENT_CHARS,
    MIN_TTS_CLAUSE_CHARS,
    SentenceAssembler,
    is_affirmative,
    is_cancel,
    is_pending_modify,
)
from school_admin.services.assistant_intents import (
    METIER_SWITCH_RE,
    NEW_QUESTION_RE,
    decide_pending_reply,
    is_explicit_navigation,
    is_navigation_only,
    is_obvious_pending_continue,
    looks_like_new_topic,
)
from school_admin.services.gemini_assistant_service import (
    CONVERSATION_TEMPERATURE,
    MAX_TOOL_ROUNDS,
    SYSTEM_PROMPT_STATIC,
    TOOL_TEMPERATURE,
    compact_tool_memory,
    format_turn_telemetry,
    extract_working_refs,
    format_cited_refs,
    _dialog_to_gemini_contents,
    _emit_spoken_fallback,
    _run_assistant_turn_cached,
    _stream_cached_round,
)
from school_admin.services.gemini_context_cache import CACHE_DISPLAY_NAME
from school_admin.services.tts_service import synthesize_audio


def _pending_edt():
    return {
        'name': 'creer_emploi_du_temps',
        'draft': {
            'statut': 'incomplet',
            'classe': '1ère S',
            'manquants': ['jour', 'heure'],
        },
    }


class SentenceAssemblerTests(SimpleTestCase):
    def test_phrase_courte_reste_entiere(self):
        assembler = SentenceAssembler()
        parts = assembler.feed('Bonjour. ')
        leftover = assembler.flush()
        self.assertEqual(parts, ['Bonjour.'])
        self.assertEqual(leftover, '')

    def test_decoupe_vers_120_150_caracteres(self):
        chunk = (
            "L’établissement compte cent vingt élèves répartis en huit classes "
            "actives cette année, avec une légère majorité de filles et des "
            "effectifs stables depuis septembre. "
        )
        self.assertGreater(len(chunk), MAX_TTS_SEGMENT_CHARS)
        assembler = SentenceAssembler()
        parts = assembler.feed(chunk)
        leftover = assembler.flush()
        if leftover:
            parts = [*parts, leftover]
        self.assertGreaterEqual(len(parts), 2)
        for part in parts[:-1]:
            self.assertLessEqual(len(part), MAX_TTS_SEGMENT_CHARS)
            self.assertGreaterEqual(len(part), 40)
        self.assertLessEqual(max(len(part) for part in parts), MAX_TTS_SEGMENT_CHARS)
        self.assertEqual(MIN_TTS_CLAUSE_CHARS, 120)

    def test_force_cut_sur_texte_sans_ponctuation(self):
        words = ' '.join(['élève'] * 40)
        self.assertGreater(len(words), MAX_TTS_SEGMENT_CHARS)
        assembler = SentenceAssembler()
        parts = assembler.feed(words)
        leftover = assembler.flush()
        if leftover:
            parts = [*parts, leftover]
        self.assertGreaterEqual(len(parts), 2)
        self.assertTrue(all(len(part) <= MAX_TTS_SEGMENT_CHARS for part in parts))


class TopicSwitchQualiteTests(SimpleTestCase):
    def test_effectifs_pendant_edt_est_un_switch(self):
        pending = _pending_edt()
        self.assertEqual(
            decide_pending_reply('quels sont les effectifs ?', pending),
            'switch',
        )
        self.assertEqual(
            decide_pending_reply('donne-moi les effectifs', pending),
            'switch',
        )
        self.assertEqual(
            decide_pending_reply('liste les impayés', pending),
            'switch',
        )
        self.assertEqual(
            decide_pending_reply('affiche le taux de présence', pending),
            'switch',
        )

    def test_reponse_edt_reste_continue(self):
        pending = _pending_edt()
        self.assertEqual(decide_pending_reply('lundi', pending), 'continue')
        self.assertEqual(decide_pending_reply('8h-10h', pending), 'continue')
        self.assertEqual(decide_pending_reply('3e A', pending), 'continue')

    def test_new_question_et_metier_elargis(self):
        self.assertTrue(NEW_QUESTION_RE.search('donne-moi les effectifs'))
        self.assertTrue(NEW_QUESTION_RE.search('liste les impayés'))
        self.assertTrue(NEW_QUESTION_RE.search('affiche le tableau de bord'))
        self.assertTrue(METIER_SWITCH_RE.search('fiche de scolarité de Diallo'))
        self.assertTrue(looks_like_new_topic('quels sont les effectifs ?'))
        self.assertTrue(looks_like_new_topic('autre chose'))
        self.assertFalse(looks_like_new_topic('lundi matin'))

    def test_reconnect_droppe_si_pas_oui_non(self):
        self.assertFalse(is_affirmative('quels sont les effectifs ?'))
        self.assertFalse(is_cancel('quels sont les effectifs ?'))
        self.assertTrue(is_affirmative('oui'))
        self.assertTrue(is_cancel('annule'))


class TtsFallbackQualiteTests(SimpleTestCase):
    def test_gemini_vide_bascule_sur_edge(self):
        async def _run():
            with patch(
                'school_admin.services.tts_service._synthesize_gemini',
                new=AsyncMock(return_value=(None, None)),
            ), patch(
                'school_admin.services.tts_service._synthesize_edge_mp3',
                new=AsyncMock(return_value=(b'EDGE-AUDIO', 'audio/mpeg')),
            ) as edge:
                audio, mime = await synthesize_audio('Bonjour le directeur.')
            edge.assert_awaited_once()
            self.assertEqual(audio, b'EDGE-AUDIO')
            self.assertEqual(mime, 'audio/mpeg')

        asyncio.run(_run())

    def test_flush_synthetise_une_phrase_a_la_fois(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        async def _run():
            consumer = AssistantConsumer()
            consumer._cancel_requested = False
            consumer._tts_tasks = []
            consumer._tts_index = 0
            consumer._opener_emitted = True
            consumer._opener_task = None
            concurrent = 0
            max_concurrent = 0

            async def fake_synth(_text):
                nonlocal concurrent, max_concurrent
                concurrent += 1
                max_concurrent = max(max_concurrent, concurrent)
                await asyncio.sleep(0.02)
                concurrent -= 1
                return b'WAV', 'audio/wav'

            sent = []

            async def fake_send(payload):
                sent.append(payload)

            consumer._send_json = fake_send
            with patch(
                'school_admin.consumers.assistant_consumer.synthesize_audio',
                new=fake_synth,
            ):
                await consumer._flush_tts_queue(['Phrase une.', 'Phrase deux.', 'Phrase trois.'])
            self.assertEqual(max_concurrent, 1)
            self.assertEqual(len(sent), 3)
            self.assertTrue(all(item.get('audio_base64') for item in sent))
            self.assertTrue(all(item.get('voice_failed') is False for item in sent))

        asyncio.run(_run())


class QualiteCGeminiTests(SimpleTestCase):
    def test_cache_prompt_v10(self):
        self.assertEqual(CACHE_DISPLAY_NAME, 'aria-directeur-tools-v13')

    def test_navigation_explicite_seulement(self):
        self.assertTrue(is_explicit_navigation('Ouvre le tableau de bord'))
        self.assertTrue(is_explicit_navigation('Va sur les classes'))
        self.assertFalse(is_explicit_navigation('affiche les effectifs'))
        self.assertFalse(is_explicit_navigation('Crée un emploi du temps pour la 1ère S'))
        self.assertFalse(is_explicit_navigation('quels sont les effectifs ?'))
        self.assertTrue(is_navigation_only('Ouvre le tableau de bord'))
        self.assertTrue(is_navigation_only('Ouvre la classe 3e A'))
        self.assertFalse(is_navigation_only('Ouvre la 6e A et dis-moi les notes'))
        self.assertFalse(is_navigation_only('Ouvre la 6e A et les impayés'))
        self.assertFalse(is_navigation_only('affiche les effectifs'))

    def test_continue_evident_sans_gemini(self):
        pending = _pending_edt()
        self.assertTrue(is_obvious_pending_continue('lundi', pending))
        self.assertTrue(is_obvious_pending_continue('8h-10h', pending))
        self.assertFalse(is_obvious_pending_continue('quels sont les effectifs ?', pending))
        self.assertFalse(
            is_obvious_pending_continue('donne-moi les notes de la 1ère S', pending)
        )

    def test_memoire_outil_compacte(self):
        memory = compact_tool_memory(
            'get_effectifs',
            {
                'nb_eleves_actifs': 120,
                'nb_classes': 8,
                'session': '2026-2027',
                'liste_complete': ['x'] * 40,
            },
        )
        self.assertIn('get_effectifs', memory)
        self.assertIn('nb_eleves_actifs=120', memory)
        self.assertIn('nb_classes=8', memory)
        self.assertNotIn('liste_complete', memory)
        self.assertLessEqual(len(memory), 400)

    def test_overlay_sans_faux_tour_contexte_recu(self):
        class FakeCtx:
            persona = 'directeur'

        with patch(
            'school_admin.services.gemini_assistant_service._context_overlay',
            return_value='SNAPSHOT-JSON',
        ):
            contents = _dialog_to_gemini_contents(
                FakeCtx(),
                [
                    {'role': 'user', 'content': 'bonjour'},
                    {'role': 'assistant', 'content': 'salut'},
                    {'role': 'user', 'content': 'les effectifs'},
                ],
                tool_memory='get_effectifs, nb_eleves=12',
            )
        texts = []
        for item in contents:
            for part in item.parts:
                texts.append(getattr(part, 'text', '') or '')
        joined = '\n'.join(texts)
        self.assertNotIn('Contexte reçu', joined)
        self.assertIn('SNAPSHOT-JSON', texts[-1])
        self.assertIn('get_effectifs', texts[-1])
        self.assertIn('les effectifs', texts[-1])
        self.assertEqual(texts[0], 'bonjour')

    def test_stream_cache_emet_les_deltas(self):
        class Chunk:
            def __init__(self, text):
                self.text = text
                self.function_calls = []
                self.candidates = []
                self.usage_metadata = None

        class DummyModels:
            async def generate_content_stream(self, **_kwargs):
                async def gen():
                    yield Chunk('Un ')
                    yield Chunk('deux.')

                return gen()

        class DummyClient:
            def __init__(self):
                self.aio = type('Aio', (), {'models': DummyModels()})()

        async def _run():
            deltas = []

            async def on_delta(piece):
                deltas.append(piece)

            _response, calls, spoken = await _stream_cached_round(
                DummyClient(),
                'model',
                'cache',
                [],
                0.5,
                on_delta,
            )
            self.assertEqual(calls, [])
            self.assertEqual(spoken, 'Un deux.')
            self.assertEqual(deltas, ['Un ', 'deux.'])

        asyncio.run(_run())


class PostToolErrorTests(SimpleTestCase):
    def test_json_safe_tool_result_serialise_date_et_decimal(self):
        from datetime import date
        from decimal import Decimal

        from school_admin.services.assistant_tools import json_safe_tool_result

        safe = json_safe_tool_result({
            'quand': date(2026, 9, 23),
            'montant': Decimal('10.50'),
        })
        self.assertEqual(safe['quand'], '2026-09-23')
        self.assertEqual(safe['montant'], '10.50')

    def test_spoken_from_tool_liste_les_noms(self):
        from school_admin.services.assistant_tools import spoken_from_tool_result

        eleves = spoken_from_tool_result(
            'chercher_en_base',
            {
                'source': 'eleves',
                'nb_trouves': 2,
                'eleves': [{'nom': 'Diallo Awa'}, {'nom': 'Ndiaye Moussa'}],
            },
        )
        self.assertIn('Diallo Awa', eleves)
        self.assertIn('Ndiaye Moussa', eleves)
        profs = spoken_from_tool_result(
            'chercher_en_base',
            {
                'source': 'professeurs',
                'professeurs': [{'nom': 'Sow Fatou'}],
            },
        )
        self.assertIn('Sow Fatou', profs)

    def test_chercher_eleves_avant_classe(self):
        from school_admin.services.assistant_tools import tool_chercher_en_base

        class FakeCtx:
            est_superieur = False
            est_college_lycee = False
            est_primaire = False

        with patch(
            'school_admin.services.assistant_tools.tool_rechercher_eleves',
            return_value={'eleves': [{'nom': 'A'}], 'nb_trouves': 1},
        ) as eleves, patch(
            'school_admin.services.assistant_tools.tool_rechercher_classes',
        ) as classes:
            result = tool_chercher_en_base(
                FakeCtx(),
                {'question': 'cite-moi les 10 élèves des deux premières classes'},
            )
        eleves.assert_called_once()
        classes.assert_not_called()
        self.assertEqual(result.get('source'), 'eleves')
        self.assertIn('A', result['eleves'][0]['nom'])


class GeminiG1TakeoverTests(SimpleTestCase):
    """G1 : un tool d’écriture n’arrête plus Gemini ; carte oui/non sans apply."""

    def _consumer(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        consumer = AssistantConsumer()
        consumer.scope = {}
        consumer.persona = 'directeur'
        consumer.pending_action = None
        consumer._last_tool_memory = ''
        consumer._followup_choices = []
        sent = []

        async def fake_send(payload):
            sent.append(payload)

        consumer._send_json = fake_send
        consumer._persist_pending = AsyncMock()
        return consumer, sent

    def test_prepare_classe_ne_stoppe_pas_et_affiche_la_carte(self):
        async def _run():
            consumer, sent = self._consumer()
            should_stop = await consumer._on_live_tool_result(
                'creer_classe',
                {
                    'statut': 'en_attente_confirmation',
                    'resume': 'créer la classe 3e A',
                    'nom': '3e A',
                    'message': 'Je m’apprête à créer la classe 3e A.',
                },
            )
            self.assertFalse(should_stop)
            self.assertEqual(consumer.pending_action['name'], 'creer_classe')
            self.assertEqual(
                consumer.pending_action['draft']['statut'],
                'en_attente_confirmation',
            )
            types = [item.get('type') for item in sent]
            self.assertIn('action.pending', types)
            self.assertNotIn('text_delta', types)
            self.assertNotIn('done', types)
            self.assertFalse(any(item.get('type') == 'action.result' for item in sent))

        asyncio.run(_run())

    def test_incomplet_pas_de_carte_confirmation(self):
        async def _run():
            consumer, sent = self._consumer()
            should_stop = await consumer._on_live_tool_result(
                'donner_sanction',
                {
                    'statut': 'incomplet',
                    'manquants': ['type_sanction'],
                    'message': 'Quel type de sanction ?',
                    'nom': 'Diallo',
                },
            )
            self.assertFalse(should_stop)
            self.assertEqual(consumer.pending_action['name'], 'donner_sanction')
            self.assertNotIn(
                'action.pending',
                [item.get('type') for item in sent],
            )

        asyncio.run(_run())

    def test_erreur_dure_laisse_gemini_parler(self):
        async def _run():
            consumer, sent = self._consumer()
            should_stop = await consumer._on_live_tool_result(
                'creer_classe',
                {'erreur': 'Cette classe existe déjà.', 'statut': 'erreur'},
            )
            self.assertFalse(should_stop)
            self.assertIsNone(consumer.pending_action)
            result = next(item for item in sent if item.get('type') == 'action.result')
            self.assertEqual(result['status'], 'error')

        asyncio.run(_run())

    def test_lecture_ne_cree_pas_de_pending(self):
        async def _run():
            consumer, sent = self._consumer()
            should_stop = await consumer._on_live_tool_result(
                'get_effectifs',
                {'nb_eleves_actifs': 12, 'source': 'effectifs'},
            )
            self.assertFalse(should_stop)
            self.assertIsNone(consumer.pending_action)
            self.assertEqual(sent, [])

        asyncio.run(_run())

    def test_annonce_carte_sans_wizard(self):
        async def _run():
            consumer, sent = self._consumer()
            should_stop = await consumer._on_live_tool_result(
                'creer_publier_annonce',
                {
                    'statut': 'en_attente_confirmation',
                    'titre': 'Réunion',
                    'contenu': 'Réunion des parents vendredi.',
                    'destinataires': ['parents'],
                    'destinataires_libelle': 'Parents',
                    'publier': True,
                },
            )
            self.assertFalse(should_stop)
            self.assertEqual(consumer.pending_action['name'], 'creer_publier_annonce')
            types = [item.get('type') for item in sent]
            self.assertIn('action.pending', types)
            self.assertNotIn('navigate', types)
            self.assertNotIn('form.fill', types)

        asyncio.run(_run())

    def test_prepare_donner_sanction_sans_auto_appliquer(self):
        from types import SimpleNamespace

        from school_admin.services.assistant_dossiers import prepare_donner_sanction

        eleve = SimpleNamespace(
            id=11,
            nom_complet='Diallo Awa',
            classe=SimpleNamespace(id=22, nom='6e A'),
        )
        with patch(
            'school_admin.services.assistant_dossiers._eleves_from_args',
            return_value=([eleve], []),
        ):
            draft = prepare_donner_sanction(
                SimpleNamespace(),
                {
                    'query': 'Diallo',
                    'type_sanction': 'blame',
                    'raison': 'retard',
                    'gravite': 'moyenne',
                },
            )
        self.assertEqual(draft['statut'], 'en_attente_confirmation')
        self.assertFalse(draft.get('auto_appliquer'))
        self.assertIn('Diallo', draft.get('description') or '')

    def test_callback_outil_ne_demande_jamais_larret(self):
        async def _run():
            consumer, _sent = self._consumer()
            for name, result in (
                (
                    'creer_classe',
                    {'statut': 'en_attente_confirmation', 'resume': 'créer 3e A'},
                ),
                (
                    'donner_sanction',
                    {'statut': 'incomplet', 'manquants': ['type_sanction']},
                ),
                ('get_effectifs', {'nb_eleves_actifs': 3}),
                ('creer_classe', {'erreur': 'refus', 'statut': 'erreur'}),
            ):
                self.assertFalse(await consumer._on_live_tool_result(name, result))

        asyncio.run(_run())


class GeminiG2PendingTests(SimpleTestCase):
    """G2 : oui / modifier / annuler seulement ; le reste droppe le pending."""

    def _pending_classe(self):
        return {
            'name': 'creer_classe',
            'draft': {
                'statut': 'en_attente_confirmation',
                'resume': 'créer la classe 3e A',
                'nom': '3e A',
            },
        }

    def _pending_edt(self):
        return {
            'name': 'creer_emploi_du_temps',
            'draft': {
                'statut': 'incomplet',
                'classe': '3e A',
                'classe_id': 4,
                'manquants': ['jour'],
            },
        }

    def _consumer(self, pending):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        consumer = AssistantConsumer()
        consumer.scope = {}
        consumer.persona = 'directeur'
        consumer.pending_action = pending
        consumer._last_tool_memory = ''
        consumer._followup_choices = []
        consumer._socket_fresh = False
        sent = []

        async def fake_send(payload):
            sent.append(payload)

        async def fake_guarded(handler):
            result = handler()
            if asyncio.iscoroutine(result):
                await result

        consumer._send_json = fake_send
        consumer._persist_pending = AsyncMock()
        consumer._confirm_pending = AsyncMock()
        consumer._cancel_pending = AsyncMock()
        consumer._run_guarded = fake_guarded
        return consumer, sent

    def test_detecte_modifier_sans_avaler_un_nouveau_sujet(self):
        self.assertTrue(is_pending_modify('Je veux modifier.'))
        self.assertTrue(is_pending_modify('Modifie le titre'))
        self.assertTrue(is_pending_modify('Change les destinataires'))
        self.assertFalse(is_pending_modify('oui'))
        self.assertFalse(is_pending_modify('annule'))
        self.assertFalse(is_pending_modify('quels sont les effectifs ?'))
        self.assertFalse(is_pending_modify('lundi 8h 10h maths'))
        self.assertFalse(is_pending_modify('ajoute un créneau'))

    def test_oui_confirme_et_garde_le_pending_jusqua_apply(self):
        async def _run():
            consumer, _sent = self._consumer(self._pending_classe())
            consumed = await consumer._route_pending_reply('Oui, c’est bon.')
            self.assertTrue(consumed)
            consumer._confirm_pending.assert_awaited_once()
            consumer._cancel_pending.assert_not_called()
            self.assertIsNotNone(consumer.pending_action)

        asyncio.run(_run())

    def test_annuler_annule(self):
        async def _run():
            consumer, _sent = self._consumer(self._pending_classe())
            consumed = await consumer._route_pending_reply('Annuler.')
            self.assertTrue(consumed)
            consumer._cancel_pending.assert_awaited_once()
            consumer._confirm_pending.assert_not_called()

        asyncio.run(_run())

    def test_modifier_garde_le_pending_pour_gemini(self):
        async def _run():
            consumer, _sent = self._consumer(self._pending_classe())
            consumed = await consumer._route_pending_reply('Je veux modifier.')
            self.assertFalse(consumed)
            self.assertEqual(consumer.pending_action['name'], 'creer_classe')
            consumer._confirm_pending.assert_not_called()
            consumer._cancel_pending.assert_not_called()
            memory = consumer._tool_memory_for_turn()
            self.assertIn('en attente', memory)
            self.assertIn('creer_classe', memory)

        asyncio.run(_run())

    def test_nouvelle_phrase_droppe_le_pending(self):
        async def _run():
            consumer, _sent = self._consumer(self._pending_edt())
            consumed = await consumer._route_pending_reply('quels sont les effectifs ?')
            self.assertFalse(consumed)
            self.assertIsNone(consumer.pending_action)
            consumer._confirm_pending.assert_not_called()

        asyncio.run(_run())

    def test_lundi_n_est_plus_un_wizard_edt(self):
        async def _run():
            consumer, _sent = self._consumer(self._pending_edt())
            consumed = await consumer._route_pending_reply('lundi 8h 10h maths')
            self.assertFalse(consumed)
            self.assertIsNone(consumer.pending_action)
            consumer._confirm_pending.assert_not_called()

        asyncio.run(_run())

    def test_execute_envoie_le_nouveau_sujet_a_gemini(self):
        async def _run():
            consumer, _sent = self._consumer(self._pending_edt())
            consumer._send_working_ack = AsyncMock()
            consumer._ensure_pending_loaded = AsyncMock()
            consumer._handle_chat = AsyncMock()
            await consumer._execute_user_message('quels sont les effectifs ?')
            self.assertIsNone(consumer.pending_action)
            consumer._handle_chat.assert_awaited_once_with('quels sont les effectifs ?')
            consumer._confirm_pending.assert_not_called()

        asyncio.run(_run())


class GeminiG3RegexTests(SimpleTestCase):
    """G3 : plus de regex métier sur le chemin conversation."""

    def test_resolve_action_intent_n_est_plus_importe_par_le_consumer(self):
        import school_admin.consumers.assistant_consumer as consumer_mod
        import inspect

        source = inspect.getsource(consumer_mod)
        self.assertNotIn('resolve_action_intent', source)
        self.assertNotIn('use_tools=not is_small_talk', source)
        self.assertNotIn('_continue_generic_action', source)
        self.assertNotIn('_continue_annonce_guidee', source)
        self.assertNotIn('_continue_emploi_guidee', source)

    def test_nav_plus_consigne_ne_court_circuite_pas_gemini(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        async def _run():
            consumer = AssistantConsumer()
            consumer.scope = {}
            consumer._execute_tool = AsyncMock()
            consumer._speak_and_finish = AsyncMock()
            handled = await consumer._handle_local_intent(
                'Ouvre la 6e A et dis-moi les notes',
                object(),
            )
            self.assertFalse(handled)
            consumer._execute_tool.assert_not_called()
            consumer._speak_and_finish.assert_not_called()

        asyncio.run(_run())

    def test_nav_seule_reste_un_raccourci(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        async def _run():
            consumer = AssistantConsumer()
            consumer.scope = {}
            consumer._execute_tool = AsyncMock(
                return_value={'nom': '3e A', 'url': '/classe/1', 'ouvrir': True},
            )
            consumer._dispatch_navigation = AsyncMock()
            consumer._speak_and_finish = AsyncMock()
            handled = await consumer._handle_local_intent(
                'Ouvre la classe 3e A',
                object(),
            )
            self.assertTrue(handled)
            consumer._execute_tool.assert_awaited_once()
            consumer._speak_and_finish.assert_awaited_once()

        asyncio.run(_run())


class GeminiG4SuggestionTests(SimpleTestCase):
    """G4 : propositions cliquables, pas un « Ouvre… » forcé."""

    def test_normalize_suggestions_borne_a_trois_et_chat_par_defaut(self):
        from school_admin.services.assistant_tools import (
            normalize_suggestions,
            tool_proposer_actions,
        )

        raw = [
            {'label': 'Relancer les familles', 'value': 'Relance les impayés de la 6e A'},
            {'titre': 'Fiche Diallo', 'url': '/eleve/1', 'intent': 'open'},
            {'label': 'Créer un moratoire', 'value': 'Crée un moratoire pour Diallo'},
            {'label': 'Trop', 'value': 'ignore'},
        ]
        cleaned = normalize_suggestions(raw)
        self.assertEqual(len(cleaned), 3)
        self.assertEqual(cleaned[0]['intent'], 'chat')
        self.assertEqual(cleaned[0]['value'], 'Relance les impayés de la 6e A')
        self.assertEqual(cleaned[1]['intent'], 'open')
        self.assertEqual(cleaned[1]['url'], '/eleve/1')
        self.assertNotIn('Ouvre ', cleaned[1]['value'])

        result = tool_proposer_actions(object(), {'suggestions': raw})
        self.assertEqual(result['nb'], 3)
        self.assertEqual(result['suggestions'][0]['label'], 'Relancer les familles')

    def test_open_sans_url_devient_chat(self):
        from school_admin.services.assistant_tools import normalize_suggestions

        cleaned = normalize_suggestions([
            {'label': 'Les effectifs', 'intent': 'open'},
        ])
        self.assertEqual(cleaned[0]['intent'], 'chat')
        self.assertEqual(cleaned[0]['value'], 'Les effectifs')

    def test_infer_choices_ne_invente_plus_oui_non(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        consumer = AssistantConsumer()
        consumer.pending_action = None
        spoken = "Souhaitez-vous que je relance les familles ?"
        self.assertEqual(consumer._infer_choices(spoken), [])

    def test_proposer_actions_ne_stoppe_pas_et_remplit_les_puces(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        async def _run():
            consumer = AssistantConsumer()
            consumer.scope = {}
            consumer.pending_action = None
            consumer._followup_suggestions = []
            consumer._last_tool_memory = ''
            should_stop = await consumer._on_live_tool_result(
                'proposer_actions',
                {
                    'statut': 'ok',
                    'suggestions': [
                        {
                            'label': 'Relancer',
                            'value': 'Relance les impayés',
                            'intent': 'chat',
                        },
                    ],
                },
            )
            self.assertFalse(should_stop)
            self.assertEqual(consumer._followup_suggestions[0]['label'], 'Relancer')
            sent = []

            async def fake_send(payload):
                sent.append(payload)

            consumer._send_json = fake_send
            await consumer._send_suggestions(consumer._followup_suggestions)
            self.assertEqual(sent[0]['type'], 'suggestions')
            self.assertEqual(sent[0]['items'][0]['value'], 'Relance les impayés')
            self.assertNotIn('Ouvre ', sent[0]['items'][0]['value'])

        asyncio.run(_run())

    def test_pas_de_suggestions_si_carte_de_confirmation(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        async def _run():
            consumer = AssistantConsumer()
            consumer.scope = {}
            consumer.pending_action = {
                'name': 'creer_classe',
                'draft': {'statut': 'en_attente_confirmation', 'nom': '3e A'},
            }
            consumer._followup_suggestions = []
            await consumer._on_live_tool_result(
                'proposer_actions',
                {'suggestions': [{'label': 'Autre chose'}]},
            )
            self.assertEqual(consumer._followup_suggestions, [])

        asyncio.run(_run())

    def test_outil_dans_le_schema(self):
        from school_admin.services.assistant_tools import TOOL_HANDLERS, TOOLS_SCHEMA

        names = {
            item['function']['name']
            for item in TOOLS_SCHEMA
            if item.get('function')
        }
        self.assertIn('proposer_actions', names)
        self.assertIn('proposer_actions', TOOL_HANDLERS)


class GeminiG5MultiToolTests(SimpleTestCase):
    """G5 : plusieurs tools dans le même tour, mémoire ids, pas de wizard."""

    def test_plafond_huit_rounds_et_prompt_enchainement(self):
        self.assertEqual(MAX_TOOL_ROUNDS, 8)
        self.assertEqual(CACHE_DISPLAY_NAME, 'aria-directeur-tools-v13')
        folded = ' '.join(SYSTEM_PROMPT_STATIC.split())
        self.assertIn('tools puis UNE', folded)
        self.assertIn('classe_id', folded)
        self.assertIn('eleve_id', folded)
        self.assertIn('relance-le', folded)

    def test_memoire_extrait_ids_et_noms(self):
        memory = compact_tool_memory(
            'get_impayes',
            {
                'nb': 2,
                'perimetre': '3e A',
                'impayes': [
                    {
                        'eleve': 'Diallo Awa',
                        'eleve_id': 11,
                        'classe': '3e A',
                        'classe_id': 4,
                    },
                    {
                        'eleve': 'Ndiaye Moussa',
                        'eleve_id': 12,
                        'classe': '3e A',
                        'classe_id': 4,
                    },
                ],
            },
        )
        self.assertIn('get_impayes', memory)
        self.assertIn('nb=2', memory)
        self.assertIn('Diallo Awa', memory)
        self.assertIn('Ndiaye Moussa', memory)
        self.assertLessEqual(len(memory), 400)

        refs = extract_working_refs(
            'get_impayes',
            {
                'impayes': [
                    {
                        'eleve': 'Diallo Awa',
                        'eleve_id': 11,
                        'classe': '3e A',
                        'classe_id': 4,
                    },
                ],
            },
        )
        self.assertEqual(refs['eleve_id'], 11)
        self.assertEqual(refs['classe_id'], 4)
        self.assertEqual(refs['eleve'], 'Diallo Awa')
        self.assertEqual(refs['classe'], '3e A')
        self.assertIn('eleve_id=11', format_cited_refs(refs))

        ouvrir = compact_tool_memory(
            'ouvrir_classe',
            {'id': 4, 'nom': '3e A', 'url': '/classe/4', 'ouvrir': True},
        )
        self.assertIn('classe_id=4', ouvrir)
        self.assertIn('nom=3e A', ouvrir)
        self.assertEqual(
            extract_working_refs(
                'ouvrir_classe',
                {'id': 4, 'nom': '3e A', 'url': '/classe/4'},
            )['classe_id'],
            4,
        )

    def test_consumer_accumule_les_refs_sur_plusieurs_tools(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        async def _run():
            consumer = AssistantConsumer()
            consumer.scope = {}
            consumer.pending_action = None
            consumer._last_tool_memory = ''
            consumer._working_refs = {}
            consumer._followup_choices = []
            consumer._persist_pending = AsyncMock()
            sent = []

            async def fake_send(payload):
                sent.append(payload)

            consumer._send_json = fake_send
            await consumer._on_live_tool_result(
                'ouvrir_classe',
                {'id': 4, 'nom': '3e A', 'url': '/classe/4', 'ouvrir': True},
            )
            await consumer._on_live_tool_result(
                'get_impayes',
                {
                    'nb': 1,
                    'impayes': [
                        {
                            'eleve': 'Diallo Awa',
                            'eleve_id': 11,
                            'classe': '3e A',
                            'classe_id': 4,
                        },
                    ],
                },
            )
            memory = consumer._tool_memory_for_turn()
            self.assertEqual(consumer._working_refs['classe_id'], 4)
            self.assertEqual(consumer._working_refs['eleve_id'], 11)
            self.assertIn('classe_id=4', memory)
            self.assertIn('eleve_id=11', memory)
            self.assertIn('Diallo', memory)
            self.assertFalse(any(item.get('type') == 'action.pending' for item in sent))

        asyncio.run(_run())

    def test_ecriture_reste_une_carte_sans_stopper(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        async def _run():
            consumer = AssistantConsumer()
            consumer.scope = {}
            consumer.pending_action = None
            consumer._last_tool_memory = ''
            consumer._working_refs = {}
            consumer._followup_choices = []
            consumer._persist_pending = AsyncMock()
            sent = []

            async def fake_send(payload):
                sent.append(payload)

            consumer._send_json = fake_send
            should_stop = await consumer._on_live_tool_result(
                'creer_publier_annonce',
                {
                    'statut': 'en_attente_confirmation',
                    'titre': 'Rentrée 3e A',
                    'contenu': 'Des impayés restent ouverts.',
                    'destinataires': ['parents'],
                    'destinataires_libelle': 'Parents',
                    'publier': True,
                },
            )
            self.assertFalse(should_stop)
            self.assertEqual(consumer.pending_action['name'], 'creer_publier_annonce')
            self.assertIn('action.pending', [item.get('type') for item in sent])

        asyncio.run(_run())

    def test_nav_plus_metier_reste_un_seul_tour_gemini(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        async def _run():
            consumer = AssistantConsumer()
            consumer.scope = {}
            consumer._execute_tool = AsyncMock()
            consumer._speak_and_finish = AsyncMock()
            handled = await consumer._handle_local_intent(
                'Ouvre la 6e A et dis-moi les notes',
                object(),
            )
            self.assertFalse(handled)
            consumer._execute_tool.assert_not_called()

        asyncio.run(_run())

    def test_quatre_tools_passent_l_ancien_plafond_de_trois(self):
        class FakeCtx:
            persona = 'directeur'

        sequence = [
            ('get_effectifs', {'nb_eleves_actifs': 28, 'classe_id': 4, 'classe': '3e A'}),
            ('get_impayes', {
                'nb': 2,
                'impayes': [{'eleve': 'Diallo Awa', 'eleve_id': 11, 'classe_id': 4}],
            }),
            ('ouvrir_classe', {'id': 4, 'nom': '3e A', 'url': '/classe/4'}),
            ('proposer_actions', {
                'suggestions': [{'label': 'Relancer', 'value': 'Relance Diallo'}],
            }),
            None,
        ]
        cursor = {'i': 0}
        executed = []

        async def fake_stream(*_args, **_kwargs):
            item = sequence[cursor['i']]
            cursor['i'] += 1
            if item is None:
                return None, [], 'La 3e A a 28 élèves et 2 impayés.'
            name, _result = item
            call = type('Call', (), {'name': name, 'args': {}})()
            return None, [call], ''

        def fake_execute(_ctx, name, _args):
            executed.append(name)
            for item in sequence:
                if item is None:
                    continue
                tool_name, result = item
                if tool_name == name:
                    return result
            return {}

        async def _run():
            called = []

            async def on_tool(name, _args, _result):
                called.append(name)
                return False

            with patch(
                'school_admin.services.gemini_assistant_service.ensure_tools_cache',
                return_value=('cache-name', 'gemini-model', 12),
            ), patch(
                'school_admin.services.gemini_assistant_service._stream_cached_round',
                new=fake_stream,
            ), patch(
                'school_admin.services.gemini_assistant_service.execute_tool',
                side_effect=fake_execute,
            ), patch(
                'school_admin.services.gemini_assistant_service._context_overlay',
                return_value='SNAPSHOT-JSON',
            ), patch(
                'google.genai.Client',
                return_value=object(),
            ):
                _messages, spoken = await _run_assistant_turn_cached(
                    FakeCtx(),
                    [{'role': 'user', 'content': 'Prépare la 3e A : effectifs et impayés'}],
                    on_tool_result=on_tool,
                )
            self.assertEqual(
                executed,
                ['get_effectifs', 'get_impayes', 'ouvrir_classe', 'proposer_actions'],
            )
            self.assertEqual(called, executed)
            self.assertIn('28 élèves', spoken)
            self.assertGreaterEqual(cursor['i'], 5)
            self.assertGreater(len(executed), 3)

        asyncio.run(_run())


class GeminiG6PromptTests(SimpleTestCase):
    """G6 : prompt d’autonomie, catalogue raccourci, pièges conservés."""

    def test_cache_et_temperatures(self):
        self.assertEqual(CACHE_DISPLAY_NAME, 'aria-directeur-tools-v13')
        self.assertEqual(TOOL_TEMPERATURE, 0.5)
        self.assertEqual(CONVERSATION_TEMPERATURE, 0.7)

    def test_blocs_assistante_et_apres_action(self):
        folded = ' '.join(SYSTEM_PROMPT_STATIC.split())
        self.assertTrue(SYSTEM_PROMPT_STATIC.strip().startswith('Tu es Aria'))
        self.assertIn('Assistante :', SYSTEM_PROMPT_STATIC)
        self.assertIn('Après une action :', SYSTEM_PROMPT_STATIC)
        self.assertIn('Tu n\'es pas un formulaire', folded)
        self.assertIn('Jamais un questionnaire vocal', folded)
        self.assertIn('Confirme clairement', folded)
        self.assertIn('Tu n\'appliques jamais toi-meme', folded.replace('ê', 'e'))
        self.assertIn('carte oui / modifier / annuler', folded)

    def test_catalogue_raccourci_pieges_gardes(self):
        folded = ' '.join(SYSTEM_PROMPT_STATIC.split())
        self.assertNotIn('Autres actions', SYSTEM_PROMPT_STATIC)
        self.assertNotIn('creer_annee_scolaire', SYSTEM_PROMPT_STATIC)
        self.assertNotIn('configurer_moyennes', SYSTEM_PROMPT_STATIC)
        self.assertNotIn('enregistrer_absence_professeur', SYSTEM_PROMPT_STATIC)
        self.assertIn('personnel_administratif', folded)
        self.assertIn('N\'invente pas', folded)
        self.assertIn('ECTS', folded)
        self.assertIn('ouvrir_classe', folded)
        self.assertIn('tools puis UNE', folded)
        self.assertLess(len(SYSTEM_PROMPT_STATIC), 4500)

    def test_addendum_type_sans_inventaire(self):
        from school_admin.services.assistant_schema import prompt_addendum_for

        class Primaire:
            est_primaire = True
            est_superieur = False
            est_college_lycee = False

        class Superieur:
            est_primaire = False
            est_superieur = True
            est_college_lycee = False

        primaire = prompt_addendum_for(Primaire())
        superieur = prompt_addendum_for(Superieur())
        self.assertIn('primaire', primaire.lower())
        self.assertIn('ECTS', primaire)
        self.assertIn('LMD', primaire)
        self.assertNotIn('get_statistiques_pilotage', primaire)
        self.assertNotIn('get_dossier_employe', primaire)
        self.assertIn('N’invente aucun crédit', superieur)
        self.assertIn('niveau LMD', superieur)
        self.assertIn('Comptabilité générale : indisponible', superieur)


class GeminiG7TelemetryTests(SimpleTestCase):
    """G7 : une ligne de tour (tool, rounds, pending, suggestions, takeover)."""

    def test_format_turn_telemetry(self):
        payload = format_turn_telemetry(
            tools=['get_effectifs', ('get_impayes', {})],
            rounds=3,
            pending_shown=True,
            suggestions_count=2,
            takeover=0,
        )
        self.assertEqual(payload['tool'], 'get_effectifs,get_impayes')
        self.assertEqual(payload['rounds'], 3)
        self.assertEqual(payload['pending_shown'], 1)
        self.assertEqual(payload['suggestions_count'], 2)
        self.assertEqual(payload['takeover'], 0)

    def test_ecriture_prend_la_carte_sans_takeover(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        async def _run():
            consumer = AssistantConsumer()
            consumer.scope = {}
            consumer.pending_action = None
            consumer._reset_turn_stats()
            consumer._persist_pending = AsyncMock()
            sent = []

            async def fake_send(payload):
                sent.append(payload)

            consumer._send_json = fake_send
            should_stop = await consumer._on_live_tool_result(
                'creer_publier_annonce',
                {
                    'statut': 'en_attente_confirmation',
                    'titre': 'Rentrée',
                    'contenu': 'Message',
                    'destinataires': ['parents'],
                    'destinataires_libelle': 'Parents',
                    'publier': True,
                },
            )
            self.assertFalse(should_stop)
            self.assertEqual(consumer._turn_stats['takeover'], 0)
            self.assertEqual(consumer._turn_stats['pending_shown'], 1)
            self.assertIn('action.pending', [item.get('type') for item in sent])
            logged = consumer._log_turn_stats()
            self.assertEqual(logged['takeover'], 0)
            self.assertEqual(logged['pending_shown'], 1)

        asyncio.run(_run())

    def test_suggestions_comptees_sans_stopper(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        async def _run():
            consumer = AssistantConsumer()
            consumer.scope = {}
            consumer.pending_action = None
            consumer._reset_turn_stats()
            consumer._followup_suggestions = []
            sent = []

            async def fake_send(payload):
                sent.append(payload)

            consumer._send_json = fake_send
            should_stop = await consumer._on_live_tool_result(
                'proposer_actions',
                {
                    'suggestions': [
                        {'label': 'Relancer', 'value': 'Relance'},
                        {'label': 'Fiche', 'value': 'Ouvre Diallo'},
                    ],
                },
            )
            self.assertFalse(should_stop)
            await consumer._send_suggestions(consumer._followup_suggestions)
            self.assertEqual(consumer._turn_stats['suggestions_count'], 2)
            self.assertEqual(consumer._turn_stats['takeover'], 0)
            self.assertEqual(sent[0]['type'], 'suggestions')

        asyncio.run(_run())

    def test_repli_oral_effectifs_impayes_caisse(self):
        from school_admin.services.assistant_tools import (
            spoken_from_tool_result,
            spoken_from_tool_results,
        )

        effectifs = spoken_from_tool_result(
            'get_effectifs',
            {'nb_eleves_actifs': 42, 'nb_classes': 3, 'nb_professeurs': 8},
        )
        self.assertIn('42', effectifs)
        self.assertIn('3 classes', effectifs)
        impayes = spoken_from_tool_result(
            'get_impayes',
            {'nb': 2, 'perimetre': 'CE1 A', 'total_reste': 15000},
        )
        self.assertIn('2 impayés', impayes)
        self.assertIn('CE1 A', impayes)
        self.assertIn('relancer', impayes)
        caisse = spoken_from_tool_result(
            'get_caisse',
            {'mois': 'septembre 2026', 'entrees': '1000', 'sorties': '200', 'solde': '800', 'devise': 'XAF'},
        )
        self.assertIn('septembre 2026', caisse)
        self.assertIn('800', caisse)
        notes = spoken_from_tool_result(
            'get_notes_classe',
            {'classe': 'CE1 A', 'nb': 4, 'notes': [{}] * 4},
        )
        self.assertIn('4', notes)
        self.assertIn('CE1 A', notes)
        edt = spoken_from_tool_result(
            'get_emploi_du_temps',
            {'classe': '3ème A', 'statut': 'Publié', 'creneaux': [{}, {}]},
        )
        self.assertIn('3ème A', edt)
        self.assertIn('2 créneaux', edt)
        walked = spoken_from_tool_results([
            ('get_effectifs', {'nb_eleves_actifs': 12, 'classe': 'CP A'}),
            ('proposer_actions', {'suggestions': []}),
        ])
        self.assertIn('CP A', walked)
        self.assertIn('12', walked)

    def test_repli_oral_est_streamé_au_client(self):
        deltas = []

        async def _run():
            async def capture(delta):
                deltas.append(delta)

            spoken = await _emit_spoken_fallback(
                capture,
                'L’établissement compte 12 élèves actifs, 3 classes.',
            )
            self.assertIn('12', spoken)
            self.assertEqual(deltas, [spoken])

        asyncio.run(_run())
