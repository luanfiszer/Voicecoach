"""Contrato HTTP da auth (ADR-0007, CARD-049).

**Nenhum schema de registro/login devolve algo que diferencie "e-mail já
existe" de "conta criada".** É a mesma regra de segurança do corpo da
tradução (RF1 do CARD-036), aplicada aqui à existência de uma conta em vez
de a um texto: o contrato só tem uma forma de resposta porque o caso de uso
só produz um desfecho observável (ver `application/use_cases/register_student.py`).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Mínimo de 8: o piso mais citado (NIST SP 800-63B não exige complexidade,
# mas pede um mínimo — 8 é o número que a maioria dos guias converge, e
# `argon2id` já é a defesa contra senha fraca reusada; um mínimo mais alto
# aqui não substituiria isso). Sem teto artificial de complexidade
# ("1 número, 1 símbolo"): NIST recomenda contra essa regra — ela empurra o
# humano para padrões previsíveis, não para senhas mais fortes.
_SENHA_MIN = 8

# **Sanidade de formato, não RFC 5322 completa** — de propósito. `EmailStr` do
# pydantic exigiria a dependência `email-validator` só para isto, e a prova
# real de "é um e-mail que existe" nunca vem de regex nenhuma: vem do aluno
# clicar no link de confirmação (RF do próprio card). Um regex apertado
# rejeitaria endereço válido; um solto deixa passar lixo óbvio — o padrão
# abaixo mira no segundo, que é o custo mais barato de errar.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN)
    password: str = Field(min_length=_SENHA_MIN)


class LoginRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN)
    password: str


class TokenPairResponse(BaseModel):
    """O par de tokens (ADR-0007) — mesma forma para login e refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Segundos até o `access_token` expirar.")


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ResendConfirmationRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN)


class RequestPasswordResetRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=_SENHA_MIN)
