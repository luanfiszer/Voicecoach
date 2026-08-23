"""O pipeline em cascata, com fakes de todas as portas (CARD-009).

Nenhum teste aqui toca Redis, Postgres, MinIO ou modelo de IA. A suíte inteira
deste arquivo roda em milissegundos, e é esse o critério de aceite: o caso de uso
é a peça arquitetural do card, e ela tem de ser exercitável sem infraestrutura.

O que cada bloco prova:

1. **a cascata existe** — o primeiro trecho é gravado antes de `replied_at`;
2. **a ordem é por construção** — a 2ª sentença terminando antes da 1ª não
   embaralha nada;
3. **o caminho triste preserva o que o aluno ouviu** — TTS falhando na 3ª
   sentença deixa 2 trechos vivos, `delivered_partially` verdadeiro e nenhum
   retry;
4. **o retry só existe antes do primeiro trecho**;
5. **o histórico da sessão chega ao professor**.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from fakes_pipeline import (
    FakeEncoder,
    FakeMediaStorage,
    FakeSessionRepository,
    FakeStt,
    FakeTeacher,
    FakeTts,
    FakeTurnEvents,
    FakeTurnRepository,
    FakeUnitOfWork,
    RelogioFalso,
)
from voicecoach.application.ports.audio_encoder import AudioEncoder
from voicecoach.application.ports.media_storage import MediaStorage, MediaStorageError
from voicecoach.application.ports.repositories import (
    SessionRepository,
    TurnRepository,
    UnitOfWork,
)
from voicecoach.application.ports.speech_to_text import SpeechToText, SttError
from voicecoach.application.ports.teacher_llm import (
    FeedbackReady,
    LlmError,
    Speaker,
    SpokenSentence,
    TeacherFeedback,
    TeacherLlm,
    TokenUsage,
)
from voicecoach.application.ports.text_to_speech import TextToSpeech, TtsError
from voicecoach.application.ports.turn_events import (
    ChunkReady,
    Completed,
    Failed,
    FeedbackAvailable,
    Transcribed,
    TurnEvents,
    TurnEventsError,
)
from voicecoach.application.use_cases.process_turn import (
    REPROCESSAMENTO_APOS_ENTREGA,
    ProcessTurn,
    ProcessTurnHandler,
    TurnNotFoundError,
    _primeira_falha,
)
from voicecoach.domain.session import Session
from voicecoach.domain.turn import Turn, TurnStatus

STUDENT_ID = uuid4()
SESSION_ID = uuid4()
INPUT_KEY = f"{STUDENT_ID}/{SESSION_ID}/input.aac"

FEEDBACK = TeacherFeedback(
    spoken_reply="That sounds stressful. Have you talked to your manager? It helps.",
    has_mistakes=True,
    original="I think my job is very stressful",
    corrected="I think my job is quite stressful",
    tip="'quite' soa mais natural aqui.",
    translation_pt="Isso parece estressante.",
)
USAGE = TokenUsage(
    input_tokens=1084,
    cache_creation_input_tokens=0,
    cache_read_input_tokens=0,
    output_tokens=180,
)


def tres_sentencas() -> list[SpokenSentence | FeedbackReady]:
    return [
        SpokenSentence("That sounds stressful."),
        SpokenSentence("Have you talked to your manager?"),
        SpokenSentence("It helps."),
        FeedbackReady(feedback=FEEDBACK, usage=USAGE),
    ]


def novo_turn(turn_id: object = None) -> Turn:
    return Turn(
        id=turn_id or uuid4(),  # type: ignore[arg-type]
        session_id=SESSION_ID,
        input_audio_ref=INPUT_KEY,
        audio_duration=timedelta(seconds=4),
        created_at=datetime(2026, 8, 23, 11, 59, tzinfo=UTC),
    )


class Montagem:
    """Tudo montado, com acesso a cada dublê para as asserções."""

    def __init__(
        self,
        turn: Turn,
        *,
        storage: FakeMediaStorage | None = None,
        stt: FakeStt | None = None,
        teacher: FakeTeacher | None = None,
        tts: FakeTts | None = None,
        encoder: FakeEncoder | None = None,
        events: FakeTurnEvents | None = None,
    ) -> None:
        self.turn = turn
        self.turns = FakeTurnRepository(turn)
        self.sessions = FakeSessionRepository(
            Session(
                id=SESSION_ID,
                student_id=STUDENT_ID,
                started_at=datetime(2026, 8, 23, 11, 0, tzinfo=UTC),
            )
        )
        self.uow = FakeUnitOfWork()
        self.uow.observar(turn)
        self.storage = storage or FakeMediaStorage()
        self.storage.objetos[INPUT_KEY] = (b"audio-do-aluno", "audio/aac")
        self.stt = stt or FakeStt()
        self.teacher = teacher or FakeTeacher(tres_sentencas())
        self.tts = tts or FakeTts()
        self.encoder = encoder or FakeEncoder()
        self.events = events or FakeTurnEvents()
        self.clock = RelogioFalso()
        self.handler = ProcessTurnHandler(
            turns=self.turns,
            sessions=self.sessions,
            unit_of_work=self.uow,
            storage=self.storage,
            speech_to_text=self.stt,
            teacher=self.teacher,
            text_to_speech=self.tts,
            encoder=self.encoder,
            events=self.events,
            clock=self.clock,
            history_turns=6,
        )

    async def processar(self, *, final: bool = True) -> None:
        await self.handler.handle(ProcessTurn(self.turn.id, final_attempt=final))


def test_os_fakes_satisfazem_todas_as_portas() -> None:
    """As anotações são as asserções — quem as verifica é o `mypy`, não o pytest.

    Sete linhas, sete portas. Se qualquer fake sair de sincronia com a porta que
    dubla — parâmetro renomeado, tipo de retorno diferente, um método novo na
    porta —, este arquivo reprova no gate de tipos com o `pytest` ainda verde.
    Foi exatamente o que aconteceu nesta sessão quando `MediaStorage` ganhou
    `get`: o `pytest` não tinha o que dizer, o `mypy` apontou os dois fakes.
    """
    turns: TurnRepository = FakeTurnRepository()
    sessions: SessionRepository = FakeSessionRepository()
    uow: UnitOfWork = FakeUnitOfWork()
    storage: MediaStorage = FakeMediaStorage()
    stt: SpeechToText = FakeStt()
    teacher: TeacherLlm = FakeTeacher([])
    tts: TextToSpeech = FakeTts()
    encoder: AudioEncoder = FakeEncoder()
    events: TurnEvents = FakeTurnEvents()

    assert all(
        p is not None
        for p in (turns, sessions, uow, storage, stt, teacher, tts, encoder, events)
    )


# -- 1. a cascata existe ----------------------------------------------------


async def test_o_primeiro_trecho_e_gravado_antes_de_replied_at() -> None:
    """O critério que separa cascata de cadeia sequencial.

    Numa cadeia, `replied_at` (o fim da geração) vem antes de qualquer áudio.
    Aqui é o contrário: o aluno já ouviu a primeira frase quando o professor
    ainda estava escrevendo a última.
    """
    m = Montagem(novo_turn())

    await m.processar()

    assert m.turn.status is TurnStatus.COMPLETED
    assert m.turn.replied_at is not None
    assert m.turn.audio_chunks[0].created_at < m.turn.replied_at


async def test_a_cascata_grava_tres_trechos_e_o_audio_inteiro() -> None:
    m = Montagem(novo_turn())

    await m.processar()

    assert [c.index for c in m.turn.audio_chunks] == [0, 1, 2]
    assert [c.text for c in m.turn.audio_chunks] == [
        "That sounds stressful.",
        "Have you talked to your manager?",
        "It helps.",
    ]
    prefixo = f"{STUDENT_ID}/{SESSION_ID}/{m.turn.id}/reply"
    assert [c.storage_key for c in m.turn.audio_chunks] == [
        f"{prefixo}/000.aac",
        f"{prefixo}/001.aac",
        f"{prefixo}/002.aac",
    ]
    assert m.turn.reply_audio_ref == f"{prefixo}/full.aac"


async def test_os_eventos_publicados_sao_exatamente_estes() -> None:
    """A lista inteira comparada com um `==` só.

    Isso só funciona porque todo evento é `@dataclass(frozen=True)`: o decorador
    gera `__eq__` por **valor**, campo a campo, em vez da identidade que um
    objeto Python tem por default. Um campo diferente e a igualdade falha —
    é o que torna a asserção uma asserção de verdade, e não um `len() == 5`.
    """
    m = Montagem(novo_turn())

    await m.processar()

    prefixo = f"{STUDENT_ID}/{SESSION_ID}/{m.turn.id}/reply"
    assert m.events.eventos == [
        Transcribed(transcript="I think my job is stressful"),
        ChunkReady(
            index=0,
            storage_key=f"{prefixo}/000.aac",
            duration_seconds=m.turn.audio_chunks[0].duration_seconds,
            text="That sounds stressful.",
        ),
        ChunkReady(
            index=1,
            storage_key=f"{prefixo}/001.aac",
            duration_seconds=m.turn.audio_chunks[1].duration_seconds,
            text="Have you talked to your manager?",
        ),
        ChunkReady(
            index=2,
            storage_key=f"{prefixo}/002.aac",
            duration_seconds=m.turn.audio_chunks[2].duration_seconds,
            text="It helps.",
        ),
        FeedbackAvailable(
            has_mistakes=True,
            original="I think my job is very stressful",
            corrected="I think my job is quite stressful",
            tip="'quite' soa mais natural aqui.",
        ),
        Completed(reply_audio_key=f"{prefixo}/full.aac"),
    ]


async def test_cada_trecho_e_confirmado_no_banco_antes_do_proximo() -> None:
    """A retomada do ADR-0026 lê os trechos persistidos — logo eles têm de estar lá.

    Um commit só no fim do turn passaria em todo teste de resultado final e
    deixaria a retomada sem nada para ler durante os ~2 s em que o aluno pode
    reconectar. A cadência é o contrato.
    """
    m = Montagem(novo_turn())

    await m.processar()

    # start_processing, transcrição, 3 trechos, attach_reply, complete
    assert m.uow.trechos_por_commit == [0, 0, 1, 2, 3, 3, 3]


# -- 2. a ordem é por construção --------------------------------------------


async def test_a_segunda_sentenca_terminando_antes_da_primeira_nao_embaralha() -> None:
    """O teste que uma implementação com `create_task` solto NÃO passa.

    Os atrasos são invertidos de propósito: a 1ª sentença demora 30 ms e a 2ª,
    1 ms. Com uma task por sentença, a 2ª chegaria primeiro ao
    `append_audio_chunk` e pediria o índice 0; a 1ª chegaria depois e pediria 0
    de novo — `OutOfOrderAudioChunkError`, de forma intermitente e dependente do
    tamanho do texto.

    Com a fila interna e um consumidor só, a ordem é preservada por construção:
    o `synthesize` da 2ª nem começa antes de o da 1ª terminar, e o consumidor lê
    FIFO.
    """
    tts = FakeTts(atrasos=[0.03, 0.001, 0.001])
    m = Montagem(novo_turn(), tts=tts)

    await m.processar()

    assert [c.index for c in m.turn.audio_chunks] == [0, 1, 2]
    assert [c.text for c in m.turn.audio_chunks] == [
        "That sounds stressful.",
        "Have you talked to your manager?",
        "It helps.",
    ]
    # E a chave gravada no storage segue a mesma ordem: é ela que o bucket
    # ordena lexicograficamente para o playback (ADR-0024).
    assert m.storage.ordem_de_escrita[:3] == [
        f"{STUDENT_ID}/{SESSION_ID}/{m.turn.id}/reply/00{i}.aac" for i in (0, 1, 2)
    ]


# -- 3. o caminho triste ----------------------------------------------------


async def test_tts_falhando_na_terceira_preserva_os_dois_trechos_anteriores() -> None:
    """O critério mais importante do card, e o mais fácil de quebrar em silêncio.

    O aluno já ouviu duas frases. O registro tem de continuar dizendo que ele
    ouviu — `fail()` não apaga trecho (ADR-0023, item 6) —, os dois objetos
    seguem no storage, e **nenhum retry acontece**: reprocessar faria o professor
    recomeçar a falar do zero.
    """
    tts = FakeTts(erro=TtsError("motor de voz caiu"), erro_na_sentenca=2)
    m = Montagem(novo_turn(), tts=tts)

    await m.processar(final=False)

    assert m.turn.status is TurnStatus.FAILED
    assert m.turn.failure_reason == "motor de voz caiu"
    assert len(m.turn.audio_chunks) == 2
    assert m.turn.delivered_partially is True
    prefixo = f"{STUDENT_ID}/{SESSION_ID}/{m.turn.id}/reply"
    assert f"{prefixo}/000.aac" in m.storage.objetos
    assert f"{prefixo}/001.aac" in m.storage.objetos
    assert m.events.eventos[-1] == Failed(
        reason="motor de voz caiu", delivered_partially=True
    )


async def test_falha_depois_do_primeiro_trecho_nao_levanta_para_a_fila() -> None:
    """`final_attempt=False` e mesmo assim nada sobe: é a guarda de retry.

    O `arq` só tenta de novo se a função levantar. Não levantar é como o caso de
    uso diz "não tente" — e ele diz isso olhando a coleção de trechos, não o tipo
    do erro.
    """
    tts = FakeTts(erro=TtsError("caiu"), erro_na_sentenca=1)
    m = Montagem(novo_turn(), tts=tts)

    await m.processar(final=False)  # não levanta

    assert m.turn.status is TurnStatus.FAILED
    assert m.turn.delivered_partially is True


async def test_abandonar_a_cascata_fecha_o_gerador_do_professor() -> None:
    """Parar de consumir o `async for` é o que cancela a geração (ADR-0031, item 6).

    Sem isso, o produto continuaria pagando tokens de uma resposta que ninguém
    vai ouvir. O `finally` do gerador do fake registra que o `GeneratorExit`
    chegou — é a prova de que o cancelamento atravessou a fronteira.
    """
    storage = FakeMediaStorage(falhar_em=MediaStorageError("bucket fora do ar"))
    m = Montagem(novo_turn(), storage=storage)

    await m.processar()

    assert m.teacher.fechado is True
    assert m.turn.status is TurnStatus.FAILED


# -- 4. retry só antes do primeiro trecho -----------------------------------


async def test_stt_falhando_devolve_o_job_a_fila_enquanto_houver_tentativa() -> None:
    """Nenhum trecho entregue ⇒ pode tentar de novo. O caso de uso **levanta**."""
    m = Montagem(novo_turn(), stt=FakeStt(erro=SttError("whisper caiu")))

    with pytest.raises(SttError, match="whisper caiu"):
        await m.processar(final=False)

    assert m.turn.status is TurnStatus.PROCESSING  # segue vivo para a próxima


async def test_stt_falhando_na_ultima_tentativa_marca_o_turn_como_falho() -> None:
    m = Montagem(novo_turn(), stt=FakeStt(erro=SttError("whisper caiu")))

    await m.processar(final=True)

    assert m.turn.status is TurnStatus.FAILED
    assert m.turn.failure_reason == "whisper caiu"
    assert m.turn.delivered_partially is False
    assert m.events.eventos == [
        Failed(reason="whisper caiu", delivered_partially=False)
    ]


async def test_turn_ja_concluido_reenfileirado_e_no_op() -> None:
    """Entrega ao menos uma vez é o normal de uma fila, não um incidente."""
    m = Montagem(novo_turn())
    await m.processar()
    commits_antes = m.uow.commits

    await m.processar()

    assert m.uow.commits == commits_antes
    assert m.turn.status is TurnStatus.COMPLETED


async def test_reprocessar_turn_que_ja_entregou_audio_e_recusado() -> None:
    """Um `processing` com trecho é uma tentativa anterior que morreu no meio.

    Recomeçar faria o professor falar de novo desde o início, por cima do que o
    aluno já ouviu. A guarda é do caso de uso porque o `arq` não tem como saber.
    """
    turn = novo_turn()
    turn.start_processing(datetime(2026, 8, 23, 11, 59, 30, tzinfo=UTC))
    turn.attach_transcript(
        "já transcrito", datetime(2026, 8, 23, 11, 59, 40, tzinfo=UTC)
    )
    turn.append_audio_chunk(
        index=0,
        storage_key="k",
        duration_seconds=1.0,
        text="ja ouvido",
        now=datetime(2026, 8, 23, 11, 59, 50, tzinfo=UTC),
    )
    m = Montagem(turn)

    await m.processar(final=False)

    assert m.turn.status is TurnStatus.FAILED
    assert m.turn.failure_reason == REPROCESSAMENTO_APOS_ENTREGA
    assert len(m.turn.audio_chunks) == 1
    assert m.tts.chamadas == []


async def test_turn_inexistente_levanta() -> None:
    handler = Montagem(novo_turn()).handler

    with pytest.raises(TurnNotFoundError):
        await handler.handle(ProcessTurn(uuid4(), final_attempt=True))


# -- 5. o histórico da sessão -----------------------------------------------


async def test_o_historico_da_sessao_chega_ao_professor() -> None:
    """Sem isto o professor responde como se cada turno fosse o primeiro."""
    anterior = novo_turn()
    anterior.status = TurnStatus.COMPLETED
    anterior.transcript = "Hi, I am Luan."
    anterior.reply_text = "Nice to meet you, Luan!"

    m = Montagem(novo_turn())
    m.turns.turns[anterior.id] = anterior

    await m.processar()

    historico = m.teacher.historicos[0]
    assert [(u.speaker, u.text) for u in historico] == [
        (Speaker.STUDENT, "Hi, I am Luan."),
        (Speaker.TEACHER, "Nice to meet you, Luan!"),
        (Speaker.STUDENT, "I think my job is stressful"),
    ]


# -- o canal é o caminho rápido, não a verdade ------------------------------


async def test_redis_fora_do_ar_nao_derruba_o_turn() -> None:
    """Perder publicação custa latência, nunca dado — o banco é a fonte.

    É a única exceção capturada e descartada no pipeline, e é deliberada:
    abortar aqui jogaria fora áudio já sintetizado e tokens já pagos.
    """
    eventos = FakeTurnEvents(erro=TurnEventsError("redis fora do ar"))
    m = Montagem(novo_turn(), events=eventos)

    await m.processar()

    assert m.turn.status is TurnStatus.COMPLETED
    assert eventos.publicados == []


async def test_professor_sem_sentenca_falavel_e_falha_de_llm() -> None:
    """Feedback sem nenhuma `SpokenSentence` não dá áudio nenhum ao aluno."""
    teacher = FakeTeacher([FeedbackReady(feedback=FEEDBACK, usage=USAGE)])
    m = Montagem(novo_turn(), teacher=teacher)

    await m.processar(final=True)

    assert m.turn.status is TurnStatus.FAILED
    assert "nenhuma sentença falável" in (m.turn.failure_reason or "")


async def test_professor_que_nao_entrega_feedback_e_falha_de_llm() -> None:
    teacher = FakeTeacher([SpokenSentence("Hello.")])
    m = Montagem(novo_turn(), teacher=teacher)

    await m.processar(final=True)

    assert m.turn.status is TurnStatus.FAILED
    assert "sem entregar o feedback" in (m.turn.failure_reason or "")


async def test_erro_do_professor_no_meio_do_fluxo_vira_falha_do_turn() -> None:
    teacher = FakeTeacher(tres_sentencas(), erro=LlmError("provedor caiu"), erro_apos=2)
    m = Montagem(novo_turn(), teacher=teacher)

    await m.processar(final=False)

    assert m.turn.status is TurnStatus.FAILED
    assert m.turn.failure_reason == "provedor caiu"
    assert m.turn.delivered_partially is True


async def test_turn_orfao_de_sessao_levanta_em_vez_de_falhar_calado() -> None:
    """Turn sem Session é divergência de banco, não falha de infraestrutura.

    Marcá-lo como `failed` esconderia um dado corrompido atrás de uma mensagem
    de erro para o aluno; levantar faz o job falhar ruidosamente.
    """
    m = Montagem(novo_turn())
    m.sessions.sessions.clear()

    with pytest.raises(TurnNotFoundError, match="Session"):
        await m.processar()


def test_a_primeira_falha_e_extraida_de_grupos_aninhados() -> None:
    """O `TaskGroup` sempre agrupa, e grupos podem aninhar.

    Quem chama o caso de uso espera `TtsError`, não
    `ExceptionGroup[ExceptionGroup[TtsError]]` — deixar o grupo subir obrigaria
    todo chamador a saber que existe concorrência aqui dentro.
    """
    dentro = TtsError("motor caiu")
    aninhado = BaseExceptionGroup("fora", [BaseExceptionGroup("dentro", [dentro])])

    assert _primeira_falha(aninhado) is dentro
