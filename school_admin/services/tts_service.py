"""
Synthèse vocale pour Aria : Gemini TTS (défaut) ou Edge Charline (rollback).
"""
import asyncio
import base64
import logging
import re
import struct
from xml.sax.saxutils import escape as xml_escape

from django.conf import settings

logger = logging.getLogger(__name__)

TTS_TIMEOUT_SECONDS = 14
DEFAULT_VOICE = 'fr-BE-CharlineNeural'
DEFAULT_GEMINI_VOICE = 'Zephyr'
DEFAULT_GEMINI_LANGUAGE = 'fr-FR'
# Consigne identique à chaque phrase pour limiter les variations de timbre.
GEMINI_TTS_FIXED_INSTRUCTION = (
    'Lis le texte suivant à voix haute en français. '
    'Garde exactement le même timbre féminin, le même rythme et la même chaleur '
    'qu’à l’habitude. Ne commente pas, n’ajoute rien, ne reformule pas.'
)

_gemini_tts_client = None

_SESSION_RE = re.compile(r'\b(20\d{2})\s*[-–/]\s*(20\d{2})\b')
_MATRICULE_RE = re.compile(r'\b([A-Z]{2,5})[-–]([A-Z0-9]{4,})\b')
_CLASS_LMD_RE = re.compile(
    r'\b([A-Za-z]{2,10})\s+L([1-3])\s+([A-Za-z0-9]{1,4})\b',
)
_CLASS_SEC_RE = re.compile(
    r'\b(\d)\s*(?:e|è|eme|ème)\s+([A-Za-z])\b',
    re.IGNORECASE,
)
_CLASS_TERM_RE = re.compile(
    r'\b(?:Tle|TLE|Terminale)\s*([A-Za-z0-9]{1,3})?\b',
    re.IGNORECASE,
)
_CLASS_PREM_RE = re.compile(
    r'\b(?:1(?:ère|ere)|premi[eè]re)\s+([A-Za-z0-9]{1,3})\b',
    re.IGNORECASE,
)
_PREMIER_ER_RE = re.compile(r'\b1er\b', re.IGNORECASE)
_CLASS_PRIM_RE = re.compile(r'\b(CP|CE1|CE2|CM1|CM2)\b')
_LMD_WITH_GROUP_RE = re.compile(r'\b([LM])([1-3])\s+([A-Za-z0-9]{1,4})\b')
_LMD_LEVEL_RE = re.compile(r'\b([LM])([1-3])\b')
_ORDINAL_RE = re.compile(r'\b(\d)\s*(?:e|è|eme|ème)\b', re.IGNORECASE)
_ALL_CAPS_WORD_RE = re.compile(
    r"\b([A-ZÁÀÂÄÉÈÊËÎÏÔÙÛÜÇ]{2,}(?:['’-][A-ZÁÀÂÄÉÈÊËÎÏÔÙÛÜÇ]+)*)\b"
)
_MULTI_BANG_RE = re.compile(r'!{2,}')
_ELLIPSIS_RE = re.compile(r'\.{3,}|…')
_NAME_TOKEN_RE = re.compile(
    r"(?:[A-ZÁÀÂÄÉÈÊËÎÏÔÙÛÜÇ]['’][A-ZÁÀÂÄÉÈÊËÎÏÔÙÛÜÇ][a-zàâäéèêëïîôùûüçœ']+"
    r"|[A-ZÁÀÂÄÉÈÊËÎÏÔÙÛÜÇ][a-zàâäéèêëïîôùûüçœ]+"
    r"(?:-[A-ZÁÀÂÄÉÈÊËÎÏÔÙÛÜÇ][a-zàâäéèêëïîôùûüçœ]+)*)"
)
_NAME_PARTICLE_RE = re.compile(
    r"\s+(?:d'|d’|de|du|des|di|van|von|ben|el|al|n'|n’|m'|m’)\s+",
    re.IGNORECASE,
)

_ORDINALS = {
    '1': 'première',
    '2': 'deuxième',
    '3': 'troisième',
    '4': 'quatrième',
    '5': 'cinquième',
    '6': 'sixième',
}

_PRIMARY = {
    'CP': 'cours préparatoire',
    'CE1': 'cours élémentaire première année',
    'CE2': 'cours élémentaire deuxième année',
    'CM1': 'cours moyen première année',
    'CM2': 'cours moyen deuxième année',
}

