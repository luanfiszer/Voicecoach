"""Hash de tokens opacos (refresh, verificação de e-mail) — sha256, não argon2id.

**Por que dois algoritmos de hash convivem neste projeto.** Uma senha tem
baixa entropia (poucos bits reais; gente reusa "123456") e por isso precisa
de uma KDF deliberadamente lenta — ``argon2id``, em
``application.ports.password_hasher``. Um refresh token ou um token de
verificação de e-mail nasce de ``secrets.token_urlsafe(32)``: 256 bits de
entropia, gerados por um CSPRNG. O problema que o hash resolve aqui não é
"dificultar força bruta offline" (o token já não é adivinhável), é "não
guardar em claro, no banco, o segredo que autoriza a família inteira de
refresh tokens de um aluno". ``sha256`` é rápido de propósito: comparar um
token a cada ``POST /auth/refresh`` não pode custar os mesmos ~50ms de um
``argon2id.verify``.
"""

from __future__ import annotations

import hashlib
import secrets

# 32 bytes = 256 bits antes do base64url — a mesma ordem de grandeza de uma
# chave de sessão TLS. `token_urlsafe` já devolve uma string sem caractere que
# precise de escape em URL (`+`/`/` trocados por `-`/`_`), o que importa porque
# este token vai dentro de uma query string (link de confirmação de e-mail).
_TOKEN_BYTES = 32


def new_opaque_token() -> tuple[str, str]:
    """Gera um token novo. Devolve ``(token em claro, hash para persistir)``.

    O chamador manda o primeiro elemento ao cliente (corpo da resposta de
    login/refresh, ou dentro do link de confirmação) e grava só o segundo.
    """
    plano = secrets.token_urlsafe(_TOKEN_BYTES)
    return plano, hash_opaque_token(plano)


def hash_opaque_token(token: str) -> str:
    """O hash determinístico usado para *procurar* um token pelo valor em claro.

    Determinístico e não salgado, ao contrário do ``argon2id`` de senha: o caso
    de uso precisa fazer ``WHERE token_hash = :hash``, e um hash salgado
    obrigaria a percorrer toda a tabela para comparar um a um. É seguro porque
    a entropia está no token, não no segredo do hash — a mesma razão por que
    HMAC-SHA256 de uma chave de API costuma ser comparado assim.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
