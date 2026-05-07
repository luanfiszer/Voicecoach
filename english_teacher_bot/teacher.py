"""English teacher persona — Claude returns structured feedback + spoken reply.

Output shape (JSON returned by Claude):
{
  "original":       "<what the student said, verbatim>",
  "corrected":      "<corrected version with WhatsApp formatting: ~wrong~ *right*>",
  "tip":            "<short tip in accessible English>",
  "spoken_reply":   "<conversational reply, 3-5 sentences, natural English, no markdown>",
  "translation_pt": "<Portuguese translation of spoken_reply>"
}

History stored in memory: {phone: [{"role", "content"}]}.
Also stored: last translation per user (for the `traduzir` command).
"""
import json
import logging
import re
from typing import Dict, List, Optional

from anthropic import Anthropic

import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a friendly English teacher chatting with a Brazilian student over WhatsApp voice messages.

Your job each turn: react to what the student said, subtly correct mistakes, and keep the conversation going.

You MUST respond with a single valid JSON object — no prose before or after, no markdown code fences. Schema:

{
  "has_mistakes": true | false,
  "original": "the student's sentence as transcribed (verbatim)",
  "corrected": "the same sentence rewritten correctly. Mark removed/wrong words with ~tildes~ and the correct replacement with *asterisks*. Empty string if has_mistakes is false.",
  "tip": "ONE short tip in simple, accessible English (1-2 sentences). Empty string if has_mistakes is false.",
  "spoken_reply": "Your conversational reply, 3-5 sentences MAX. React to what they said, ask a follow-up, naturally use the corrected form. NO markdown, NO bullets — this becomes audio. Warm and encouraging tone.",
  "translation_pt": "Brazilian Portuguese translation of spoken_reply."
}

Rules:
- has_mistakes = true ONLY when the sentence has real grammar errors, wrong word choice, or unnatural phrasing. Minor things like missing punctuation or slight informality DO NOT count.
- When has_mistakes = false: leave "corrected" and "tip" as empty strings. Just respond conversationally via spoken_reply.
- When has_mistakes = true: fill "corrected" with marked-up version (~wrong~ *right*) and "tip" with one short fix in simple English. Cover either a grammar fix OR a pronunciation hint, not both. Spell phonetic hints like 'COMF-ter-ble'.
- spoken_reply MUST be plain text (no asterisks, no tildes, no symbols) — it goes to TTS.
- Keep "tip" focused on ONE thing. Do not list multiple corrections.
- Always reply in valid JSON. No trailing commas. Escape quotes inside strings.
"""

_client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
_history: Dict[str, List[dict]] = {}
_last_translation: Dict[str, str] = {}


def reset_history(user_id: str) -> None:
    _history.pop(user_id, None)
    _last_translation.pop(user_id, None)
    logger.info("History reset for %s", user_id)


def get_last_translation(user_id: str) -> Optional[str]:
    return _last_translation.get(user_id)


def _trim(messages: List[dict]) -> List[dict]:
    if len(messages) > config.MAX_HISTORY_ITEMS:
        return messages[-config.MAX_HISTORY_ITEMS:]
    return messages


def _extract_json(text: str) -> dict:
    """Tolerant JSON extraction — strips code fences if Claude added them."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


def get_feedback(user_id: str, user_text: str) -> dict:
    """Returns the structured feedback dict from Claude."""
    history = _history.setdefault(user_id, [])
    history.append({"role": "user", "content": user_text})
    history[:] = _trim(history)

    logger.info("Calling Claude for %s (%d history items)", user_id, len(history))
    response = _client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=history,
    )
    raw = response.content[0].text.strip()

    try:
        data = _extract_json(raw)
    except json.JSONDecodeError:
        logger.exception("Claude returned invalid JSON: %r", raw)
        # Fallback: treat the whole thing as a spoken reply
        data = {
            "original": user_text,
            "corrected": user_text,
            "tip": "",
            "spoken_reply": raw,
            "translation_pt": "",
        }

    # Store assistant turn in history using the spoken_reply (what the student "heard")
    history.append({"role": "assistant", "content": data.get("spoken_reply", "")})
    history[:] = _trim(history)

    if data.get("translation_pt"):
        _last_translation[user_id] = data["translation_pt"]

    return data


def has_corrections(data: dict) -> bool:
    """True when the structured feedback contains corrections worth showing."""
    if not data.get("has_mistakes"):
        return False
    return bool(data.get("corrected", "").strip()) or bool(data.get("tip", "").strip())


def format_feedback_card(data: dict) -> str:
    """WhatsApp-friendly text card. Uses *bold* and ~strikethrough~ markdown.

    Only call when has_corrections(data) is True.
    """
    parts = []
    parts.append("🗣️ *You said*")
    parts.append(f"_{data.get('original', '').strip()}_")
    corrected = data.get("corrected", "").strip()
    if corrected:
        parts.append("")
        parts.append("✍️ *Better way*")
        parts.append(corrected)
    tip = data.get("tip", "").strip()
    if tip:
        parts.append("")
        parts.append("💡 *Tip*")
        parts.append(tip)
    parts.append("")
    parts.append("🎧 _Listen to my reply below 👇_")
    return "\n".join(parts)
