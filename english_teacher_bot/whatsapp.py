"""Twilio WhatsApp client wrapper."""
import logging
from typing import Optional

from twilio.rest import Client

import config

logger = logging.getLogger(__name__)

_client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)


def send_text(to: str, body: str) -> None:
    logger.info("Sending text to %s", to)
    _client.messages.create(
        from_=config.TWILIO_WHATSAPP_NUMBER,
        to=to,
        body=body,
    )


def send_audio(to: str, audio_url: str, caption: Optional[str] = None) -> None:
    logger.info("Sending audio to %s: %s", to, audio_url)
    _client.messages.create(
        from_=config.TWILIO_WHATSAPP_NUMBER,
        to=to,
        body=caption or "",
        media_url=[audio_url],
    )
