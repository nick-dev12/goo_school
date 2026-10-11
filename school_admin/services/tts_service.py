"""
Synthèse vocale pour Aria : Gemini TTS (défaut), Chirp 3 HD (chirp) ou Gemini
via Cloud Text-to-Speech (cloud_gemini), Edge Charline (rollback).
"""
import asyncio
import base64
import logging
import math
import re
import struct
from xml.sax.saxutils import escape as xml_escape

from django.conf import settings

logger = logging.getLogger(__name__)

TTS_TIMEOUT_SECONDS = 25
DEFAULT_VOICE = 'fr-FR-EloiseNeural'
DEFAULT_GEMINI_VOICE = 'Aoede'
DEFAULT_GEMINI_LANGUAGE = 'fr-FR'
# Voix Gemini féminines recommandées pour le français (timbe naturel).
_GEMINI_FEMALE_VOICES = frozenset({
    'Achernar', 'Aoede', 'Autonoe', 'Callirrhoe', 'Despina', 'Erinome', 'Gacrux',
    'Kore', 'Laomedeia', 'Leda', 'Pulcherrima', 'Sulafat', 'Vindemiatrix', 'Zephyr',
})
# Consigne identique à chaque phrase pour limiter les variations de timbre.
GEMINI_TTS_FIXED_INSTRUCTION = (
    'Tu es Aria, assistante vocale à voix féminine Aoede : ton très enjoué, '
    'accueillant et bienveillant, comme si tu recevais quelqu’un avec le sourire. '
    'Énergie douce et positive, jamais monotone ni froide. '
    'Lis le texte en français standard, rythme conversationnel naturel (pas robotique). '
    'Prononce clairement les prénoms, noms de famille et lieux (y compris N\'Diaye, '
    'Sow, Dakar, etc.) sans les angliciser ni les épeler lettre par lettre. '
    'Ne commente pas, n’ajoute rien, ne reformule pas, ne traduis pas.'
)
GEMINI_TTS_WOLOF_INSTRUCTION = (
    'Tu es Aria. Lis le texte à voix haute en wolof dakarois courant (alphabet latin), '
    'voix féminine enjouée et accueillante, chaleureuse et familière — comme à Dakar '
    'à l’école, pas un wolof littéraire ou soutenu. '
    'Garde les mots français déjà présents dans le texte (devoir, classe, notes, etc.). '
    'Ne commente pas, n’ajoute rien, ne reformule pas, ne traduis pas en français.'
)
# Aucune voix wolof chez Edge (fr-SN-AissatouNeural n'existe pas) : vide = même voix qu'en français.
DEFAULT_EDGE_VOICE_WOLOF = ''
# Edge (service gratuit non officiel) refuse parfois (403) ou traîne : on abandonne vite
# pour passer au repli plutôt que de laisser Aria muette.
EDGE_TTS_TIMEOUT_SECONDS = 8

_gemini_tts_client = None

