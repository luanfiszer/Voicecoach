# Setup Guide

Full walkthrough to get the bot running on your machine. Should take ~20 minutes the first time.

## Prerequisites

- **Python 3.9+** (check with `python3 --version` on Mac/Linux or `python --version` on Windows)
- A terminal (Terminal on Mac, any shell on Linux, PowerShell or Git Bash on Windows)
- Accounts on:
  - [Anthropic Console](https://console.anthropic.com) — for Claude API
  - [OpenAI Platform](https://platform.openai.com) — for Whisper + TTS
  - [Twilio](https://www.twilio.com) — for WhatsApp Sandbox (free trial is enough)
- Each account needs **payment method + credits** (~$5 each is plenty to start)

---

## 1. Clone the repository

### Mac / Linux
```bash
git clone <your-repo-url>
cd <repo-folder>/english_teacher_bot
```

### Windows (PowerShell)
```powershell
git clone <your-repo-url>
cd <repo-folder>\english_teacher_bot
```

---

## 2. Create a virtual environment and install dependencies

### Mac / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Windows (PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> If PowerShell blocks the activation script, run once:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

When the venv is active, your prompt should start with `(.venv)`.

---

## 3. Get your API keys

### Anthropic (Claude)
1. Go to [console.anthropic.com](https://console.anthropic.com) → **Settings → API Keys**
2. Click **Create Key** → owner: `You` is fine for personal use
3. Copy the key (starts with `sk-ant-...`)
4. Add credits in **Settings → Billing** (~$5 minimum)
5. Set a spend limit in **Settings → Limits** (recommended: $10/mo)

### OpenAI (Whisper + TTS)
1. Go to [platform.openai.com](https://platform.openai.com) → **API Keys**
2. Click **Create new secret key**
3. Copy the key (starts with `sk-...`)
4. Add credit in **Billing → Add to credit balance** (~$5 minimum)
5. Set a hard limit in **Billing → Usage limits** (recommended: $10/mo)

### Twilio (WhatsApp)
1. Sign up at [twilio.com](https://www.twilio.com) (free trial gives ~$15 credit, enough for sandbox)
2. Go to **Account → API keys & tokens** → **Auth Tokens** tab
3. Copy:
   - **Account SID** (starts with `AC...`) — visible on the dashboard
   - **Primary Auth Token** — click "View"
4. Note the WhatsApp sandbox number — usually `+1 415 523 8886`

---

## 4. Configure the .env file

### Mac / Linux
```bash
cp .env.example .env
```

### Windows (PowerShell)
```powershell
Copy-Item .env.example .env
```

Open `.env` in your editor and fill in:

```dotenv
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
PUBLIC_URL=https://placeholder.ngrok-free.dev    # filled in step 6
ALLOWED_NUMBERS=whatsapp:+5511999999999          # YOUR WhatsApp, full international format
```

> ⚠️ **Never commit `.env`.** It's already in `.gitignore`. If you ever push it by accident, rotate all keys immediately.

---

## 5. Install ngrok

ngrok exposes your local server to the public internet so Twilio can reach it.

### Mac (recommended: Homebrew)
```bash
brew install ngrok
```

### Linux
```bash
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
  && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list \
  && sudo apt update && sudo apt install ngrok
```

### Windows
Download installer from [ngrok.com/download](https://ngrok.com/download) and run it.

### Authenticate (all OSes)
1. Sign up at [ngrok.com](https://ngrok.com)
2. Copy your token from [dashboard.ngrok.com/get-started/your-authtoken](https://dashboard.ngrok.com/get-started/your-authtoken)
3. Run:
   ```
   ngrok config add-authtoken YOUR_TOKEN_HERE
   ```

### Reserve a static dev domain (free)
Free ngrok accounts get one static domain like `something-something.ngrok-free.dev`. Find yours at [dashboard.ngrok.com/domains](https://dashboard.ngrok.com/domains). Using a static domain means **the URL never changes** when you restart ngrok.

---

## 6. Wire ngrok to your .env and to Twilio

Get your ngrok domain (e.g. `cool-name.ngrok-free.dev`) and:

### a) Update `.env`
```dotenv
PUBLIC_URL=https://cool-name.ngrok-free.dev
```

### b) Configure the Twilio webhook
1. Go to [Twilio Console → Messaging → Try it out → Send a WhatsApp message](https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn)
2. Click the **"Sandbox settings"** tab
3. Set **"When a message comes in"** to:
   ```
   https://cool-name.ngrok-free.dev/webhook
   ```
4. Method: **HTTP POST**
5. Click **Save**

### c) Join the sandbox from your phone
On the same Twilio page, you'll see instructions like:
> Send `join word-word` to +1 415 523 8886

Send that message from your WhatsApp. You should get a confirmation reply.

---

## 7. Run it (3 things active at once)

You need **two terminals** open simultaneously:

### Terminal 1 — FastAPI server

#### Mac / Linux
```bash
cd english_teacher_bot
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

#### Windows (PowerShell)
```powershell
cd english_teacher_bot
.venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000
```

You should see `Uvicorn running on http://127.0.0.1:8000`.

### Terminal 2 — ngrok tunnel
```
ngrok http --url=cool-name.ngrok-free.dev 8000
```
(replace with your actual domain)

You should see `Forwarding https://cool-name.ngrok-free.dev -> http://localhost:8000`.

### Sanity check
Open `https://cool-name.ngrok-free.dev` in your browser — you should see:
```json
{"status":"ok","service":"english-teacher-bot"}
```

---

## 8. Test it

From your WhatsApp, send a **5-10 second voice message in English** to **+1 415 523 8886**.

In ~5-10 seconds you should receive:
1. A text card with corrections + tip
2. An audio reply from the teacher

Watch Terminal 1 (uvicorn) — every step is logged: download, transcription, Claude call, TTS, send.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `command not found: uvicorn` | venv not activated | `source .venv/bin/activate` (or Windows equivalent) |
| `No module named pip` (in venv) | Broken venv | Delete `.venv` and recreate |
| `TypeError: unsupported operand type(s) for \|: 'type' and 'NoneType'` | Python <3.10 with new union types | Already fixed in code; pull latest |
| `RateLimitError 429 insufficient_quota` | API has no credit | Add credits at OpenAI / Anthropic console |
| `ERR_NGROK_3200 endpoint offline` | ngrok crashed or not running | Start `ngrok http --url=... 8000` |
| ngrok `authentication failed` | No authtoken | `ngrok config add-authtoken YOUR_TOKEN` |
| WhatsApp says "Sorry, something went wrong" | See the uvicorn log for the real error | Read Terminal 1 |
| Twilio webhook returns 404 | Wrong URL or wrong method | Confirm `https://your-domain/webhook` + POST |
| No log appears when you send WhatsApp | Webhook URL wrong, or you didn't `join` the sandbox | Recheck Twilio Sandbox settings |

For provider-specific quota errors, also confirm you've actually added credits — most accounts don't include free API usage.
