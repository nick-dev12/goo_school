"""
Smoke Wolof v1 — détection langue, STT, périmètre tools (Par3).
"""
from __future__ import annotations

from django.test import SimpleTestCase

from school_admin.services.assistant_parent_language import (
    detect_text_language,
    normalize_lang_preference,
    pick_best_stt_transcript,
    resolve_tts_language,
    resolve_user_turn_language,
    stt_language_order,
    wolof_marker_score,
)
from school_admin.services.assistant_parent_tools import (
    PARENT_TOOL_NAMES,
    execute_parent_tool,
)


class AssistantParentLanguageTests(SimpleTestCase):
    def test_normalize_preference(self):
        self.assertEqual(normalize_lang_preference('wolof'), 'wo')
        self.assertEqual(normalize_lang_preference('FR'), 'fr')
        self.assertEqual(normalize_lang_preference(''), 'auto')

    def test_detect_wolof_greeting(self):
        self.assertEqual(
            detect_text_language('Na nga def? Wax ma ci xale bi.'),
            'wo',
        )
        self.assertEqual(
            detect_text_language('Bonjour, quelles sont les notes de mon enfant ?'),
            'fr',
        )

    def test_resolve_user_turn_respects_chip_fr(self):
        text = 'Na nga def, wax ma ci notes yi'
        self.assertEqual(resolve_user_turn_language(text, 'fr'), 'fr')

    def test_resolve_tts_wolof_when_response_wolof(self):
        resp = 'Waaw, dama la dimbali. Jëf jëf.'
        self.assertEqual(resolve_tts_language(resp, preference='auto'), 'wo')

    def test_stt_order_auto(self):
        order = stt_language_order('auto')
        self.assertIn('fr-FR', order)
        self.assertIn('wo-SN', order)

    def test_pick_stt_prefers_wolof_markers(self):
        text, locale, weak = pick_best_stt_transcript({
            'fr-FR': 'hello test',
            'wo-SN': 'Na nga def wax ma',
        })
        self.assertEqual(locale, 'wo-SN')
        self.assertIn('nga', text.lower())
        self.assertFalse(weak)

    def test_wolof_query_cannot_call_directeur_tool(self):
        ctx = type('Ctx', (), {'persona': 'parent', 'parent': object()})()
        result = execute_parent_tool(ctx, 'get_comptabilite', {})
        self.assertIn('erreur', result)
        self.assertNotIn('get_comptabilite', PARENT_TOOL_NAMES)

    def test_wolof_marker_score(self):
        self.assertGreater(wolof_marker_score('Jërëjëf, dama la bëgg xale bi'), 1)
