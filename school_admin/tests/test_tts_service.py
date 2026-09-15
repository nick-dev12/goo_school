"""Préparation orale Charline : noms cités, sans casser le rythme natif."""
from django.test import SimpleTestCase

from school_admin.services.tts_service import (
    _mark_cited_names,
    parse_pcm_sample_rate,
    pcm16_to_wav,
    prepare_spoken_text,
    strip_assistant_markup,
)


class CharlineSpokenTextTests(SimpleTestCase):
    def test_noms_en_capitales_ne_sont_plus_epeles(self):
        spoken = prepare_spoken_text(
            "Blâme enregistré pour CLÉ Jason, en 1er L1 A."
        )
        self.assertIn('Clé Jason', spoken)
        self.assertIn('licence', spoken)
        self.assertIn('groupe A', spoken)
        self.assertNotIn('groupe R', spoken)
        classe = prepare_spoken_text('La classe 3e A')
        self.assertIn('troisième', classe)
        self.assertIn('groupe A', classe)
        self.assertNotIn('C, L', spoken)
        self.assertNotIn('pour, Clé', spoken)

    def test_lieux_et_noms_composes_restent_lisibles(self):
        spoken = prepare_spoken_text(
            "L'élève N'DIAYE Fatou habite à DAKAR."
        )
        self.assertIn("N'Diaye Fatou", spoken)
        self.assertIn('Dakar', spoken)
        marked = _mark_cited_names(spoken)
        self.assertIn(
            "<emphasis level=\"moderate\">N'Diaye Fatou</emphasis>",
            marked,
        )
        self.assertIn('<emphasis level="moderate">Dakar</emphasis>', marked)
        self.assertNotIn("L'élève N'Diaye", marked)

    def test_sigles_scolaires_restent_developpes(self):
        spoken = prepare_spoken_text('Le cours de SVT commence à 8:30.')
        self.assertIn('sciences de la vie et de la terre', spoken)
        self.assertIn('huit heures trente', spoken)

    def test_noms_cites_sont_marquables_sans_casser_le_texte(self):
        spoken = prepare_spoken_text('Blâme enregistré pour CLÉ Jason.')
        marked = _mark_cited_names(spoken)
        self.assertIn('Clé Jason', spoken)
        self.assertIn('<emphasis level="moderate">Clé Jason</emphasis>', marked)
        self.assertNotIn('<emphasis level="moderate">Blâme</emphasis>', marked)

    def test_markdown_et_tableaux_sont_retires(self):
        raw = (
            "Vous avez **50 élèves** au total pour l'année **2026-2027**.\n"
            "| Classe | Effectif |\n"
            "|--------|----------|\n"
            "| CP A | 10 |"
        )
        cleaned = strip_assistant_markup(raw)
        self.assertNotIn('*', cleaned)
        self.assertNotIn('|', cleaned)
        self.assertNotIn('---', cleaned)
        self.assertIn('50 élèves', cleaned)
        self.assertIn('CP A', cleaned)
        self.assertIn('10', cleaned)

    def test_phrase_courante_sans_virgules_artificielles(self):
        spoken = prepare_spoken_text(
            "La seule sanction que je peux confirmer à l'instant c'est le blâme."
        )
        self.assertNotIn('instant, c', spoken)
        self.assertNotIn('peux, confirmer', spoken)

    def test_parse_pcm_sample_rate(self):
        self.assertEqual(parse_pcm_sample_rate('audio/L16;codec=pcm;rate=24000'), 24000)
        self.assertEqual(parse_pcm_sample_rate(''), 24000)

    def test_pcm16_to_wav_header(self):
        pcm = b'\x00\x01' * 100
        wav = pcm16_to_wav(pcm, sample_rate=24000)
        self.assertTrue(wav.startswith(b'RIFF'))
        self.assertIn(b'WAVE', wav[:16])
        self.assertEqual(len(wav), 44 + len(pcm))
