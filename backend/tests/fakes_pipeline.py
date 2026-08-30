"""Dublês de **todas** as portas, para o caso de uso rodar sem infraestrutura.

Este arquivo é o critério de aceite do CARD-009 em forma executável: o teste do
pipeline inteiro roda em milissegundos, sem Redis, sem Postgres, sem MinIO e sem
carregar modelo nenhum.

**Nenhuma classe aqui herda de coisa alguma.** Elas satisfazem os `Protocol` de
`application/ports` estruturalmente — por ter os métodos com a assinatura certa.
Não há framework de mock, não há registro, não há `: IAlgumaCoisa`. Em troca, a
verificação de que um fake de fato serve acontece no **`mypy`**, não em runtime:
`test_process_turn.py` declara `porta: SpeechToText = FakeStt()` e é essa linha
que reprova quando uma assinatura sai de sincronia — com o `pytest` ainda verde.
Aconteceu três vezes no CARD-007 e de novo nesta sessão, quando `MediaStorage`
ganhou `get`.

Mora em `tests/` e não em `tests/application/` porque o teste de integração do
worker usa os mesmos dublês para as portas que ele NÃO quer reais (storage,
repositório, canal) enquanto usa modelos de verdade nas outras três. O pytest
insere no `sys.path` o diretório de cada `conftest.py`, então `tests/` é
alcançável de qualquer subpasta — foi por isso que `from fakes import ...`
funcionava em `tests/application` e quebrava em `tests/worker`.

Os fakes são **programáveis por falha**: cada um aceita uma exceção que passa a
levantar, e alguns aceitam um atraso. É o que permite testar o caminho triste e
a ordem da cascata sem tocar em nada real.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from voicecoach.application.ports.audio_encoder import EncodedAudio
from voicecoach.application.ports.media_storage import MediaStorageError
from voicecoach.application.ports.speech_to_text import AudioInput, Transcript
from voicecoach.application.ports.teacher_llm import TeacherEvent, Utterance
from voicecoach.application.ports.text_to_speech import (
    BYTES_PER_SAMPLE,
    SynthesizedAudio,
)
from voicecoach.application.ports.turn_events import TurnEvent
from voicecoach.domain.session import Session
from voicecoach.domain.turn import Turn
from voicecoach.domain.usage import StudentUsageTotals, UsageEvent

TAXA = 22_050
CONTENT_TYPE = "audio/aac"
EXTENSION = "aac"


def pcm_de(segundos: float, taxa: int = TAXA) -> bytes:
    """Silêncio com a duração pedida: o conteúdo não importa, o tamanho sim."""
    return b"\x00" * (int(segundos * taxa) * BYTES_PER_SAMPLE)


class RelogioFalso:
    """Um relógio que anda 1 s a cada leitura.

    **É a peça que torna a cascata verificável.** O critério de aceite do card
    é "o primeiro trecho foi gravado ANTES de `replied_at`", e isso é uma
    afirmação sobre ordem no tempo. Com `datetime.now()` real, dois eventos
    separados por microssegundos podem empatar; com um relógio que avança a cada
    leitura, a ordem fica legível na asserção.
    """

    def __init__(self, inicio: datetime | None = None, passo_s: float = 1.0) -> None:
        self.instante = inicio or datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
        self._passo = timedelta(seconds=passo_s)

    def __call__(self) -> datetime:
        agora = self.instante
        self.instante = self.instante + self._passo
        return agora


class FakeUnitOfWork:
    """Conta commits. Não há transação: o que se verifica é a **cadência**.

    O caso de uso comita por marco (transcrição, cada trecho, feedback, fim), e
    é isso que faz a retomada do ADR-0026 ter o que ler no meio do turn. Um
    commit só no fim passaria em qualquer teste de resultado final e quebraria a
    retomada — por isso a contagem é asserção, não curiosidade.
    """

    def __init__(self) -> None:
        self.commits = 0
        self.trechos_por_commit: list[int] = []
        self._turn: Turn | None = None

    def observar(self, turn: Turn) -> None:
        self._turn = turn

    async def commit(self) -> None:
        self.commits += 1
        if self._turn is not None:
            self.trechos_por_commit.append(len(self._turn.audio_chunks))


class FakeTurnRepository:
    """Guarda Turns em memória, por id."""

    def __init__(self, *turns: Turn) -> None:
        self.turns: dict[UUID, Turn] = {t.id: t for t in turns}
        self.updates = 0

    async def add(self, turn: Turn) -> None:
        self.turns[turn.id] = turn

    async def get(self, turn_id: UUID) -> Turn | None:
        return self.turns.get(turn_id)

    async def get_by_idempotency_key(self, key: str) -> Turn | None:
        return next((t for t in self.turns.values() if t.idempotency_key == key), None)

    async def update(self, turn: Turn) -> None:
        self.updates += 1
        self.turns[turn.id] = turn

    async def list_by_session(self, session_id: UUID, *, limit: int) -> list[Turn]:
        from voicecoach.domain.turn import TurnStatus

        concluidos = [
            t
            for t in self.turns.values()
            if t.session_id == session_id and t.status is TurnStatus.COMPLETED
        ]
        concluidos.sort(key=lambda t: t.created_at)
        return concluidos[-limit:]

    async def list_stale(self, *, before: datetime, limit: int) -> list[UUID]:
        """Reproduz o ``coalesce`` do adapter, incluindo o caso ``queued``.

        Um fake que só olhasse ``started_processing_at`` passaria em todos os
        testes de ``processing`` e esconderia o buraco do turn que o worker nunca
        pegou — que é metade do card.
        """
        from voicecoach.domain.turn import TurnStatus

        parados = [
            t
            for t in self.turns.values()
            if t.status in (TurnStatus.QUEUED, TurnStatus.PROCESSING)
            and (t.started_processing_at or t.created_at) < before
        ]
        parados.sort(key=lambda t: t.started_processing_at or t.created_at)
        return [t.id for t in parados[:limit]]


class FakeUsageEventRepository:
    """Guarda o custo em memória, indexado por turn.

    **Sem ``update``**, como a porta: medição não se corrige. E a escrita
    duplicada levanta em vez de sobrescrever — é a chave primária do Postgres
    (``turn_id``) reproduzida em memória, para que o teste do caso de uso possa
    afirmar "um turn, uma linha" sem precisar de banco.
    """

    def __init__(self) -> None:
        self.eventos: dict[UUID, UsageEvent] = {}

    async def add(self, event: UsageEvent) -> None:
        if event.turn_id in self.eventos:
            message = f"UsageEvent do turn {event.turn_id} já existe."
            raise RuntimeError(message)
        self.eventos[event.turn_id] = event

    async def get(self, turn_id: UUID) -> UsageEvent | None:
        return self.eventos.get(turn_id)

    async def totals_for_student(
        self, student_id: UUID, *, since: datetime, until: datetime
    ) -> StudentUsageTotals:
        na_janela = [
            e
            for e in self.eventos.values()
            if e.student_id == student_id and since <= e.occurred_at < until
        ]
        return StudentUsageTotals(
            turns=len(na_janela),
            spoken=sum((e.stt_audio_duration for e in na_janela), timedelta(0)),
            cost_usd=sum(
                (
                    e.estimated_cost_usd
                    for e in na_janela
                    if e.estimated_cost_usd is not None
                ),
                Decimal(0),
            ),
            unpriced_turns=sum(1 for e in na_janela if e.estimated_cost_usd is None),
        )


class FakeSessionRepository:
    def __init__(self, *sessions: Session) -> None:
        self.sessions: dict[UUID, Session] = {s.id: s for s in sessions}

    async def add(self, session: Session) -> None:
        self.sessions[session.id] = session

    async def get(self, session_id: UUID) -> Session | None:
        return self.sessions.get(session_id)

    async def update(self, session: Session) -> None:
        self.sessions[session.id] = session


class FakeMediaStorage:
    """Um dicionário com cara de bucket."""

    def __init__(self, *, falhar_em: Exception | None = None) -> None:
        self.objetos: dict[str, tuple[bytes, str]] = {}
        self.ordem_de_escrita: list[str] = []
        self._falhar_em = falhar_em

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        if self._falhar_em is not None:
            raise self._falhar_em
        self.objetos[key] = (data, content_type)
        self.ordem_de_escrita.append(key)

    async def get(self, key: str) -> bytes:
        if key not in self.objetos:
            message = f"chave inexistente: {key}"
            raise MediaStorageError(message)
        return self.objetos[key][0]

    async def presigned_get_url(self, key: str, ttl: timedelta) -> str:
        return f"https://storage.test/{key}?expires={int(ttl.total_seconds())}"

    async def delete_prefix(self, prefix: str) -> int:
        alvos = [k for k in self.objetos if k.startswith(prefix)]
        for k in alvos:
            del self.objetos[k]
        return len(alvos)


class FakeStt:
    def __init__(
        self,
        texto: str = "I think my job is stressful",
        *,
        erro: Exception | None = None,
    ) -> None:
        self.texto = texto
        self._erro = erro
        self.chamadas: list[bytes] = []

    async def transcribe(self, audio: AudioInput) -> Transcript:
        if self._erro is not None:
            raise self._erro
        self.chamadas.append(audio.data)
        return Transcript(text=self.texto, language="en", duration_seconds=4.0)


class FakeTeacher:
    """Um gerador assíncrono — a porta NÃO é `async def` (ADR-0031).

    `respond_streaming` é declarada sem `async` e com `yield` dentro: isso a
    torna um *gerador assíncrono*. Chamá-la devolve o gerador na hora, sem
    `await`, e nada dentro dela roda até alguém iterar com `async for`. Declarar
    `async def ... -> AsyncIterator` seria outra coisa (uma corrotina que devolve
    um iterador) e não satisfaria a porta.
    """

    def __init__(
        self,
        eventos: Sequence[TeacherEvent],
        *,
        erro: Exception | None = None,
        erro_apos: int | None = None,
    ) -> None:
        self._eventos = list(eventos)
        self._erro = erro
        self._erro_apos = erro_apos
        self.historicos: list[list[Utterance]] = []
        self.emitidos = 0
        self.fechado = False

    def respond_streaming(
        self, history: Sequence[Utterance]
    ) -> AsyncIterator[TeacherEvent]:
        self.historicos.append(list(history))
        return self._fluxo()

    async def _fluxo(self) -> AsyncIterator[TeacherEvent]:
        try:
            for i, evento in enumerate(self._eventos):
                if self._erro is not None and self._erro_apos == i:
                    raise self._erro
                self.emitidos += 1
                yield evento
            if self._erro is not None and self._erro_apos is None:
                raise self._erro
        finally:
            # O `finally` roda também quando o consumidor ABANDONA o `async for`:
            # o Python fecha o gerador levantando `GeneratorExit` dentro dele. É
            # assim que se prova que o cancelamento chegou até aqui — e que o
            # produto parou de pagar tokens (ADR-0031, item 6).
            self.fechado = True


class FakeTts:
    """Sintetiza texto em silêncio, opcionalmente com atraso por sentença.

    `atrasos` é o que permite escrever o teste que separa uma implementação
    correta de uma que só parece correta: com a 2ª sentença terminando antes da
    1ª, uma cascata baseada em `create_task` grava fora de ordem.
    """

    def __init__(
        self,
        *,
        atrasos: Sequence[float] | None = None,
        erro: Exception | None = None,
        erro_na_sentenca: int | None = None,
        taxa: int = TAXA,
    ) -> None:
        self.chamadas: list[str] = []
        self.concluidas: list[str] = []
        self._atrasos = list(atrasos or [])
        self._erro = erro
        self._erro_na = erro_na_sentenca
        self._taxa = taxa

    async def synthesize(self, text: str) -> SynthesizedAudio:
        indice = len(self.chamadas)
        self.chamadas.append(text)
        if indice < len(self._atrasos):
            await asyncio.sleep(self._atrasos[indice])
        if self._erro is not None and self._erro_na == indice:
            raise self._erro
        self.concluidas.append(text)
        return SynthesizedAudio(
            pcm=pcm_de(0.05 * len(text), self._taxa), sample_rate=self._taxa
        )


class FakeEncoder:
    """Finge comprimir: devolve os mesmos bytes com o rótulo certo.

    Não codifica de verdade porque codificar é do adapter e tem teste próprio.
    O que este fake preserva é o que o caso de uso consome: `extension` (que vai
    para a chave do ADR-0024) e `content_type` (que vai para o storage).
    """

    def __init__(self, *, erro: Exception | None = None) -> None:
        self.chamadas = 0
        self._erro = erro

    async def encode(self, audio: SynthesizedAudio) -> EncodedAudio:
        if self._erro is not None:
            raise self._erro
        self.chamadas += 1
        return EncodedAudio(
            data=audio.pcm, content_type=CONTENT_TYPE, extension=EXTENSION
        )


@dataclass(frozen=True, slots=True)
class Publicado:
    """Um evento publicado, com o turn a que pertence."""

    turn_id: UUID
    event: TurnEvent


class FakeTurnEvents:
    """Canal em memória. Publica numa lista e entrega por fila aos assinantes.

    A fila é o que torna o fake útil para o SSE: um teste publica de um lado e
    o `async for` do outro acorda, exatamente como o pub/sub real — sem Redis e
    sem `sleep` para "dar tempo" de a mensagem chegar.
    """

    def __init__(self, *, erro: Exception | None = None) -> None:
        self.publicados: list[Publicado] = []
        self._erro = erro
        self._assinantes: dict[UUID, list[asyncio.Queue[TurnEvent]]] = {}

    async def publish(self, turn_id: UUID, event: TurnEvent) -> None:
        if self._erro is not None:
            raise self._erro
        self.publicados.append(Publicado(turn_id, event))
        for fila in self._assinantes.get(turn_id, []):
            fila.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self, turn_id: UUID) -> AsyncIterator[AsyncIterator[TurnEvent]]:
        """Assina ANTES de devolver o iterador — como o adapter real.

        A fila é criada e registrada no `__aenter__`; é isso que faz o fake
        reproduzir a garantia da porta (nada publicado depois do `async with`
        se perde enquanto o caso de uso lê o banco). Um fake que registrasse a
        fila só na primeira iteração passaria nos mesmos testes e esconderia
        exatamente a corrida que a porta existe para fechar.
        """
        fila: asyncio.Queue[TurnEvent] = asyncio.Queue()
        self._assinantes.setdefault(turn_id, []).append(fila)

        async def eventos() -> AsyncIterator[TurnEvent]:
            while True:
                yield await fila.get()

        try:
            yield eventos()
        finally:
            self._assinantes[turn_id].remove(fila)

    def assinantes(self, turn_id: UUID) -> int:
        """Quantos streams estão ouvindo este turn AGORA.

        Público de propósito: é a única forma de um teste provar que o
        fechamento aconteceu — que a conexão foi devolvida em vez de vazar.
        """
        return len(self._assinantes.get(turn_id, []))

    @property
    def eventos(self) -> list[TurnEvent]:
        """Só os eventos, para a comparação de lista inteira com um `==` só."""
        return [p.event for p in self.publicados]
