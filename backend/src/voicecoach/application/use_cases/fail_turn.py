"""A receita de marcar um turn como falho — **um lugar só** (CARD-025).

Este módulo existe por causa de uma duplicação que ainda não aconteceu, e é o
tipo de duplicação que não dá erro: até o CARD-025, a receita
``fail() → gravar → publicar`` vivia dentro de ``ProcessTurnHandler``, e a
varredura de turns travados precisa exatamente dela sobre N turns, sem pipeline.
Copiar as quatro linhas seria barato hoje e caro no dia em que a marcação ganhar
um campo novo no evento ou um segundo efeito: uma das duas cópias ficaria para
trás, e seria a que ninguém olha.

**Não é um caso de uso.** É um colaborador de aplicação que dois casos de uso
compartilham — o ``ProcessTurn`` (falha no meio do pipeline) e o
``SweepStaleTurns`` (falha por decurso de prazo). Não tem comando próprio porque
não é uma intenção do sistema: é um passo dentro de duas intenções diferentes.

**A ordem dos três passos é contrato, não estilo** (ADR-0035): o banco é a fonte
da verdade e o canal é o caminho rápido. Publicar antes de gravar anunciaria um
desfecho que a próxima leitura do ``GET`` desmentiria — e falha ao publicar
**não pode** desfazer a marcação, que é o motivo de ``publicar_tolerante``
existir.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from voicecoach.application.ports.turn_events import Failed, TurnEventsError

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from uuid import UUID

    from voicecoach.application.ports.repositories import TurnRepository, UnitOfWork
    from voicecoach.application.ports.turn_events import TurnEvent, TurnEvents
    from voicecoach.domain.turn import Turn

logger = logging.getLogger(__name__)


async def publicar_tolerante(
    events: TurnEvents, turn_id: UUID, event: TurnEvent
) -> None:
    """Publica no canal e **engole a falha de propósito**.

    É a única exceção capturada e descartada em todo o pipeline, e ela tem
    justificativa (ADR-0035): o canal é o caminho rápido, não a verdade (o banco
    é). Um Redis fora do ar atrasa o aluno em alguns segundos, até o cliente cair
    no polling do ADR-0026 item 4; abortar por isso jogaria fora áudio já
    sintetizado e tokens já pagos — ou, na varredura, deixaria o turn travado
    exatamente como estava.

    Mora aqui, e não em cada caso de uso, porque é **uma política** ("o canal é
    cortesia") e não um detalhe local: dois lugares engolindo por conta própria
    seriam dois lugares onde alguém pode decidir o contrário sem perceber.
    """
    try:
        await events.publish(turn_id, event)
    except TurnEventsError as exc:
        logger.warning("turn %s: evento não publicado (%s)", turn_id, exc)


class FailTurn:
    """Marca um turn como falho: ``fail()`` → grava → publica ``Failed``.

    **Falhar não apaga trecho** (ADR-0023, item 6). A invariante é da entidade —
    ``Turn.fail`` preserva a coleção — e o que este colaborador acrescenta é
    contá-la a quem está ouvindo: ``delivered_partially`` é lido **depois** do
    ``fail()``, do mesmo objeto, para que o evento diga a verdade sobre o que o
    aluno já ouviu.

    Recebe as portas por parâmetro nomeado, como todo o resto de ``application``:
    quem monta é a composition root. ``Turn.fail`` levanta
    ``InvalidStateTransitionError`` se o turn já é ``completed`` ou ``failed`` —
    e essa exceção **atravessa**, de propósito. Quem chama com um turn terminado
    tem um bug (ADR-0017); quem varre em lote é que decide se pula ou para, e a
    decisão é dele, não deste objeto.
    """

    def __init__(
        self,
        *,
        turns: TurnRepository,
        unit_of_work: UnitOfWork,
        events: TurnEvents,
        clock: Callable[[], datetime],
    ) -> None:
        self._turns = turns
        self._uow = unit_of_work
        self._events = events
        self._clock = clock

    async def __call__(self, turn: Turn, motivo: str) -> None:
        """``__call__`` e não ``handle``: a instância É a operação.

        Idioma de Python sem paralelo direto em C#: definir ``__call__`` torna o
        objeto invocável como função (``await falhar(turn, motivo)``). O mais
        próximo em .NET é uma classe que expõe um ``Func<>`` — aqui a própria
        instância é o delegate, com as dependências capturadas no construtor.
        """
        turn.fail(motivo, self._clock())
        await self._turns.update(turn)
        await self._uow.commit()
        await publicar_tolerante(
            self._events,
            turn.id,
            Failed(reason=motivo, delivered_partially=turn.delivered_partially),
        )
