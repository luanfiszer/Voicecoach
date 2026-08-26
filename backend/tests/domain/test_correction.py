"""``Correction`` e a derivação dos campos legados (CARD-013).

Domínio puro: sem banco, sem IO, sem container. O que estes testes seguram é a
única regra que responde *"quem preenche `original`/`corrected`/`tip` quando há
duas correções?"* — e ela precisa de teste justamente porque a resposta é
arbitrária e, sem verificação, cada chamador inventaria a sua.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from voicecoach.domain.correction import (
    Correction,
    CorrectionType,
    Severity,
    legacy_summary,
)
from voicecoach.domain.errors import (
    InvalidStateTransitionError,
    OutOfOrderCorrectionError,
)
from voicecoach.domain.turn import Turn, TurnStatus

AGORA = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def correcao(index: int = 0, **campos: object) -> Correction:
    base: dict[str, object] = {
        "index": index,
        "type": CorrectionType.GRAMMAR,
        "original_excerpt": f"errado {index}",
        "corrected_form": f"certo {index}",
        "explanation": f"dica {index}",
        "severity": Severity.MINOR,
    }
    base.update(campos)
    return Correction(**base)  # type: ignore[arg-type]  # dict heterogêneo do helper


def turn_em_processamento() -> Turn:
    turn = Turn(
        id=uuid4(),
        session_id=uuid4(),
        input_audio_ref="a/b/input.aac",
        audio_duration=timedelta(seconds=5),
        created_at=AGORA,
    )
    turn.start_processing(AGORA)
    return turn


# --- a derivação dos campos legados do contrato /v1 ------------------------


def test_sem_correcao_os_campos_legados_sao_vazios_e_has_mistakes_e_falso() -> None:
    """O contrato que o ``v1.md`` já descrevia, preservado por construção."""
    legado = legacy_summary([])

    assert legado.has_mistakes is False
    assert (legado.original, legado.corrected, legado.tip) == ("", "", "")


def test_com_duas_correcoes_os_campos_legados_saem_da_primeira() -> None:
    """A decisão do CARD-013 — a primeira correção, não a mais severa.

    "A primeira" é escolha, não consequência: o prompt v2 ordena
    ``corrections[]`` por prioridade pedagógica, então o índice 0 já é a
    correção que o professor destacaria. Escolher pela severidade acoplaria o
    campo legado à escala do enum — e aí acrescentar um nível, movimento aditivo
    e permitido pelo ADR-0008, mudaria o que um cliente antigo vê.
    """
    primeira = correcao(0, severity=Severity.MINOR)
    segunda = correcao(1, severity=Severity.MAJOR)

    legado = legacy_summary([primeira, segunda])

    assert legado.has_mistakes is True
    assert legado.original == primeira.original_excerpt
    assert legado.corrected == primeira.corrected_form
    assert legado.tip == primeira.explanation


def test_a_severidade_nao_reordena_o_que_vai_para_os_campos_legados() -> None:
    """O contraponto explícito da alternativa recusada.

    Se um dia a regra virar "a mais severa", é aqui que a mudança fica visível —
    e é aqui que se lembra de que ela muda o que um cliente antigo lê.
    """
    legado = legacy_summary(
        [correcao(0, severity=Severity.MINOR), correcao(1, severity=Severity.MAJOR)]
    )

    assert legado.tip == "dica 0"


# --- a invariante de escrita ----------------------------------------------


def test_attach_corrections_grava_a_colecao_em_ordem() -> None:
    turn = turn_em_processamento()

    turn.attach_corrections([correcao(0), correcao(1)])

    assert [c.index for c in turn.corrections] == [0, 1]


def test_indice_furado_e_recusado() -> None:
    """Índice denso, como o do trecho de áudio — e pela mesma razão de chave."""
    turn = turn_em_processamento()

    with pytest.raises(OutOfOrderCorrectionError) as erro:
        turn.attach_corrections([correcao(0), correcao(2)])

    assert erro.value.expected == 1
    assert erro.value.received == 2


def test_gravar_duas_vezes_e_recusado() -> None:
    """Write-once: substituir apagaria a correção que o aluno já viu na tela."""
    turn = turn_em_processamento()
    turn.attach_corrections([correcao(0)])

    with pytest.raises(InvalidStateTransitionError):
        turn.attach_corrections([correcao(0)])


def test_nao_da_para_gravar_correcao_em_turn_que_nao_esta_processando() -> None:
    turn = turn_em_processamento()
    turn.attach_transcript("hi", AGORA)
    turn.attach_reply("Hi.", AGORA)
    turn.attach_reply_audio("reply/full.aac", AGORA)
    turn.complete(AGORA)

    with pytest.raises(InvalidStateTransitionError):
        turn.attach_corrections([correcao(0)])


def test_falhar_nao_apaga_as_correcoes_ja_gravadas() -> None:
    """O ADR-0023 item 6 aplicado ao dado mais valioso do produto.

    Se o ``reply/full`` falhar depois de o professor ter respondido, o turn fica
    ``failed`` — e a correção continua lá, porque é dela que o histórico do
    CARD-016 vive. Um turn falho não é um turn sem valor pedagógico.
    """
    turn = turn_em_processamento()
    turn.attach_reply("Hi.", AGORA)
    turn.attach_corrections([correcao(0)])

    turn.fail("o storage caiu", AGORA)

    assert turn.status is TurnStatus.FAILED
    assert len(turn.corrections) == 1


# --- igualdade estrutural (o que sustenta o teste de roundtrip) -----------


def test_duas_correcoes_com_os_mesmos_campos_sao_iguais() -> None:
    """``frozen=True`` gera ``__eq__`` por VALOR — é o que faz o roundtrip caber
    numa asserção só, em vez de uma por campo.
    """
    assert correcao(0) == correcao(0)
    assert correcao(0) != correcao(0, severity=Severity.MAJOR)


def test_correcao_e_hasheavel() -> None:
    """A outra metade do ``frozen=True``, e a que ``list`` teria quebrado.

    ``frozen=True`` congela a *ligação*, não o objeto: um campo ``list`` dentro
    de um dataclass congelado continua mutável, o ``__hash__`` gerado estoura com
    ``unhashable type: 'list'``, e nem o mypy nem o pytest acusam — só o dia em
    que alguém puser o objeto num ``set``. Este teste é esse dia, antecipado.
    """
    assert len({correcao(0), correcao(0), correcao(1)}) == 2
