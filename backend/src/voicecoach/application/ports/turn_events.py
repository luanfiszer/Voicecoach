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
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
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
    """Publica o que aconteceu com um turn — e, do outro lado, escuta.

    A porta nasceu no CARD-009 só com ``publish``, porque só havia produtor. O
    CARD-010 trouxe o consumidor e ela cresceu por **extensão**, que é o mesmo
    movimento que o ADR-0036 registrou quando ``MediaStorage`` ganhou ``get``:
    o primeiro consumidor é quem revela o que faltava.

    A assimetria é deliberada e vale a pena nomear: **o worker só publica, a
    API só assina**, e mesmo assim é uma porta só. Duas portas dariam a cada
    lado um `Protocol` com um método, ao custo de dois fakes por teste e de a
    pergunta "onde mora o canal do turn?" passar a ter duas respostas. É o
    mesmo desenho de ``MediaStorage``, onde escrever é do worker e assinar é da
    API.
    """

    async def publish(self, turn_id: UUID, event: TurnEvent) -> None: ...

    def subscribe(
        self, turn_id: UUID
    ) -> AbstractAsyncContextManager[AsyncIterator[TurnEvent]]:
        """Assinatura ativa do canal do turn, como **context manager**.

        **Por que um context manager e não simplesmente um ``AsyncIterator``.**
        Esta é a decisão que fecha uma corrida que nenhum teste com fake pega.
        O corpo de um gerador assíncrono **não roda até a primeira iteração**:
        se a porta devolvesse o iterador direto, ``events.subscribe(id)`` não
        teria emitido ``SUBSCRIBE`` coisa nenhuma, e o caso de uso — que lê o
        banco antes de começar a iterar — deixaria uma janela aberta. Todo
        evento publicado nessa janela cai no chão, porque pub/sub não guarda
        nada (ADR-0035). O sintoma seria um trecho de áudio que simplesmente
        não chega, de forma intermitente e dependente do tempo do banco.

        Com o context manager, ``__aenter__`` faz a assinatura **antes** de
        devolver o iterador. O caso de uso então tem a garantia que precisa:
        *assino, depois leio o banco* — e o que for publicado durante a leitura
        fica esperando na assinatura em vez de se perder.

        Contraste com ``TeacherLlm.respond_streaming`` (ADR-0031), que é um
        gerador puro: lá não existe estado a estabelecer antes de iterar, e o
        que se quer é justamente que abandonar a iteração pare a geração. Aqui
        há uma conexão a tomar do pool, e o momento em que ela é tomada é
        contrato.

        **Fechar continua sendo do consumidor**, agora explicitamente: sair do
        ``async with`` desfaz a assinatura e devolve a conexão. Segurá-la viva
        depois que o aluno foi embora é vazar uma conexão de Redis por turn
        esquecido — o que o timeout do ADR-0026 item 5 existe para limitar.

        **Este iterador não conhece histórico.** Quem assina recebe o que for
        publicado a partir de agora e nada do que passou; reconstituir é do
        banco, e é o caso de uso quem costura as duas metades.
        """
        ...
