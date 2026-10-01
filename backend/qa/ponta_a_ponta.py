"""Roteiro de QA ponta a ponta contra a stack local (API + worker reais).

Origem: LEARNING-0009 / CARD-062. Os gates provam que o código é coerente
consigo mesmo; isto prova que o produto funciona — do cadastro ao delete da
conta, mais o que um SEGUNDO aluno tentaria contra o primeiro.

Uso (de `backend/`, com `docker compose up -d` na raiz):

    EMAIL_PROVIDER=console uv run uvicorn voicecoach.api.app:create_app \
        --factory --port 8077 > /tmp/api.log 2>&1 &
    uv run voicecoach-worker &
    uv run python qa/ponta_a_ponta.py tests/fixtures/stt/amazing-project.wav \
        /tmp/api.log

`EMAIL_PROVIDER=console` é o que põe o link de confirmação no log da API, de
onde o roteiro o lê. O rate limit de cadastro por IP (CARD-049) barra a
segunda rodada na mesma hora: apague `voicecoach:ratelimit:auth-*:ip:127.0.0.1`
no Redis LOCAL para repetir.
"""

import os
import re
import sys
import time
import uuid
from pathlib import Path

import httpx

B = os.environ.get("QA_BASE_URL", "http://localhost:8077")
AUDIO = Path(sys.argv[1])
LOG = Path(sys.argv[2])
falhas: list[str] = []


def checa(nome: str, cond: bool, extra: object = "") -> None:
    print(("OK   " if cond else "FAIL ") + nome, extra if not cond else "")
    if not cond:
        falhas.append(nome)


c = httpx.Client(base_url=B, timeout=60)
email = f"qa+{uuid.uuid4().hex[:8]}@example.com"
senha = "SenhaForte123!"

r = c.post("/v1/auth/register", json={"email": email, "password": senha})
checa("register 202", r.status_code == 202, r.text)
time.sleep(0.5)
tokens = re.findall(r"confirm-email\?token=([A-Za-z0-9_\-]+)", LOG.read_text())
checa("link de confirmação no log (console sender)", bool(tokens))

r = c.post("/v1/auth/login", json={"email": email, "password": "errada123456"})
checa("login senha errada 401", r.status_code == 401, r.text)
r = c.post("/v1/auth/login", json={"email": email, "password": senha})
checa("login 200", r.status_code == 200, r.text)
par = r.json()
h = {"Authorization": f"Bearer {par['access_token']}"}

r = c.post("/v1/sessions", headers=h)
checa("cria sessão (não verificado)", r.status_code in (200, 201), r.text)
sid = r.json()["id"]
r = c.post(
    f"/v1/sessions/{sid}/turns",
    headers={**h, "Idempotency-Key": uuid.uuid4().hex},
    files={"audio": ("a.wav", AUDIO.read_bytes(), "audio/wav")},
)
checa("turn com e-mail não verificado é recusado (403)", r.status_code == 403, r.text)

r = c.get("/v1/auth/confirm-email", params={"token": tokens[-1]})
checa("confirm-email 2xx", r.is_success, r.text)
r = c.get("/v1/auth/confirm-email", params={"token": tokens[-1]})
checa("confirm-email reuso não é 500", r.status_code < 500, r.text)

r = c.post("/v1/auth/refresh", json={"refresh_token": par["refresh_token"]})
checa("refresh 200", r.status_code == 200, r.text)
novo = r.json()
r = c.post("/v1/auth/refresh", json={"refresh_token": par["refresh_token"]})
checa("refresh reusado 401", r.status_code == 401, r.text)
r = c.post("/v1/auth/refresh", json={"refresh_token": novo["refresh_token"]})
checa("família revogada após reuso (401)", r.status_code == 401, r.text)

r = c.post("/v1/auth/login", json={"email": email, "password": senha})
par = r.json()
h = {"Authorization": f"Bearer {par['access_token']}"}

r = c.get("/v1/students/me/quota", headers=h)
checa("quota 200", r.status_code == 200, r.text)
print("     quota:", r.text[:200])

r = c.post("/v1/sessions", headers=h)
sid = r.json()["id"]
chave = uuid.uuid4().hex
corpo = {"audio": ("a.wav", AUDIO.read_bytes(), "audio/wav")}
r = c.post(
    f"/v1/sessions/{sid}/turns", headers={**h, "Idempotency-Key": chave}, files=corpo
)
checa("turn aceito 202", r.status_code == 202, r.text)
tid = r.json()["turn_id"]
r = c.post(
    f"/v1/sessions/{sid}/turns", headers={**h, "Idempotency-Key": chave}, files=corpo
)
checa(
    "idempotência: mesmo turn, replayed",
    r.json().get("turn_id") == tid and r.json().get("replayed"),
    r.text,
)

