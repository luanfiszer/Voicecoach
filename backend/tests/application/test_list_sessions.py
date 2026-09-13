"""A listagem de sessões: ordem, zeros e a regra de mídia expirada (CARD-030).

A contagem de queries (RNF1) mora em `tests/adapters/test_persistence.py`,
contra Postgres real — é lá que ela significa algo. Aqui se verifica a REGRA:
o que entra na lista, em que ordem, e quando o áudio deixa de ser prometido.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes_pipeline import FakeSessionRepository, FakeTurnRepository
from voicecoach.application.use_cases.list_sessions import (
    ListSessions,
    ListSessionsHandler,
)
from voicecoach.domain.session import Session

ALUNO = UUID("00000000-0000-0000-0000-000000000001")
OUTRO_ALUNO = UUID("00000000-0000-0000-0000-000000000002")
AGORA = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
RETENCAO_DO_TRECHO = timedelta(days=1)


def sessao(
    *, quando: datetime, student_id: UUID = ALUNO, encerrada: bool = False
) -> Session:
    s = Session(id=uuid4(), student_id=student_id, started_at=quando)
    if encerrada:
        s.ended_at = quando + timedelta(minutes=8)
    return s


def montar(
    *sessoes: Session, turns: FakeTurnRepository | None = None
) -> ListSessionsHandler:
    return ListSessionsHandler(
        sessions=FakeSessionRepository(*sessoes, turns=turns or FakeTurnRepository()),
        clock=lambda: AGORA,
        reply_media_retention=RETENCAO_DO_TRECHO,
    )


def com_turns(
    sessao_alvo: Session, *, quantos: int, quando: datetime
) -> FakeTurnRepository:
    turns = FakeTurnRepository()
    for i in range(quantos):
        turn = sessao_alvo.start_turn(
            turn_id=uuid4(),
            input_audio_ref=f"dev/{i}.m4a",
            audio_duration=timedelta(seconds=30),
            now=quando,
        )
        turns.turns[turn.id] = turn
    return turns


async def test_as_sessoes_vem_da_mais_recente_para_a_mais_antiga() -> None:
    """Critério de aceite: 3 sessões, ordenadas, com as contagens certas."""
    velha = sessao(quando=AGORA - timedelta(days=3))
    media = sessao(quando=AGORA - timedelta(days=2))
    nova = sessao(quando=AGORA - timedelta(hours=1))
    handler = montar(velha, media, nova)

    itens = await handler.handle(
        ListSessions(student_id=ALUNO, window=timedelta(days=30))
    )

    assert [item.digest.id for item in itens] == [nova.id, media.id, velha.id]


async def test_sessao_sem_turn_nenhum_aparece_com_zeros() -> None:
    """RF4: o aluno abriu e desistiu — zero é dado, não ausência."""
    vazia = sessao(quando=AGORA - timedelta(hours=2))
    handler = montar(vazia)

    itens = await handler.handle(
        ListSessions(student_id=ALUNO, window=timedelta(days=30))
    )

    assert len(itens) == 1
    assert itens[0].digest.turns == 0
    assert itens[0].digest.spoken == timedelta(0)
    assert itens[0].digest.corrections == 0
    # Não há mídia sobre a qual responder — dizer "disponível" prometeria o que
    # nunca existiu.
    assert itens[0].reply_media_available is False


async def test_a_duracao_falada_soma_os_turns() -> None:
    """RF6: a mesma definição do resumo pós-sessão (CARD-031)."""
    alvo = sessao(quando=AGORA - timedelta(hours=1))
    handler = montar(alvo, turns=com_turns(alvo, quantos=3, quando=AGORA))

    itens = await handler.handle(
        ListSessions(student_id=ALUNO, window=timedelta(days=30))
    )

    assert itens[0].digest.turns == 3
    assert itens[0].digest.spoken == timedelta(seconds=90)


async def test_aluno_sem_sessao_recebe_lista_vazia() -> None:
    """RF5: ausência de sessões é resposta, não recurso inexistente."""
    handler = montar(sessao(quando=AGORA, student_id=OUTRO_ALUNO))

    itens = await handler.handle(
        ListSessions(student_id=ALUNO, window=timedelta(days=30))
    )

    assert itens == []


async def test_a_janela_corta_o_que_e_mais_velho_que_ela() -> None:
    """RF2: o que ficou fora da janela não é erro — é ausência."""
    dentro = sessao(quando=AGORA - timedelta(days=5))
    fora = sessao(quando=AGORA - timedelta(days=40))
    handler = montar(dentro, fora)

    itens = await handler.handle(
        ListSessions(student_id=ALUNO, window=timedelta(days=30))
    )

    assert [item.digest.id for item in itens] == [dentro.id]


async def test_audio_dentro_da_retencao_e_prometido() -> None:
    alvo = sessao(quando=AGORA - timedelta(hours=2))
    handler = montar(
        alvo, turns=com_turns(alvo, quantos=1, quando=AGORA - timedelta(hours=2))
    )

    itens = await handler.handle(
        ListSessions(student_id=ALUNO, window=timedelta(days=30))
    )

    assert itens[0].reply_media_available is True


async def test_audio_de_ontem_ja_expirou_e_o_resto_continua_intacto() -> None:
    """Critério de aceite: o campo diz que expirou, e as contagens vêm íntegras.

    Com `retention_reply_chunk` de 1 dia, a conversa de ontem já perdeu os
    trechos — que é o caso comum, não a exceção que o artboard sugere ao pôr o
    aviso na terceira linha.
    """
    ontem = AGORA - timedelta(days=1, hours=2)
    alvo = sessao(quando=ontem)
    handler = montar(alvo, turns=com_turns(alvo, quantos=2, quando=ontem))

    itens = await handler.handle(
        ListSessions(student_id=ALUNO, window=timedelta(days=30))
    )

    assert itens[0].reply_media_available is False
    assert itens[0].digest.turns == 2
    assert itens[0].digest.spoken == timedelta(minutes=1)


async def test_sessao_encerrada_traz_o_ended_at() -> None:
    alvo = sessao(quando=AGORA - timedelta(hours=3), encerrada=True)
    handler = montar(alvo)

    itens = await handler.handle(
        ListSessions(student_id=ALUNO, window=timedelta(days=30))
    )

    assert itens[0].digest.ended_at is not None
