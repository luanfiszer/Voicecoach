"""``Turn`` — um ciclo aluno-fala → professor-responde (visão §A).

O ciclo de vida segue o **ADR-0023**, que substituiu o ADR-0016. O que
sobreviveu do antigo é o princípio: o estado persistido é grosso
(``queued → processing → completed | failed``) e responde uma pergunta só —
*o trabalho terminou, e como terminou?*. O que caiu foi a premissa de que cada
artefato é **um** objeto produzido inteiro.

Com a entrega em cascata, o áudio da resposta é uma **sequência ordenada de
trechos** (``TurnAudioChunk``): o professor começa a falar enquanto o LLM ainda
está gerando o resto. Consequência que inverte a leitura antiga — **existe áudio
tocando com ``reply_text`` ainda nulo**.

Por que a etapa continua não sendo campo: com ela gravada, status e payload
viram duas fontes da mesma verdade e podem divergir — nada impediria
``stage='speaking'`` sem trecho nenhum. Derivando, esse estado é
**irrepresentável**.

Uma honestidade sobre a enum: ``completed`` é, a rigor, derivável de
``reply_audio_ref`` estar preenchido. Ele permanece no estado porque
``queued``/``processing`` (nada produzido ainda) e ``failed`` **não** são
deriváveis de artefato nenhum, e uma enum que cobre só metade dos desfechos
seria pior de consultar do que uma que cobre todos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from voicecoach.domain.errors import (
    InvalidStateTransitionError,
    OutOfOrderAudioChunkError,
    OutOfOrderCorrectionError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from voicecoach.domain.correction import Correction


class TurnStatus(StrEnum):
    """Estado de execução do Turn (ADR-0023).

    ``StrEnum`` (Python 3.11+) é uma enum cujos membros **são** strings: o valor
    vai para o banco e para o JSON sem conversão manual, e ainda assim o mypy
    cobra o tipo. Em C# você precisaria de um conversor ou de um
    ``[JsonStringEnumConverter]`` para o mesmo efeito.

    A enum **não ganha valor** com a cascata, e isso é deliberado: acrescentar
    ``speaking`` aqui quebraria o contrato aditivo do ADR-0008 (cliente antigo
    que trate os casos de forma exaustiva) e recriaria a duplicação que o
    ADR-0016 rejeitou. A granularidade fina vive em ``TurnStage``, que é
    derivado e por isso pode crescer sem migration.
    """

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TurnStage(StrEnum):
    """Etapa exibida ao aluno — **derivada**, nunca persistida (ADR-0023).

    O vocabulário é o mesmo do ADR-0016; o que mudou foi a ordem em que os
    artefatos aparecem. ``queued`` não está aqui de propósito: nenhuma tela
    distingue "na fila" de "transcrevendo", e expor isso vazaria mecânica de
    infraestrutura no contrato.
    """

    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    COMPLETED = "completed"


@dataclass(frozen=True)
class TurnAudioChunk:
    """Um trecho de áudio da resposta, já tocável pelo aluno (ADR-0023).

    ``frozen=True`` torna a instância imutável (o compilador gera ``__hash__`` e
    faz atribuição levantar erro) — o equivalente de um ``record`` com
    propriedades ``init``-only. É o que se quer aqui: um trecho já entregue não
    tem por que mudar, e a falha posterior do turn não o apaga.

    ``index`` é 0-based e denso, e a ordenação é por ele — **nunca** por
    ``created_at``. O instante de criação é medição (é o que dá ao CARD-012 o
    "quando o aluno pôde ouvir a primeira palavra"); a ordem é contrato de
    playback, e dois trechos podem ficar prontos no mesmo milissegundo.

    ``duration_seconds`` carrega a unidade no nome, ao contrário de
    ``Turn.audio_duration`` (um ``timedelta``). A diferença é intencional e vem
    do ADR-0023: a duração do trecho serve ao agendamento de playback no
    cliente, que fala em segundos fracionários, e não é insumo de quota — quem
    soma minutos falados é o áudio do **aluno**.
    """

    index: int
    storage_key: str
    duration_seconds: float
    text: str
    created_at: datetime


@dataclass
class Turn:
    """Um turno da conversa, com os artefatos que o pipeline vai produzindo.

    Cada artefato vem com o instante em que ficou pronto. Esses timestamps não
    são enfeite: são o que permite derivar a etapa (ADR-0023), medir a latência
    ponta a ponta que o CARD-012 exige, e detectar o "demorou mais que o normal"
    da tela de timeout.

    Sobre o áudio da resposta: ``reply_audio_ref`` aponta para o **áudio inteiro
    concatenado**, gravado ao completar o turn — é ele que o histórico reproduz
    e que a retenção longa guarda depois que os trechos expiram (ADR-0024).
    Nulo **com** ``synthesized_at`` preenchido significa "o áudio existiu e
    expirou" — diferente de "nunca houve áudio" (ambos nulos). É o que sustenta
    a regra "áudio expirado ≠ Turn inválido: transcrição e correções permanecem"
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

    # A chave que o cliente mandou no `Idempotency-Key` do POST (CARD-010).
    #
    # **Por que isto é campo da entidade e não um registro à parte.** É a
    # tensão honesta desta decisão: a chave é vocabulário de transporte, não de
    # pedagogia. Ela mora aqui porque a unicidade que a torna útil é imposta
    # pelo BANCO (índice único), e o que o banco grava é esta entidade — e
    # porque a pergunta que ela responde ("o aluno mandou esta mesma fala duas
    # vezes?") é sobre o Turn, não sobre uma tabela paralela de chaves com TTL
    # próprio, que seria uma segunda fonte de verdade.
    #
    # É o mesmo tipo de concessão já aceita em `input_audio_ref`, que também é
    # uma chave de infraestrutura morando no núcleo por ser parte do registro.
    #
    # Nulo é permitido para que a entidade continue construível sem passar pela
    # borda HTTP (o worker, os testes de domínio, um backfill). O índice único
    # é PARCIAL — `WHERE idempotency_key IS NOT NULL` — exatamente por isso.
    idempotency_key: str | None = None

    status: TurnStatus = TurnStatus.QUEUED

    transcript: str | None = None
    transcribed_at: datetime | None = None

    reply_text: str | None = None
    replied_at: datetime | None = None

    reply_audio_ref: str | None = None
    synthesized_at: datetime | None = None

    # `field(default_factory=list)` e não `= []`: num `@dataclass`, o default é
    # avaliado UMA vez, na definição da classe, e uma lista literal viraria
    # estado compartilhado por todas as instâncias — dois Turns diferentes com a
    # mesma lista de trechos. C# não tem essa armadilha porque `= new()` num
    # inicializador de propriedade roda por instância. O `default_factory` é a
    # forma de dizer "chame isto a cada construção".
    audio_chunks: list[TurnAudioChunk] = field(default_factory=list)

    # A segunda coleção filha do agregado, e a mais valiosa do produto
    # (visão §A). Diferente dos trechos, ela é escrita de **uma vez só**: o
    # professor entrega todas as correções juntas, no fim do JSON, e não há
    # cenário em que uma correção chegue depois. Por isso `attach_corrections`
    # é write-once, e não append-only como `append_audio_chunk`.
    corrections: list[Correction] = field(default_factory=list)

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

    # -- etapa derivada -----------------------------------------------------

    @property
    def stage(self) -> TurnStage:
        """A etapa que o app mostra, calculada dos artefatos (ADR-0023, item 4).

        **A ordem de avaliação é o contrato**, e é onde o bug nasce: checar
        ``transcript`` antes dos trechos devolveria ``thinking`` com o professor
        já falando. A cascata inverteu a tabela do ADR-0016 — o primeiro trecho
        de áudio existe **antes** de ``reply_text`` fechar, e por isso
        ``reply_text`` deixou de ser a condição de ``speaking``.

        Um turn ``failed`` não tem etapa própria: ele devolve a etapa em que
        parou, que é o que a tela de erro precisa dizer ("falhou enquanto o
        professor pensava"). É o ADR-0016 §6 preservado — o motivo e o ponto da
        falha saem de graça da tabela, sem campo extra.
        """
        if self.reply_audio_ref is not None:
            return TurnStage.COMPLETED
        if self.audio_chunks:
            return TurnStage.SPEAKING
        if self.transcript is not None:
            return TurnStage.THINKING
        return TurnStage.TRANSCRIBING

    @property
    def delivered_partially(self) -> bool:
        """O turn falhou **depois** de o aluno já ter ouvido alguma coisa.

        Derivado, não persistido (ADR-0023, item 5): falhar tendo entregue duas
        frases não é o mesmo desfecho que falhar antes de entregar qualquer
        coisa, e a diferença muda o que a tela diz ao aluno.
        """
        return self.status is TurnStatus.FAILED and bool(self.audio_chunks)

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
        """O ``spoken_reply`` do professor fechou por completo.

        Atenção ao significado novo (ADR-0023, item 7): sob o ADR-0016 isto
        queria dizer "o texto ficou disponível ao cliente". Não quer mais — o
        texto agora sai por trecho, junto com o áudio, e este método marca o fim
        da geração, não o começo da entrega.
        """
        self._require(TurnStatus.PROCESSING, action="attach_reply")
        self.reply_text = reply_text
        self.replied_at = now

    def append_audio_chunk(
        self,
        *,
        index: int,
        storage_key: str,
        duration_seconds: float,
        text: str,
        now: datetime,
    ) -> TurnAudioChunk:
        """Acrescenta um trecho já sintetizado e tocável (ADR-0023).

        É o **único** caminho de escrita da coleção. Duas invariantes:

        1. **Só em ``processing``.** Depois de ``completed`` ou ``failed`` o
           turn acabou, e um trecho que chega atrasado é bug de orquestração —
           não se acrescenta em silêncio a um turno que o aluno já viu fechar.
        2. **Índice denso e crescente.** O próximo índice é sempre o tamanho
           atual da coleção; repetido ou furado levanta
           ``OutOfOrderAudioChunkError``.

        O ``index`` vem de fora, e não é calculado aqui, porque quem grava no
        storage precisa dele **antes** para montar a chave
        ``reply/{index:03d}.mp3`` do ADR-0024. Calcular internamente tornaria o
        furo irrepresentável — o que soa bom, mas só moveria o erro para a
        divergência silenciosa entre a chave gravada e a posição na sequência.
        """
        self._require(TurnStatus.PROCESSING, action="append_audio_chunk")
        expected = len(self.audio_chunks)
        if index != expected:
            raise OutOfOrderAudioChunkError(expected=expected, received=index)
        chunk = TurnAudioChunk(
            index=index,
            storage_key=storage_key,
            duration_seconds=duration_seconds,
            text=text,
            created_at=now,
        )
        self.audio_chunks.append(chunk)
        return chunk

    def attach_corrections(self, corrections: Sequence[Correction]) -> None:
        """Grava as correções do professor. **Uma vez só** (CARD-013).

        Duas invariantes, e as duas nascem da forma como a correção é produzida:

        1. **Só em ``processing``, e só uma vez.** As correções vêm todas juntas
           no ``FeedbackReady``, que é o último evento do fluxo do professor
           (ADR-0031). Um segundo `attach` significaria ou reprocessamento de um
           turn já respondido — que o pipeline recusa — ou dois escritores no
           mesmo turn, que é o bug que o ``StaleTurnError`` do mapeador existe
           para denunciar. Substituir em silêncio apagaria a correção que o aluno
           já viu na tela.
        2. **Índice denso e 0-based**, como o do trecho de áudio: ele é a
           identidade natural da linha filha e a ordem pedagógica da lista.

        **Não recebe ``now``**, e a ausência é a decisão: todas as correções de
        um turn existem no mesmo instante — o ``replied_at``, gravado por
        ``attach_reply``. Um timestamp por correção seria o mesmo valor repetido
        N vezes, que é o dado duplicado que o ADR-0016 recusa.
        """
        self._require(TurnStatus.PROCESSING, action="attach_corrections")
        if self.corrections:
            raise InvalidStateTransitionError(
                entity="Turn",
                action="attach_corrections",
                state="processing (as correções já foram gravadas)",
            )
        for esperado, correcao in enumerate(corrections):
            if correcao.index != esperado:
                raise OutOfOrderCorrectionError(
                    expected=esperado, received=correcao.index
                )
        self.corrections = list(corrections)

    def attach_reply_audio(self, reply_audio_ref: str, now: datetime) -> None:
        """O áudio inteiro concatenado ficou pronto no storage."""
        self._require(TurnStatus.PROCESSING, action="attach_reply_audio")
        self.reply_audio_ref = reply_audio_ref
        self.synthesized_at = now

    def complete(self, now: datetime) -> None:
        """Fecha o Turn: tudo que o app precisa mostrar já existe.

        Note que os ``attach_*`` acima **não** exigem ordem entre si. É
        deliberado (ADR-0003 + ADR-0023): no V2 realtime as etapas deixam de ser
        sequenciais — STT incremental e TTS em stream se sobrepõem — e uma
        entidade que exigisse a ordem do V1 não sobreviveria à transição, que é
        justamente o que o ADR-0003 promete preservar. A ordem quem garante é o
        pipeline do worker (CARD-009), não a entidade.

        Pela mesma razão, completar **não** exige trecho nenhum: a cascata é
        como o worker do V1 trabalha, não uma invariante da entidade. O que se
        exige é ``reply_audio_ref`` — o áudio inteiro, que é o que o histórico
        reproduz.
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

        **Falhar não apaga trecho** (ADR-0023, item 6). É a invariante mais
        fácil de quebrar sem que nenhum teste de status perceba: o aluno já
        ouviu duas frases, e o registro tem de continuar dizendo que ele ouviu.
        Quem quiser saber se isso aconteceu pergunta a
        ``delivered_partially`` — que é derivado exatamente disto.
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
