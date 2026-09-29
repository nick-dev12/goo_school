"""Dédoublonnage flux texte assistant (stream + TTS)."""
from __future__ import annotations

import json
import re

ARIA_SUGGESTIONS_MARKER = re.compile(
    r'\[\[ARIA_SUGGESTIONS:\s*(\[[\s\S]*?\])\s*\]\]\s*$',
)
ARIA_SUGGESTIONS_INCOMPLETE = re.compile(r'\[\[ARIA_SUGGESTIONS:[\s\S]*$')


def _fold(text: str) -> str:
    return re.sub(r'\s+', '', (text or '').lower())


def merge_stream_delta(accumulated: str, delta: str) -> tuple[str, str]:
    """
    Fusionne un delta dans le texte déjà streamé.
    Retourne (nouveau_cumul, morceau_à_émettre) — morceau vide si doublon.
    """
    piece = delta or ''
    prev = accumulated or ''
    if not piece:
        return prev, ''
    if not prev:
        return piece, piece
    if piece == prev:
        return prev, ''
    if prev.endswith(piece):
        return prev, ''
    if piece.startswith(prev):
        extra = piece[len(prev):]
        if not extra.strip():
            return prev, ''
        return prev + extra, extra
    folded_piece = _fold(piece)
    folded_prev = _fold(prev)
    if folded_piece == folded_prev:
        return prev, ''
    if (
        len(folded_piece) > len(folded_prev)
        and folded_piece.startswith(folded_prev)
        and _fold(piece[len(prev):]).startswith(folded_prev[: max(24, len(folded_prev) // 2)])
    ):
        return prev, ''
    if len(folded_piece) >= 2 * len(folded_prev) and folded_prev and folded_piece == folded_prev * 2:
        return prev, ''
    return prev + piece, piece


def _prefix_repeat_cut(norm: str) -> str | None:
    """Détecte « phrase A + phrase A » même avec espaces différents."""
    length = len(norm)
    if length < 40:
        return None
    min_len = max(30, int(length * 0.28))
    max_len = min(length - 30, int(length * 0.72))
    for cut in range(min_len, max_len + 1):
        left = norm[:cut].strip()
        right = norm[cut:].strip()
        if not left or not right:
            continue
        a = _fold(left)
        b = _fold(right)
        if a == b:
            return left
        if len(a) >= 24 and b.startswith(a[: max(20, int(len(a) * 0.82))]):
            return left
    return None


def collapse_near_duplicate_reply(text: str) -> str:
    """Supprime une répétition quasi identique (souvent stream + réémission complète)."""
    raw = (text or '').strip()
    if len(raw) < 40:
        return raw
    norm = re.sub(r'\s+', ' ', raw).strip()
    cut = _prefix_repeat_cut(norm)
    if cut:
        return cut
    mid = len(norm) // 2
    for offset in range(-20, 21):
        split = mid + offset
        if split < 30 or split > len(norm) - 30:
            continue
        left = norm[:split].strip()
        right = norm[split:].strip()
        if not left or not right:
            continue
        a = _fold(left)
        b = _fold(right)
        if a == b:
            return left
        if len(a) > 40 and (b.startswith(a[: int(len(a) * 0.88)]) or a.startswith(b[: int(len(b) * 0.88)])):
            return left if len(left) >= len(right) else right
    return raw


def split_spoken_and_suggestions(text: str) -> tuple[str, list[dict]]:
    """
    Sépare le texte oral des suggestions UI [[ARIA_SUGGESTIONS:[...]]].
    Retire aussi un marqueur incomplet en fin de flux (stream).
    """
    raw = (text or '').strip()
    if not raw:
        return '', []
    incomplete = ARIA_SUGGESTIONS_INCOMPLETE.search(raw)
    if incomplete and not ARIA_SUGGESTIONS_MARKER.search(raw):
        raw = raw[: incomplete.start()].rstrip()
    match = ARIA_SUGGESTIONS_MARKER.search(raw)
    if not match:
        return raw, []
    spoken = raw[: match.start()].strip()
    suggestions: list[dict] = []
    try:
        parsed = json.loads(match.group(1))
        if isinstance(parsed, list):
            from school_admin.services.assistant_tools import normalize_suggestions

            suggestions = normalize_suggestions(parsed, limit=3)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return spoken, suggestions


def finalize_assistant_turn_text(*parts: str) -> tuple[str, list[dict]]:
    """Texte oral + suggestions natives pour fin de tour."""
    merged = ' '.join((p or '').strip() for p in parts if (p or '').strip())
    collapsed = collapse_near_duplicate_reply(merged.strip())
    return split_spoken_and_suggestions(collapsed)


def finalize_assistant_spoken(*parts: str) -> str:
    """Texte oral unique pour TTS + historique."""
    spoken, _ = finalize_assistant_turn_text(*parts)
    return spoken


DEFAULT_MAX_TTS_SEGMENT_CHARS = 150
DEFAULT_MIN_TTS_CLAUSE_CHARS = 120

SENTENCE_BOUNDARY_RE = re.compile(r'(.+?(?:[.!?…]|\n)+)\s*', re.DOTALL)
CLAUSE_BOUNDARY_RE = re.compile(r'(.{120,}?[,;:])\s+')


class SpokenSentenceBuffer:
    """Découpe un flux oral en phrases/clauses prêtes pour la synthèse TTS."""

    def __init__(
        self,
        max_chars=DEFAULT_MAX_TTS_SEGMENT_CHARS,
        min_clause=DEFAULT_MIN_TTS_CLAUSE_CHARS,
    ):
        self.buffer = ''
        self.max_chars = max_chars
        self.min_clause = min_clause

    def feed(self, delta: str) -> list[str]:
        self.buffer += delta or ''
        sentences: list[str] = []
        while True:
            match = SENTENCE_BOUNDARY_RE.match(self.buffer)
            if not match and len(self.buffer) >= self.min_clause:
                match = CLAUSE_BOUNDARY_RE.match(self.buffer)
            if match:
                sentence = match.group(1).strip()
                self.buffer = self.buffer[match.end():]
                if sentence:
                    sentences.extend(self._split_long(sentence))
                continue
            forced = self._force_cut()
            if not forced:
                break
            sentences.append(forced)
        return sentences

    def _force_cut(self) -> str:
        if len(self.buffer) < self.max_chars:
            return ''
        cut = self.buffer.rfind(' ', 0, self.max_chars)
        if cut < 40:
            cut = self.max_chars
        sentence = self.buffer[:cut].strip()
        self.buffer = self.buffer[cut:].lstrip()
        return sentence

    def _split_long(self, sentence: str) -> list[str]:
        if len(sentence) <= self.max_chars:
            return [sentence]
        parts: list[str] = []
        rest = sentence
        while len(rest) > self.max_chars:
            cut = rest.rfind(' ', 0, self.max_chars)
            if cut < 40:
                cut = self.max_chars
            parts.append(rest[:cut].strip())
            rest = rest[cut:].lstrip()
        if rest:
            parts.append(rest)
        return [part for part in parts if part]

    def flush(self) -> str:
        leftover = self.buffer.strip()
        self.buffer = ''
        return leftover


# Alias historique (tests / consumer).
SentenceAssembler = SpokenSentenceBuffer
MAX_TTS_SEGMENT_CHARS = DEFAULT_MAX_TTS_SEGMENT_CHARS
MIN_TTS_CLAUSE_CHARS = DEFAULT_MIN_TTS_CLAUSE_CHARS
