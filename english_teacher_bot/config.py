"""Centralized configuration loaded from environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# API keys
ANTHROPIC_API_KEY = _required("ANTHROPIC_API_KEY")
OPENAI_API_KEY = _required("OPENAI_API_KEY")

# Twilio
TWILIO_ACCOUNT_SID = _required("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = _required("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = _required("TWILIO_WHATSAPP_NUMBER")

# Public URL where Twilio can reach our /audio/ static files (e.g. ngrok)
PUBLIC_URL = _required("PUBLIC_URL").rstrip("/")

# Models
CLAUDE_MODEL = "claude-sonnet-4-20250514"
WHISPER_MODEL = "whisper-1"
TTS_MODEL = "tts-1"
TTS_VOICE = "nova"

# Conversation
MAX_HISTORY_ITEMS = 20  # 10 exchanges (user + assistant)
RESET_COMMANDS = {"reset", "clear", "start over"}
TRANSLATE_COMMANDS = {"traduzir", "translate", "tradução", "traducao"}

# Paths
AUDIO_DIR = "temp_audio"

# --- Cost / abuse protection ---
# Max input audio size in MB (Whisper bills per minute, ~1MB/min for ogg)
MAX_AUDIO_MB = int(os.getenv("MAX_AUDIO_MB", "2"))
# Max messages per user per minute (simple in-memory rate limit)
MAX_MSGS_PER_MINUTE = int(os.getenv("MAX_MSGS_PER_MINUTE", "5"))
# Max total messages per user per day (hard cap)
MAX_MSGS_PER_DAY = int(os.getenv("MAX_MSGS_PER_DAY", "100"))
# Allowlist of phone numbers (comma-separated, e.g. "whatsapp:+5511...,whatsapp:+5511...")
# If empty, anyone who messages the sandbox can trigger the bot.
ALLOWED_NUMBERS = {n.strip() for n in os.getenv("ALLOWED_NUMBERS", "").split(",") if n.strip()}
