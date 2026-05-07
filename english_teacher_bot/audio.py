"""Audio pipeline: download from Twilio, Whisper STT, OpenAI TTS.

TTS is isolated here so swapping OpenAI for ElevenLabs is a one-function change.
"""
import logging
import os
import uuid

import httpx
from openai import OpenAI

import config

logger = logging.getLogger(__name__)

_openai = OpenAI(api_key=config.OPENAI_API_KEY)

os.makedirs(config.AUDIO_DIR, exist_ok=True)


class AudioTooLargeError(Exception):
    pass


def download_twilio_media(media_url: str) -> str:
    """Download a media file from Twilio (auth required) into temp_audio/.

    Raises AudioTooLargeError if the file exceeds MAX_AUDIO_MB (cost protection).
    """
    logger.info("Downloading media: %s", media_url)
    auth = (config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    max_bytes = config.MAX_AUDIO_MB * 1024 * 1024
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(media_url, auth=auth)
        response.raise_for_status()
        if len(response.content) > max_bytes:
            raise AudioTooLargeError(
                f"Audio is {len(response.content) / 1024 / 1024:.1f}MB, max is {config.MAX_AUDIO_MB}MB"
            )
        content_type = response.headers.get("content-type", "audio/ogg")
        ext = "ogg" if "ogg" in content_type else "mp3"
        path = os.path.join(config.AUDIO_DIR, f"in_{uuid.uuid4().hex}.{ext}")
        with open(path, "wb") as f:
            f.write(response.content)
    logger.info("Saved input audio: %s (%d bytes)", path, len(response.content))
    return path


def transcribe(audio_path: str) -> str:
    """Whisper STT, forced to English."""
    logger.info("Transcribing %s", audio_path)
    with open(audio_path, "rb") as f:
        result = _openai.audio.transcriptions.create(
            model=config.WHISPER_MODEL,
            file=f,
            language="en",
        )
    text = (result.text or "").strip()
    logger.info("Transcription: %r", text)
    return text


def synthesize(text: str) -> str:
    """OpenAI TTS → returns the path of the generated mp3 inside temp_audio/."""
    filename = f"out_{uuid.uuid4().hex}.mp3"
    path = os.path.join(config.AUDIO_DIR, filename)
    logger.info("Synthesizing TTS → %s", path)
    response = _openai.audio.speech.create(
        model=config.TTS_MODEL,
        voice=config.TTS_VOICE,
        input=text,
    )
    response.stream_to_file(path)
    return filename


def public_audio_url(filename: str) -> str:
    return f"{config.PUBLIC_URL}/audio/{filename}"


def safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
