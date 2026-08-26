"""A entrega progressiva de um turn: retomada do banco + o canal ao vivo.

**O problema que este módulo resolve.** O ADR-0026 pede duas coisas que puxam
para lados opostos: entregar o trecho no instante em que ele existe (o canal, que
não guarda nada) e **retomar** de onde o cliente parou (o banco, que guarda tudo
e não avisa ninguém). Costurar as duas é o trabalho daqui, e a costura tem uma
ordem obrigatória:

    1. assina o canal          ← o `async with`; a partir daqui nada se perde
    2. lê o Turn do banco      ← o que já aconteceu
    3. emite o histórico       ← só o que vem DEPOIS do `Last-Event-ID`
    4. emite o que chegar      ← pulando o que o passo 3 já entregou

Inverter 1 e 2 abre uma janela em que um trecho publicado cai no chão, porque
pub/sub é *fire-and-forget* (ADR-0035). É a razão de a porta ``subscribe`` ser um
context manager e não um gerador — o docstring dela conta a história inteira.

**O esquema de ``id`` é contrato de API** (ADR do CARD-010) e a escolha foi por
id **estruturado** (`transcribed`, `chunk:0`, `feedback`, `completed`, `failed`)
em vez de contador monotônico. A razão é uma só: o contador é mais natural para
o ``Last-Event-ID``, mas **não é derivável do banco** — reconstruí-lo exigiria
guardá-lo em algum lugar, o que é a segunda fonte de verdade que o ADR-0035
recusou. O id estruturado o servidor recalcula do próprio Turn.

**A retomada recupera os cinco eventos, ``feedback`` incluído** (CARD-013). Até
aqui ele era o buraco declarado do ADR-0041 item 5: correção não era persistida,
então um cliente que reconectasse depois de o feedback ter passado simplesmente
não o recebia naquele turn. Com ``turn.corrections`` no banco, ele é
reconstituível como os outros — e o gatilho que aquele ADR deixou escrito ("o
CARD-013") disparou.

**Por que este handler levanta em vez de devolver ``Result`` quando o turn não
existe.** É a limitação honesta do ``Result``: ele não atravessa um gerador. Um
gerador assíncrono não tem valor de retorno que o consumidor leia — ele produz
itens —, e a alternativa seria um item-sentinela "deu erro" na própria união de
eventos, o que faria todo consumidor tratar um caso que não é evento. A borda
traduz o ``TurnNotFoundError`` para 404, no mesmo lugar em que traduz tudo o
mais.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, assert_never

from voicecoach.application.ports.turn_events import (
    ChunkReady,
    Completed,
    Failed,
    FeedbackAvailable,
    Transcribed,
)
from voicecoach.application.use_cases.process_turn import TurnNotFoundError
from voicecoach.domain.turn import TurnStatus

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from datetime import timedelta
    from uuid import UUID

    from voicecoach.application.ports.repositories import TurnRepository
    from voicecoach.application.ports.turn_events import TurnEvent, TurnEvents
    from voicecoach.domain.turn import Turn

logger = logging.getLogger(__name__)

TRANSCRIBED_ID = "transcribed"
FEEDBACK_ID = "feedback"
COMPLETED_ID = "completed"
FAILED_ID = "failed"
CHUNK_PREFIX = "chunk:"

# Os dois ids que fecham o stream. Depois deles não há mais nada a dizer sobre
# este turn, e manter a conexão aberta seria a "conexão vazando" do ADR-0026.
TERMINAIS = frozenset({COMPLETED_ID, FAILED_ID})


class MalformedEventIdError(ValueError):
    """O ``Last-Event-ID`` que o cliente devolveu não é do esquema deste turn.

    Levanta em vez de ignorar: um id inventado tratado como "comece do começo"
    reentregaria trechos que o aluno já ouviu, e o modo de falha seria áudio
    repetido — muito mais confuso de depurar do que um 400.
    """


@dataclass(frozen=True, slots=True)
class Delivery:
    """Um evento pronto para ir ao fio, com o ``id:`` que o identifica."""

    event_id: str
    event: TurnEvent


def chunk_id(index: int) -> str:
    """O id de um trecho. O índice do ADR-0023 **é** a identidade natural."""
    return f"{CHUNK_PREFIX}{index}"


def event_id_of(event: TurnEvent) -> str:
    """O id de um evento que chegou pelo canal.

    ``match`` com ``assert_never``, como o ``wire_name`` (ADR-0035 item 6):
    acrescentar um evento à união sem lhe dar um id quebra no ``mypy``, e não em
    produção com um ``id:`` vazio que estraga a retomada de quem reconectar.
    """
    match event:
        case Transcribed():
            return TRANSCRIBED_ID
        case ChunkReady(index=index):
            return chunk_id(index)
        case FeedbackAvailable():
            return FEEDBACK_ID
        case Completed():
            return COMPLETED_ID
        case Failed():
            return FAILED_ID
        case _:  # pragma: no cover - inalcançável enquanto o mypy passar
            assert_never(event)


def posicao(event_id: str) -> tuple[int, int]:
    """A posição do evento na ordem total de um turn.

    A ordem é a que o pipeline produz de fato (conferida em
    ``process_turn.py``): a transcrição abre, os trechos saem em sequência, o
    feedback fecha o JSON do professor **depois** do último trecho, e o desfecho
    encerra. A tupla existe para que ``chunk:10`` venha depois de ``chunk:2`` —
    comparar as strings daria a ordem lexicográfica, que é o mesmo bug que o
    zero-padding das chaves de storage evita no bucket (ADR-0024).
    """
    if event_id == TRANSCRIBED_ID:
        return (0, 0)
    if event_id.startswith(CHUNK_PREFIX):
        sufixo = event_id[len(CHUNK_PREFIX) :]
        if not sufixo.isdigit():
            message = f"índice de trecho inválido em {event_id!r}"
            raise MalformedEventIdError(message)
        return (1, int(sufixo))
    if event_id == FEEDBACK_ID:
        return (2, 0)
    if event_id in TERMINAIS:
        return (3, 0)
    message = f"id de evento fora do esquema deste turn: {event_id!r}"
    raise MalformedEventIdError(message)


class StreamTurnEventsHandler:
    """Produz a sequência de eventos de um turn, retomável e com prazo."""

    def __init__(
        self,
        *,
        turns: TurnRepository,
        events: TurnEvents,
        timeout: timedelta,
    ) -> None:
        self._turns = turns
        self._events = events
        self._timeout = timeout

    async def stream(
        self, turn_id: UUID, *, last_event_id: str | None = None
    ) -> AsyncIterator[Delivery]:
        """Os eventos do turn a partir de ``last_event_id`` (exclusive).

        O prazo é do **stream inteiro**, não de cada evento: um turn saudável
        fecha em ~2 s, e o default de 60 s (ADR-0026 item 5) existe para o turn
        que travou, não para o que está indo bem. Estourado o prazo, o gerador
        termina — o ``EventSource`` do cliente reconecta sozinho com o
        ``Last-Event-ID`` e continua de onde parou, sem perder nada.
        """
        corte = posicao(last_event_id) if last_event_id else None

        # O `async with` PRIMEIRO: a assinatura tem de existir antes da leitura
        # do banco, ou o que for publicado durante ela se perde (ADR-0035).
        async with self._events.subscribe(turn_id) as ao_vivo:
            turn = await self._turns.get(turn_id)
            if turn is None:
                message = f"Turn {turn_id} não existe."
                raise TurnNotFoundError(message)

            entregues: set[str] = set()
            for entrega in historico(turn):
                if corte is not None and posicao(entrega.event_id) <= corte:
                    continue
                entregues.add(entrega.event_id)
                yield entrega
                if entrega.event_id in TERMINAIS:
                    return

            async for entrega in self._ao_vivo(ao_vivo, corte, entregues):
                yield entrega
                if entrega.event_id in TERMINAIS:
                    return

    async def _ao_vivo(
        self,
        fluxo: AsyncIterator[TurnEvent],
        corte: tuple[int, int] | None,
        entregues: set[str],
    ) -> AsyncIterator[Delivery]:
        """O canal, com prazo e sem repetir o que o histórico já entregou.

        **`asyncio.wait_for` em volta de cada `anext`, e não um
        `asyncio.timeout` em volta do laço.** Os dois parecem equivalentes e não
        são: `asyncio.timeout` é um context manager que cancela a *task*, e esta
        função **suspende no `yield`** enquanto o consumidor processa o evento —
        o prazo continuaria correndo dentro de um escopo que ninguém está
        aguardando, e o cancelamento chegaria num ponto arbitrário do consumidor.
        Com o prazo calculado por espera, o cancelamento só pode acontecer onde
        estamos de fato esperando: dentro do `anext`.
        """
        loop = asyncio.get_running_loop()
        prazo = loop.time() + self._timeout.total_seconds()
        iterador = fluxo.__aiter__()
        while True:
            restante = prazo - loop.time()
            if restante <= 0:
                logger.info("stream encerrado por prazo (%s)", self._timeout)
                return
            try:
                event = await asyncio.wait_for(anext(iterador), restante)
            except (TimeoutError, StopAsyncIteration):
                return
            event_id = event_id_of(event)
            if event_id in entregues:
                continue
            if corte is not None and posicao(event_id) <= corte:
                continue
            entregues.add(event_id)
            yield Delivery(event_id, event)


def historico(turn: Turn) -> Iterator[Delivery]:
    """O que já aconteceu, reconstruído do Turn persistido (ADR-0026 item 3).

    **Função livre e síncrona de propósito:** ela é pura sobre a entidade, o que
    a torna testável sem canal, sem banco e sem event loop — e é ela que
    sustenta o critério de aceite "reconectar no 2º trecho recebe do 3º em
    diante".

    ``feedback`` **passou a aparecer aqui** no CARD-013, e a condição é
    ``replied_at``, não ``corrections``: um turn sem erro nenhum teve o evento
    ``feedback`` com a lista vazia, e o cliente que reconectar precisa recebê-lo
    igual — senão o app fica esperando para sempre um evento que já passou. É a
    diferença entre "não houve correção" e "ainda não chegou".

    A etapa do turn não é recalculada em lugar nenhum deste módulo (ADR-0028) —
    o que se lê são os artefatos, que são o mesmo insumo de ``turn.stage``.
    """
    if turn.transcript is not None:
        yield Delivery(TRANSCRIBED_ID, Transcribed(transcript=turn.transcript))

    for chunk in turn.audio_chunks:
        yield Delivery(
            chunk_id(chunk.index),
            ChunkReady(
                index=chunk.index,
                storage_key=chunk.storage_key,
                duration_seconds=chunk.duration_seconds,
                text=chunk.text,
            ),
        )

    if turn.replied_at is not None:
        yield Delivery(
            FEEDBACK_ID, FeedbackAvailable(corrections=tuple(turn.corrections))
        )

    if turn.status is TurnStatus.COMPLETED and turn.reply_audio_ref is not None:
        yield Delivery(COMPLETED_ID, Completed(reply_audio_key=turn.reply_audio_ref))
    elif turn.status is TurnStatus.FAILED:
        yield Delivery(
            FAILED_ID,
            Failed(
                reason=turn.failure_reason or "",
                delivered_partially=turn.delivered_partially,
            ),
        )
