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
from decimal import Decimal
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
    FakeUsageEventRepository,
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
    TeacherUnavailableError,
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
    PROVEDOR_INDISPONIVEL,
    REPROCESSAMENTO_APOS_ENTREGA,
    ProcessTurn,
    ProcessTurnHandler,
    RetryableTurnFailureError,
    TurnNotFoundError,
    _primeira_falha,
)

# A tabela de preços REAL, não um dublê: o critério de aceite é "o custo bate
# com a tabela de preços", e um preço inventado no teste provaria só que a
# multiplicação funciona.
from voicecoach.config import preco_do_modelo
from voicecoach.domain.correction import Correction, CorrectionType, Severity
from voicecoach.domain.session import Session
from voicecoach.domain.turn import Turn, TurnStatus

STUDENT_ID = uuid4()
SESSION_ID = uuid4()
INPUT_KEY = f"{STUDENT_ID}/{SESSION_ID}/input.aac"

CORRECAO = Correction(
    index=0,
    type=CorrectionType.VOCABULARY,
    original_excerpt="very stressful",
    corrected_form="quite stressful",
    explanation="'quite' soa mais natural aqui.",
    severity=Severity.MINOR,
)
FEEDBACK = TeacherFeedback(
    spoken_reply="That sounds stressful. Have you talked to your manager? It helps.",
    translation_pt="Isso parece estressante.",
    corrections=(CORRECAO,),
)
# Os tokens do fake, e eles são o insumo do teste de custo exato: 1084 de
# entrada a US$ 1/MTok e 180 de saída a US$ 5/MTok dão US$ 0,001984 — uma conta
# que se confere à mão contra a tabela de preços, sem tolerância nenhuma.
#
# O `model` é o id DATADO, como a API o devolve. A tabela guarda a família
# (`claude-haiku-4-5`), e é por isso que `preco_do_modelo` casa por prefixo.
USAGE = TokenUsage(
    model="claude-haiku-4-5-20251001",
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
        self.usage_events = FakeUsageEventRepository()
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
            usage_events=self.usage_events,
            unit_of_work=self.uow,
            storage=self.storage,
            speech_to_text=self.stt,
            teacher=self.teacher,
            text_to_speech=self.tts,
            encoder=self.encoder,
            events=self.events,
            clock=self.clock,
            history_turns=6,
            llm_price=preco_do_modelo,
            stt_provider="faster_whisper",
            tts_provider="piper",
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
        FeedbackAvailable(corrections=(CORRECAO,)),
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


async def test_stt_falhando_pede_nova_tentativa_enquanto_houver_uma() -> None:
    """Nenhum trecho entregue ⇒ pode tentar de novo. O caso de uso **levanta**.

    **O tipo levantado mudou no CARD-025, e o nome deste teste também** — ele
    dizia "devolve o job à fila", que era exatamente a crença falsa que o card
    desfez: uma exceção comum não volta para fila nenhuma (ADR-0052). O caso de
    uso agora levanta um `RetryableTurnFailureError`, e quem o traduz em
    `arq.Retry` é a composition root do worker.

    A causa original continua acessível em `__cause__` — o `raise ... from exc`
    preserva o `SttError`, e é isso que faz o log do worker dizer o que de fato
    quebrou em vez de só "pediu retry".
    """
    m = Montagem(novo_turn(), stt=FakeStt(erro=SttError("whisper caiu")))

    with pytest.raises(RetryableTurnFailureError) as capturado:
        await m.processar(final=False)

    assert isinstance(capturado.value.__cause__, SttError)
    assert "whisper caiu" in str(capturado.value.__cause__)
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


# --- CARD-014: o custo deixa de ser jogado no chão -------------------------


async def test_o_custo_do_turn_e_gravado_e_bate_exato_com_a_tabela_de_precos() -> None:
    """O `usage` atravessava a porta desde o CARD-007 e caía no chão. Não cai mais.

    O custo é conferível à mão contra `LLM_PRICES`: 1084 tokens de entrada a
    US$ 1/MTok e 180 de saída a US$ 5/MTok. Igualdade exata, sem `approx` — um
    número de dinheiro que só bate por aproximação está no tipo errado.
    """
    montagem = Montagem(novo_turn())

    await montagem.processar()

    evento = await montagem.usage_events.get(montagem.turn.id)
    assert evento is not None
    assert evento.estimated_cost_usd == Decimal("0.00198400")


async def test_as_tres_contagens_de_entrada_sao_gravadas_e_o_zero_e_um_valor() -> None:
    """`cache_read = 0` gravado é o instrumento do ADR-0021, não um campo vazio.

    O dia em que uma destas duas deixar de ser zero é o gatilho de reabrir o
    prompt caching — e sem a linha gravada não há como saber que esse dia
    chegou. Por isso o teste afirma o **valor** 0, e não a ausência.
    """
    montagem = Montagem(novo_turn())

    await montagem.processar()

    evento = await montagem.usage_events.get(montagem.turn.id)
    assert evento is not None
    assert evento.llm_input_tokens == 1084
    assert evento.llm_cache_creation_tokens == 0
    assert evento.llm_cache_read_tokens == 0
    assert evento.llm_output_tokens == 180


async def test_stt_e_tts_tem_volume_gravado_e_custo_zero() -> None:
    """Os dois rodam local (ADR-0032): custam US$ 0 e ainda assim são medidos.

    `stt_audio_duration` vem de `turn.audio_duration`, que já é insumo declarado
    da quota — não é medido de novo, e não vira um `stt_seconds: float` ao lado
    de um `timedelta`. `tts_chars` é a soma das sentenças que o professor falou,
    contada onde elas passam, porque não existe contador de caracteres em lugar
    nenhum do pipeline.
    """
    montagem = Montagem(novo_turn())

    await montagem.processar()

    evento = await montagem.usage_events.get(montagem.turn.id)
    assert evento is not None
    assert evento.stt_audio_duration == montagem.turn.audio_duration
    assert evento.stt_provider == "faster_whisper"
    assert evento.tts_provider == "piper"
    # As três sentenças de `tres_sentencas()`, somadas. O número é o volume
    # falado; o custo dele é zero e não aparece em `estimated_cost_usd`, que é
    # só do LLM.
    esperado = sum(
        len(evento_llm.text)
        for evento_llm in tres_sentencas()
        if isinstance(evento_llm, SpokenSentence)
    )
    assert evento.tts_chars == esperado


async def test_o_custo_e_gravado_no_mesmo_commit_das_correcoes() -> None:
    """ADR-0051, decisão 1: o custo entra com o feedback, não no fechamento.

    A pergunta que essa escolha responde não é a do CARD-013 ("não apagar o que é
    do aluno") — é **"não perder o que já foi pago"**. O teste prova a cadência:
    quando o `UsageEvent` existe, o turn já tem correções e ainda **não** está
    completo.
    """
    montagem = Montagem(novo_turn())
    estado_no_add: list[tuple[int, int, bool]] = []
    add_original = montagem.usage_events.add

    async def espiar(event: object) -> None:
        estado_no_add.append(
            (
                montagem.uow.commits,
                len(montagem.turn.corrections),
                montagem.turn.reply_audio_ref is not None,
            )
        )
        await add_original(event)  # type: ignore[arg-type]  # o dublê recebe o mesmo UsageEvent

    montagem.usage_events.add = espiar  # type: ignore[method-assign]  # espião de teste

    await montagem.processar()

    assert len(estado_no_add) == 1, "um turn, uma linha de custo"
    commits_no_add, correcoes_no_add, ja_fechou = estado_no_add[0]

    # As correções já estão na entidade: o custo entra no MESMO marco delas.
    assert correcoes_no_add == len(FEEDBACK.corrections)
    # E o `_fechar` ainda não rodou — se rodasse antes, um turn que falhasse no
    # `reply/full` perderia o custo dos tokens já pagos.
    assert not ja_fechou
    # Exatamente um commit acontece depois deste marco: o do fechamento. Prova
    # que o `add` não foi parar no commit final por acidente.
    assert montagem.uow.commits == commits_no_add + 2
    assert montagem.turn.status is TurnStatus.COMPLETED


async def test_turn_que_falha_depois_do_llm_mantem_o_custo_registrado() -> None:
    """O custo dos tokens já pagos não some porque o `reply/full` falhou.

    É a consequência que a decisão 1 do ADR-0051 comprou de propósito, e a
    alternativa (gravar no `_fechar`) perderia exatamente este caso — o custo mais
    fácil de perder de vista e o mais caro de não enxergar.
    """
    storage = FakeMediaStorage()
    montagem = Montagem(novo_turn(), storage=storage)
    # A última escrita do turn é o `reply/full`; falhar só nela deixa os trechos
    # entregues e o feedback gravado.
    chamadas = {"n": 0}
    put_original = storage.put

    async def put_que_falha_no_full(key: str, data: bytes, content_type: str) -> None:
        chamadas["n"] += 1
        if key.endswith("full.aac"):
            raise MediaStorageError(key)
        await put_original(key, data, content_type)

    storage.put = put_que_falha_no_full  # type: ignore[method-assign]  # injeção de falha de teste

    await montagem.processar()

    assert montagem.turn.status is TurnStatus.FAILED
    evento = await montagem.usage_events.get(montagem.turn.id)
    assert evento is not None
    assert evento.estimated_cost_usd == Decimal("0.00198400")


async def test_modelo_fora_da_tabela_grava_custo_desconhecido_sem_derrubar_o_turn() -> (
    None
):
    """Preço ausente vira `None`, nunca `0`, e nunca uma exceção.

    Levantar aqui derrubaria um turn cujo áudio o aluno **já ouviu**, por um
    problema que não é dele. Gravar `0` faria a cota do CARD-015 ler como grátis
    um turn que ninguém sabe quanto custou. Nulo é a única leitura honesta — e as
    contagens de token continuam gravadas, que é o que permite reprecificar a
    linha depois.
    """
    desconhecido = TokenUsage(
        model="modelo-que-nao-existe",
        input_tokens=1084,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
        output_tokens=180,
    )
    teacher = FakeTeacher(
        [
            SpokenSentence("That sounds stressful."),
            FeedbackReady(feedback=FEEDBACK, usage=desconhecido),
        ]
    )
    montagem = Montagem(novo_turn(), teacher=teacher)

    await montagem.processar()

    assert montagem.turn.status is TurnStatus.COMPLETED
    evento = await montagem.usage_events.get(montagem.turn.id)
    assert evento is not None
    assert evento.estimated_cost_usd is None
    assert evento.llm_input_tokens == 1084


async def test_turn_que_falha_antes_do_llm_nao_gera_linha_de_custo() -> None:
    """Nada foi pago, então não há o que registrar — nem uma linha com zeros.

    Uma linha de custo zero para um turn que nunca chamou o professor poluiria a
    contagem de turns da agregação, que é uma das duas unidades candidatas da
    cota (análise de custo §8).
    """
    montagem = Montagem(novo_turn(), stt=FakeStt(erro=SttError("motor caiu")))

    await montagem.processar()

    assert montagem.turn.status is TurnStatus.FAILED
    assert await montagem.usage_events.get(montagem.turn.id) is None


# --- CARD-026: "o provedor caiu" é um desfecho distinto de "deu erro" --------


async def test_provedor_indisponivel_grava_motivo_ESTAVEL_e_nao_a_mensagem(  # noqa: N802 — o nome É a asserção
) -> None:
    """Critério de aceite: o motivo distingue indisponibilidade de falha de conteúdo.

    O texto de uma exceção descreve a falha para quem lê log; ele carrega nome
    de classe do SDK, código HTTP e o que mais o provedor tenha mandado. Como
    **motivo** ele é péssimo: muda quando alguém renomeia uma classe, e a tela
    do aluno deixaria de casar sem que teste nenhum reclamasse.

    O CARD-027 desenha a tela em cima desta constante, e o CARD-033 precisa que
    ela seja distinguível de "o produto pausou por orçamento".
    """
    teacher = FakeTeacher(
        tres_sentencas(),
        erro=TeacherUnavailableError("APITimeoutError: ..."),
        erro_apos=0,
    )
    m = Montagem(novo_turn(), teacher=teacher)

    await m.processar(final=True)

    assert m.turn.status is TurnStatus.FAILED
    assert m.turn.failure_reason == PROVEDOR_INDISPONIVEL
    assert m.events.eventos[-1] == Failed(
        reason=PROVEDOR_INDISPONIVEL, delivered_partially=False
    )


async def test_falha_de_CONTEUDO_do_professor_continua_com_a_mensagem_crua() -> None:  # noqa: N802 — o nome É a asserção
    """O outro lado da mesma decisão: só a indisponibilidade ganha motivo fixo.

    Um `LlmError` comum é o provedor respondendo mal — bug de prompt, schema
    violado. A mensagem é o que ajuda a diagnosticar, e não há tela especial
    para ela.
    """
    teacher = FakeTeacher(
        tres_sentencas(), erro=LlmError("fora do schema"), erro_apos=0
    )
    m = Montagem(novo_turn(), teacher=teacher)

    await m.processar(final=True)

    assert m.turn.failure_reason == "fora do schema"


async def test_provedor_indisponivel_ANTES_do_primeiro_trecho_pede_retry() -> None:  # noqa: N802 — o nome É a asserção
    """A indisponibilidade não pula a guarda do ADR-0037: ela a respeita.

    `TeacherUnavailableError` herda de `LlmError` de propósito — quem só quer
    saber "o professor falhou?" continua funcionando sem mudar uma linha. Aqui
    isso se paga: o retry do CARD-025 cobre o provedor fora do ar sem que nada
    tenha sido acrescentado ao `FALHAS_DE_INFRAESTRUTURA`.
    """
    teacher = FakeTeacher(
        tres_sentencas(), erro=TeacherUnavailableError("morto"), erro_apos=0
    )
    m = Montagem(novo_turn(), teacher=teacher)

    with pytest.raises(RetryableTurnFailureError) as capturado:
        await m.processar(final=False)

    assert isinstance(capturado.value.__cause__, TeacherUnavailableError)
    assert m.turn.status is TurnStatus.PROCESSING


async def test_provedor_que_cai_DEPOIS_de_falar_nao_apaga_o_que_o_aluno_ouviu() -> None:  # noqa: N802 — o nome É a asserção
    """Motivo estável **e** os trechos preservados (ADR-0023, item 6).

    `delivered_partially=True` é o que muda a tela: o aluno ouviu parte da
    resposta e o app precisa dizer isso, não fingir que nada aconteceu.
    """
    teacher = FakeTeacher(
        tres_sentencas(), erro=TeacherUnavailableError("caiu no meio"), erro_apos=2
    )
    m = Montagem(novo_turn(), teacher=teacher)

    await m.processar(final=False)

    assert m.turn.status is TurnStatus.FAILED
    assert m.turn.failure_reason == PROVEDOR_INDISPONIVEL
    assert m.turn.delivered_partially is True
    assert len(m.turn.audio_chunks) == 2
