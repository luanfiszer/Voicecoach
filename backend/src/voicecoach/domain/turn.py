"""``Turn`` — um ciclo aluno-fala → professor-responde (visão §A).

O ciclo de vida segue o **ADR-0016**: o estado persistido é grosso
(``queued → processing → completed | failed``) e responde uma pergunta só —
*o trabalho terminou, e como terminou?*. A **etapa** que o app mostra
("transcrevendo", "professor pensando", "áudio a caminho") **não** é campo:
é derivada dos artefatos já produzidos, na borda (CARD-010).

Por que assim: com a etapa gravada num campo próprio, status e payload viram
duas fontes da mesma verdade e podem divergir — nada impediria
``status='speaking'`` com ``reply_text`` nulo. Derivando, esse estado é
**irrepresentável**.

Uma honestidade sobre a enum: ``completed`` é, a rigor, derivável de
``reply_audio_ref`` estar preenchido. Ele permanece no estado porque
``queued``/``processing`` (nada produzido ainda) e ``failed`` **não** são
deriváveis de artefato nenhum, e uma enum que cobre só metade dos desfechos
seria pior de consultar do que uma que cobre todos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from voicecoach.domain.errors import InvalidStateTransitionError


class TurnStatus(StrEnum):
    """Estado de execução do Turn (ADR-0016).

    ``StrEnum`` (Python 3.11+) é uma enum cujos membros **são** strings: o valor
    vai para o banco e para o JSON sem conversão manual, e ainda assim o mypy
    cobra o tipo. Em C# você precisaria de um conversor ou de um
    ``[JsonStringEnumConverter]`` para o mesmo efeito.
    """

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Turn:
    """Um turno da conversa, com os artefatos que o pipeline vai produzindo.

    Cada artefato vem com o instante em que ficou pronto. Esses timestamps não
    são enfeite: são o que permite derivar a etapa (ADR-0016), medir a latência
    ponta a ponta que o CARD-012 exige, e detectar o "demorou mais que o normal"
    da tela de timeout.

    Sobre o áudio da resposta: ``reply_audio_ref`` nulo **com**
    ``synthesized_at`` preenchido significa "o áudio existiu e expirou" — que é
    diferente de "nunca houve áudio" (ambos nulos). É o que sustenta a regra
    "áudio expirado ≠ Turn inválido: transcrição e correções permanecem"
    (CARD-017), sem precisar de campo novo.
    """

    id: UUID
    session_id: UUID
    # Áudio que o aluno enviou. Existe desde o nascimento do Turn: sem ele não
    # há o que processar.
    input_audio_ref: str
    # Quanto tempo o aluno falou. É o insumo da quota em **minutos falados**
    # (CARD-015) e do "8 minutos hoje" do resumo de sessão. `timedelta` é o tipo
    # da stdlib para duração — o `TimeSpan` do C# — e evita a unidade implícita
    # que um `int segundos` carregaria no nome.
    audio_duration: timedelta
    created_at: datetime

    status: TurnStatus = TurnStatus.QUEUED

    transcript: str | None = None
    transcribed_at: datetime | None = None

    reply_text: str | None = None
    replied_at: datetime | None = None

    reply_audio_ref: str | None = None
    synthesized_at: datetime | None = None

    failure_reason: str | None = None
    failed_at: datetime | None = None

    started_processing_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        """Valida o que precisa valer desde o instante zero.

        ``__post_init__`` é um gancho que o ``@dataclass`` chama no fim do
        ``__init__`` gerado — é onde se põe validação sem ter que escrever o
        construtor à mão. Não há equivalente exato em C#: o mais próximo é
        validar no corpo do construtor primário de um ``record``.
        """
        if self.audio_duration <= timedelta(0):
            message = "Turn: a duração do áudio precisa ser positiva."
            raise ValueError(message)

    # -- transições ---------------------------------------------------------

    def start_processing(self, now: datetime) -> None:
        """O worker pegou o Turn da fila."""
        self._require(TurnStatus.QUEUED, action="start_processing")
        self.status = TurnStatus.PROCESSING
        self.started_processing_at = now

    def attach_transcript(self, transcript: str, now: datetime) -> None:
        """O STT terminou."""
        self._require(TurnStatus.PROCESSING, action="attach_transcript")
        self.transcript = transcript
        self.transcribed_at = now

    def attach_reply(self, reply_text: str, now: datetime) -> None:
        """O professor (LLM) respondeu."""
        self._require(TurnStatus.PROCESSING, action="attach_reply")
        self.reply_text = reply_text
        self.replied_at = now

    def attach_reply_audio(self, reply_audio_ref: str, now: datetime) -> None:
        """O TTS terminou de sintetizar."""
        self._require(TurnStatus.PROCESSING, action="attach_reply_audio")
        self.reply_audio_ref = reply_audio_ref
        self.synthesized_at = now

    def complete(self, now: datetime) -> None:
        """Fecha o Turn: tudo que o app precisa mostrar já existe.

        Note que os três ``attach_*`` acima **não** exigem ordem entre si. É
        deliberado (ADR-0003 + ADR-0016): no V2 realtime as etapas deixam de ser
        sequenciais — STT incremental e TTS em stream se sobrepõem — e uma
        entidade que exigisse a ordem do V1 não sobreviveria à transição, que é
        justamente o que o ADR-0003 promete preservar. A ordem quem garante é o
        pipeline do worker (CARD-009), não a entidade.
        """
        self._require(TurnStatus.PROCESSING, action="complete")
        if self.transcript is None or self.reply_text is None:
            raise InvalidStateTransitionError(
                entity="Turn",
                action="complete",
                state="processing (transcrição ou resposta ausente)",
            )
        if self.reply_audio_ref is None:
            raise InvalidStateTransitionError(
                entity="Turn",
                action="complete",
                state="processing (áudio da resposta ausente)",
            )
        self.status = TurnStatus.COMPLETED
        self.completed_at = now

    def fail(self, reason: str, now: datetime) -> None:
        """Marca o Turn como falho, preservando o que já tinha sido produzido.

        Aceita a partir de ``queued`` **e** de ``processing``: um Turn pode
        morrer antes de alguém pegá-lo da fila (o worker caiu), e é isso que dá
        dono ao "demorou mais que o normal" da tela de timeout.
        """
        if self.status in (TurnStatus.COMPLETED, TurnStatus.FAILED):
            raise InvalidStateTransitionError(
                entity="Turn", action="fail", state=self.status.value
            )
        self.status = TurnStatus.FAILED
        self.failure_reason = reason
        self.failed_at = now

    # -- interno ------------------------------------------------------------

    def _require(self, expected: TurnStatus, *, action: str) -> None:
        if self.status is not expected:
            raise InvalidStateTransitionError(
                entity="Turn", action=action, state=self.status.value
            )