t0 = time.monotonic()
turn: dict = {}
while time.monotonic() - t0 < 90:
    turn = c.get(f"/v1/turns/{tid}", headers=h).json()
    if turn["status"] not in ("pending", "processing", "received", "queued"):
        break
    time.sleep(1)
decorrido = time.monotonic() - t0
print(f"     turn {turn['status']} em {decorrido:.1f}s")
print(f"     transcript={turn.get('transcript')!r}")
print(f"     reply={str(turn.get('reply_text'))[:160]!r}")
print(f"     corrections={len(turn.get('corrections') or [])}")
checa("turn completou", turn["status"] == "completed", turn)
if turn.get("reply_audio_url") or turn.get("chunks"):
    url = turn.get("reply_audio_url") or turn["chunks"][0].get("url")
    a = httpx.get(url, timeout=30) if url else None
    checa(
        "áudio da resposta baixável",
        a is not None and a.status_code == 200 and len(a.content) > 1000,
    )

r = c.post(
    f"/v1/turns/{tid}/translations", headers=h, json={"target": "reply", "index": 0}
)
checa("tradução da resposta 200", r.status_code == 200, r.text)
print("     tradução:", r.text[:160])

r = c.get(f"/v1/turns/{tid}", headers={"Authorization": "Bearer lixo"})
checa("token inválido 401", r.status_code == 401, r.text)

# Aluno B (CARD-062): não lê, não acompanha, não grava, não encerra o que é de A.
eb = f"qa+{uuid.uuid4().hex[:8]}@example.com"
c.post("/v1/auth/register", json={"email": eb, "password": senha})
time.sleep(0.5)
c.get(
    "/v1/auth/confirm-email",
    params={
        "token": re.findall(r"confirm-email\?token=([A-Za-z0-9_\-]+)", LOG.read_text())[
            -1
        ]
    },
)
hb = {
    "Authorization": "Bearer "
    + c.post("/v1/auth/login", json={"email": eb, "password": senha}).json()[
        "access_token"
    ]
}
checa("B lê turn de A → 404", c.get(f"/v1/turns/{tid}", headers=hb).status_code == 404)
checa(
    "B acompanha SSE de A → 404",
    c.get(f"/v1/turns/{tid}/events", headers=hb).status_code == 404,
)
r = c.post(
    f"/v1/sessions/{sid}/turns",
    headers={**hb, "Idempotency-Key": uuid.uuid4().hex},
    files=corpo,
)
checa("B grava na sessão de A → 404", r.status_code == 404, r.text)
r = c.post(
    f"/v1/sessions/{sid}/turns", headers={**hb, "Idempotency-Key": chave}, files=corpo
)
checa(
    "B com a chave de A → 404 (sem turn_id)",
    r.status_code == 404 and tid not in r.text,
    r.text,
)
checa(
    "B encerra sessão de A → 404",
    c.post(f"/v1/sessions/{sid}/end", headers=hb).status_code == 404,
)
checa("SSE sem token → 401", c.get(f"/v1/turns/{tid}/events").status_code == 401)

r = c.post(f"/v1/sessions/{sid}/end", headers=h)
checa("encerrar sessão 2xx", r.is_success, r.text)
r = c.get("/v1/sessions", headers=h)
checa("lista sessões 200", r.status_code == 200, r.text)

r = c.post("/v1/auth/google", json={"id_token": "nao.e.um.jwt"})
checa(
    "google token adulterado 401 problem+json",
    r.status_code == 401 and "problem" in r.headers.get("content-type", ""),
    (r.status_code, r.text),
)
r = c.post("/v1/auth/apple", json={"identity_token": "x.y.z"})
checa("apple sem APPLE_CLIENT_ID 503", r.status_code == 503, (r.status_code, r.text))

r = c.post("/v1/auth/logout", json={"refresh_token": par["refresh_token"]})
checa("logout 2xx", r.is_success, r.text)
r = c.post("/v1/auth/login", json={"email": email, "password": senha})
h = {"Authorization": f"Bearer {r.json()['access_token']}"}
r = c.delete("/v1/students/me", headers=h)
checa("delete conta 2xx", r.is_success, r.text)
r = c.post("/v1/auth/login", json={"email": email, "password": senha})
checa("login após delete 401", r.status_code == 401, r.text)

print("\nFALHAS:", falhas or "nenhuma")
