"""
Transcription vocale de secours (PCM 16 kHz) via l'API Web Speech de Google.
"""
import json
import logging

import httpx

logger = logging.getLogger(__name__)

GOOGLE_STT_URL = 'https://www.google.com/speech-api/v2/recognize'
GOOGLE_STT_KEY = 'AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw'
STT_TIMEOUT = 20.0
MAX_PCM_BYTES = 16000 * 2 * 20


def _extract_pcm(payload):
    raw = payload or b''
    if raw[:4] == b'RIFF' and raw[8:12] == b'WAVE':
        data_at = raw.find(b'data')
        if data_at >= 0 and data_at + 8 <= len(raw):
            return raw[data_at + 8:]
    return raw


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

    try:
        async with httpx.AsyncClient(timeout=STT_TIMEOUT) as client:
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
    except Exception:
        logger.exception("Échec de la transcription vocale.")
        return ''

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
