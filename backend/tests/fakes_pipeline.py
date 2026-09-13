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
from voicecoach.application.ports.email_sender import EmailSenderError
from voicecoach.application.ports.media_storage import MediaStorageError
from voicecoach.application.ports.repositories import (
    ConflictingWriteError,
    RowNotFoundError,
)
from voicecoach.application.ports.speech_to_text import AudioInput, Segment, Transcript
from voicecoach.application.ports.teacher_llm import (
    TeacherEvent,
    TokenUsage,
    Utterance,
)
from voicecoach.application.ports.text_to_speech import (
    BYTES_PER_SAMPLE,
    SynthesizedAudio,
)
from voicecoach.application.ports.translator import Translated, TranslatorError
from voicecoach.application.ports.turn_events import TurnEvent
from voicecoach.domain.auth import (
    Credential,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
)
from voicecoach.domain.correction import CorrectionType
from voicecoach.domain.session import Session, SessionDigest, SessionSummary
from voicecoach.domain.student import Student
from voicecoach.domain.translation import Translation, TranslationTarget
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

    async def try_discard(self, turn_id: UUID, now: datetime) -> datetime | None:
        from voicecoach.domain.turn import TurnStatus

        turn = self.turns.get(turn_id)
        if turn is None:
            message = f"Turn {turn_id} não existe."
            raise LookupError(message)
        if turn.status is not TurnStatus.COMPLETED and turn.discarded_at is None:
            turn.discarded_at = now
        return turn.discarded_at


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


class FakeServiceBudget:
    """O kill switch, programável por um `bool` — não por acumular de verdade.

    O `add_cost` real soma em dois contadores Redis (diário/mensal); o fake só
    registra o que foi somado, para o teste afirmar "o worker chamou com este
    valor" sem precisar reconstruir a aritmética de centavos do adapter.
    """

    def __init__(self, *, excedido: bool = False) -> None:
        self.excedido = excedido
        self.somado: list[Decimal] = []

    async def add_cost(self, usd: Decimal, *, when: datetime) -> None:
        del when  # o fake não tem noção de dia/mês — quem testa isso é o adapter
        self.somado.append(usd)

    async def is_exceeded(self, *, when: datetime) -> bool:
        del when
        return self.excedido


class FakeSessionRepository:
    """``turns`` é opcional e serve só a `summary_for` (CARD-031) — os testes
    de `StartTurn`/`ProcessTurn` que não mexem com resumo nunca o passam.
    """

    def __init__(
        self, *sessions: Session, turns: FakeTurnRepository | None = None
    ) -> None:
        self.sessions: dict[UUID, Session] = {s.id: s for s in sessions}
        self._turns = turns or FakeTurnRepository()

    async def add(self, session: Session) -> None:
        self.sessions[session.id] = session

    async def get(self, session_id: UUID) -> Session | None:
        return self.sessions.get(session_id)

    async def update(self, session: Session) -> None:
        self.sessions[session.id] = session

    async def list_inactive(self, *, before: datetime, limit: int) -> list[UUID]:
        """Reproduz o `HAVING` do adapter, inclusive a exclusão do RF3."""
        from voicecoach.domain.turn import TurnStatus

        candidatas = []
        for sessao in self.sessions.values():
            if sessao.ended_at is not None:
                continue
            turnos = [
                t for t in self._turns.turns.values() if t.session_id == sessao.id
            ]
            if any(
                t.status in (TurnStatus.QUEUED, TurnStatus.PROCESSING) for t in turnos
            ):
                continue
            marco = max((t.created_at for t in turnos), default=sessao.started_at)
            if marco < before:
                candidatas.append((marco, sessao.id))
        candidatas.sort()
        return [session_id for _, session_id in candidatas[:limit]]

    async def try_end(self, session_id: UUID, now: datetime) -> datetime:
        """Reproduz o `COALESCE` do adapter: só escreve se ainda estiver nulo."""
        sessao = self.sessions.get(session_id)
        if sessao is None:
            # A MESMA exceção do adapter, não um `LookupError` genérico: o
            # `except` do `SweepInactiveSessionsHandler` é por tipo, e um fake
            # que levantasse a mãe deixaria o caminho de captura sem teste.
            message = f"Session {session_id} não existe."
            raise RowNotFoundError(message)
        if sessao.ended_at is None:
            sessao.ended_at = now
        return sessao.ended_at

    async def list_for_student(
        self, student_id: UUID, *, since: datetime
    ) -> list[SessionDigest]:
        """Reproduz o `outer join` do adapter: sessão sem turn ENTRA, com zeros."""
        na_janela = [
            s
            for s in self.sessions.values()
            if s.student_id == student_id and s.started_at >= since
        ]
        na_janela.sort(key=lambda s: s.started_at, reverse=True)
        digests = []
        for sessao in na_janela:
            turnos = [
                t for t in self._turns.turns.values() if t.session_id == sessao.id
            ]
            digests.append(
                SessionDigest(
                    id=sessao.id,
                    started_at=sessao.started_at,
                    ended_at=sessao.ended_at,
                    spoken=sum((t.audio_duration for t in turnos), timedelta(0)),
                    turns=len(turnos),
                    corrections=sum(len(t.corrections) for t in turnos),
                    last_turn_at=max((t.created_at for t in turnos), default=None),
                )
            )
        return digests

    async def summary_for(self, session_id: UUID) -> SessionSummary:
        turnos = [t for t in self._turns.turns.values() if t.session_id == session_id]
        por_tipo: dict[CorrectionType, int] = {}
        for turno in turnos:
            for correcao in turno.corrections:
                por_tipo[correcao.type] = por_tipo.get(correcao.type, 0) + 1
        return SessionSummary(
            spoken=sum((t.audio_duration for t in turnos), timedelta(0)),
            turns=len(turnos),
            corrections_by_type=por_tipo,
        )


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
        language: str = "en",
        confidence: float = -0.2,
        no_speech: float = 0.0,
        # Um segmento por padrão, não `()`: vazio significa "silêncio" para o
        # caso de uso (CARD-040) e desviaria o caminho feliz para recusa.
        segments: tuple[Segment, ...] | None = None,
    ) -> None:
        self.texto = texto
        self._erro = erro
        self._language = language
        self._confidence = confidence
        self._no_speech = no_speech
        self._segments = segments
        self.chamadas: list[bytes] = []

    async def transcribe(self, audio: AudioInput) -> Transcript:
        if self._erro is not None:
            raise self._erro
        self.chamadas.append(audio.data)
        segments = self._segments
        if segments is None:
            segments = (Segment(start_seconds=0.0, end_seconds=4.0, text=self.texto),)
        return Transcript(
            text=self.texto,
            language=self._language,
            duration_seconds=4.0,
            confidence=self._confidence,
            no_speech=self._no_speech,
            segments=segments,
        )


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


