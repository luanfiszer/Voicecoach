# Commands Cheat Sheet

Quick reference for everyday operation. Assumes you've already done a full setup once (see [SETUP.md](./SETUP.md)).

## Run the bot (every session)

You need **two terminals** open at the same time.

### Terminal 1 — FastAPI server

**Mac / Linux**
```bash
cd english_teacher_bot
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

**Windows (PowerShell)**
```powershell
cd english_teacher_bot
.venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000
```

### Terminal 2 — ngrok tunnel

```
ngrok http --url=YOUR-DOMAIN.ngrok-free.dev 8000
```
Replace `YOUR-DOMAIN` with your reserved ngrok domain.

### Stop everything
`Ctrl+C` in each terminal.

---

## Sanity checks

```bash
# Local server is up
curl http://localhost:8000

# Public tunnel is up
curl https://YOUR-DOMAIN.ngrok-free.dev

# Both should return:
# {"status":"ok","service":"english-teacher-bot"}
```

---

## Virtual environment

| Action | Mac / Linux | Windows (PowerShell) |
|---|---|---|
| Create venv | `python3 -m venv .venv` | `python -m venv .venv` |
| Activate | `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
| Deactivate | `deactivate` | `deactivate` |
| Recreate (broken) | `rm -rf .venv && python3 -m venv .venv` | `Remove-Item -Recurse -Force .venv ; python -m venv .venv` |

---

## Install / update dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Add a new package:
```bash
pip install <package>
pip freeze > requirements.txt   # or pin manually in the file
```

---

## ngrok

| Action | Command |
|---|---|
| Authenticate (one-time) | `ngrok config add-authtoken YOUR_TOKEN` |
| Run on reserved domain | `ngrok http --url=YOUR-DOMAIN.ngrok-free.dev 8000` |
| Run on random URL | `ngrok http 8000` |
| Show config path | `ngrok config check` |

---

## WhatsApp commands (chat with the bot)

Send these as plain text to the Twilio WhatsApp number:

| Command | Effect |
|---|---|
| `reset` / `clear` / `start over` | Wipes your conversation history |
| `traduzir` | Sends the Portuguese translation of the last reply *(coming soon)* |
| Any audio in English | Normal conversation flow |
| Any other text | Bot reminds you to send audio |

Leave the sandbox completely:
```
stop
```

Rejoin the sandbox:
```
join your-sandbox-words
```

---

## Git

```bash
# Confirm .env is ignored — must NOT show up
git status
git check-ignore -v english_teacher_bot/.env

# Stage and commit
git add .
git commit -m "your message"
git push
```

If you ever accidentally committed `.env`:
1. Remove it from history with `git filter-repo` or BFG
2. **Rotate every key** (Anthropic, OpenAI, Twilio) — assume they're compromised

---

## Logs and debugging

The uvicorn terminal logs every request. Useful filters:

```bash
# Tail uvicorn output (if running in background or saved to file)
tail -f server.log

# Check OpenAI quota in browser
open https://platform.openai.com/settings/organization/billing/overview

# Check Anthropic spend
open https://console.anthropic.com/settings/billing
```

---

## Common one-shot fixes

```bash
# Reread .env after changing it
# Just Ctrl+C and rerun uvicorn

# Free port 8000 if something is stuck
lsof -ti:8000 | xargs kill -9        # Mac/Linux
# Windows: Get-NetTCPConnection -LocalPort 8000 | Stop-Process

# Clean up generated audio files
rm -rf temp_audio/*.mp3 temp_audio/*.ogg     # Mac/Linux
# Windows: Remove-Item temp_audio\*.mp3, temp_audio\*.ogg
```
