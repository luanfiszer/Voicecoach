"""A listagem de sessões do aluno (CARD-030, backend do artboard 10).

**Leitura pura, e isso é requisito** (RNF5): não gasta cota, não incrementa
orçamento e continua respondendo com a cota estourada — a regra "quota bloqueia
escrita, não leitura" que o ADR-0063 já fixou. Por isso não há `Result` aqui:
a única entrada é um id de aluno e uma janela, e nenhuma das duas tem desfecho
de negócio que possa falhar. Aluno sem sessão recebe lista vazia (RF5), nunca
404 — ausência de sessões é uma resposta, não um recurso que não existe.

**Sem URL assinada** (RNF6): assinar é HMAC local e barato, mas 30 sessões
vezes N trechos é trabalho para uma tela que não toca áudio. Quem assina é a
tela de detalhe, que é web e é Fase 5.

**Sem cache, e a resposta é explícita** (RNF4, que proíbe ficar em silêncio):
as duas agregações são feitas no banco, sustentadas pelo índice composto
`(student_id, started_at)` criado por este card. Cachear introduziria uma
terceira fonte para divergir do que o `POST /turns` acabou de escrever — e o
gatilho de invalidação seria "qualquer turn novo", ou seja, invalidação a cada
fala do aluno, que é a frequência exata em que a tela é aberta. TTL e gatilho,
portanto: **não há**; a decisão é não cachear, e ela se revê se a agregação
aparecer como hot path em profiling real.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime, timedelta
    from uuid import UUID

    from voicecoach.application.ports.repositories import SessionRepository
    from voicecoach.domain.session import SessionDigest


@dataclass(frozen=True, slots=True)
class ListSessions:
    """A consulta: de quem, e por quanto tempo para trás."""

    student_id: UUID
    window: timedelta


@dataclass(frozen=True, slots=True)
class SessionListItem:
    """Uma sessão na listagem, já com a disponibilidade de mídia resolvida.

    **``reply_media_available`` é uma PREVISÃO conservadora, não uma leitura do
    bucket** — e o card pede que a escolha entre os dois significados esteja
    escrita. O lifecycle do S3 apaga *"em até 24h depois"* da data de
    expiração, nunca no segundo exato. Logo:

    - antes de ``last_turn_at + retenção``, o áudio **certamente** está lá;
    - depois, ele **pode** estar (na janela de graça do bucket) ou não.

    Este campo diz ``False`` a partir do segundo caso. A direção do erro é
    deliberada: prometer áudio que sumiu deixa o aluno tocando o play e
    ouvindo silêncio; esconder áudio que ainda existiria por algumas horas
    custa uma reprodução que ninguém sabia estar disponível. O significado, em
    português, é **"não conte com ele"** — e é isso que a tela deve afirmar.

    Sessão sem turn nenhum tem ``reply_media_available = False``: não há mídia
    sobre a qual responder, e dizer "disponível" seria prometer o que nunca
    existiu.
    """

    digest: SessionDigest
    reply_media_available: bool


class ListSessionsHandler:
    def __init__(
        self,
        *,
        sessions: SessionRepository,
        clock: Callable[[], datetime],
        reply_media_retention: timedelta,
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        # Número cru e não `Settings`: `application` não lê configuração
        # (ADR-0013) — a composition root já resolveu o valor.
        self._retention = reply_media_retention

    async def handle(self, query: ListSessions) -> list[SessionListItem]:
        agora = self._clock()
        digests = await self._sessions.list_for_student(
            query.student_id, since=agora - query.window
        )
        return [
            SessionListItem(
                digest=digest,
                reply_media_available=self._midia_disponivel(
                    digest.last_turn_at, agora
                ),
            )
            for digest in digests
        ]

    def _midia_disponivel(self, last_turn_at: datetime | None, agora: datetime) -> bool:
        """O trecho mais NOVO da sessão ainda está dentro da retenção?

        O mais novo, e não o mais velho: se nem ele sobreviveu, nenhum outro
        sobreviveu — e a tela fala da sessão inteira, não de um trecho.
        """
        if last_turn_at is None:
            return False
        return agora < last_turn_at + self._retention
