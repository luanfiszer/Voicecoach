"""A entrega progressiva: retomada do banco, canal ao vivo e o fechamento.

Nenhum Redis: o ``FakeTurnEvents`` é um canal em memória com fila por assinante,
e ele reproduz a garantia que importa — **assina no ``__aenter__``**, não na
primeira iteração.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from fakes_pipeline import FakeTurnEvents, FakeTurnRepository
from voicecoach.application.ports.turn_events import (
    ChunkReady,
    Completed,
    Failed,
    FeedbackAvailable,
    Transcribed,
)
from voicecoach.application.use_cases.process_turn import TurnNotFoundError
from voicecoach.application.use_cases.stream_turn_events import (
    Delivery,
    MalformedEventIdError,
    StreamTurnEventsHandler,
    historico,
    posicao,
)
from voicecoach.domain.turn import Turn, TurnStatus

AGORA = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def turn_em_processamento(*, trechos: int = 0, transcript: str | None = None) -> Turn:
    turn = Turn(
        id=uuid4(),
        session_id=uuid4(),
        input_audio_ref="in.aac",
        audio_duration=timedelta(seconds=4),
        created_at=AGORA,
    )
    turn.start_processing(AGORA)
    if transcript is not None:
        turn.attach_transcript(transcript, AGORA)
    for i in range(trechos):
        turn.append_audio_chunk(
            index=i,
            storage_key=f"reply/{i:03d}.aac",
            duration_seconds=1.5,
            text=f"frase {i}",
            now=AGORA,
        )
    return turn


def montar(
    turn: Turn, *, timeout: float = 5.0
) -> tuple[StreamTurnEventsHandler, FakeTurnEvents]:
    canal = FakeTurnEvents()
    handler = StreamTurnEventsHandler(
        turns=FakeTurnRepository(turn),
        events=canal,
        timeout=timedelta(seconds=timeout),
    )
    return handler, canal


async def coletar(
    handler: StreamTurnEventsHandler, turn: Turn, **kw: object
) -> list[Delivery]:
    return [d async for d in handler.stream(turn.id, **kw)]  # type: ignore[arg-type]


# --- a ordem total dos ids (o esquema de `id:` do SSE) ---------------------


def test_a_ordem_dos_ids_e_a_do_pipeline_e_nao_a_lexicografica() -> None:
    """``chunk:10`` vem DEPOIS de ``chunk:2``.

    Comparar as strings daria a ordem do dicionário — o mesmo bug que o
    zero-padding das chaves de storage evita no bucket (ADR-0024). Aqui o id é
    legível de propósito, então a ordem mora na função, não no formato.
    """
    ordenados = sorted(
        ["completed", "chunk:10", "transcribed", "feedback", "chunk:2"], key=posicao
    )

    assert ordenados == ["transcribed", "chunk:2", "chunk:10", "feedback", "completed"]


@pytest.mark.parametrize("invalido", ["", "chunk:", "chunk:a", "qualquer", "3"])
def test_id_fora_do_esquema_levanta(invalido: str) -> None:
    """Tratar id inventado como "comece do começo" reentregaria áudio já ouvido.

    O modo de falha seria o professor repetindo frases — muito mais confuso de
    depurar do que um 400.
    """
    with pytest.raises(MalformedEventIdError):
        posicao(invalido)


# --- o histórico reconstruído do banco -------------------------------------


def test_o_historico_reconstroi_transcricao_trechos_e_desfecho() -> None:
    turn = turn_em_processamento(trechos=2, transcript="hi there")
    turn.attach_reply("Hi there. How are you?", AGORA)
    turn.attach_reply_audio("reply/full.aac", AGORA)
    turn.complete(AGORA)

    ids = [d.event_id for d in historico(turn)]

    assert ids == ["transcribed", "chunk:0", "chunk:1", "completed"]


def test_o_historico_nao_reconstroi_feedback() -> None:
    """A dívida do ADR-0035, verificada em vez de escrita só em prosa.

    Correção não é persistida até o CARD-013. Um cliente que reconecte depois de
    o ``feedback`` ter passado não o recebe neste stream — ele o vê no histórico,
    mais tarde. Inventar um evento vazio seria pior que não mandar nada.
    """
    turn = turn_em_processamento(trechos=1, transcript="hi")

    assert all(d.event_id != "feedback" for d in historico(turn))


def test_turn_que_falhou_depois_de_trechos_mantem_os_trechos_e_marca_parcial() -> None:
    """Critério de aceite do card, no nível em que ele é barato de verificar."""
    turn = turn_em_processamento(trechos=2, transcript="hi")
    turn.fail("tts caiu", AGORA)

    entregas = list(historico(turn))
    ids = [d.event_id for d in entregas]
    falha = entregas[-1].event

    assert ids == ["transcribed", "chunk:0", "chunk:1", "failed"]
    assert isinstance(falha, Failed)
    assert falha.delivered_partially is True


# --- retomada ---------------------------------------------------------------


async def test_reconectar_no_segundo_trecho_recebe_do_terceiro_em_diante() -> None:
    """O critério de aceite do ``Last-Event-ID``: sem repetir e sem pular."""
    turn = turn_em_processamento(trechos=4, transcript="hi")
    turn.fail("parou", AGORA)
    handler, _ = montar(turn)

    entregas = await coletar(handler, turn, last_event_id="chunk:1")

    assert [d.event_id for d in entregas] == ["chunk:2", "chunk:3", "failed"]


async def test_sem_last_event_id_recebe_tudo_desde_o_comeco() -> None:
    turn = turn_em_processamento(trechos=2, transcript="hi")
    turn.fail("parou", AGORA)
    handler, _ = montar(turn)

    entregas = await coletar(handler, turn)

    assert [d.event_id for d in entregas] == [
        "transcribed",
        "chunk:0",
        "chunk:1",
        "failed",
    ]


async def test_turn_inexistente_levanta_para_a_borda_traduzir() -> None:
    """A limitação honesta do ``Result``: ele não atravessa um gerador."""
    handler = StreamTurnEventsHandler(
        turns=FakeTurnRepository(), events=FakeTurnEvents(), timeout=timedelta(1)
    )

    with pytest.raises(TurnNotFoundError):
        async for _ in handler.stream(uuid4()):
            pass


# --- o canal ao vivo --------------------------------------------------------


async def test_eventos_ao_vivo_seguem_o_historico_sem_repetir() -> None:
    """O trecho 0 já está no banco; o 1 chega pelo canal. Nenhum vem duas vezes."""
    turn = turn_em_processamento(trechos=1, transcript="hi")
    handler, canal = montar(turn)

    async def publicar() -> None:
        await asyncio.sleep(0)
        # O trecho 0 REPUBLICADO: o worker o publicou e o banco já o tinha.
        # A deduplicação por id é o que impede o aluno de ouvi-lo duas vezes.
        await canal.publish(
            turn.id,
            ChunkReady(
                index=0,
                storage_key="reply/000.aac",
                duration_seconds=1.5,
                text="frase 0",
            ),
        )
        await canal.publish(
            turn.id,
            ChunkReady(
                index=1,
                storage_key="reply/001.aac",
                duration_seconds=1.5,
                text="frase 1",
            ),
        )
        await canal.publish(
            turn.id,
            FeedbackAvailable(has_mistakes=False, original="", corrected="", tip=""),
        )
        await canal.publish(turn.id, Completed(reply_audio_key="reply/full.aac"))

    tarefa = asyncio.create_task(publicar())
    entregas = await coletar(handler, turn)
    await tarefa

    assert [d.event_id for d in entregas] == [
        "transcribed",
        "chunk:0",
        "chunk:1",
        "feedback",
        "completed",
    ]


async def test_o_stream_fecha_no_evento_terminal() -> None:
    """Sem isto, a conexão viveria até o prazo mesmo com o turn fechado."""
    turn = turn_em_processamento(transcript="hi")
    handler, canal = montar(turn, timeout=30.0)

    async def publicar() -> None:
        await asyncio.sleep(0)
        await canal.publish(turn.id, Failed(reason="x", delivered_partially=False))
        # Publicado DEPOIS do terminal: ninguém mais está ouvindo.
        await canal.publish(turn.id, Transcribed(transcript="tarde demais"))

    tarefa = asyncio.create_task(publicar())
    entregas = await asyncio.wait_for(coletar(handler, turn), timeout=2)
    await tarefa

    assert [d.event_id for d in entregas] == ["transcribed", "failed"]


async def test_o_stream_fecha_no_prazo_mesmo_sem_evento_nenhum() -> None:
    """Stream sem prazo é conexão vazando (ADR-0026, item 5).

    O turn está em ``processing`` e travado; ninguém publica nada. O gerador tem
    de terminar sozinho — o ``EventSource`` do cliente reconecta e nada se perde,
    porque a retomada lê do banco.
    """
    turn = turn_em_processamento(transcript="hi")
    handler, _ = montar(turn, timeout=0.05)

    entregas = await asyncio.wait_for(coletar(handler, turn), timeout=2)

    assert [d.event_id for d in entregas] == ["transcribed"]


async def test_a_assinatura_acontece_antes_da_leitura_do_banco() -> None:
    """A corrida que a porta ``subscribe`` fecha, e que nenhum outro teste pega.

    O repositório publica **enquanto** a leitura do banco acontece. Se o
    ``SUBSCRIBE`` só fosse emitido na primeira iteração do canal (o que
    aconteceria se a porta devolvesse um gerador em vez de um context manager),
    este evento cairia no chão — pub/sub não guarda nada (ADR-0035) — e o aluno
    simplesmente nunca receberia aquele trecho.
    """
    turn = turn_em_processamento(transcript="hi")
    canal = FakeTurnEvents()

    class RepositorioQuePublicaEnquantoLe(FakeTurnRepository):
        async def get(self, turn_id: UUID) -> Turn | None:
            await canal.publish(
                turn_id,
                ChunkReady(
                    index=0,
                    storage_key="reply/000.aac",
                    duration_seconds=1.0,
                    text="publicado durante a leitura",
                ),
            )
            await canal.publish(turn_id, Completed(reply_audio_key="reply/full.aac"))
            return await super().get(turn_id)

    handler = StreamTurnEventsHandler(
        turns=RepositorioQuePublicaEnquantoLe(turn),
        events=canal,
        timeout=timedelta(seconds=2),
    )

    entregas = await asyncio.wait_for(coletar(handler, turn), timeout=5)

    assert [d.event_id for d in entregas] == ["transcribed", "chunk:0", "completed"]


async def test_evento_anterior_ao_last_event_id_e_descartado_tambem_ao_vivo() -> None:
    """O corte vale para os dois caminhos, ou a retomada reentrega áudio."""
    turn = turn_em_processamento(trechos=2, transcript="hi")
    handler, canal = montar(turn)

    async def publicar() -> None:
        await asyncio.sleep(0)
        await canal.publish(
            turn.id,
            ChunkReady(index=0, storage_key="a", duration_seconds=1.0, text="velho"),
        )
        await canal.publish(turn.id, Completed(reply_audio_key="reply/full.aac"))

    tarefa = asyncio.create_task(publicar())
    entregas = await asyncio.wait_for(
        coletar(handler, turn, last_event_id="chunk:0"), timeout=2
    )
    await tarefa

    assert [d.event_id for d in entregas] == ["chunk:1", "completed"]


def test_turn_completed_mas_sem_audio_nao_finge_ter_url() -> None:
    """Áudio expirado (ADR-0024, item 5) não vira ``completed`` mentiroso."""
    turn = turn_em_processamento(trechos=1, transcript="hi")
    turn.attach_reply("x", AGORA)
    turn.attach_reply_audio("reply/full.aac", AGORA)
    turn.complete(AGORA)
    turn.reply_audio_ref = None  # a retenção levou o objeto

    ids = [d.event_id for d in historico(turn)]

    assert turn.status is TurnStatus.COMPLETED
    assert "completed" not in ids
