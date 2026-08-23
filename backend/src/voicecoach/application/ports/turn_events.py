"""Porta do canal worker → API (ADR-0026, e o ADR de canal do CARD-009).

**O que este canal é, e o que ele não é.** Ele é o *caminho rápido*: existe para
que o SSE do CARD-010 saiba que há trecho novo no instante em que há, em vez de
descobrir num polling interno. Ele **não** é a fonte da verdade — essa é o banco,
onde o ADR-0023 já persiste os trechos, e é de lá que a retomada por
``Last-Event-ID`` reconstrói o que o cliente perdeu.

A consequência dessa divisão é o que torna pub/sub aceitável apesar de ser
*fire-and-forget*: perder uma publicação custa latência, nunca dado.

**O que viaja aqui é a chave do storage, não a URL assinada.** O ADR-0024 diz
que a URL viaja junto do evento, e ela viaja — no evento **SSE**, que é outro
evento, montado pela API. Assinar aqui produziria URLs com TTL contado a partir
da publicação, que já teriam envelhecido quando um cliente reconectasse; e a
retomada, que lê do banco, só tem a chave para oferecer. Uma origem só, um
caminho só de assinatura.

**Nenhum evento de "começou".** O turn nasce ``queued`` e o cliente já sabe
disso: publicar "estou processando" seria repetir no canal o que a resposta do
POST já disse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID


class TurnEventsError(RuntimeError):
    """A publicação falhou.

    Existe para ser **capturável e ignorável** pelo caso de uso, que é o oposto
    dos outros erros de porta. Perder um evento atrasa o aluno; abortar o turn
    por causa disso jogaria fora áudio já sintetizado e pago. O caso de uso
    registra e segue.
    """


@dataclass(frozen=True, slots=True)
class Transcribed:
    """O STT terminou. Vira o evento ``transcribed`` do ADR-0026."""

    transcript: str


@dataclass(frozen=True, slots=True)
class ChunkReady:
    """Um trecho de áudio ficou tocável. Vira o evento ``chunk``.

    ``storage_key`` e não ``url``: ver o docstring do módulo. ``index`` é o
    mesmo do ``TurnAudioChunk`` — denso, 0-based, e é ele que dá a ordem de
    playback.
    """

    index: int
    storage_key: str
    duration_seconds: float
    text: str


@dataclass(frozen=True, slots=True)
class FeedbackAvailable:
    """As correções fecharam. Vira o evento ``feedback``.

    **Este é o único evento que a retomada não consegue reconstruir**, porque
    correção ainda não é persistida — o CARD-013 é quem cria a tabela. Até lá,
    um cliente que reconecte no meio do turn perde o feedback deste turn e o vê
    só no histórico, depois. Dívida registrada no card, com o CARD-013 como
    gatilho.

    ``translation_pt`` fica de fora porque o ADR-0026 fixou o payload do evento
    ``feedback`` sem ela — é o campo mais descartável (ADR-0022) e não paga o
    tráfego no caminho crítico.
    """

    has_mistakes: bool
    original: str
    corrected: str
    tip: str


@dataclass(frozen=True, slots=True)
class Completed:
    """O turn fechou. Vira o evento ``completed``."""

    reply_audio_key: str


@dataclass(frozen=True, slots=True)
class Failed:
    """O turn falhou. Vira o evento ``failed``.

    ``delivered_partially`` viaja junto porque é o que muda a tela: falhar tendo
    entregue duas frases pede "a conexão caiu, o que você ouviu está aqui", e
    falhar antes de qualquer áudio pede "não deu, tente de novo" (ADR-0023).
    """

    reason: str
    delivered_partially: bool


# União FECHADA, como o `TeacherEvent` do ADR-0031. Quem consome faz `match` e
# termina com `assert_never`: sem isso, acrescentar um evento novo passa VERDE
# no mypy e some em runtime.
type TurnEvent = Transcribed | ChunkReady | FeedbackAvailable | Completed | Failed


class TurnEvents(Protocol):
    """Publica o que aconteceu com um turn, para quem estiver ouvindo."""

    async def publish(self, turn_id: UUID, event: TurnEvent) -> None: ...