# Sigles lus comme un mot (la voix les connaît déjà).
_SAY_AS_WORD = {
    'ARIA', 'OK', 'BTS', 'DUT', 'BUT', 'CAP', 'BAC', 'LMD',
}

# Sigles développés pour une intonation naturelle.
_EXPAND = {
    'SVT': 'sciences de la vie et de la terre',
    'EPS': 'éducation physique et sportive',
    'HG': 'histoire géographie',
    'HGEO': 'histoire géographie',
    'MATH': 'mathématiques',
    'MATHS': 'mathématiques',
    'PC': 'physique chimie',
    'SPC': 'sciences physiques',
    'FR': 'français',
    'ANG': 'anglais',
    'ANGL': 'anglais',
    'ESP': 'espagnol',
    'ALL': 'allemand',
    'PHILO': 'philosophie',
    'SES': 'sciences économiques et sociales',
    'NSI': 'numérique et sciences informatiques',
    'SI': 'sciences de l’ingénieur',
    'EMC': 'enseignement moral et civique',
    'TIC': 'informatique',
    'INFO': 'informatique',
    'GL': 'génie logiciel',
    'GE': 'génie électrique',
    'GF': 'génie financier',
    'CF': 'comptabilité finance',
    'MC': 'marketing communication',
    'TL': 'techniques de laboratoire',
    'GC': 'génie civil',
    'GM': 'génie mécanique',
    'RH': 'ressources humaines',
    'UE': 'unité d’enseignement',
    'ECTS': 'crédits',
    'EDT': 'emploi du temps',
    'L1': 'licence 1',
    'L2': 'licence 2',
    'L3': 'licence 3',
    'M1': 'master 1',
    'M2': 'master 2',
    'FCFA': 'francs C F A',
    'XOF': 'francs C F A',
    'EUR': 'euros',
    'USD': 'dollars',
    'STMG': 'sciences et technologies du management et de la gestion',
    'STI2D': 'sciences et technologies de l’industrie et du développement durable',
    'ST2S': 'sciences et technologies de la santé et du social',
    'STL': 'sciences et technologies de laboratoire',
    'LLCE': 'langues, littératures et cultures étrangères',
    'HGGSP': 'histoire géographie, géopolitique et sciences politiques',
    'HLP': 'humanités, littérature et philosophie',
}

_ONES = [
    'zéro', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept',
    'huit', 'neuf', 'dix', 'onze', 'douze', 'treize', 'quatorze',
    'quinze', 'seize', 'dix-sept', 'dix-huit', 'dix-neuf',
]
_MARKDOWN_RE = re.compile(r'[*_`#]+|\[|\]|\(|\)')
_TABLE_SEP_RE = re.compile(r'^\s*\|?[\s:\-]+(?:\|[\s:\-]+)+\|?\s*$')
_HEADING_RE = re.compile(r'^#{1,6}\s+', re.MULTILINE)
_BULLET_RE = re.compile(r'^\s*[-*•]\s+', re.MULTILINE)
_TIME_RE = re.compile(r'\b(\d{1,2})\s*[:hH]\s*(\d{2})\b')
_PERCENT_RE = re.compile(r'\b(\d{1,3})\s*%')
_NUMBER_RE = re.compile(r'\b(\d{1,6})\b')
_NOT_A_NAME = frozenset({
    'aria', 'je', 'tu', 'il', 'elle', 'on', 'nous', 'vous', 'ils', 'elles',
    'le', 'la', 'les', 'un', 'une', 'des', 'du', 'de', 'ce', 'cet', 'cette',
    'ces', 'mon', 'ma', 'mes', 'ton', 'ta', 'tes', 'son', 'sa', 'ses',
    'notre', 'nos', 'votre', 'vos', 'leur', 'leurs', 'et', 'ou', 'mais',
    'donc', 'or', 'ni', 'car', 'si', 'que', 'qui', 'quand', 'comme', 'pour',
    'avec', 'dans', 'sur', 'sous', 'chez', 'vers', 'par', 'plus', 'moins',
    'très', 'tres', 'bien', 'oui', 'non', 'alors', 'ensuite', 'puis',
    'aussi', 'encore', 'déjà', 'deja', 'ici', 'bonjour', 'merci', 'voilà',
    'voila', 'voici', 'aucun', 'aucune', 'plusieurs', 'combien', 'demain',
    'hier', 'monsieur', 'madame', 'mademoiselle', 'élève', 'eleve',
    'élèves', 'eleves', 'étudiant', 'etudiant', 'étudiants', 'etudiants',
    'classe', 'sanction', 'sanctions', 'blâme', 'blame', 'avertissement',
    'action', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi',
    'dimanche', 'janvier', 'février', 'fevrier', 'mars', 'avril', 'mai',
    'juin', 'juillet', 'août', 'aout', 'septembre', 'octobre', 'novembre',
    'décembre', 'decembre', 'trimestre', 'semestre', 'licence', 'master',
    'groupe', 'première', 'premiere', 'deuxième', 'deuxieme', 'troisième',
    'troisieme', 'terminale', 'aujourd',
})


