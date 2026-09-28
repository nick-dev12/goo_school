"""Consignes wolof dakarois dans les system prompts Aria."""
from django.test import SimpleTestCase

from school_admin.services.assistant_wolof_language import WOLOF_DAKAR_SYSTEM_PROMPT
from school_admin.services.gemini_assistant_service import system_prompt_static_for


class WolofPromptAllPersonasTests(SimpleTestCase):
    def test_shared_block_bans_litterary_wolof(self):
        folded = ' '.join(WOLOF_DAKAR_SYSTEM_PROMPT.split())
        self.assertIn('léttal', folded)
        self.assertIn('Neex na lool', WOLOF_DAKAR_SYSTEM_PROMPT)
        self.assertIn('wolof dakarois', folded.lower())

    def _ctx(self, persona):
        class Ctx:
            pass

        ctx = Ctx()
        ctx.persona = persona
        ctx.est_superieur = False
        ctx.est_primaire = False
        ctx.est_college_lycee = True
        return ctx

    def test_directeur_prompt_includes_wolof(self):
        prompt = system_prompt_static_for(self._ctx('directeur'))
        self.assertIn('Langues — Wolof dakarois', prompt)

    def test_enseignant_prompt_includes_wolof(self):
        for persona in ('enseignant', 'enseignant_primaire', 'parent', 'eleve'):
            prompt = system_prompt_static_for(self._ctx(persona))
            self.assertIn('léttal', prompt, msg=persona)
            self.assertIn('waxtaan', prompt, msg=persona)