class FakeTranslationRepository:
    """Guarda traduções em memória, pela chave composta (CARD-036).

    A escrita duplicada **levanta**, como no `FakeUsageEventRepository`: é a
    chave primária do Postgres reproduzida em memória, para que o teste do RF4
    possa afirmar "uma tradução, uma linha" sem precisar de banco.
    """

    def __init__(self, *translations: Translation) -> None:
        self.translations: dict[tuple[UUID, TranslationTarget, int], Translation] = {
            (t.turn_id, t.target, t.index): t for t in translations
        }

    async def get(
        self, turn_id: UUID, target: TranslationTarget, index: int
    ) -> Translation | None:
        return self.translations.get((turn_id, target, index))

    async def add(self, translation: Translation) -> None:
        chave = (translation.turn_id, translation.target, translation.index)
        if chave in self.translations:
            message = f"tradução {chave} já existe."
            raise RuntimeError(message)
        self.translations[chave] = translation


class FakeStudentRepository:
    """Guarda ``Student`` em memória, por id (CARD-049)."""

    def __init__(self) -> None:
        self.students: dict[UUID, Student] = {}

    async def add(self, student: Student) -> None:
        self.students[student.id] = student

    async def get(self, student_id: UUID) -> Student | None:
        return self.students.get(student_id)


class FakeCredentialRepository:
    """Guarda ``Credential`` em memória, com o mesmo índice único do banco
    (CARD-049) — dois e-mails iguais levantam ``ConflictingWriteError``, a
    mesma tradução que ``SqlAlchemyUnitOfWork`` faz para o ``IntegrityError``
    real, para que ``RegisterStudentHandler`` seja testável sem Postgres.
    """

    def __init__(self, *credentials: Credential) -> None:
        self.by_id: dict[UUID, Credential] = {c.id: c for c in credentials}

    async def add(self, credential: Credential) -> None:
        if any(c.email == credential.email for c in self.by_id.values()):
            message = f"e-mail {credential.email} já cadastrado."
            raise ConflictingWriteError(message)
        self.by_id[credential.id] = credential

    async def get_by_email(self, email: str) -> Credential | None:
        return next((c for c in self.by_id.values() if c.email == email), None)

    async def get_by_student_id(self, student_id: UUID) -> Credential | None:
        return next(
            (c for c in self.by_id.values() if c.student_id == student_id), None
        )

    async def mark_email_verified(self, student_id: UUID, when: datetime) -> None:
        credencial = next(c for c in self.by_id.values() if c.student_id == student_id)
        credencial.email_verified_at = when

    async def update_password_hash(self, student_id: UUID, password_hash: str) -> None:
        credencial = next(c for c in self.by_id.values() if c.student_id == student_id)
        credencial.password_hash = password_hash


class FakeRefreshTokenRepository:
    """Guarda ``RefreshToken`` em memória, incluindo a revogação em massa por
    família — a peça central da detecção de reuso (ADR-0007, CARD-049).
    """

    def __init__(self, *tokens: RefreshToken) -> None:
        self.by_id: dict[UUID, RefreshToken] = {t.id: t for t in tokens}

    async def add(self, token: RefreshToken) -> None:
        self.by_id[token.id] = token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return next(
            (t for t in self.by_id.values() if t.token_hash == token_hash), None
        )

    async def mark_revoked(self, token_id: UUID, when: datetime) -> None:
        self.by_id[token_id].revoked_at = when

    async def revoke_family(self, family_id: UUID, when: datetime) -> None:
        for token in self.by_id.values():
            if token.family_id == family_id and token.revoked_at is None:
                token.revoked_at = when

    async def revoke_all_for_student(self, student_id: UUID, when: datetime) -> None:
        for token in self.by_id.values():
            if token.student_id == student_id and token.revoked_at is None:
                token.revoked_at = when