def _spell(raw):
    parts = []
    digits = ''
    for char in str(raw):
        if char.isalpha():
            if digits:
                parts.extend(list(digits))
                digits = ''
            parts.append(char.upper())
        elif char.isdigit():
            digits += char
        elif digits:
            parts.extend(list(digits))
            digits = ''
    if digits:
        parts.extend(list(digits))
    return ', '.join(parts)


def _natural_caps(token):
    """Casse naturelle d'un nom ou d'un lieu : CLÉ → Clé, N'DIAYE → N'Diaye."""
    pieces = re.split(r"(['’\-])", token or '')
    rebuilt = []
    for piece in pieces:
        if not piece:
            continue
        if piece in "'’-":
            rebuilt.append(piece)
            continue
        rebuilt.append(piece[0].upper() + piece[1:].lower())
    return ''.join(rebuilt)


def _speak_token(token):
    key = (token or '').strip().upper()
    if not key:
        return token
    if key in _EXPAND:
        return _EXPAND[key]
    if key in _SAY_AS_WORD:
        return key
    if key in _PRIMARY:
        return _PRIMARY[key]
    if key.isdigit() and key in _ORDINALS:
        return _ORDINALS[key]
    return _natural_caps(token)


_GROUP_ALNUM_RE = re.compile(r'^([A-Za-z]+)(\d+)$')


def _speak_group(raw):
    token = (raw or '').strip()
    if not token:
        return ''
    if len(token) == 1 and token.isalpha():
        return f'groupe {token.upper()}'
    if token.upper() in _EXPAND:
        return _EXPAND[token.upper()]
    if token.isdigit():
        return token
    mixed = _GROUP_ALNUM_RE.match(token)
    if mixed:
        letters = mixed.group(1)
        spoken = _speak_token(letters) if len(letters) > 1 else letters.upper()
        return f'{spoken} {mixed.group(2)}'
    return _speak_token(token)


def _speak_lmd_class(match):
    code = _speak_token(match.group(1))
    level = match.group(2)
    group = _speak_group(match.group(3))
    return f'{code}, licence {level}, {group}'


def _speak_sec_class(match):
    ordinal = _ORDINALS.get(match.group(1), f'{match.group(1)}ème')
    return f'{ordinal}, {_speak_group(match.group(2))}'


def _speak_term_class(match):
    group = match.group(1)
    if group:
        return f'terminale, {_speak_group(group)}'
    return 'terminale'


def _speak_prem_class(match):
    return f'première, {_speak_group(match.group(1))}'


def _speak_lmd_level_group(match):
    cycle = 'licence' if match.group(1).upper() == 'L' else 'master'
    return f'{cycle} {match.group(2)}, {_speak_group(match.group(3))}'


def _under_hundred(number):
    if number < 20:
        return _ONES[number]
    if number < 70:
        ten, unit = divmod(number, 10)
        if unit == 0:
            return ['', '', 'vingt', 'trente', 'quarante', 'cinquante', 'soixante'][ten]
        tens = ['', '', 'vingt', 'trente', 'quarante', 'cinquante', 'soixante'][ten]
        if unit == 1:
            return f'{tens} et un'
        return f'{tens}-{_ONES[unit]}'
    if number < 80:
        if number == 71:
            return 'soixante et onze'
        return f'soixante-{_ONES[number - 60]}'
    if number == 80:
        return 'quatre-vingts'
    if number == 81:
        return 'quatre-vingt-un'
    return f'quatre-vingt-{_ONES[number - 80]}'


