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
    TeacherUnavailableError,
    TokenUsage,
    Utterance,
)
from voicecoach.application.ports.text_to_speech import TtsError, concat
from voicecoach.application.ports.turn_events import (
    ChunkReady,
    Completed,
    FeedbackAvailable,
    Transcribed,
)
from voicecoach.application.use_cases.fail_turn import FailTurn, publicar_tolerante
from voicecoach.domain.media_keys import reply_chunk_key, reply_full_key
from voicecoach.domain.turn import TurnStatus
from voicecoach.domain.usage import UsageEvent, estimate_llm_cost

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
        UsageEventRepository,
    )
    from voicecoach.application.ports.speech_to_text import SpeechToText
    from voicecoach.application.ports.teacher_llm import TeacherLlm
    from voicecoach.application.ports.text_to_speech import (
        SynthesizedAudio,
        TextToSpeech,
    )
    from voicecoach.application.ports.turn_events import TurnEvent, TurnEvents
    from voicecoach.domain.turn import Turn
    from voicecoach.domain.usage import LlmPrice

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

# **Motivo estável, e "estável" é o ponto** (CARD-026, D4; ADR-0053 decisão 6).
# Todo outro motivo gravado num turn é `str(exc)` — texto que descreve a falha
# para quem lê um log. Este é diferente: ele é a **única** informação com que o
# app distingue "a dependência caiu" de "não deu para entender sua fala", e as
# duas telas são outras. O CARD-027 desenha em cima dele e o CARD-033 precisa
# que ele seja distinguível de "o produto pausou por orçamento".
#
# Constante e não interpolação da exceção porque um motivo que carrega o
# `type(exc).__name__` muda quando alguém renomeia uma classe — e a tela do
# aluno deixaria de casar sem que teste nenhum reclamasse.
#
# **Dívida declarada:** isto é um contrato por string, e string é o tipo mais
# fraco que serve. O lugar certo é um campo estruturado no `Failed` e no `GET`,
# com o `assert_never` do ADR-0039 cobrando exaustividade — o que muda a rota, o
# schema e o client TypeScript. Fica para o CARD-027, que é quem tem a tela e
# portanto quem sabe de quantos casos ela precisa. Gatilho: o segundo motivo que
# o app precisar distinguir.
PROVEDOR_INDISPONIVEL = "provedor indisponível: o professor não atendeu"


class RetryableTurnFailureError(RuntimeError):
    """O turn falhou **antes** do primeiro trecho: vale tentar de novo.

    Existe porque "levantar" e "pedir retentativa" deixaram de ser a mesma coisa
    quando o CARD-025 mediu o `arq`: exceção comum **não** volta para a fila, e o
    comentário que dizia o contrário manteve o produto com um caminho de falha
    sem dono. Um tipo próprio deixa a intenção legível para quem traduz.

    **Quem traduz é o worker**, não este módulo: `application` não pode importar
    `arq` (ADR-0012), então o `arq.Retry` é montado na composition root. Herda de
    `RuntimeError` e não de `DomainError` porque nenhuma invariante foi violada
    (ADR-0017) — é infraestrutura que não colaborou.

    A causa original viaja em `__cause__` (o `raise ... from exc`): quem loga vê
    o `SttError` ou o `LlmError` de verdade, não só "deu retry".
    """


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


