"""Processa um turn de ponta a ponta, em cascata (ADR-0023, ADR-0031).

**O que este módulo é.** O primeiro handler do projeto — o lugar onde as portas
deixam de existir isoladas e viram um pipeline. Ele não conhece Redis, Postgres,
S3, arq, nem HTTP: recebe as capacidades por parâmetro e devolve efeito no
``Turn``. É por isso que o teste dele roda em milissegundos sem infraestrutura
nenhuma.

**Cascata, não cadeia.** Uma cadeia ``STT → LLM → TTS`` sequencial entrega o
primeiro áudio depois de a resposta inteira estar escrita — ~4,1 s medidos. Aqui
o ``async for`` consome o professor enquanto ele ainda gera, e cada sentença vira
áudio no ato. O aluno ouve a primeira frase enquanto o modelo escreve a terceira.

**A forma da concorrência é o contrato, e é a decisão cara desta sessão.** São
duas corrotinas ligadas por uma ``asyncio.Queue``:

    sintetizar()  async for evento → SpokenSentence → tts → fila.put(...)
    gravar()      fila.get() → codifica → storage.put → append_audio_chunk

A alternativa óbvia — ``asyncio.create_task`` por sentença — é mais curta e está
**errada**: ela não preserva ordem nenhuma, e a ordem aqui é invariante de
domínio. ``Turn.append_audio_chunk`` exige índice denso e crescente; duas
sentenças em voo, a segunda terminando antes da primeira, e o turn levanta
``OutOfOrderAudioChunkError``. O modo de falha é intermitente e depende do
tamanho do texto — o pior tipo de bug para descobrir em produção. Com um
consumidor só sobre uma fila FIFO, a ordem é **preservada por construção**, e o
paralelismo que interessa continua existindo: a síntese da sentença N+1 corre
enquanto o trecho N sobe para o storage.

**Três idiomas de Python sem paralelo direto em C#**, porque são o miolo daqui:

- ``asyncio.Queue`` é o ``Channel<T>`` do .NET: fila assíncrona onde ``get()``
  suspende a corrotina até haver item, sem travar a thread;
- ``asyncio.TaskGroup`` (3.11+) roda as duas corrotinas e **cancela a irmã**
  quando uma falha, esperando as duas terminarem antes de sair do ``async with``.
  O mais próximo em C# é ``Parallel.ForEachAsync`` com ``CancellationToken``
  ligado — mas aqui o erro sai empacotado num ``ExceptionGroup``, e é por isso
  que este módulo o desempacota antes de deixá-lo subir;
- cancelar a corrotina que faz ``async for`` sobre o gerador do professor é o
  que **fecha o gerador** e para a geração (ADR-0031, item 6). Não há
  ``CancellationToken`` a repassar: o cancelamento é o próprio protocolo do
  gerador assíncrono, e engolir o ``GeneratorExit`` faria o produto pagar por
  tokens que ninguém vai ouvir.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, assert_never

from voicecoach.application.ports.audio_encoder import AudioEncodingError
from voicecoach.application.ports.media_storage import MediaStorageError
from voicecoach.application.ports.speech_to_text import AudioInput, SttError
from voicecoach.application.ports.teacher_llm import (
    FeedbackReady,
    LlmError,
    Speaker,
    SpokenSentence,
    Utterance,
)
from voicecoach.application.ports.text_to_speech import TtsError, concat
from voicecoach.application.ports.turn_events import (
    ChunkReady,
    Completed,
    Failed,
    FeedbackAvailable,
    Transcribed,
    TurnEventsError,
)
from voicecoach.domain.media_keys import reply_chunk_key, reply_full_key
from voicecoach.domain.turn import TurnStatus

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from uuid import UUID

    from voicecoach.application.ports.audio_encoder import AudioEncoder
    from voicecoach.application.ports.media_storage import MediaStorage
    from voicecoach.application.ports.repositories import (
        SessionRepository,
        TurnRepository,
        UnitOfWork,
    )
    from voicecoach.application.ports.speech_to_text import SpeechToText
    from voicecoach.application.ports.teacher_llm import TeacherLlm
    from voicecoach.application.ports.text_to_speech import (
        SynthesizedAudio,
        TextToSpeech,
    )
    from voicecoach.application.ports.turn_events import TurnEvent, TurnEvents
    from voicecoach.domain.turn import Turn

logger = logging.getLogger(__name__)

# Falhas de INFRAESTRUTURA que o pipeline sabe traduzir em "o turn falhou".
# Todas herdam de `RuntimeError` e nenhuma de `DomainError`, e a distinção é a
# do ADR-0017: motor que cai é infraestrutura; invariante violada é bug do
# chamador e **não** está aqui de propósito — um `OutOfOrderAudioChunkError`
# capturado como "falha do turn" esconderia exatamente o defeito de orquestração
# que ele existe para denunciar.
FALHAS_DE_INFRAESTRUTURA = (
    SttError,
    LlmError,
    TtsError,
    MediaStorageError,
    AudioEncodingError,
)

REPROCESSAMENTO_APOS_ENTREGA = (
    "reprocessamento recusado: o aluno já ouviu parte desta resposta"
)


class TurnNotFoundError(LookupError):
    """Pediram para processar um turn que não existe.

    Não é falha de infraestrutura nem de domínio: é um job apontando para nada,
    o que só acontece se a fila e o banco divergirem. Sobe, para que o job falhe
    ruidosamente em vez de sumir.
    """


@dataclass(frozen=True, slots=True)
class ProcessTurn:
    """O comando. Um handler, uma entrada — CQS sem MediatR.

    ``final_attempt`` é a única concessão à mecânica da fila, e ela é deliberada.
    O ``arq`` reexecuta a **função inteira** quando ela levanta, e o card exige
    duas coisas incompatíveis sem esta informação: *"STT falhando ⇒ failed com
    motivo e retry respeitando o limite"* e *"nada de retry depois do primeiro
    trecho"*. O handler resolve as duas assim:

    - falha **depois** de um trecho entregue ⇒ marca ``failed`` e **não levanta**
      (o ``arq`` não tem por que tentar de novo);
    - falha **antes** de qualquer trecho, ainda havendo tentativa ⇒ **levanta**,
      e o ``arq`` tenta de novo;
    - falha antes de qualquer trecho, na última tentativa ⇒ marca ``failed``.

    Um ``bool`` e não o ``ctx`` do arq: o handler precisa saber *"esta é a última
    chance?"*, não *"quantas tentativas restam e qual o backoff"*. A tradução é
    de quem conhece a fila.
    """

    turn_id: UUID
    final_attempt: bool


@dataclass(frozen=True, slots=True)
class _Sintetizado:
    """O que atravessa a fila interna: o áudio e o texto que o originou.

    O texto viaja junto porque ``TurnAudioChunk`` o guarda — é ele que o app
    mostra legendado durante o playback. Reconstruí-lo do lado do consumidor
    exigiria um segundo canal em paralelo, com as duas pontas podendo sair de
    sincronia.
    """

    text: str
    audio: SynthesizedAudio


class ProcessTurnHandler:
    """Compõe as portas num turn inteiro.

    Recebe tudo por parâmetro nomeado. Não há container de DI aqui: quem monta é
    a composition root do worker, e o ``clock`` entra junto das portas pelo mesmo
    motivo que elas — ``datetime.now()`` chamado lá dentro tornaria impossível
    afirmar, num teste, que o primeiro trecho existiu **antes** de ``replied_at``.
    """

    def __init__(
        self,
        *,
        turns: TurnRepository,
        sessions: SessionRepository,
        unit_of_work: UnitOfWork,
        storage: MediaStorage,
        speech_to_text: SpeechToText,
        teacher: TeacherLlm,
        text_to_speech: TextToSpeech,
        encoder: AudioEncoder,
        events: TurnEvents,
        clock: Callable[[], datetime],
        history_turns: int,
    ) -> None:
        self._turns = turns
        self._sessions = sessions
        self._uow = unit_of_work
        self._storage = storage
        self._stt = speech_to_text
        self._teacher = teacher
        self._tts = text_to_speech
        self._encoder = encoder
        self._events = events
        self._clock = clock
        self._history_turns = history_turns

    async def handle(self, command: ProcessTurn) -> None:
        turn = await self._turns.get(command.turn_id)
        if turn is None:
            message = f"Turn {command.turn_id} não existe."
            raise TurnNotFoundError(message)

        if turn.status in (TurnStatus.COMPLETED, TurnStatus.FAILED):
            # Job repetido de um turn que já terminou é **no-op**, não erro
            # (ADR-0005 + card): a fila garante entrega ao menos uma vez, e
            # levantar aqui transformaria uma reentrega normal em incidente.
            logger.info("turn %s já terminou (%s): nada a fazer", turn.id, turn.status)
            return

        if turn.audio_chunks:
            # `processing` COM trecho = uma tentativa anterior morreu depois de o
            # aluno já ter ouvido alguma coisa. Reprocessar faria o professor
            # recomeçar a falar do zero — o análogo exato do que o ADR-0030
            # proibiu dentro do adapter de LLM. O `arq` não sabe disso; a guarda
            # é nossa, e o lugar dela é aqui, olhando o estado do Turn.
            await self._marcar_falha(turn, REPROCESSAMENTO_APOS_ENTREGA)
            return

        if turn.status is TurnStatus.QUEUED:
            turn.start_processing(self._clock())
            await self._gravar(turn)

        try:
            await self._executar(turn)
        except FALHAS_DE_INFRAESTRUTURA as exc:
            await self._tratar_falha(turn, exc, final=command.final_attempt)

    # -- o pipeline ---------------------------------------------------------

    async def _executar(self, turn: Turn) -> None:
        session = await self._sessions.get(turn.session_id)
        if session is None:
            message = f"Session {turn.session_id} do turn {turn.id} não existe."
            raise TurnNotFoundError(message)
        student_id = session.student_id

        transcript = await self._transcrever(turn)
        history = await self._montar_historico(turn, transcript)

        sintetizados, feedback = await self._cascata(turn, student_id, history)
        if feedback is None:
            message = "o professor fechou o fluxo sem entregar o feedback"
            raise LlmError(message)

        # As correções entram na entidade ANTES do `_gravar` que já existia:
        # elas viram N inserts na MESMA escrita, e não numa nova. É a resposta à
        # pergunta "em que momento do pipeline as correções são gravadas?" —
        # aqui, e não no fechamento, por duas razões:
        #
        # 1. **Custo zero no caminho crítico.** Este ponto vem DEPOIS do último
        #    trecho de áudio (o `FeedbackReady` fecha o fluxo do professor), e o
        #    `_gravar` já acontecia. Gravar no fechamento não pouparia nada e
        #    ainda assim seria mais tarde.
        # 2. **Falha posterior não apaga o que já é do aluno.** É o mesmo
        #    princípio do ADR-0023 item 6 aplicado ao dado mais valioso do
        #    produto: se o `reply/full` falhar depois disto, o turn fica `failed`
        #    — e as correções continuam lá, para o histórico do CARD-016.
        turn.attach_reply(feedback.feedback.spoken_reply, self._clock())
        turn.attach_corrections(feedback.feedback.corrections)
        await self._gravar(turn)
        await self._publicar(
            turn.id,
            FeedbackAvailable(corrections=feedback.feedback.corrections),
        )

        await self._fechar(turn, student_id, sintetizados)

    async def _transcrever(self, turn: Turn) -> str:
        bytes_do_aluno = await self._storage.get(turn.input_audio_ref)
        transcript = await self._stt.transcribe(AudioInput(data=bytes_do_aluno))
        turn.attach_transcript(transcript.text, self._clock())
        await self._gravar(turn)
        await self._publicar(turn.id, Transcribed(transcript=transcript.text))
        return transcript.text

    async def _montar_historico(self, turn: Turn, fala_atual: str) -> list[Utterance]:
        """As trocas anteriores da sessão, mais a fala nova do aluno no fim.

        A ordem importa e é contrato da porta (ADR-0031): o **último** item é a
        fala nova. Sem isto o professor responderia como se cada turno fosse o
        primeiro da conversa.
        """
        anteriores = await self._turns.list_by_session(
            turn.session_id, limit=self._history_turns
        )
        historico: list[Utterance] = []
        for anterior in anteriores:
            if anterior.transcript is not None:
                historico.append(Utterance(Speaker.STUDENT, anterior.transcript))
            if anterior.reply_text is not None:
                historico.append(Utterance(Speaker.TEACHER, anterior.reply_text))
        historico.append(Utterance(Speaker.STUDENT, fala_atual))
        return historico

    async def _cascata(
        self, turn: Turn, student_id: UUID, history: list[Utterance]
    ) -> tuple[list[SynthesizedAudio], FeedbackReady | None]:
        """As duas corrotinas, e o desempacotamento do ``ExceptionGroup``.

        Tudo que a cascata acumula é **local a esta chamada** — nada em ``self``.
        Guardar o feedback num atributo de instância seria a corrida clássica de
        um handler reusado por dois jobs, e o worker reusa: o ``ctx`` do arq vive
        o processo inteiro (ADR-0025).
        """
        fila: asyncio.Queue[_Sintetizado | None] = asyncio.Queue()
        sintetizados: list[SynthesizedAudio] = []
        feedback: FeedbackReady | None = None

        async def sintetizar() -> None:
            # `nonlocal` diz que a atribuição abaixo mexe na variável da função
            # de fora, e não cria uma nova local. É o idioma Python para o que em
            # C# uma lambda faz de graça ao capturar a variável do escopo.
            nonlocal feedback
            try:
                async for evento in self._teacher.respond_streaming(history):
                    match evento:
                        case SpokenSentence(text=texto):
                            audio = await self._tts.synthesize(texto)
                            await fila.put(_Sintetizado(text=texto, audio=audio))
                        case FeedbackReady():
                            feedback = evento
                        case _:  # pragma: no cover - o mypy prova que é inalcançável
                            assert_never(evento)
            finally:
                # A sentinela vai no `finally` e não depois do laço: se o
                # professor levantar, o consumidor precisa acordar e terminar,
                # ou o `TaskGroup` esperaria para sempre por uma fila que
                # ninguém mais alimenta.
                await fila.put(None)

        async def gravar() -> None:
            while (item := await fila.get()) is not None:
                await self._gravar_trecho(turn, student_id, item)
                sintetizados.append(item.audio)

        try:
            async with asyncio.TaskGroup() as grupo:
                grupo.create_task(sintetizar())
                grupo.create_task(gravar())
        except BaseExceptionGroup as grupo_de_erros:
            raise _primeira_falha(grupo_de_erros) from None

        return sintetizados, feedback

    async def _gravar_trecho(
        self, turn: Turn, student_id: UUID, item: _Sintetizado
    ) -> None:
        """Grava um trecho e o torna visível ao aluno — nesta ordem.

        Storage **antes** do banco, e o banco antes do evento: o app recebe o
        evento e vai buscar o áudio, então uma linha que aponte para um objeto
        que ainda não subiu é um 404 na mão do aluno. Na ordem inversa, o pior
        caso é um objeto órfão no bucket, que a retenção de 1 dia (ADR-0024)
        recolhe sozinha.

        O ``index`` é calculado **aqui**, do tamanho da coleção, e é isso que
        torna a ordem correta por construção: só existe um chamador desta
        função, e ele é sequencial.
        """
        index = len(turn.audio_chunks)
        codificado = await self._encoder.encode(item.audio)
        chave = reply_chunk_key(
            student_id, turn.session_id, turn.id, index, codificado.extension
        )
        await self._storage.put(chave, codificado.data, codificado.content_type)
        chunk = turn.append_audio_chunk(
            index=index,
            storage_key=chave,
            duration_seconds=item.audio.duration_seconds,
            text=item.text,
            now=self._clock(),
        )
        await self._gravar(turn)
        await self._publicar(
            turn.id,
            ChunkReady(
                index=chunk.index,
                storage_key=chunk.storage_key,
                duration_seconds=chunk.duration_seconds,
                text=chunk.text,
            ),
        )

    async def _fechar(
        self, turn: Turn, student_id: UUID, sintetizados: list[SynthesizedAudio]
    ) -> None:
        """Concatena, grava o ``reply/full`` e fecha o turn.

        ``concat`` mora em ``application`` porque é aritmética sobre ``bytes``
        (ADR-0033); comprimir mora numa porta porque precisa de um codec. As
        duas acontecem aqui, no último momento possível — juntar PCM é um
        ``b"".join``, e juntar AAC exigiria decodificar tudo de volta.
        """
        if not sintetizados:
            message = "o professor não produziu nenhuma sentença falável"
            raise LlmError(message)

        codificado = await self._encoder.encode(concat(sintetizados))
        chave = reply_full_key(
            student_id, turn.session_id, turn.id, codificado.extension
        )
        await self._storage.put(chave, codificado.data, codificado.content_type)
        turn.attach_reply_audio(chave, self._clock())
        turn.complete(self._clock())
        await self._gravar(turn)
        await self._publicar(turn.id, Completed(reply_audio_key=chave))

    # -- caminho triste -----------------------------------------------------

    async def _tratar_falha(self, turn: Turn, exc: Exception, *, final: bool) -> None:
        """Decide entre marcar o turn como falho e deixar o ``arq`` tentar de novo.

        A pergunta que separa os dois casos não é "que erro foi?", é **"o aluno
        já ouviu alguma coisa?"**. Ela é respondida pela coleção de trechos, que
        `fail()` não apaga (ADR-0023, item 6) — e é a mesma pergunta que
        `delivered_partially` faz.
        """
        if turn.audio_chunks or final:
            await self._marcar_falha(turn, str(exc))
            return
        logger.warning(
            "turn %s falhou antes do primeiro trecho (%s); devolvendo à fila",
            turn.id,
            exc,
        )
        raise exc

    async def _marcar_falha(self, turn: Turn, motivo: str) -> None:
        turn.fail(motivo, self._clock())
        await self._gravar(turn)
        await self._publicar(
            turn.id,
            Failed(reason=motivo, delivered_partially=turn.delivered_partially),
        )

    # -- persistência e publicação ------------------------------------------

    async def _gravar(self, turn: Turn) -> None:
        """Marco confirmado. Sem change tracking, gravar é sempre explícito."""
        await self._turns.update(turn)
        await self._uow.commit()

    async def _publicar(self, turn_id: UUID, event: TurnEvent) -> None:
        """Publica, e **engole a falha de propósito**.

        É a única exceção capturada e descartada em todo o pipeline, e ela tem
        justificativa: o canal é o caminho rápido, não a verdade (o banco é). Um
        Redis fora do ar atrasa o aluno em alguns segundos, até o cliente cair
        no polling do ADR-0026 item 4; abortar o turn por isso jogaria fora
        áudio já sintetizado e tokens já pagos.
        """
        try:
            await self._events.publish(turn_id, event)
        except TurnEventsError as exc:
            logger.warning("turn %s: evento não publicado (%s)", turn_id, exc)


def _primeira_falha(grupo: BaseExceptionGroup[BaseException]) -> BaseException:
    """Desempacota o ``ExceptionGroup`` do ``TaskGroup`` na primeira exceção real.

    O ``TaskGroup`` sempre agrupa, mesmo quando só uma corrotina falhou, e
    grupos podem aninhar. Quem chama o caso de uso espera `TtsError`, não
    `ExceptionGroup[TtsError]` — deixar o grupo subir obrigaria todo chamador
    (e todo teste) a saber que existe concorrência aqui dentro, que é
    exatamente o detalhe que este módulo encapsula.
    """
    primeira = grupo.exceptions[0]
    if isinstance(primeira, BaseExceptionGroup):
        return _primeira_falha(primeira)
    return primeira