def int_to_fr(number):
    """Lit un entier positif en français (0 à 999 999)."""
    number = int(number)
    if number < 0:
        return f'moins {int_to_fr(-number)}'
    if number < 100:
        return _under_hundred(number)
    if number < 1000:
        hundreds, rest = divmod(number, 100)
        head = 'cent' if hundreds == 1 else f'{_ONES[hundreds]} cent'
        if rest == 0:
            return 'cent' if hundreds == 1 else f'{_ONES[hundreds]} cents'
        return f'{head} {_under_hundred(rest)}'
    if number < 1000000:
        thousands, rest = divmod(number, 1000)
        head = 'mille' if thousands == 1 else f'{int_to_fr(thousands)} mille'
        if rest == 0:
            return head
        return f'{head} {int_to_fr(rest)}'
    return str(number)


def _speak_time(match):
    hours = int(match.group(1))
    minutes = int(match.group(2))
    hour_word = 'une heure' if hours == 1 else f'{int_to_fr(hours)} heures'
    if minutes == 0:
        return hour_word
    if minutes == 1:
        return f'{hour_word} une'
    return f'{hour_word} {int_to_fr(minutes)}'


def _speak_number(match):
    return int_to_fr(int(match.group(1)))


def _mark_cited_names(spoken):
    """Met les noms et lieux cités dans une autre couleur, sans changer Charline."""
    if not spoken:
        return spoken

    matches = list(_NAME_TOKEN_RE.finditer(spoken))
    if not matches:
        return xml_escape(spoken)

    spans = []
    start = end = None
    for match in matches:
        if match.group(0).casefold() in _NOT_A_NAME:
            if start is not None:
                spans.append((start, end))
                start = end = None
            continue
        if start is None:
            start, end = match.start(), match.end()
            continue
        between = spoken[end:match.start()]
        if between == ' ' or _NAME_PARTICLE_RE.fullmatch(between):
            end = match.end()
        else:
            spans.append((start, end))
            start, end = match.start(), match.end()
    if start is not None:
        spans.append((start, end))

    parts = []
    cursor = 0
    for start, end in spans:
        parts.append(xml_escape(spoken[cursor:start]))
        parts.append(
            f'<emphasis level="moderate">{xml_escape(spoken[start:end])}</emphasis>'
        )
        cursor = end
    parts.append(xml_escape(spoken[cursor:]))
    return ''.join(parts)


def _soften_prosody(spoken):
    """Nettoie seulement ce qui gêne la lecture, sans imposer de rythme."""
    spoken = _MULTI_BANG_RE.sub('.', spoken)
    spoken = _ELLIPSIS_RE.sub('.', spoken)
    spoken = re.sub(r'\s+', ' ', spoken).strip()
    return spoken


def strip_assistant_markup(text):
    """Retire markdown, tableaux et barres pour un texte oral lisible."""
    spoken = (text or '').replace('\r\n', '\n').replace('\r', '\n')
    if not spoken.strip():
        return ''

    lines = []
    for line in spoken.split('\n'):
        stripped = line.strip()
        if not stripped:
            continue
        if _TABLE_SEP_RE.match(stripped):
            continue
        if stripped.count('|') >= 2:
            cells = [cell.strip() for cell in stripped.strip('|').split('|')]
            cells = [cell for cell in cells if cell and not re.fullmatch(r'[-: ]+', cell)]
            if cells:
                lines.append(', '.join(cells) + '.')
            continue
        lines.append(stripped)
    spoken = ' '.join(lines)
    spoken = _HEADING_RE.sub('', spoken)
    spoken = _BULLET_RE.sub('', spoken)
    spoken = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', spoken)
    spoken = re.sub(r'\*\*([^*]+)\*\*', r'\1', spoken)
    spoken = re.sub(r'__([^_]+)__', r'\1', spoken)
    spoken = re.sub(r'`([^`]+)`', r'\1', spoken)
    spoken = re.sub(r'(?<!\w)\*([^*]+)\*(?!\w)', r'\1', spoken)
    spoken = spoken.replace('|', ' ')
    spoken = re.sub(r'-{3,}', ' ', spoken)
    spoken = _MARKDOWN_RE.sub('', spoken)
    spoken = re.sub(r'\s+', ' ', spoken).strip(' -:|')
    spoken = re.sub(r'\s+([,.;:!?])', r'\1', spoken)
    spoken = re.sub(r'\.{2,}', '.', spoken)
    return spoken.strip()


