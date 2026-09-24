"""
Transcription vocale de secours (PCM 16 kHz) via l'API Web Speech de Google.
Les dictées longues sont découpées en segments pour rester dans la limite du service.
"""
import json
import logging

import httpx

logger = logging.getLogger(__name__)

GOOGLE_STT_URL = 'https://www.google.com/speech-api/v2/recognize'
GOOGLE_STT_KEY = 'AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw'
STT_TIMEOUT = 30.0
SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2
CHUNK_SECONDS = 12
MAX_SECONDS = 90
MAX_PCM_BYTES = BYTES_PER_SECOND * MAX_SECONDS
CHUNK_BYTES = BYTES_PER_SECOND * CHUNK_SECONDS


def _extract_pcm(payload):
    raw = payload or b''
    if raw[:4] == b'RIFF' and raw[8:12] == b'WAVE':
        data_at = raw.find(b'data')
        if data_at >= 0 and data_at + 8 <= len(raw):
            return raw[data_at + 8:]
    return raw


async def _transcribe_chunk(client, pcm, language):
    response = await client.post(
        GOOGLE_STT_URL,
        params={
            'client': 'chromium',
            'lang': language,
            'key': GOOGLE_STT_KEY,
            'output': 'json',
        },
        headers={'Content-Type': 'audio/l16; rate=16000'},
        content=pcm,
    )
    response.raise_for_status()
    transcript = ''
    for line in (response.text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        results = payload.get('result') or []
        for result in results:
            alternatives = result.get('alternative') or []
            if alternatives:
                piece = (alternatives[0].get('transcript') or '').strip()
                if piece:
                    transcript = piece
    return transcript


async def transcribe_pcm16_multi(audio_bytes, languages=None):
    """
    Transcrit avec plusieurs locales (parent Wolof v1).
    Retourne {locale: transcript}.
    """
    langs = list(languages or ['fr-FR'])
    pcm = _extract_pcm(audio_bytes)
    if not pcm or len(pcm) < 3200:
        return {lang: '' for lang in langs}
    if len(pcm) > MAX_PCM_BYTES:
        pcm = pcm[:MAX_PCM_BYTES]

    out = {lang: '' for lang in langs}
    try:
        async with httpx.AsyncClient(timeout=STT_TIMEOUT) as client:
            for lang in langs:
                pieces = []
                for start in range(0, len(pcm), CHUNK_BYTES):
                    chunk = pcm[start:start + CHUNK_BYTES]
                    if len(chunk) < 3200:
                        continue
                    text = await _transcribe_chunk(client, chunk, lang)
                    if text:
                        pieces.append(text)
                out[lang] = ' '.join(pieces).strip()
    except Exception:
        logger.exception('Échec transcription multi-langue.')
    return out


async def transcribe_pcm16(audio_bytes, language='fr-FR'):
    """
    Transcrit du PCM 16-bit mono 16 kHz (éventuellement encapsulé WAV).
    Retourne une chaîne vide si la reconnaissance échoue.
    """
    pcm = _extract_pcm(audio_bytes)
    if not pcm or len(pcm) < 3200:
        return ''
    if len(pcm) > MAX_PCM_BYTES:
        pcm = pcm[:MAX_PCM_BYTES]

    pieces = []
    try:
        async with httpx.AsyncClient(timeout=STT_TIMEOUT) as client:
            for start in range(0, len(pcm), CHUNK_BYTES):
                chunk = pcm[start:start + CHUNK_BYTES]
                if len(chunk) < 3200:
                    continue
                text = await _transcribe_chunk(client, chunk, language)
                if text:
                    pieces.append(text)
    except Exception:
        logger.exception("Échec de la transcription vocale.")
        return ' '.join(pieces).strip()

    return ' '.join(pieces).strip()
