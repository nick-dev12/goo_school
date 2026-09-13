"""
Synthèse vocale Microsoft Neural via edge-tts (voix femme Charline).
Le texte est mis en forme orale ; la voix reste à ses réglages natifs.
"""
import asyncio
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

TTS_TIMEOUT_SECONDS = 14
DEFAULT_VOICE = 'fr-BE-CharlineNeural'

_SESSION_RE = re.compile(r'\b(20\d{2})\s*[-–/]\s*(20\d{2})\b')
_MATRICULE_RE = re.compile(r'\b([A-Z]{2,5})[-–]([A-Z0-9]{4,})\b')
_CLASS_LMD_RE = re.compile(
    r'\b([A-Za-z]{2,10})\s+L([1-3])\s+([A-Za-z0-9]{1,4})\b',
)
_CLASS_SEC_RE = re.compile(
    r'\b(\d)\s*(?:e|è|eme|ème)\s*([A-Za-z])\b',
    re.IGNORECASE,
)
_CLASS_TERM_RE = re.compile(
    r'\b(?:Tle|TLE|Terminale)\s*([A-Za-z0-9]{1,3})?\b',
    re.IGNORECASE,
)
_CLASS_PREM_RE = re.compile(
    r'\b(?:1(?:e|ère|ere)|premi[eè]re)\s*([A-Za-z0-9]{1,3})\b',
    re.IGNORECASE,
)
_CLASS_PRIM_RE = re.compile(r'\b(CP|CE1|CE2|CM1|CM2)\b')
_LMD_LEVEL_RE = re.compile(r'\b([LM])([1-3])\b')
_ORDINAL_RE = re.compile(r'\b(\d)\s*(?:e|è|eme|ème)\b', re.IGNORECASE)
_ACRONYM_RE = re.compile(r'\b([A-ZÁÀÂÄÉÈÊËÎÏÔÙÛÜ]{2,6})\b')
_COLON_RE = re.compile(r'\s*[:：]\s*')
_SEMI_RE = re.compile(r'\s*;\s*')
_MULTI_BANG_RE = re.compile(r'!{2,}')
_ELLIPSIS_RE = re.compile(r'\.{3,}|…')

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
_TIME_RE = re.compile(r'\b(\d{1,2})\s*[:hH]\s*(\d{2})\b')
_PERCENT_RE = re.compile(r'\b(\d{1,3})\s*%')
_NUMBER_RE = re.compile(r'\b(\d{1,6})\b')
_BREATH_RE = re.compile(
    r'\b(et|puis|pour|avec|dans|mais|donc|ensuite)\b',
    re.IGNORECASE,
)


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
    if 2 <= len(key) <= 5 and key.isalpha():
        return _spell(key)
    return token


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


def _breathe_long_clauses(spoken):
    chunks = re.split(r'([.!?])', spoken)
    rebuilt = []
    for chunk in chunks:
        if chunk in '.!?' or not chunk.strip():
            rebuilt.append(chunk)
            continue
        words = chunk.split()
        if len(words) <= 12 or ',' in chunk:
            rebuilt.append(chunk)
            continue
        rewritten = []
        count = 0
        for word in words:
            rewritten.append(word)
            count += 1
            if count >= 7 and _BREATH_RE.fullmatch(word.strip(' ,;:')):
                rewritten[-1] = f'{word},'
                count = 0
        rebuilt.append(' '.join(rewritten))
    return ''.join(rebuilt)


def _soften_prosody(spoken):
    """Ajoute des pauses que la voix neurale interprète naturellement."""
    spoken = _COLON_RE.sub(', ', spoken)
    spoken = _SEMI_RE.sub(', ', spoken)
    spoken = _MULTI_BANG_RE.sub('.', spoken)
    spoken = _ELLIPSIS_RE.sub(', ', spoken)
    spoken = _breathe_long_clauses(spoken)
    spoken = re.sub(r'\s*,\s*', ', ', spoken)
    spoken = re.sub(r',\s*,+', ', ', spoken)
    spoken = re.sub(r'\s+\.', '.', spoken)
    spoken = re.sub(r'([.!?])\s*', r'\1 ', spoken)
    spoken = re.sub(r'\s+', ' ', spoken).strip()
    return spoken


def prepare_spoken_text(text):
    """Adapte le texte à une lecture orale naturelle pour Charline."""
    spoken = (text or '').strip()
    if not spoken:
        return spoken

    spoken = _MARKDOWN_RE.sub(' ', spoken)
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

    def _acronym(match):
        return _speak_token(match.group(1))

    spoken = _ACRONYM_RE.sub(_acronym, spoken)
    spoken = _PERCENT_RE.sub(
        lambda match: f'{int_to_fr(int(match.group(1)))} pour cent',
        spoken,
    )
    spoken = _NUMBER_RE.sub(_speak_number, spoken)
    spoken = _soften_prosody(spoken)
    for index, code in enumerate(held_ids):
        spoken = spoken.replace(f'__M{index}__', _spell(code))
    return spoken


async def synthesize_mp3(text, voice=None, rate=None, pitch=None):
    """
    Convertit un texte en MP3 (bytes).

    Retourne None si le texte est vide ou si la synthèse échoue.
    Rate, pitch et volume restent aux valeurs natives de la voix.
    """
    clean = prepare_spoken_text(text)
    if not clean:
        return None

    voice = voice or getattr(settings, 'EDGE_TTS_VOICE', DEFAULT_VOICE) or DEFAULT_VOICE

    try:
        import edge_tts
    except ImportError:
        logger.exception("Le package edge-tts n'est pas installé.")
        return None

    try:
        communicate = edge_tts.Communicate(clean, voice)
        chunks = []

        async def _collect():
            async for chunk in communicate.stream():
                if chunk.get('type') == 'audio' and chunk.get('data'):
                    chunks.append(chunk['data'])

        await asyncio.wait_for(_collect(), timeout=TTS_TIMEOUT_SECONDS)
        audio = b''.join(chunks)
        return audio or None
    except Exception:
        logger.exception("Échec de la synthèse vocale edge-tts.")
        return None
