"""Credencial de acesso e refresh token — a auth que o ADR-0007 desenhou (CARD-049).

**Por que ``Credential`` é entidade própria, e não campos em ``Student``.**
``Student`` continua magro de propósito (ver o docstring de ``student.py``):
nem todo consumidor dele (turns, sessões, cota) precisa saber que existe
e-mail/senha, e o CARD-060 (login social) vai ser **outra forma de provar a
mesma identidade** — o dia em que o Google/Apple entrarem, eles apontam para
o mesmo ``student_id`` sem tocar nesta classe.

**Por que ``RefreshToken`` guarda só o hash, nunca o token em claro.** O valor
que atravessa a rede e chega ao cliente nasce em
``application.token_hashing.new_opaque_token`` e nunca é persistido — só o
hash sha256 dele. Um dump do banco não entrega refresh token de ninguém.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Credential:
    """E-mail + senha (hash) de um ``Student``.

    ``email_verified_at`` nulo é o estado inicial de todo cadastro (ADR-0007):
    a conta existe e pode logar, mas não pode postar um turn até confirmar —
    a checagem mora na borda (``api/dependencies.py``), não aqui, porque
    "postar turn" é conhecimento de outra camada.
    """

    id: UUID
    student_id: UUID
    email: str
    password_hash: str
    created_at: datetime
    email_verified_at: datetime | None = None

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None


@dataclass
class RefreshToken:
    """Um elo de uma família de refresh (ADR-0007).

    **``family_id`` é o que a detecção de reuso revoga.** Cada rotação cria um
    ``RefreshToken`` novo com o MESMO ``family_id`` do anterior — a família
    inteira nasce no primeiro login e sobrevive a cada refresh até o logout ou
    até um reuso ser detectado. Ver ``application.use_cases.refresh_tokens``
    para a lógica que usa isto.
    """

    id: UUID
    student_id: UUID
    family_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def is_usable(self, now: datetime) -> bool:
        """Ainda não foi revogado (rotacionado, deslogado ou por reuso) e não
        passou do prazo.
        """
        return self.revoked_at is None and now < self.expires_at


@dataclass
class EmailVerificationToken:
    """Um link de confirmação de e-mail, de uso único (ADR-0007).

    Mesma disciplina do ``RefreshToken``: só o hash é persistido, e
    ``used_at`` marca "já foi clicado" sem apagar a linha — histórico de
    confirmação é dado barato de guardar e caro de reconstruir se faltar.
    """

    id: UUID
    student_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None

    def is_usable(self, now: datetime) -> bool:
        return self.used_at is None and now < self.expires_at


@dataclass
class PasswordResetToken:
    """Um link de "esqueci minha senha", de uso único (ADR-0007, CARD-049).

    **Mesma forma de ``EmailVerificationToken``, entidade própria mesmo
    assim.** As duas são "prova de acesso à caixa de entrada", mas o que a
    posse do link autoriza é diferente — uma confirma a conta, a outra troca
    a senha e desloga todas as sessões (ADR-0007: "troca de senha revoga").
    Uma tabela só para os dois obrigaria uma coluna discriminadora e um
    `CHECK` para impedir usar um token de verificação para resetar senha.
    """

    id: UUID
    student_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None

    def is_usable(self, now: datetime) -> bool:
        return self.used_at is None and now < self.expires_at
