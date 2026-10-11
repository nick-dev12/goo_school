"""Notes vocales : transcription Gemini (wolof compris) pour tous les espaces."""
import asyncio
import base64
from unittest.mock import AsyncMock, patch

from django.test import SimpleTestCase

from school_admin.services import stt_service


class TranscriptionNoteVocaleTests(SimpleTestCase):
    def test_repli_web_speech_si_gemini_echoue(self):
        with patch.object(
            stt_service, 'transcribe_with_gemini', new=AsyncMock(return_value=('', 'fr'))
        ), patch.object(
            stt_service, 'transcribe_pcm16', new=AsyncMock(return_value='bonjour aria')
        ):
            text, lang = asyncio.run(stt_service.transcribe_voice_note(b'\x00' * 4000))
        self.assertEqual((text, lang), ('bonjour aria', 'fr'))

    def test_note_trop_courte_ignoree(self):
        self.assertEqual(asyncio.run(stt_service.transcribe_with_gemini(b'\x00' * 100)), ('', 'fr'))

    def test_enseignant_wolof_reconnu_sans_preference_langue(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        consumer = AssistantConsumer()
        consumer.persona = 'enseignant'
        consumer._send_json = AsyncMock()
        b64 = base64.b64encode(b'\x00' * 4000).decode('ascii')
        with patch.object(
            stt_service,
            'transcribe_with_gemini',
            new=AsyncMock(return_value=('Naka la classe bi def ci notes yi ?', 'mixed')),
        ):
            asyncio.run(consumer._handle_stt({'audio_base64': b64}))
        payload = consumer._send_json.call_args[0][0]
        self.assertEqual(payload['type'], 'transcript')
        self.assertEqual(payload['text'], 'Naka la classe bi def ci notes yi ?')
        self.assertEqual(payload['stt_locale'], 'wo-SN')
