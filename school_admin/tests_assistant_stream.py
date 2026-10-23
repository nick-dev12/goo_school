"""Flux Gemini (endpoint OpenAI) : appels d'outils sans index, thought_signature, cache expiré."""
from types import SimpleNamespace

from django.test import SimpleTestCase

from school_admin.services import gemini_assistant_service as g
from school_admin.services import gemini_context_cache as cc


def _appel(nom, args, call_id, index=None, sig='SIG'):
    fn = SimpleNamespace(name=nom, arguments=args)
    return SimpleNamespace(index=index, id=call_id, function=fn,
                           extra_content={'google': {'thought_signature': sig}}, model_extra={})


class FluxOutilsTests(SimpleTestCase):
    def test_appel_sans_index_conserve_avec_signature(self):
        sac = {}
        g._merge_stream_tool_call(sac, None, _appel('rechercher_classes', '{"query":""}', 'call_1'))
        g._merge_stream_tool_call(sac, None, _appel('get_effectifs', '{}', 'call_2', sig='S2'))
        appels = g._finalize_stream_tool_calls(sac)
        self.assertEqual([a['name'] for a in appels], ['rechercher_classes', 'get_effectifs'])
        payload = g._tool_calls_payload(appels)
        self.assertEqual(payload[0]['extra_content']['google']['thought_signature'], 'SIG')
        self.assertEqual(payload[1]['id'], 'call_2')

    def test_appel_fragmente_avec_index(self):
        sac = {}
        g._merge_stream_tool_call(sac, 0, _appel('rechercher_classes', '{"que', 'c1'))
        g._merge_stream_tool_call(sac, 0, SimpleNamespace(id=None, function=SimpleNamespace(name=None, arguments='ry":"3e"}'),
                                                          extra_content=None, model_extra={}))
        self.assertEqual(g._finalize_stream_tool_calls(sac)[0]['arguments'], {'query': '3e'})


class CacheExpireTests(SimpleTestCase):
    def test_erreur_cache_introuvable_reinitialise(self):
        cc._cache_name = 'cachedContents/abc'
        self.assertTrue(cc.est_erreur_cache_introuvable(Exception('403 CachedContent not found (or permission denied)')))
        self.assertFalse(cc.est_erreur_cache_introuvable(Exception('500 internal')))
        cc.oublier_cache('cachedContents/abc')
        self.assertIsNone(cc._cache_name)
