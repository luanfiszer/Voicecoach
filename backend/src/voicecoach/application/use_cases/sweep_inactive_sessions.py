"""Fecha a sessão que ninguém encerrou (CARD-034) — o irmão do CARD-025.

**O problema é de produto, não de higiene.** "Encerrar" é um botão que exige
que o aluno se lembre dele, e a maioria das sessões nunca vai ser encerrada por
ninguém: o aluno fecha o app e some. Sem esta varredura, o histórico do
CARD-030 vira uma pilha de sessões "em andamento" que acabaram há semanas, e o
resumo pós-sessão do artboard 09 — o momento pedagógico do produto — nunca
acontece para quem não tocou no botão. Pior: ``ended_at`` nulo passaria a
significar duas coisas ("está falando agora" e "sumiu em julho"), e um campo
que significa duas coisas não significa nenhuma.

**Por que o encerramento passa por ``try_end`` e não por ``Session.end()``.**
O RF1 pede "o mesmo ``Session.end()`` do domínio — nunca um ``UPDATE``
direto", e a intenção dele está cumprida: o que este caso de uso **não** faz é
escrever SQL ad-hoc. Mas o caminho de escrita em produção já tinha sido
decidido no CARD-031, e está escrito no docstring do próprio ``Session.end()``:
a mutação real é ``SessionRepository.try_end``, um ``UPDATE ... COALESCE``
atômico, porque dois processos que chamam ``end()`` em memória não veem a
escrita um do outro antes de comitar. Usar ``end()`` aqui reabriria exatamente
a corrida que aquele card fechou.

O ganho é direto no **RNF3**: ``try_end`` é idempotente por construção — uma
sessão já encerrada devolve o ``ended_at`` que já tinha, sem levantar. Não há
``InvalidStateTransitionError`` em massa a capturar, porque não há exceção
nenhuma. Duas execuções sobrepostas convergem para o mesmo estado.

**A corrida residual, escrita porque é aceita.** Entre a listagem das
candidatas e o ``try_end``, o aluno pode falar. A sessão fecha, e o turn
seguinte é recusado com ``session-ended`` (CARD-031, RF3) — a fala se perde.
A defesa que o card escolhe **não** é lock: é o prazo generoso do RF5
(30 min). A janela é de milissegundos dentro de uma rodada, contra um prazo de
meia hora de silêncio; e o desfecho, quando acontece, é um 409 que o app sabe
explicar, não um erro mudo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicecoach.application.ports.repositories import RowNotFoundError

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime, timedelta

    from voicecoach.application.ports.repositories import SessionRepository, UnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SweepInactiveSessions:
    """O comando. Sem campos, e a ausência tem o mesmo significado do CARD-025.

    O prazo e o lote são configuração do handler, não parâmetros da intenção:
    quem dispara (o ``cron_job``, e amanhã talvez um endpoint de operação) não
    deve poder varrer com 30 s e fechar a sessão de todo mundo que está
    pensando.
    """


@dataclass(frozen=True, slots=True)
class InactiveSweepReport:
    """O que a rodada fez — para o log e para o teste, não para o produto."""

    examinadas: int
    encerradas: int
    ignoradas: int


class SweepInactiveSessionsHandler:
    """Encerra em lote as sessões paradas além do prazo.

    **Um commit por sessão, não um por rodada** — a mesma disciplina do
    ``SweepStaleTurnsHandler`` e pelo mesmo motivo: com ``MAX_JOBS = 1``, uma
    transação única sobre 50 linhas seguraria o aluno vivo pelo lote inteiro e,
    se o processo morresse no meio, não teria encerrado nada.
    """

    def __init__(
        self,
        *,
        sessions: SessionRepository,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
        inactive_after: timedelta,
        batch_limit: int,
    ) -> None:
        self._sessions = sessions
        self._uow = unit_of_work
        self._clock = clock
        # Números crus e não `Settings`: `application` não lê configuração
        # (ADR-0013) — a composition root do worker já resolveu os dois.
        self._inactive_after = inactive_after
        self._batch_limit = batch_limit

    async def handle(self, command: SweepInactiveSessions) -> InactiveSweepReport:
        del command  # sem campos: a intenção é toda a configuração do handler
        agora = self._clock()
        limite = agora - self._inactive_after
        ids = await self._sessions.list_inactive(before=limite, limit=self._batch_limit)

        encerradas = ignoradas = 0
        for session_id in ids:
            try:
                await self._sessions.try_end(session_id, agora)
            except RowNotFoundError:
                # A linha sumiu entre a listagem e a escrita (delete de conta,
                # CARD-017). Não é erro: o que este caso de uso quer é que
                # nenhuma sessão fique aberta para sempre, e uma sessão que não
                # existe não está aberta. Capturar por item e seguir — uma
                # sessão não pode derrubar o lote.
                ignoradas += 1
                continue
            await self._uow.commit()
            encerradas += 1

        if ids:
            logger.info(
                "varredura de sessões: %d examinadas, %d encerradas, %d ignoradas "
                "(paradas desde antes de %s)",
                len(ids),
                encerradas,
                ignoradas,
                limite.isoformat(),
            )
        return InactiveSweepReport(
            examinadas=len(ids), encerradas=encerradas, ignoradas=ignoradas
        )