def prepare_spoken_text(text):
    """Adapte le texte à une lecture orale naturelle pour Charline."""
    spoken = strip_assistant_markup(text)
    if not spoken:
        return spoken
    spoken = _SESSION_RE.sub(r'\1 à \2', spoken)
    spoken = _TIME_RE.sub(_speak_time, spoken)
    held_ids = []

    def _stash_matricule(match):
        held_ids.append(f'{match.group(1)}{match.group(2)}')
        return f' __M{len(held_ids) - 1}__ '

    spoken = _MATRICULE_RE.sub(_stash_matricule, spoken)
    spoken = _CLASS_LMD_RE.sub(_speak_lmd_class, spoken)
    spoken = _CLASS_SEC_RE.sub(_speak_sec_class, spoken)
    spoken = _CLASS_TERM_RE.sub(_speak_term_class, spoken)
    spoken = _CLASS_PREM_RE.sub(_speak_prem_class, spoken)
    spoken = _CLASS_PRIM_RE.sub(lambda match: _PRIMARY[match.group(1)], spoken)
    spoken = _PREMIER_ER_RE.sub('première,', spoken)
    spoken = _LMD_WITH_GROUP_RE.sub(_speak_lmd_level_group, spoken)
    spoken = _LMD_LEVEL_RE.sub(
        lambda match: (
            f"{'licence' if match.group(1) == 'L' else 'master'} {match.group(2)}"
        ),
        spoken,
    )
    spoken = _ORDINAL_RE.sub(
        lambda match: _ORDINALS.get(match.group(1), match.group(0)),
        spoken,
    )

    def _caps_word(match):
        return _speak_token(match.group(1))

    spoken = _ALL_CAPS_WORD_RE.sub(_caps_word, spoken)
    spoken = _PERCENT_RE.sub(
        lambda match: f'{int_to_fr(int(match.group(1)))} pour cent',
        spoken,
    )
    spoken = _NUMBER_RE.sub(_speak_number, spoken)
    spoken = _soften_prosody(spoken)
    for index, code in enumerate(held_ids):
        spoken = spoken.replace(f'__M{index}__', _spell(code))
    return spoken


def _tts_backend():
    return getattr(settings, 'ASSISTANT_TTS_BACKEND', 'gemini') or 'gemini'


def parse_pcm_sample_rate(mime_type):
    """Extrait le sample rate d'un MIME Gemini (ex. audio/L16;codec=pcm;rate=24000)."""
    raw = (mime_type or '').lower()
    match = re.search(r'rate=(\d+)', raw)
    if match:
        return int(match.group(1))
    return 24000


def pcm16_to_wav(pcm_data, sample_rate=24000, num_channels=1):
    """Encapsule du PCM 16-bit little-endian en WAV."""
    if not pcm_data:
        return b''
    bits_per_sample = 16
    block_align = num_channels * bits_per_sample // 8
    byte_rate = sample_rate * block_align
    data_size = len(pcm_data)
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,
        b'WAVE',
        b'fmt ',
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b'data',
        data_size,
    )
    return header + pcm_data


def _gemini_tts_prompt(spoken_text):
    return f'{GEMINI_TTS_FIXED_INSTRUCTION}\n\n{spoken_text}'


def _resolve_gemini_voice():
    raw = getattr(settings, 'GEMINI_TTS_VOICE', DEFAULT_GEMINI_VOICE) or DEFAULT_GEMINI_VOICE
    return raw.strip().title()


def _resolve_gemini_language():
    return (
        getattr(settings, 'GEMINI_TTS_LANGUAGE', DEFAULT_GEMINI_LANGUAGE)
        or DEFAULT_GEMINI_LANGUAGE
    ).strip()


