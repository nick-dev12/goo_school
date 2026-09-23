"""
Qualité assistant — Vagues A (voix) et B (changement de sujet).
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
)
from school_admin.services.assistant_intents import (
    METIER_SWITCH_RE,
    NEW_QUESTION_RE,
    decide_pending_reply,
    looks_like_new_topic,
)
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
