# English Teacher Bot

Personal English teacher over WhatsApp voice messages. You record an audio in English, the bot transcribes it, replies as a friendly teacher with subtle corrections and one pronunciation tip, then speaks the reply back to you on WhatsApp.

Inspired by apps like BeConfident — same idea, but personal, hackable, and runs on your machine.

## How it works

```
WhatsApp audio
    ↓
Twilio Sandbox  →  webhook (FastAPI)
                       ↓
                 Whisper STT  (audio → text)
                       ↓
                 Claude       (teacher response with feedback)
                       ↓
                 OpenAI TTS   (reply → audio)
                       ↓
WhatsApp audio  ←  Twilio
```

For each message, the user receives:
1. A **text card** with: what they said, the corrected version, a tip in accessible English
2. An **audio reply** with the teacher's natural conversational response

## Stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.9+ | Personal preference |
| Web framework | FastAPI | Async, modern, fast |
| WhatsApp | Twilio Sandbox | Free trial, easiest for development |
| Speech-to-text | OpenAI Whisper (`whisper-1`) | Best STT available |
| LLM | Anthropic Claude (`claude-sonnet-4-20250514`) | Natural, warm replies |
| Text-to-speech | OpenAI TTS (`tts-1`, voice `nova`) | Cheap, decent quality |
| Tunneling | ngrok (dev) | Expose local webhook to Twilio |

## Project structure

```
english_teacher_bot/
├── main.py            # FastAPI app + /webhook orchestration
├── teacher.py         # Claude system prompt, history, structured feedback
├── audio.py           # Twilio media download, Whisper STT, OpenAI TTS
├── whatsapp.py        # Twilio REST client (send text/audio)
├── limits.py          # Rate limiting + daily caps + allowlist
├── config.py          # .env loader, validates required vars
├── requirements.txt
├── .env.example
├── README.md          # ← you are here
├── SETUP.md           # full setup guide (Mac, Linux, Windows)
├── COMMANDS.md        # quick command reference
└── temp_audio/        # generated mp3s (served at /audio/)
```

## Teacher behavior

The teacher persona is defined in `teacher.py` and follows these rules:
- Always replies in English (translation provided on demand via `traduzir`)
- Subtly corrects mistakes by restating the correct form
- Gives ONE pronunciation tip per message
- 3-5 sentences max (becomes audio)
- Warm, encouraging, conversational tone — not a strict teacher

Output is structured JSON parsed by the backend:
- `original` — what the student said
- `corrected` — corrected version with `~wrong~` and `*right*` markers
- `tip` — one short tip in simple English
- `spoken_reply` — natural reply for TTS
- `translation_pt` — Portuguese translation (used by `traduzir` command)

## Supported user commands

Send these as plain text in WhatsApp:

| Command | Effect |
|---|---|
| `reset` / `clear` / `start over` | Wipes your conversation history |
| `traduzir` *(coming soon)* | Sends Portuguese translation of the last reply |

Any other plain text → bot replies asking for an audio.

## Cost & safety

- Estimated cost: **$3-10/month** for personal use (~10 min/day)
- Hard caps configured per-user in `.env`:
  - `MAX_AUDIO_MB` — rejects audios above this size (default: 2MB ≈ 1-2 min)
  - `MAX_MSGS_PER_MINUTE` — rate limit per user (default: 5)
  - `MAX_MSGS_PER_DAY` — daily cap per user (default: 100)
  - `ALLOWED_NUMBERS` — comma-separated allowlist (recommended: only your own number)
- Spend limits should also be set on each provider's dashboard (OpenAI, Anthropic)

## Security

- All credentials live in `.env` (gitignored)
- `.gitignore` at repo root excludes `.env`, `temp_audio/`, `.venv/`
- Never commit `.env` — if you do, rotate **all** keys immediately

## Future improvements

| Feature | Where to evolve |
|---|---|
| Persistent history | Replace in-memory dict in `teacher.py` with Redis/SQLite |
| Audio cleanup | Add background task in FastAPI to delete old `temp_audio/*.mp3` |
| Production deploy | Move from ngrok to Railway/Render/VPS |
| Difficulty levels | Add command `level beginner|intermediate|advanced` and adapt system prompt |
| Conversation topics | Add command `topic travel|work|daily life`, bot starts the chat |
| Weekly reports | Persist common errors, send weekly summary |
| Different TTS | Swap OpenAI TTS for ElevenLabs — single function in `audio.py` |
| Webhook signature | Validate Twilio request signature to lock down endpoint |

## Documentation

- 👉 **[SETUP.md](./SETUP.md)** — full setup walkthrough (Mac, Linux, Windows)
- 👉 **[COMMANDS.md](./COMMANDS.md)** — quick command reference

## License

Personal project. Use at your own risk.