def _get_gemini_tts_client():
    global _gemini_tts_client
    if _gemini_tts_client is not None:
        return _gemini_tts_client
    from google import genai

    api_key = getattr(settings, 'GEMINI_API_KEY', '') or ''
    _gemini_tts_client = genai.Client(api_key=api_key)
    return _gemini_tts_client


async def _synthesize_gemini(clean):
    api_key = getattr(settings, 'GEMINI_API_KEY', '') or ''
    if not api_key:
        logger.warning('GEMINI_API_KEY manquante pour la synthèse vocale.')
        return None, None

    model = getattr(
        settings,
        'GEMINI_TTS_MODEL',
        'gemini-2.5-flash-preview-tts',
    )
    voice_name = _resolve_gemini_voice()
    language_code = _resolve_gemini_language()

    try:
        from google.genai import types
    except ImportError:
        logger.exception("Le package google-genai n'est pas installé.")
        return None, None

    client = _get_gemini_tts_client()
    prompt = _gemini_tts_prompt(clean)

    async def _call():
        return await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=['AUDIO'],
                speech_config=types.SpeechConfig(
                    language_code=language_code,
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name,
                        ),
                    ),
                ),
            ),
        )

    try:
        response = await asyncio.wait_for(_call(), timeout=TTS_TIMEOUT_SECONDS)
    except Exception:
        logger.exception('Échec de la synthèse vocale Gemini TTS.')
        return None, None

    candidates = getattr(response, 'candidates', None) or []
    for candidate in candidates:
        content = getattr(candidate, 'content', None)
        parts = getattr(content, 'parts', None) or []
        for part in parts:
            inline = getattr(part, 'inline_data', None)
            if not inline:
                continue
            raw = getattr(inline, 'data', None)
            mime = getattr(inline, 'mime_type', None) or 'audio/L16;codec=pcm;rate=24000'
            if isinstance(raw, str):
                pcm = base64.b64decode(raw)
            elif isinstance(raw, (bytes, bytearray)):
                pcm = bytes(raw)
            else:
                continue
            rate = parse_pcm_sample_rate(mime)
            wav = pcm16_to_wav(pcm, sample_rate=rate)
            return wav, 'audio/wav'
    logger.warning('Gemini TTS : aucun segment audio dans la réponse.')
    return None, None


async def _synthesize_edge_mp3(clean, voice=None):
    voice = voice or getattr(settings, 'EDGE_TTS_VOICE', DEFAULT_VOICE) or DEFAULT_VOICE
    try:
        import edge_tts
    except ImportError:
        logger.exception("Le package edge-tts n'est pas installé.")
        return None, None

    try:
        communicate = edge_tts.Communicate(clean, voice)
        chunks = []

        async def _collect():
            async for chunk in communicate.stream():
                if chunk.get('type') == 'audio' and chunk.get('data'):
                    chunks.append(chunk['data'])

        await asyncio.wait_for(_collect(), timeout=TTS_TIMEOUT_SECONDS)
        audio = b''.join(chunks)
        if audio:
            return audio, 'audio/mpeg'
        return None, None
    except Exception:
        logger.exception('Échec de la synthèse vocale edge-tts.')
        return None, None


async def synthesize_audio(text, voice=None, rate=None, pitch=None):
    """
    Convertit un texte en bytes audio + MIME (WAV Gemini ou MP3 Edge).

    rate/pitch ignorés (rythme natif du moteur).
    """
    del rate, pitch
    clean = prepare_spoken_text(text)
    if not clean:
        return None, None

    backend = _tts_backend()
    if backend == 'edge':
        return await _synthesize_edge_mp3(clean, voice=voice)

    audio, mime = await _synthesize_gemini(clean)
    if audio:
        return audio, mime
    if getattr(settings, 'ASSISTANT_TTS_FALLBACK_EDGE', False):
        logger.warning('Gemini TTS indisponible, repli Edge (voix différente).')
        return await _synthesize_edge_mp3(clean, voice=voice)
    logger.warning('Gemini TTS indisponible, pas de repli Edge (voix fixe).')
    return None, None


async def synthesize_mp3(text, voice=None, rate=None, pitch=None):
    """Compatibilité : retourne uniquement les bytes (MP3 Edge ou WAV Gemini)."""
    audio, _mime = await synthesize_audio(text, voice=voice, rate=rate, pitch=pitch)
    return audio
