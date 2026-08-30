"""Dá dono ao turn que ninguém terminou (CARD-025).

**O problema é de produto, não de higiene.** Um turn cujo worker morreu fica
``queued`` ou ``processing`` para sempre: o app permanece na tela de espera e
nada a encerra. A tela de timeout existe no desenho e não tinha o que a
alimentasse. Este caso de uso é o que a alimenta.

**Ele marca falho; ele não retenta** (ADR-0037). Reprocessar um turn que já
entregou trechos faria o professor recomeçar a falar do zero, e a decisão de não
fazer isso é anterior a este card. Se alguém aqui um dia escrever "e então
reenfileira", está desfazendo o ADR-0037 sem escrever o ADR que o substitui.

**Por que uma varredura e não um timeout no próprio job.** Um turn travado é,
por definição, um turn cujo processo parou de existir — não há quem execute o
`finally`. O relógio tem de correr **fora** do job, e no `arq` isso é um
`cron_job` (a tradução para a mecânica de fila mora em `worker/main.py`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from voicecoach.application.use_cases.fail_turn import FailTurn
from voicecoach.domain.errors import InvalidStateTransitionError

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from voicecoach.application.ports.repositories import TurnRepository, UnitOfWork
    from voicecoach.application.ports.turn_events import TurnEvents

logger = logging.getLogger(__name__)

MOTIVO = "o turno excedeu o prazo de processamento e foi encerrado pela varredura"


@dataclass(frozen=True, slots=True)
class SweepStaleTurns:
    """O comando. Sem campos, e a ausência tem significado.

    O prazo e o tamanho do lote são **configuração do handler**, não parâmetros
    da intenção: quem dispara a varredura (um `cron_job`, e amanhã talvez um
    endpoint de operação) não deve poder escolher um prazo diferente por chamada.
    Um `before` no comando seria um jeito elegante de alguém, um dia, varrer com
    30 s e matar todo turn que estava só demorando.

    Existe mesmo assim, em vez de um handler sem comando, para que o CQS do
    projeto continue tendo uma forma só (visão §D).
    """


@dataclass(frozen=True, slots=True)
class SweepReport:
    """O que a rodada fez. Existe para o log e para o teste, não para o produto.

    ``ignorados`` conta os turns que a leitura fresca mostrou já terminados —
    é a corrida com o worker vivo acontecendo, e ela é **normal**. Um número
    grande aqui não é incidente: é sinal de que o prazo está curto demais, e
    é a única evidência que a varredura tem para dizê-lo.
    """

    examinados: int
    encerrados: int
    ignorados: int


class SweepStaleTurnsHandler:
    """Varre os turns parados além do prazo e os encerra.

    **Um commit por turn, não um por rodada**, e a razão não é estilo: o worker
    roda com ``MAX_JOBS = 1`` (ADR-0025), então enquanto esta varredura corre
    nenhum turn de aluno é processado. Uma transação única sobre 500 linhas
    seguraria o aluno vivo pelo tempo inteiro do lote e, se o processo morresse
    no meio, não teria encerrado nada. Marco a marco é a mesma disciplina que o
    ``ProcessTurn`` já usa (ADR-0036).

    **Relê cada turn antes de encerrá-lo.** A listagem devolve ids justamente
    para isso: entre o SELECT e o UPDATE, o worker pode ter concluído o turn, e
    gravar uma foto velha escreveria ``failed`` por cima de um ``completed``.
    Com o objeto fresco, quem recusa é o domínio.
    """

    def __init__(
        self,
        *,
        turns: TurnRepository,
        unit_of_work: UnitOfWork,
        events: TurnEvents,
        clock: Callable[[], datetime],
        stale_after: timedelta,
        batch_limit: int,
    ) -> None:
        self._turns = turns
        self._clock = clock
        # O prazo entra por parâmetro, não lido de `config` — `application` não
        # pode importar `voicecoach.config` (ADR-0013). Quem conhece a forma da
        # configuração é a composition root do worker.
        self._stale_after = stale_after
        self._batch_limit = batch_limit
        self._falhar = FailTurn(
            turns=turns, unit_of_work=unit_of_work, events=events, clock=clock
        )

    async def handle(self, command: SweepStaleTurns) -> SweepReport:
        del command  # sem campos: a intenção é toda a configuração do handler
        limite = self._clock() - self._stale_after
        ids = await self._turns.list_stale(before=limite, limit=self._batch_limit)

        encerrados = ignorados = 0
        for turn_id in ids:
            turn = await self._turns.get(turn_id)
            if turn is None:
                # A linha sumiu entre a listagem e a leitura (retenção, delete
                # manual). Não é erro: o que este caso de uso quer é que nenhum
                # turn fique travado, e um turn que não existe não está travado.
                ignorados += 1
                continue
            try:
                await self._falhar(turn, MOTIVO)
            except InvalidStateTransitionError:
                # O worker terminou o turn entre a listagem e agora. **Capturar
                # por item e seguir**, nunca deixar subir: um turn não pode
                # derrubar o lote, ou o primeiro concluído impediria todos os
                # travados atrás dele de serem encerrados — e a próxima rodada
                # cairia no mesmo lugar, para sempre.
                logger.info(
                    "turn %s terminou durante a varredura; nada a fazer", turn_id
                )
                ignorados += 1
                continue
            encerrados += 1
            logger.warning(
                "turn %s encerrado pela varredura (parado desde antes de %s)",
                turn_id,
                limite.isoformat(),
            )

        if ids:
            logger.info(
                "varredura: %d examinados, %d encerrados, %d ignorados",
                len(ids),
                encerrados,
                ignorados,
            )
        return SweepReport(
            examinados=len(ids), encerrados=encerrados, ignorados=ignorados
        )
