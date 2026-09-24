"""
Wolof v1 — préférence langue parent, heuristiques STT/TTS (Par3).
"""
from __future__ import annotations

import re

SESSION_LANG_KEY = 'aria_parent_lang'
VALID_PREFS = frozenset({'auto', 'fr', 'wo'})

STT_FR = 'fr-FR'
STT_WO = 'wo-SN'

# Mots / expressions wolof fréquents (latin) — heuristique légère, pas de blocage métier.
_WOLOF_MARKERS = re.compile(
    r'\b(?:'
    r'na\s+nga\s+def|nanga\s+def|j[ëe]r[ëe]j[ëe]f|jerejef|'
    r'waaw|d[ée]ed[ée]et|déedéet|xale|xale\s*bi|'
    r'dama|dama\s+la|wax|wax\s+ma|ci\s+wolof|'
    r'man\s+degg|dimbali|jamm|yow|sama|sa\s+xale|'
    r'ndax|lu\s+la\s+tàmbale|tàmbale|'
    r'mbaa|lu\s+la\s+war|'
    r'akk\s+jamm|ba\s+beneen|'
    r'ñu|ñun|'
    r'jëf|jëf\s+jëf'
    r')\b',
    re.IGNORECASE,
)

def normalize_lang_preference(value) -> str:
    raw = (value or 'auto').strip().lower()
    if raw in ('wolof', 'wo', 'sn'):
        return 'wo'
    if raw in ('fr', 'francais', 'français', 'french'):
        return 'fr'
    if raw in VALID_PREFS:
        return raw
    return 'auto'


def wolof_marker_score(text: str) -> int:
    if not text:
        return 0
    score = len(_WOLOF_MARKERS.findall(text))
    lowered = text.lower()
    for token in ('ñ', 'à', 'ë', 'ó'):
        if token in lowered:
            score += 1
    return score


def detect_text_language(text: str) -> str:
    """
    Retourne 'wo', 'fr' ou 'mixed' (heuristique sur le texte utilisateur / réponse).
    """
    cleaned = (text or '').strip()
    if not cleaned:
        return 'fr'
    wo = wolof_marker_score(cleaned)
    latin_words = len(re.findall(r'[a-zA-ZÀ-ÿ]{2,}', cleaned))
    if wo >= 2:
        return 'wo'
    if wo == 1 and latin_words <= 6:
        return 'wo'
    if wo >= 1 and latin_words >= 8:
        return 'mixed'
    return 'fr'


def resolve_user_turn_language(text: str, preference: str = 'auto') -> str:
    pref = normalize_lang_preference(preference)
    if pref == 'fr':
        return 'fr'
    if pref == 'wo':
        return 'wo'
    detected = detect_text_language(text)
    if detected == 'mixed':
        return 'wo' if wolof_marker_score(text) else 'fr'
    return detected


def resolve_tts_language(
    response_text: str,
    user_turn_language: str | None = None,
    preference: str = 'auto',
) -> str:
    """
    'fr' ou 'wo' pour synthesize_audio(language=...).
    """
    pref = normalize_lang_preference(preference)
    if pref == 'fr':
        return 'fr'
    if pref == 'wo':
        return 'wo'
    resp_lang = detect_text_language(response_text)
    if resp_lang == 'wo' or (resp_lang == 'mixed' and wolof_marker_score(response_text) >= 1):
        return 'wo'
    if user_turn_language == 'wo':
        return 'wo'
    return 'fr'


def stt_language_order(preference: str = 'auto', hint_text: str | None = None) -> list[str]:
    pref = normalize_lang_preference(preference)
    if pref == 'fr':
        return [STT_FR]
    if pref == 'wo':
        return [STT_WO, STT_FR]
    hint = detect_text_language(hint_text or '')
    if hint == 'wo':
        return [STT_WO, STT_FR]
    return [STT_FR, STT_WO]


def pick_best_stt_transcript(candidates: dict[str, str]) -> tuple[str, str, bool]:
    """
    candidates: locale -> transcript
    Retourne (texte, locale_utilisée, faible_qualité_wolof).
    """
    fr_text = (candidates.get(STT_FR) or '').strip()
    wo_text = (candidates.get(STT_WO) or '').strip()

    if wo_text and not fr_text:
        weak = len(wo_text) < 3 or wolof_marker_score(wo_text) == 0 and len(wo_text) < 8
        return wo_text, STT_WO, weak

    if fr_text and not wo_text:
        return fr_text, STT_FR, False

    if not fr_text and not wo_text:
        return '', STT_FR, True

    wo_score = wolof_marker_score(wo_text) + len(wo_text) * 0.05
    fr_score = wolof_marker_score(fr_text) * 0.5 + len(fr_text) * 0.05
    if wo_score > fr_score + 0.5:
        weak = len(wo_text) < 4
        return wo_text, STT_WO, weak
    return fr_text, STT_FR, False


STT_WOLOF_WEAK_MESSAGE = (
    'Dafa am lu nekk ci dégg gi ci Wolof. Bindal sa laaj ci Wolof ci suuf, '
    'walla waxaat ci Français. '
    'Je n’ai pas bien saisi votre message en wolof : écrivez votre question ci-dessous '
    'en wolof ou réessayez en français.'
)
