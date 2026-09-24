"""
Elv3 — Wolof v1 (STT/TTS/chips) pour persona élève.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from school_admin.services.assistant_eleve_tools import execute_eleve_tool
from school_admin.services.assistant_parent_language import (
    SESSION_LANG_KEY_ELEVE,
    detect_text_language,
    normalize_lang_preference,
    pick_best_stt_transcript,
    resolve_tts_language,
    wolof_marker_score,
)


class AssistantEleveLanguageTests(SimpleTestCase):
    def test_session_key_eleve_distinct(self):
        self.assertEqual(SESSION_LANG_KEY_ELEVE, 'aria_eleve_lang')

    def test_detect_wolof_eleve(self):
        self.assertEqual(
            detect_text_language('Na nga def? Wax ma ci sama devoir yi.'),
            'wo',
        )

    def test_resolve_tts_wolof(self):
        self.assertEqual(
            resolve_tts_language('Waaw, dama la dimbali.', preference='auto'),
            'wo',
        )

    def test_pick_stt_wolof(self):
        _text, locale, weak = pick_best_stt_transcript({
            'fr-FR': 'hello',
            'wo-SN': 'Na nga def',
        })
        self.assertEqual(locale, 'wo-SN')
        self.assertFalse(weak)

    def test_wolof_query_bloque_tool_directeur(self):
        ctx = type('Ctx', (), {
            'persona': 'eleve',
            'eleve': type('E', (), {'pk': 1, 'actif': True, 'etablissement': None})(),
        })()
        out = execute_eleve_tool(ctx, 'get_effectifs', {})
        self.assertEqual(out.get('statut'), 'hors_perimetre')

    def test_normalize_pref(self):
        self.assertEqual(normalize_lang_preference('wolof'), 'wo')

    def test_wolof_marker_score(self):
        self.assertGreater(wolof_marker_score('Jërëjëf, wax ma ci notes yi'), 0)
