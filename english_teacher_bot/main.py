"""FastAPI app exposing /webhook for Twilio WhatsApp and /audio/ for static replies."""
import logging
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

import audio
import config
import limits
import teacher
import whatsapp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("english_teacher_bot")

app = FastAPI(title="English Teacher Bot")
app.mount("/audio", StaticFiles(directory=config.AUDIO_DIR), name="audio")


@app.get("/")
async def root():
    return {"status": "ok", "service": "english-teacher-bot"}


@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request):
    """Twilio sends form-encoded webhooks. We respond 200 fast and process inline.

    Twilio fields we care about:
      - From: "whatsapp:+5511..."
      - Body: text body (may be empty if media-only)
      - NumMedia: number of media attachments
      - MediaUrl0, MediaContentType0: first media item
    """
    form = await request.form()
    sender = form.get("From", "")
    body = (form.get("Body") or "").strip()
    num_media = int(form.get("NumMedia") or 0)
    media_url = form.get("MediaUrl0")
    media_type = (form.get("MediaContentType0") or "").lower()

    logger.info("Incoming from=%s media=%d type=%s body=%r", sender, num_media, media_type, body)

    # Cost / abuse protection
    block = limits.check(sender)
    if block:
        logger.warning("Blocked %s: %s", sender, block)
        try:
            whatsapp.send_text(sender, block)
        except Exception:
            logger.exception("Failed to send block message")
        return ""

    try:
        await _handle_message(sender, body, num_media, media_url, media_type)
    except Exception:
        logger.exception("Error handling message")
        try:
            whatsapp.send_text(sender, "Sorry, something went wrong on my side. Please try again.")
        except Exception:
            logger.exception("Also failed to send error message")

    # Twilio expects a 200 with TwiML or empty body. We're replying out-of-band via REST API.
    return ""


async def _handle_message(
    sender: str,
    body: str,
    num_media: int,
    media_url: Optional[str],
    media_type: str,
) -> None:
    # Text-only message
    if num_media == 0:
        cmd = body.lower()
        if cmd in config.RESET_COMMANDS:
            teacher.reset_history(sender)
            whatsapp.send_text(sender, "Conversation reset. Send me a voice message in English to start fresh!")
            return
        if cmd in config.TRANSLATE_COMMANDS:
            translation = teacher.get_last_translation(sender)
            if translation:
                whatsapp.send_text(sender, f"🌐 *Tradução*\n{translation}")
            else:
                whatsapp.send_text(sender, "Não tenho nada pra traduzir ainda. Manda um áudio primeiro!")
            return
        whatsapp.send_text(
            sender,
            "Hi! I'm your English practice partner. Send me a voice message in English and I'll reply with feedback.\n\n"
            "Commands: *reset* (clear history) · *traduzir* (translate my last reply)",
        )
        return

    # Reject non-audio media
    if not media_type.startswith("audio"):
        whatsapp.send_text(sender, "Please send a voice message (audio) in English so I can help you practice.")
        return

    if not media_url:
        whatsapp.send_text(sender, "I couldn't find your audio. Could you send it again?")
        return

    # Audio pipeline
    try:
        input_path = audio.download_twilio_media(media_url)
    except audio.AudioTooLargeError as e:
        logger.warning("Audio too large from %s: %s", sender, e)
        whatsapp.send_text(sender, f"That audio is too long. Please keep it under {config.MAX_AUDIO_MB}MB (~1-2 min).")
        return
    try:
        transcript = audio.transcribe(input_path)
    finally:
        audio.safe_remove(input_path)

    if not transcript:
        whatsapp.send_text(sender, "I couldn't hear anything in that audio. Could you try again?")
        return

    feedback = teacher.get_feedback(sender, transcript)
    logger.info("Teacher feedback: %r", feedback)

    # 1) Only send the feedback "card" when there are real corrections to show.
    #    If the student nailed it, just reply with audio — feels natural.
    if teacher.has_corrections(feedback):
        card = teacher.format_feedback_card(feedback)
        whatsapp.send_text(sender, card)

    # 2) Generate and send the spoken reply as audio
    spoken = feedback.get("spoken_reply", "").strip()
    if spoken:
        audio_filename = audio.synthesize(spoken)
        audio_url = audio.public_audio_url(audio_filename)
        whatsapp.send_audio(sender, audio_url)
