"""Dédoublonnage flux texte assistant (stream + TTS)."""
from __future__ import annotations

import re


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


def finalize_assistant_spoken(*parts: str) -> str:
    """Texte oral unique pour TTS + historique."""
    merged = ' '.join((p or '').strip() for p in parts if (p or '').strip())
    return collapse_near_duplicate_reply(merged.strip())
