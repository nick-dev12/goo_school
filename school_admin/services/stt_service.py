"""
Transcription des notes vocales (PCM 16 kHz).

Gemini (multimodal) transcrit le français, le wolof et leur mélange ; l'API Web Speech
de Google (fr-FR) ne sert plus que de secours : elle ne reconnaît pas le wolof (wo-SN
renvoie de l'anglais inventé). Les dictées longues y sont découpées en segments.
"""
import io
import json
import logging
import wave

import httpx
from django.conf import settings

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


GEMINI_STT_PROMPT = (
    'Transcris exactement ce message vocal adressé à Aria, assistante d’une école au Sénégal. '
    'La personne parle français, wolof du Sénégal, ou mélange les deux. '
    'Écris le wolof en alphabet latin avec l’orthographe wolof usuelle '
    '(ex. « Naka nga def », « ndax », « ci », « ak », « ñaari »), garde les mots français '
    'tels quels, n’ajoute rien et ne traduis pas. Message vide ou inaudible : texte vide. '
    'Réponds en JSON : {"text": "...", "lang": "fr" | "wo" | "mixed"}'
)


def _pcm_to_wav(pcm):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm)
    return buffer.getvalue()


async def transcribe_with_gemini(audio_bytes):
    """
    Transcrit une note vocale FR / wolof / mixte avec Gemini.
    Retourne (texte, langue) avec langue dans {'fr', 'wo', 'mixed'} ; ('', 'fr') si échec.
    """
    pcm = _extract_pcm(audio_bytes)
    if not pcm or len(pcm) < 3200:
        return '', 'fr'
    pcm = pcm[:MAX_PCM_BYTES]
    try:
        from google.genai import types

        from school_admin.services.gemini_context_cache import _get_native_client

        response = await _get_native_client().aio.models.generate_content(
            model=getattr(settings, 'GEMINI_MODEL', 'gemini-3.6-flash') or 'gemini-3.6-flash',
            contents=[
                GEMINI_STT_PROMPT,
                types.Part.from_bytes(data=_pcm_to_wav(pcm), mime_type='audio/wav'),
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type='application/json',
                thinking_config=types.ThinkingConfig(thinking_level='low'),
            ),
        )
        payload = json.loads(response.text or '{}')
    except Exception:
        logger.exception('Échec de la transcription Gemini.')
        return '', 'fr'
    text = str(payload.get('text') or '').strip()
    lang = str(payload.get('lang') or 'fr').strip().lower()
    if lang not in ('fr', 'wo', 'mixed'):
        lang = 'fr'
    return text, lang


async def transcribe_voice_note(audio_bytes):
    """Gemini d'abord (wolof compris), puis Web Speech fr-FR en secours. Retourne (texte, langue)."""
    text, lang = await transcribe_with_gemini(audio_bytes)
    if text:
        return text, lang
    return await transcribe_pcm16(audio_bytes), 'fr'