@dataclass(frozen=True, slots=True)
class _Cascata:
    """O que a cascata acumulou: áudio, feedback e o volume que o TTS falou.

    Um objeto em vez de uma tupla de três porque o terceiro campo é a armadilha
    do CARD-014: ``tts_chars`` só está **completo** quando as duas corrotinas do
    ``TaskGroup`` terminaram. Numa tupla, um dia alguém lê o terceiro elemento no
    meio do laço e subconta em silêncio; num objeto construído depois do ``async
    with``, o valor incompleto nem existe.
    """

    audios: list[SynthesizedAudio]
    feedback: FeedbackReady | None
    tts_chars: int


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
        usage_events: UsageEventRepository,
        unit_of_work: UnitOfWork,
        storage: MediaStorage,
        speech_to_text: SpeechToText,
        teacher: TeacherLlm,
        text_to_speech: TextToSpeech,
        encoder: AudioEncoder,
        events: TurnEvents,
        clock: Callable[[], datetime],
        history_turns: int,
        llm_price: Callable[[str], LlmPrice | None],
        stt_provider: str,
        tts_provider: str,
    ) -> None:
        self._turns = turns
        self._sessions = sessions
        self._usage = usage_events
        self._uow = unit_of_work
        self._storage = storage
        self._stt = speech_to_text
        self._teacher = teacher
        self._tts = text_to_speech
        self._encoder = encoder
        self._events = events
        self._clock = clock
        # Construído aqui e não recebido por parâmetro: é um colaborador feito
        # das MESMAS portas que este handler já tem, não uma capacidade nova.
        # Pedi-lo à composition root obrigaria o worker a montar duas vezes o
        # mesmo grafo, e a segunda montagem é a que um dia diverge.
        self._falhar = FailTurn(
            turns=turns, unit_of_work=unit_of_work, events=events, clock=clock
        )
        self._history_turns = history_turns
        # Uma função, e não a tabela de preços inteira: a tabela mora em
        # `config.py`, que `application` NÃO pode importar (ADR-0013). O que
        # atravessa é a capacidade "diga o preço deste modelo", e quem a resolve
        # é a composition root. Passar o dicionário obrigaria o caso de uso a
        # conhecer a forma da configuração; passar a função obriga-o a conhecer
        # só a pergunta.
        self._llm_price = llm_price
        # Rótulos, não capacidades — por isso são `str` e não algo lido da porta.
        # O que a linha de custo precisa registrar é **qual motor rodou**, e no
        # STT isso não é o que a config diz: `STT_PROVIDER=auto` resolve para
        # `mlx` ou `faster_whisper` no boot (ADR-0027). Quem sabe o resultado
        # dessa resolução é a composition root, e é ela que passa o nome já
        # resolvido. Ler `settings.stt_provider` daqui gravaria "auto", que não
        # é o nome de motor nenhum.
        self._stt_provider = stt_provider
        self._tts_provider = tts_provider

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

        cascata = await self._cascata(turn, student_id, history)
        feedback = cascata.feedback
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
        # O custo entra no MESMO commit (ADR-0051, decisão 1), e a pergunta que
        # essa escolha responde não é a do CARD-013 ("não apagar o que é do
        # aluno") — é **"não perder o que já foi pago"**. Um turn que falhe
        # depois disto, no `_fechar`, deixa registrado o custo de uma resposta
        # que o aluno viu falhar: está correto, os tokens saíram da conta. A
        # alternativa (gravar no fechamento) perderia exatamente o custo dos
        # turns que falham depois do LLM — que é o custo mais fácil de perder de
        # vista e o mais caro de não enxergar.
        await self._registrar_uso(turn, student_id, feedback.usage, cascata.tts_chars)
        await self._gravar(turn)
        await self._publicar(
            turn.id,
            FeedbackAvailable(corrections=feedback.feedback.corrections),
        )

        await self._fechar(turn, student_id, cascata.audios)

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
    ) -> _Cascata:
        """As duas corrotinas, e o desempacotamento do ``ExceptionGroup``.

        Tudo que a cascata acumula é **local a esta chamada** — nada em ``self``.
        Guardar o feedback num atributo de instância seria a corrida clássica de
        um handler reusado por dois jobs, e o worker reusa: o ``ctx`` do arq vive
        o processo inteiro (ADR-0025).
        """
        fila: asyncio.Queue[_Sintetizado | None] = asyncio.Queue()
        sintetizados: list[SynthesizedAudio] = []
        feedback: FeedbackReady | None = None
        # O volume que o TTS falou, somado onde as sentenças passam — não existe
        # contador de caracteres em lugar nenhum do pipeline, e a porta de TTS
        # recebe texto por sentença (ADR-0033). Hoje isto custa US$ 0: o Piper é
        # local (ADR-0032). Existe para que a série histórica já exista no dia em
        # que o TTS virar API paga.
        tts_chars = 0

        async def sintetizar() -> None:
            # `nonlocal` diz que a atribuição abaixo mexe na variável da função
            # de fora, e não cria uma nova local. É o idioma Python para o que em
            # C# uma lambda faz de graça ao capturar a variável do escopo.
            nonlocal feedback, tts_chars
            try:
                async for evento in self._teacher.respond_streaming(history):
                    match evento:
                        case SpokenSentence(text=texto):
                            tts_chars += len(texto)
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

        return _Cascata(audios=sintetizados, feedback=feedback, tts_chars=tts_chars)

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

    async def _registrar_uso(
        self,
        turn: Turn,
        student_id: UUID,
        usage: TokenUsage,
        tts_chars: int,
    ) -> None:
        """Monta a linha de custo e a registra na unidade de trabalho.

        **Não comita**: quem comita é o `_gravar` logo em seguida, e é isso que
        põe o `UsageEvent` no mesmo commit do `attach_reply`/`attach_corrections`
        (ADR-0051, decisão 1).

        O custo é **congelado aqui** (decisão 3): a tabela de preços responde
        "quanto custa hoje", e a linha gravada responde "quanto custou naquele
        dia". Recalcular na leitura faria "quanto gastei em julho" mudar de
        resposta a cada reajuste do provedor.

        **Modelo sem preço não vira zero.** Zero é o custo verdadeiro do STT e do
        TTS locais; `None` é "não sabemos precificar". Gravar zero faria a cota
        do CARD-015 ler como grátis um turn que ninguém sabe quanto custou — e
        levantar aqui derrubaria um turn cujo áudio o aluno **já ouviu**, por um
        problema que não é dele. O ERROR no log é o que torna a lacuna visível.
        """
        preco = self._llm_price(usage.model)
        if preco is None:
            logger.error(
                "turn %s: modelo %r fora da tabela de preços; "
                "custo gravado como desconhecido",
                turn.id,
                usage.model,
            )
        custo = (
            None
            if preco is None
            else estimate_llm_cost(
                input_tokens=usage.input_tokens,
                cache_creation_tokens=usage.cache_creation_input_tokens,
                cache_read_tokens=usage.cache_read_input_tokens,
                output_tokens=usage.output_tokens,
                price=preco,
            )
        )
        await self._usage.add(
            UsageEvent(
                turn_id=turn.id,
                student_id=student_id,
                occurred_at=self._clock(),
                llm_model=usage.model,
                llm_input_tokens=usage.input_tokens,
                llm_cache_creation_tokens=usage.cache_creation_input_tokens,
                llm_cache_read_tokens=usage.cache_read_input_tokens,
                llm_output_tokens=usage.output_tokens,
                # A duração do áudio do ALUNO, que já é insumo declarado da quota
                # e já está no `Turn`. Não é medida de novo aqui, e não vira um
                # `stt_seconds: float` ao lado de um `timedelta`: seria criar a
                # divergência de unidade que o CARD-015 teria de resolver.
                stt_audio_duration=turn.audio_duration,
                stt_provider=self._stt_provider,
                tts_chars=tts_chars,
                tts_provider=self._tts_provider,
                estimated_cost_usd=custo,
            )
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
        """Decide entre marcar o turn como falho e pedir outra tentativa.

        A pergunta que separa os dois casos não é "que erro foi?", é **"o aluno
        já ouviu alguma coisa?"**. Ela é respondida pela coleção de trechos, que
        `fail()` não apaga (ADR-0023, item 6) — e é a mesma pergunta que
        `delivered_partially` faz.

        **O pedido de nova tentativa é um TIPO, não a exceção original** — e essa
        distinção custou o CARD-025 a descobrir. Até aqui este método levantava
        `exc` cru, com um comentário dizendo "devolvendo à fila". Não devolvia:
        medido contra um `arq` 0.28 real, uma exceção comum **não** é retentada
        (só `Retry`, `CancelledError` e `RetryJob` caem no ramo de retry do
        `arq.worker.run_job`), e o turn ficava `processing` para sempre. Um tipo
        próprio torna a intenção explícita para quem traduz — e quem traduz é a
        composition root do worker, porque `application` não pode importar `arq`
        (ADR-0012).
        """
        if turn.audio_chunks or final:
            await self._marcar_falha(turn, _motivo(exc))
            return
        logger.warning(
            "turn %s falhou antes do primeiro trecho (%s); pedindo nova tentativa",
            turn.id,
            exc,
        )
        message = f"turn {turn.id} falhou antes do primeiro trecho: {exc}"
        raise RetryableTurnFailureError(message) from exc

    async def _marcar_falha(self, turn: Turn, motivo: str) -> None:
        """A receita mora em ``fail_turn.py``, compartilhada com a varredura.

        Ela era quatro linhas aqui dentro até o CARD-025. O `SweepStaleTurns`
        precisa exatamente delas sobre N turns, e duas cópias da marcação sairiam
        de sincronia na primeira mudança do evento.
        """
        await self._falhar(turn, motivo)

    # -- persistência e publicação ------------------------------------------

    async def _gravar(self, turn: Turn) -> None:
        """Marco confirmado. Sem change tracking, gravar é sempre explícito."""
        await self._turns.update(turn)
        await self._uow.commit()

    async def _publicar(self, turn_id: UUID, event: TurnEvent) -> None:
        """Publica, e **engole a falha de propósito** (ADR-0035).

        A política mora em ``fail_turn.publicar_tolerante`` desde o CARD-025, e
        não aqui: ela vale igualmente para a varredura de turns travados, e dois
        lugares engolindo por conta própria seriam dois lugares onde alguém pode
        decidir o contrário sem perceber.
        """
        await publicar_tolerante(self._events, turn_id, event)


def _motivo(exc: Exception) -> str:
    """O que fica gravado no turn — e é o que o aluno acaba lendo.

    Duas categorias, e a diferença é de quem é o problema:

    - **o provedor não atendeu** (`TeacherUnavailableError`): estado transitório
      e conhecido. Motivo constante, porque o app decide a tela por ele;
    - **qualquer outra falha**: a mensagem da exceção, como sempre foi.

    O `isinstance` é sobre o tipo da PORTA, não sobre o do SDK: `application` não
    conhece `anthropic` (ADR-0012), e quem classificou "isto é indisponibilidade"
    foi o adapter, que é quem tinha a informação para isso.
    """
    if isinstance(exc, TeacherUnavailableError):
        return PROVEDOR_INDISPONIVEL
    return str(exc)


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