_SESSION_RE = re.compile(r'\b(20\d{2})\s*[-–/]\s*(20\d{2})\b')
_MATRICULE_RE = re.compile(r'\b([A-Z]{2,5})[-–]([A-Z0-9]{4,})\b')
_CLASS_LMD_RE = re.compile(
    r'\b([A-Z][A-Za-z]{1,9})\s+L([1-3])\s+([A-Za-z0-9]{1,4})\b',
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
_ORDINAL_RE = re.compile(r'\b(\d{1,3})\s*(?:e|è|eme|ème)\b', re.IGNORECASE)
_MONTHS = [
    'janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août',
    'septembre', 'octobre', 'novembre', 'décembre',
]
_DATE_DMY_RE = re.compile(r'(?<![\d/.-])(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?![\d/-]|\.\d)')
_DATE_ISO_RE = re.compile(r'(?<![\d/.-])(\d{4})-(\d{2})-(\d{2})(?![\d/-]|\.\d)')
# Mobiles et fixes sénégalais : 77 123 45 67, 77-123-45-67, 771234567, +221 33 820 00 00.
_PHONE_SN_RE = re.compile(
    r'(?<![\d+])(\+?221[\s.-]?)?(7[05678]|3[03])[\s.-]?(\d{3})[\s.-]?(\d{2})[\s.-]?(\d{2})(?!\d)'
)
_PHONE_FR_RE = re.compile(r'(?<![\d+])(\+33[\s.-]?|0)([1-9])((?:[\s.-]?\d{2}){4})(?!\d)')
_HOUR_ONLY_RE = re.compile(r'\b(\d{1,2})\s*h\b')
_SCORE_RE = re.compile(r'(?<![\d/])(\d{1,3}(?:,\d{1,2})?)\s*/\s*(\d{1,3})(?![\d/])')
_RANGE_RE = re.compile(r'(?<![\d,./-])(\d{1,4})\s*[-–]\s*(\d{1,4})(?![\d/-]|[.,]\d)')
_THOUSANDS_RE = re.compile(r'(?<![\d,.])\d{1,3}(?:[ .]\d{3})+(?!\d|,\d)')
# Virgule = décimale ; point = décimale seulement avec 1 ou 2 chiffres (1.500 = mille cinq cents).
_DECIMAL_RE = re.compile(r'(?<![\d,.])(\d{1,9})(?:,(\d{1,3})|\.(\d{1,2}))(?!\d|[.,]\d)')
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
_NUMBER_RE = re.compile(r'\b(\d{1,9})\b')
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
    return ' '.join(parts)


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
        head = 'mille' if thousands == 1 else f'{_invariable(int_to_fr(thousands))} mille'
        if rest == 0:
            return head
        return f'{head} {int_to_fr(rest)}'
    if number < 1000000000:
        millions, rest = divmod(number, 1000000)
        head = 'un million' if millions == 1 else f'{int_to_fr(millions)} millions'
        if rest == 0:
            return head
        return f'{head} {int_to_fr(rest)}'
    return ' '.join(int_to_fr(int(digit)) for digit in str(number))


def _invariable(words):
    """« deux cents » / « quatre-vingts » perdent leur s devant mille."""
    if words.endswith('cents') or words.endswith('vingts'):
        return words[:-1]
    return words


def ordinal_fr(number):
    """10 → dixième, 21 → vingt et unième (1 → premier)."""
    number = int(number)
    if number == 1:
        return 'premier'
    words = _invariable(int_to_fr(number))
    if words.endswith('cinq'):
        return words + 'uième'
    if words.endswith('neuf'):
        return words[:-1] + 'vième'
    if words.endswith('e'):
        return words[:-1] + 'ième'
    return words + 'ième'


def _digit_group(raw):
    """Groupe de chiffres lu tel quel : « 05 » → zéro cinq, « 123 » → cent vingt-trois."""
    raw = re.sub(r'\D', '', raw or '')
    if not raw:
        return ''
    if raw.startswith('0') and len(raw) > 1:
        return 'zéro ' + _digit_group(raw[1:])
    return int_to_fr(int(raw))


def _speak_date(day, month, year):
    day, month = int(day), int(month)
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None
    day_word = 'premier' if day == 1 else int_to_fr(day)
    return f'{day_word} {_MONTHS[month - 1]} {int_to_fr(int(year))}'


def _speak_phone_sn(match):
    prefix = 'plus deux cent vingt et un, ' if match.group(1) else ''
    return prefix + ', '.join(_digit_group(match.group(index)) for index in range(2, 6))


def _speak_phone_fr(match):
    prefix = 'plus trente-trois, ' if match.group(1).startswith('+') else 'zéro '
    pairs = re.findall(r'\d{2}', match.group(3))
    return prefix + int_to_fr(int(match.group(2))) + ', ' + ', '.join(_digit_group(p) for p in pairs)


def _speak_decimal(match):
    fraction = match.group(2) or match.group(3) or ''
    return f'{int_to_fr(int(match.group(1)))} virgule {_digit_group(fraction)}'


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
    spoken = spoken.replace('’', "'").replace(' ', ' ').replace(' ', ' ')
    # Ordre important : dates et téléphones avant sessions, scores, plages et milliers.
    spoken = _DATE_ISO_RE.sub(
        lambda m: _speak_date(m.group(3), m.group(2), m.group(1)) or m.group(0),
        spoken,
    )
    spoken = _DATE_DMY_RE.sub(
        lambda m: _speak_date(m.group(1), m.group(2), m.group(3)) or m.group(0),
        spoken,
    )
    spoken = _PHONE_SN_RE.sub(_speak_phone_sn, spoken)
    spoken = _PHONE_FR_RE.sub(_speak_phone_fr, spoken)
    spoken = _SESSION_RE.sub(r'\1 à \2', spoken)
    spoken = _TIME_RE.sub(_speak_time, spoken)
    spoken = _HOUR_ONLY_RE.sub(
        lambda m: 'une heure' if m.group(1) == '1' else f'{int_to_fr(int(m.group(1)))} heures',
        spoken,
    )
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
    spoken = _PREMIER_ER_RE.sub('premier', spoken)
    spoken = _LMD_WITH_GROUP_RE.sub(_speak_lmd_level_group, spoken)
    spoken = _LMD_LEVEL_RE.sub(
        lambda match: (
            f"{'licence' if match.group(1) == 'L' else 'master'} {match.group(2)}"
        ),
        spoken,
    )
    spoken = _ORDINAL_RE.sub(
        lambda match: _ORDINALS.get(match.group(1)) or ordinal_fr(match.group(1)),
        spoken,
    )
    spoken = _SCORE_RE.sub(r'\1 sur \2', spoken)
    spoken = _RANGE_RE.sub(r'\1 à \2', spoken)
    spoken = _THOUSANDS_RE.sub(lambda match: re.sub(r'[ .]', '', match.group(0)), spoken)
    spoken = _DECIMAL_RE.sub(_speak_decimal, spoken)

    def _caps_word(match):
        return _speak_token(match.group(1))

    spoken = _ALL_CAPS_WORD_RE.sub(_caps_word, spoken)
    spoken = _PERCENT_RE.sub(
        lambda match: f'{int_to_fr(int(match.group(1)))} pour cent',
        spoken,
    )
    spoken = _NUMBER_RE.sub(_speak_number, spoken)
    spoken = re.sub(r'\s*%', ' pour cent', spoken)
    spoken = _soften_prosody(spoken)
    for index, code in enumerate(held_ids):
        spoken = spoken.replace(f'__M{index}__', _spell(code))
    return re.sub(r'\s+([,.;:!?])', r'\1', spoken)


def _tts_backend():
    return getattr(settings, 'ASSISTANT_TTS_BACKEND', 'gemini') or 'gemini'


def parse_pcm_sample_rate(mime_type):
    """Extrait le sample rate d'un MIME Gemini (ex. audio/L16;codec=pcm;rate=24000)."""
    raw = (mime_type or '').lower()
    match = re.search(r'rate=(\d+)', raw)
    if match:
        return int(match.group(1))
    return 24000


def _pcm16_to_samples(pcm_data):
    import array

    usable = len(pcm_data) - (len(pcm_data) % 2)
    if usable < 2:
        return array.array('h'), 0
    samples = array.array('h')
    samples.frombytes(pcm_data[:usable])
    return samples, len(samples)


def _window_zcr(samples, start, end):
    window = samples[start:end]
    size = len(window)
    if size < 2:
        return 0.0
    crossings = 0
    previous = window[0]
    for sample in window[1:]:
        if (previous >= 0 > sample) or (previous < 0 <= sample):
            crossings += 1
        previous = sample
    return crossings / size


def strip_pcm16_end_squelch(pcm_data, sample_rate=24000, max_ms=160):
    """
    Coupe le crissement de fin (squelch type talkie-walkie) ajouté par Gemini TTS.
    Le burst est bruité (beaucoup de passages par zéro), souvent après une baisse d’énergie.
    """
    samples, count = _pcm16_to_samples(pcm_data)
    frame = max(8, int(sample_rate * 0.005))
    if count < frame * 8:
        return samples.tobytes() if count else pcm_data

    max_scan = min(count // 2, max(frame * 4, int(sample_rate * max_ms / 1000)))
    scan_start = count - max_scan
    energies = []
    index = scan_start
    while index + frame <= count:
        window = samples[index:index + frame]
        energy = sum(abs(sample) for sample in window) / frame
        energies.append((index, energy, _window_zcr(samples, index, index + frame)))
        index += frame
    if len(energies) < 4:
        return samples.tobytes()

    peak = max(item[1] for item in energies) or 1
    quiet = max(220, peak * 0.14)
    loud = max(700, peak * 0.32)
    cut = None
    for pos in range(len(energies) - 2, 0, -1):
        if energies[pos][1] >= quiet or energies[pos - 1][1] >= quiet:
            continue
        if any(item[1] > loud for item in energies[pos + 1:]):
            cut = energies[pos][0]
            break
    noisy_cut = None
    for pos in range(len(energies) - 1, -1, -1):
        energy = energies[pos][1]
        zcr = energies[pos][2]
        if zcr >= 0.22 and energy > 350:
            noisy_cut = energies[pos][0]
            continue
        break
    if noisy_cut is not None and 0 < count - noisy_cut <= max_scan:
        if cut is None or noisy_cut < cut:
            cut = noisy_cut
    if cut is not None and frame < count - cut <= max_scan:
        del samples[cut:]
    return samples.tobytes()


def append_pcm16_silence(pcm_data, sample_rate=24000, silence_ms=40):
    """Ajoute du silence pour que le lecteur s’arrête sur des zéros (pas de pop)."""
    samples, count = _pcm16_to_samples(pcm_data)
    if count < 2:
        return pcm_data
    pad = max(1, int(sample_rate * silence_ms / 1000))
    samples.extend([0] * pad)
    return samples.tobytes()


def trim_pcm16_trailing_artifacts(
    pcm_data,
    sample_rate=24000,
    max_trim_ms=220,
    noise_floor=160,
    hangover_ms=8,
):
    """
    Retire la queue bruitée (souffle / artefact Gemini) avant le fade-out.
    """
    samples, count = _pcm16_to_samples(pcm_data)
    if count < 16:
        return pcm_data

    max_trim = max(8, int(sample_rate * max_trim_ms / 1000))
    hangover = max(4, int(sample_rate * hangover_ms / 1000))
    scan_start = max(0, count - max_trim)
    last_loud = count - 1
    for index in range(count - 1, scan_start - 1, -1):
        if abs(samples[index]) > noise_floor:
            last_loud = index
            break
    end = min(count, last_loud + hangover)
    if end < count:
        del samples[end:count]
    return samples.tobytes()


def smooth_pcm16_edges(pcm_data, sample_rate=24000, fade_in_ms=6, fade_out_ms=28):
    """
    Atténue les bords du PCM (cosinus) pour éviter les clics entre phrases.
    """
    samples, count = _pcm16_to_samples(pcm_data)
    if count < 8:
        return samples.tobytes() if count else pcm_data

    fade_in = min(count // 4, max(2, int(sample_rate * fade_in_ms / 1000)))
    fade_out = min(count // 3, max(4, int(sample_rate * fade_out_ms / 1000)))

    for index in range(fade_in):
        t = (index + 1) / fade_in
        factor = math.sin(t * math.pi / 2)
        samples[index] = int(samples[index] * factor)

    for offset in range(fade_out):
        index = count - 1 - offset
        t = offset / max(fade_out - 1, 1)
        factor = math.sin(t * math.pi / 2)
        samples[index] = int(samples[index] * factor)

    for tail in range(min(4, count)):
        samples[count - 1 - tail] = 0

    return samples.tobytes()


def finalize_pcm16(pcm_data, sample_rate=24000):
    pcm = strip_pcm16_end_squelch(pcm_data, sample_rate=sample_rate)
    pcm = trim_pcm16_trailing_artifacts(pcm, sample_rate=sample_rate)
    pcm = smooth_pcm16_edges(pcm, sample_rate=sample_rate)
    return append_pcm16_silence(pcm, sample_rate=sample_rate, silence_ms=50)


def _join_pcm16_with_micro_crossfade(left_pcm, right_pcm, sample_rate=24000, overlap_ms=4):
    """Évite un clic si Gemini renvoie plusieurs parts PCM pour une même phrase."""
    left, left_n = _pcm16_to_samples(left_pcm)
    right, right_n = _pcm16_to_samples(right_pcm)
    if left_n < 2 or right_n < 2:
        return left_pcm + right_pcm

    overlap = min(
        left_n // 4,
        right_n // 4,
        max(2, int(sample_rate * overlap_ms / 1000)),
    )
    if overlap < 2:
        return left.tobytes() + right.tobytes()

    out = left[: left_n - overlap]
    for index in range(overlap):
        li = left_n - overlap + index
        ri = index
        t = (index + 1) / overlap
        fade_out = math.cos(t * math.pi / 2)
        fade_in = math.sin(t * math.pi / 2)
        mixed = int(left[li] * fade_out + right[ri] * fade_in)
        out.append(max(-32768, min(32767, mixed)))
    out.extend(right[overlap:right_n])
    return out.tobytes()


def concat_pcm16_chunks(chunks, sample_rate=24000):
    if not chunks:
        return b''
    normalized = []
    for chunk in chunks:
        usable = len(chunk) - (len(chunk) % 2)
        if usable >= 2:
            normalized.append(chunk[:usable])
    if not normalized:
        return b''
    if len(normalized) == 1:
        return normalized[0]
    merged = normalized[0]
    for chunk in normalized[1:]:
        merged = _join_pcm16_with_micro_crossfade(merged, chunk, sample_rate=sample_rate)
    return merged


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


def _gemini_tts_system_instruction(language='fr'):
    """Consignes modèle (systemInstruction) — ne doivent pas être lues à voix haute."""
    if (language or 'fr').lower() in ('wo', 'wolof', 'wo-sn'):
        base = GEMINI_TTS_WOLOF_INSTRUCTION
    else:
        base = GEMINI_TTS_FIXED_INSTRUCTION
    return (
        f'{base}\n\n'
        'Règle absolue : tu génères uniquement l’audio du message utilisateur, '
        'mot pour mot, sans lire ni paraphraser ces consignes.'
    )


def _gemini_tts_prompt(spoken_text, language='fr'):
    """Compat tests / ancien format — ne plus envoyer tel quel au modèle TTS lite."""
    instruction = _gemini_tts_system_instruction(language)
    return f'{instruction}\n\nTexte à lire mot pour mot :\n{spoken_text}'


def _edge_fallback_enabled():
    return bool(getattr(settings, 'ASSISTANT_TTS_FALLBACK_EDGE', False))


def _resolve_gemini_voice():
    raw = getattr(settings, 'GEMINI_TTS_VOICE', DEFAULT_GEMINI_VOICE) or DEFAULT_GEMINI_VOICE
    name = raw.strip().title()
    if name not in _GEMINI_FEMALE_VOICES:
        logger.warning(
            'GEMINI_TTS_VOICE=%s inconnue ou non féminine, repli sur %s.',
            raw,
            DEFAULT_GEMINI_VOICE,
        )
        return DEFAULT_GEMINI_VOICE
    return name


def _resolve_gemini_language():
    return (
        getattr(settings, 'GEMINI_TTS_LANGUAGE', DEFAULT_GEMINI_LANGUAGE)
        or DEFAULT_GEMINI_LANGUAGE
    ).strip()


def _gemini_tts_model_supports_system_instruction(model):
    """Les modèles lite-tts n’acceptent pas system_instruction (HTTP 400)."""
    return 'lite-tts' not in (model or '').lower()


def _get_gemini_tts_client():
    global _gemini_tts_client
    if _gemini_tts_client is not None:
        return _gemini_tts_client
    from google import genai

    api_key = getattr(settings, 'GEMINI_API_KEY', '') or ''
    _gemini_tts_client = genai.Client(api_key=api_key)
    return _gemini_tts_client


async def _synthesize_gemini(clean, language='fr'):
    api_key = getattr(settings, 'GEMINI_API_KEY', '') or ''
    if not api_key:
        logger.warning('GEMINI_API_KEY manquante pour la synthèse vocale.')
        return None, None

    model = getattr(
        settings,
        'GEMINI_TTS_MODEL',
        'gemini-2.5-pro-preview-tts',
    )
    voice_name = _resolve_gemini_voice()
    language_code = _resolve_gemini_language()

    try:
        from google.genai import types
    except ImportError:
        logger.exception("Le package google-genai n'est pas installé.")
        return None, None

    client = _get_gemini_tts_client()
    use_style = _gemini_tts_model_supports_system_instruction(model)

    async def _call():
        config_kwargs = {
            'response_modalities': ['AUDIO'],
            'speech_config': types.SpeechConfig(
                language_code=language_code,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name,
                    ),
                ),
            ),
        }
        if use_style:
            config_kwargs['system_instruction'] = _gemini_tts_system_instruction(
                language
            )
        return await client.aio.models.generate_content(
            model=model,
            contents=clean,
            config=types.GenerateContentConfig(**config_kwargs),
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
        pcm_chunks = []
        rate = 24000
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
            pcm_chunks.append(pcm)
        if pcm_chunks:
            pcm = concat_pcm16_chunks(pcm_chunks, sample_rate=rate)
            pcm = finalize_pcm16(pcm, sample_rate=rate)
            wav = pcm16_to_wav(pcm, sample_rate=rate)
            return wav, 'audio/wav'
    logger.warning('Gemini TTS : aucun segment audio dans la réponse.')
    return None, None


CLOUD_TTS_URL = 'https://texttospeech.googleapis.com/v1/text:synthesize'
# Cloud TTS n'accepte pas wo-SN pour les voix Gemini : le wolof est lu en fr-FR
# avec une consigne de style wolof (rendu validé à l'écoute).
CLOUD_TTS_STYLE_FR = (
    'Voix féminine enjouée, accueillante et bienveillante, comme si tu recevais '
    'quelqu’un avec le sourire. Rythme conversationnel naturel.'
)
CLOUD_TTS_STYLE_WOLOF = (
    'Lis en wolof dakarois courant, voix féminine enjouée, chaleureuse et familière, '
    'comme à Dakar. Garde les mots français tels quels.'
)
_cloud_tts_credentials = None
_cloud_tts_http = {}


async def _cloud_tts_token():
    global _cloud_tts_credentials
    creds = _cloud_tts_credentials
    if creds is None:
        from google.oauth2 import service_account

        path = getattr(settings, 'GOOGLE_CLOUD_TTS_CREDENTIALS', '') or ''
        creds = service_account.Credentials.from_service_account_file(
            path,
            scopes=['https://www.googleapis.com/auth/cloud-platform'],
        )
        _cloud_tts_credentials = creds
    if not creds.valid:
        from google.auth.transport.requests import Request

        # Rafraîchissement OAuth synchrone (~1 fois par heure) : hors de la boucle.
        await asyncio.to_thread(creds.refresh, Request())
    return creds.token, creds.project_id


def _cloud_tts_client():
    """Client HTTP partagé par boucle d'événements (connexion TLS gardée chaude)."""
    import httpx

    loop = asyncio.get_running_loop()
    client = _cloud_tts_http.get(id(loop))
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=TTS_TIMEOUT_SECONDS)
        _cloud_tts_http[id(loop)] = client
    return client


async def _synthesize_cloud_gemini(clean, language='fr'):
    wolof = (language or 'fr').lower() in ('wo', 'wolof', 'wo-sn')
    try:
        token, project = await _cloud_tts_token()
        body = {
            'input': {
                'text': clean,
                'prompt': CLOUD_TTS_STYLE_WOLOF if wolof else CLOUD_TTS_STYLE_FR,
            },
            'voice': {
                'languageCode': 'fr-FR' if wolof else _resolve_gemini_language(),
                'name': _resolve_gemini_voice(),
                'modelName': getattr(settings, 'GOOGLE_CLOUD_TTS_MODEL', 'gemini-2.5-flash-tts'),
            },
            'audioConfig': {'audioEncoding': 'LINEAR16', 'sampleRateHertz': 24000},
        }
        response = await _cloud_tts_client().post(
            CLOUD_TTS_URL,
            json=body,
            headers={'Authorization': f'Bearer {token}', 'x-goog-user-project': project},
        )
        if response.status_code != 200:
            logger.warning(
                'Cloud TTS Gemini HTTP %s : %s',
                response.status_code,
                response.text[:300],
            )
            return None, None
        audio = base64.b64decode(response.json().get('audioContent') or '')
    except Exception:
        logger.exception('Échec de la synthèse vocale Cloud TTS Gemini.')
        return None, None
    if not audio:
        return None, None
    return audio, 'audio/wav'


async def _synthesize_chirp(clean):
    """Chirp 3 HD : pas de voix wolof chez Google, le wolof est lu par la même voix fr-FR."""
    api_key = getattr(settings, 'GOOGLE_TTS_API_KEY', '') or ''
    if not api_key:
        logger.warning('GOOGLE_TTS_API_KEY manquante pour Chirp 3 HD.')
        return None, None
    voice = getattr(settings, 'CHIRP_TTS_VOICE', '') or 'fr-FR-Chirp3-HD-Callirrhoe'
    body = {
        'input': {'text': clean},
        'voice': {'languageCode': voice[:5], 'name': voice},
        'audioConfig': {'audioEncoding': 'LINEAR16', 'sampleRateHertz': 24000},
    }
    try:
        response = await _cloud_tts_client().post(
            CLOUD_TTS_URL,
            json=body,
            headers={'x-goog-api-key': api_key},
        )
        if response.status_code != 200:
            logger.warning('Chirp 3 HD HTTP %s : %s', response.status_code, response.text[:300])
            return None, None
        audio = base64.b64decode(response.json().get('audioContent') or '')
    except Exception:
        logger.exception('Échec de la synthèse vocale Chirp 3 HD.')
        return None, None
    if not audio:
        return None, None
    return audio, 'audio/wav'


async def _synthesize_edge_mp3(clean, voice=None):
    voice = voice or getattr(settings, 'EDGE_TTS_VOICE', DEFAULT_VOICE) or DEFAULT_VOICE
    try:
        import edge_tts
    except ImportError:
        logger.exception("Le package edge-tts n'est pas installé.")
        return None, None

    tuning = {
        key: value
        for key, value in (
            ('rate', getattr(settings, 'EDGE_TTS_RATE', '')),
            ('pitch', getattr(settings, 'EDGE_TTS_PITCH', '')),
            ('volume', getattr(settings, 'EDGE_TTS_VOLUME', '')),
        )
        if value
    }
    try:
        communicate = edge_tts.Communicate(clean, voice, **tuning)
        chunks = []

        async def _collect():
            async for chunk in communicate.stream():
                if chunk.get('type') == 'audio' and chunk.get('data'):
                    chunks.append(chunk['data'])

        await asyncio.wait_for(_collect(), timeout=EDGE_TTS_TIMEOUT_SECONDS)
        audio = b''.join(chunks)
        if audio:
            return audio, 'audio/mpeg'
        return None, None
    except Exception as exc:
        logger.warning('Échec de la synthèse vocale edge-tts : %s', str(exc)[:200])
        return None, None


async def synthesize_audio(text, voice=None, rate=None, pitch=None, language=None):
    """
    Convertit un texte en bytes audio + MIME (WAV Gemini ou MP3 Edge).

    rate/pitch ignorés (rythme natif du moteur).
    language: None ou 'fr' (défaut directeur/enseignant) ; 'wo' pour wolof (parent).
    """
    del rate, pitch
    clean = prepare_spoken_text(text)
    if not clean:
        return None, None

    lang = (language or 'fr').lower()
    edge_voice = voice
    if not edge_voice and lang in ('wo', 'wolof', 'wo-sn'):
        edge_voice = getattr(
            settings,
            'EDGE_TTS_VOICE_WOLOF',
            DEFAULT_EDGE_VOICE_WOLOF,
        ) or DEFAULT_EDGE_VOICE_WOLOF

    backend = _tts_backend()
    if backend == 'edge':
        audio, mime = await _synthesize_edge_mp3(clean, voice=edge_voice or voice)
        if audio:
            return audio, mime
        if not getattr(settings, 'GOOGLE_TTS_API_KEY', ''):
            return None, None
        logger.warning('Edge TTS indisponible, repli Chirp 3 HD.')
        return await _synthesize_chirp(clean)

    audio, mime = None, None
    if backend == 'chirp':
        audio, mime = await _synthesize_chirp(clean)
        if audio:
            return audio, mime
        logger.warning('Chirp 3 HD indisponible, repli Gemini AI Studio.')
    if backend == 'cloud_gemini':
        audio, mime = await _synthesize_cloud_gemini(clean, language=lang)
        if audio:
            return audio, mime
        # Repli AI Studio (même voix, quota plus faible) plutôt qu'une phrase muette.
        logger.warning('Cloud TTS Gemini indisponible, repli Gemini AI Studio.')
    audio, mime = await _synthesize_gemini(clean, language=lang)
    if audio:
        logger.debug(
            'TTS gemini ok model=%s bytes=%s',
            getattr(settings, 'GEMINI_TTS_MODEL', ''),
            len(audio),
        )
        return audio, mime
    if not _edge_fallback_enabled():
        logger.warning(
            'Gemini TTS indisponible et ASSISTANT_TTS_FALLBACK_EDGE=false : '
            'phrase sans audio (voix Gemini uniquement).'
        )
        return None, None
    logger.warning(
        'Gemini TTS indisponible, repli Edge (%s) — voix différente d’Aoede.',
        edge_voice or getattr(settings, 'EDGE_TTS_VOICE', DEFAULT_VOICE),
    )
    audio, mime = await _synthesize_edge_mp3(clean, voice=edge_voice or voice)
    if audio:
        return audio, mime
    logger.warning('TTS vide après Gemini et Edge : phrase muette évitée côté file.')
    return None, None


async def synthesize_mp3(text, voice=None, rate=None, pitch=None):
    """Compatibilité : retourne uniquement les bytes (MP3 Edge ou WAV Gemini)."""
    audio, _mime = await synthesize_audio(text, voice=voice, rate=rate, pitch=pitch)
    return audio