class FakePasswordHasher:
    """Hash determinístico e reversível de mentirinha — nunca use fora de teste.

    O ponto NÃO é criptografia (isso é o ``argon2-cffi`` real, testado em
    ``tests/adapters/test_argon2_password_hasher.py``); é a REGRA que
    ``LoginStudentHandler`` implementa em cima da porta: chamar ``verify``
    sempre, mesmo quando a credencial não existe.
    """

    def __init__(self) -> None:
        self.chamadas_de_verify = 0
        self.chamadas_de_hash = 0

    async def hash(self, password: str) -> str:
        self.chamadas_de_hash += 1
        return f"hash-de-{password}"

    async def verify(self, password: str, password_hash: str) -> bool:
        self.chamadas_de_verify += 1
        return password_hash == f"hash-de-{password}"


class FakeAccessTokenIssuer:
    """Emite um token que é a própria representação do ``student_id`` — o
    suficiente para o caso de uso, que só chama ``issue``. ``decode`` não é
    exercitado por nenhum caso de uso (é a borda quem chama), mas está aqui
    para satisfazer a porta.
    """

    def __init__(self) -> None:
        self.emitidos: list[UUID] = []

    def issue(self, student_id: UUID) -> str:
        self.emitidos.append(student_id)
        return f"access-token-para-{student_id}"

    def decode(self, token: str) -> UUID:
        return UUID(token.removeprefix("access-token-para-"))


class FakeEmailVerificationTokenRepository:
    """Guarda ``EmailVerificationToken`` em memória (CARD-049)."""

    def __init__(self, *tokens: EmailVerificationToken) -> None:
        self.by_id: dict[UUID, EmailVerificationToken] = {t.id: t for t in tokens}

    async def add(self, token: EmailVerificationToken) -> None:
        self.by_id[token.id] = token

    async def get_by_hash(self, token_hash: str) -> EmailVerificationToken | None:
        return next(
            (t for t in self.by_id.values() if t.token_hash == token_hash), None
        )

    async def mark_used(self, token_id: UUID, when: datetime) -> None:
        self.by_id[token_id].used_at = when


class FakePasswordResetTokenRepository:
    """Guarda ``PasswordResetToken`` em memória (CARD-049)."""

    def __init__(self, *tokens: PasswordResetToken) -> None:
        self.by_id: dict[UUID, PasswordResetToken] = {t.id: t for t in tokens}

    async def add(self, token: PasswordResetToken) -> None:
        self.by_id[token.id] = token

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        return next(
            (t for t in self.by_id.values() if t.token_hash == token_hash), None
        )

    async def mark_used(self, token_id: UUID, when: datetime) -> None:
        self.by_id[token_id].used_at = when


class FakeEmailSender:
    """Registra os e-mails "enviados", sem tocar rede (CARD-049).

    ``falha`` programa o caminho triste do RNF do card: "o cadastro conclui,
    o e-mail é retentado" — o teste liga a falha e afirma que o handler não
    propaga.
    """

    def __init__(self, *, falha: bool = False) -> None:
        self.falha = falha
        self.enviados: list[tuple[str, str]] = []
        self.resets_enviados: list[tuple[str, str]] = []

    async def send_verification(self, *, to: str, verification_url: str) -> None:
        if self.falha:
            message = "provedor de e-mail fora do ar (fake)"
            raise EmailSenderError(message)
        self.enviados.append((to, verification_url))

    async def send_password_reset(self, *, to: str, reset_url: str) -> None:
        if self.falha:
            message = "provedor de e-mail fora do ar (fake)"
            raise EmailSenderError(message)
        self.resets_enviados.append((to, reset_url))


class FakeTranslator:
    """Devolve um texto fixo e conta as chamadas — é a contagem que prova o RF4.

    ``chamadas`` é o instrumento central dos testes deste card: "não pagou duas
    vezes" só é verificável olhando quantas vezes o provedor foi chamado.
    """

    def __init__(
        self,
        *,
        texto: str = "Qual praia você foi?",
        erro: Exception | None = None,
        model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        self.texto = texto
        self.model = model
        self._erro = erro
        self.chamadas: list[str] = []

    async def to_portuguese(self, text: str) -> Translated:
        self.chamadas.append(text)
        if self._erro is not None:
            raise self._erro
        return Translated(
            text=self.texto,
            usage=TokenUsage(
                model=self.model,
                input_tokens=120,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
                output_tokens=40,
            ),
        )


def tradutor_fora_do_ar() -> FakeTranslator:
    """O provedor caído — o caminho do RF6."""
    return FakeTranslator(erro=TranslatorError("o tradutor não atendeu"))
