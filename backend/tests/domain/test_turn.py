"""Regras de ciclo de vida do Turn (ADR-0023, ADR-0017).

Testes de domínio puro: sem banco, sem IO, sem container. O relógio entra por
parâmetro — é o que permite asserção sobre instante exato sem congelar tempo com
biblioteca nenhuma.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from voicecoach.domain.errors import (
    DomainError,
    InvalidStateTransitionError,
    OutOfOrderAudioChunkError,
)
from voicecoach.domain.turn import Turn, TurnStage, TurnStatus

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def make_turn() -> Turn:
    return Turn(
        id=uuid4(),
        session_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=14),
        created_at=NOW,
    )


def make_processing_turn() -> Turn:
    turn = make_turn()
    turn.start_processing(NOW)
    return turn


def test_turn_nasce_na_fila() -> None:
    assert make_turn().status is TurnStatus.QUEUED


def test_duracao_precisa_ser_positiva() -> None:
    with pytest.raises(ValueError, match="duração"):
        Turn(
            id=uuid4(),
            session_id=uuid4(),
            input_audio_ref="dev/entrada.m4a",
            audio_duration=timedelta(0),
            created_at=NOW,
        )


def test_start_processing_marca_o_instante() -> None:
    turn = make_turn()
    turn.start_processing(NOW)

    assert turn.status is TurnStatus.PROCESSING
    assert turn.started_processing_at == NOW


def test_turn_completo_recusa_voltar_a_processar() -> None:
    """Critério de aceite do CARD-005."""
    turn = make_processing_turn()
    turn.attach_transcript("I go to the beach", NOW)
    turn.attach_reply("Which beach?", NOW)
    turn.attach_reply_audio("dev/resposta.mp3", NOW)
    turn.complete(NOW)

    with pytest.raises(InvalidStateTransitionError) as erro:
        turn.start_processing(NOW)

    assert erro.value.state == "completed"
    assert erro.value.action == "start_processing"


def test_artefato_so_entra_com_o_turn_em_processamento() -> None:
    turn = make_turn()

    with pytest.raises(InvalidStateTransitionError):
        turn.attach_transcript("I go to the beach", NOW)


@pytest.mark.parametrize(
    ("transcript", "reply", "audio"),
    [
        (None, None, None),
        ("I go to the beach", None, None),
        ("I go to the beach", "Which beach?", None),
    ],
)
def test_complete_exige_todos_os_artefatos(
    transcript: str | None, reply: str | None, audio: str | None
) -> None:
    turn = make_processing_turn()
    if transcript is not None:
        turn.attach_transcript(transcript, NOW)
    if reply is not None:
        turn.attach_reply(reply, NOW)
    if audio is not None:
        turn.attach_reply_audio(audio, NOW)

    with pytest.raises(InvalidStateTransitionError):
        turn.complete(NOW)

    assert turn.status is TurnStatus.PROCESSING


def test_artefatos_nao_exigem_ordem_entre_si() -> None:
    """ADR-0003: no V2 as etapas se sobrepõem — a entidade não pode fixar a ordem."""
    turn = make_processing_turn()

    turn.attach_reply_audio("dev/resposta.mp3", NOW)
    turn.attach_reply("Which beach?", NOW)
    turn.attach_transcript("I go to the beach", NOW)
    turn.complete(NOW)

    assert turn.status is TurnStatus.COMPLETED


def test_etapa_e_deriva_dos_artefatos_e_nao_de_um_campo() -> None:
    """ADR-0023: a etapa sai dos artefatos, não de um campo que se mantém à mão."""
    turn = make_processing_turn()
    assert turn.transcript is None
    assert turn.reply_text is None

    turn.attach_transcript("I go to the beach", NOW)
    assert turn.transcribed_at == NOW
    assert turn.reply_text is None  # ainda não pensou

    turn.attach_reply("Which beach?", NOW)
    assert turn.reply_audio_ref is None  # texto pronto, áudio a caminho


def test_falha_pode_acontecer_antes_de_alguem_pegar_da_fila() -> None:
    """O worker pode morrer com o Turn ainda em `queued` (tela de timeout)."""
    turn = make_turn()
    turn.fail("worker indisponível", NOW)

    assert turn.status is TurnStatus.FAILED
    assert turn.failure_reason == "worker indisponível"
    assert turn.failed_at == NOW


def test_falha_preserva_o_que_ja_tinha_sido_produzido() -> None:
    turn = make_processing_turn()
    turn.attach_transcript("I go to the beach", NOW)

    turn.fail("TTS fora do ar", NOW)

    assert turn.status is TurnStatus.FAILED
    assert turn.transcript == "I go to the beach"


@pytest.mark.parametrize("estado_final", [TurnStatus.COMPLETED, TurnStatus.FAILED])
def test_turn_encerrado_nao_falha_de_novo(estado_final: TurnStatus) -> None:
    turn = make_processing_turn()
    turn.attach_transcript("I go to the beach", NOW)
    turn.attach_reply("Which beach?", NOW)
    turn.attach_reply_audio("dev/resposta.mp3", NOW)
    if estado_final is TurnStatus.COMPLETED:
        turn.complete(NOW)
    else:
        turn.fail("primeira falha", NOW)

    with pytest.raises(InvalidStateTransitionError):
        turn.fail("segunda falha", NOW)


def test_audio_expirado_e_diferente_de_audio_inexistente() -> None:
    """CARD-017: transcrição e correções permanecem quando o áudio expira."""
    nunca_teve = make_processing_turn()
    assert nunca_teve.reply_audio_ref is None
    assert nunca_teve.synthesized_at is None

    expirou = make_processing_turn()
    expirou.attach_reply_audio("dev/resposta.mp3", NOW)
    expirou.reply_audio_ref = None  # o lifecycle do storage apagou o objeto

    assert expirou.synthesized_at == NOW  # o áudio existiu, e dá para provar


# -- entrega em cascata: trechos de áudio (ADR-0023) -------------------------


def fala(turn: Turn, index: int) -> None:
    """Acrescenta o trecho `index` com valores plausíveis do CARD-008."""
    turn.append_audio_chunk(
        index=index,
        storage_key=f"aluno/sessao/turn/reply/{index:03d}.mp3",
        duration_seconds=1.4,
        text="Which beach did you go to?",
        now=NOW,
    )


def test_etapa_e_transcribing_enquanto_nao_ha_artefato_nenhum() -> None:
    assert make_processing_turn().stage is TurnStage.TRANSCRIBING


def test_etapa_e_thinking_com_transcricao_e_sem_trecho() -> None:
    turn = make_processing_turn()
    turn.attach_transcript("I go to the beach", NOW)

    assert turn.stage is TurnStage.THINKING


def test_etapa_e_speaking_com_trecho_e_reply_text_ainda_nulo() -> None:
    """O caso que só existe na cascata — e o que a tabela do ADR-0016 errava.

    Sob o ADR-0016 a condição de `speaking` era `reply_text`; aqui ele é nulo e
    o professor já está falando. Checar `transcript` antes dos trechos devolveria
    `thinking` com áudio tocando.
    """
    turn = make_processing_turn()
    turn.attach_transcript("I go to the beach", NOW)
    fala(turn, 0)

    assert turn.reply_text is None
    assert turn.stage is TurnStage.SPEAKING


def test_etapa_e_completed_com_o_audio_inteiro() -> None:
    turn = make_processing_turn()
    turn.attach_transcript("I go to the beach", NOW)
    fala(turn, 0)
    turn.attach_reply("Which beach?", NOW)
    turn.attach_reply_audio("dev/resposta.mp3", NOW)

    assert turn.stage is TurnStage.COMPLETED


def test_indice_do_trecho_e_denso_e_crescente() -> None:
    turn = make_processing_turn()
    fala(turn, 0)
    fala(turn, 1)

    assert [chunk.index for chunk in turn.audio_chunks] == [0, 1]


@pytest.mark.parametrize("indice_ruim", [0, 2, 5, -1])
def test_indice_repetido_ou_furado_e_recusado(indice_ruim: int) -> None:
    turn = make_processing_turn()
    fala(turn, 0)

    with pytest.raises(OutOfOrderAudioChunkError) as erro:
        fala(turn, indice_ruim)

    assert erro.value.expected == 1
    assert erro.value.received == indice_ruim
    assert len(turn.audio_chunks) == 1  # a coleção não foi tocada


def test_erro_de_indice_e_erro_de_dominio() -> None:
    """ADR-0017: a borda captura `DomainError` num lugar só."""
    assert issubclass(OutOfOrderAudioChunkError, DomainError)


def test_turn_completo_recusa_trecho_novo() -> None:
    """Critério de aceite do CARD-018."""
    turn = make_processing_turn()
    turn.attach_transcript("I go to the beach", NOW)
    turn.attach_reply("Which beach?", NOW)
    turn.attach_reply_audio("dev/resposta.mp3", NOW)
    turn.complete(NOW)

    with pytest.raises(InvalidStateTransitionError) as erro:
        fala(turn, 0)

    assert erro.value.action == "append_audio_chunk"
    assert erro.value.state == "completed"


def test_turn_falho_recusa_trecho_novo() -> None:
    turn = make_processing_turn()
    turn.fail("TTS fora do ar", NOW)

    with pytest.raises(InvalidStateTransitionError):
        fala(turn, 0)


def test_trecho_so_entra_com_o_turn_em_processamento() -> None:
    turn = make_turn()

    with pytest.raises(InvalidStateTransitionError):
        fala(turn, 0)


def test_falha_nao_apaga_o_que_o_aluno_ja_ouviu() -> None:
    """Critério de aceite do CARD-018: contar os trechos, não olhar o status.

    É a invariante que nenhum teste de transição pega — `fail()` continuaria
    passando com a coleção esvaziada.
    """
    turn = make_processing_turn()
    fala(turn, 0)
    fala(turn, 1)

    turn.fail("tts timeout", NOW)

    assert turn.status is TurnStatus.FAILED
    assert len(turn.audio_chunks) == 2
    assert turn.delivered_partially


def test_falha_sem_trecho_nao_e_entrega_parcial() -> None:
    turn = make_processing_turn()
    turn.attach_transcript("I go to the beach", NOW)

    turn.fail("LLM fora do ar", NOW)

    assert not turn.delivered_partially


def test_turn_completo_nao_e_entrega_parcial() -> None:
    """`delivered_partially` fala de falha, não de quantidade de trechos."""
    turn = make_processing_turn()
    turn.attach_transcript("I go to the beach", NOW)
    fala(turn, 0)
    turn.attach_reply("Which beach?", NOW)
    turn.attach_reply_audio("dev/resposta.mp3", NOW)
    turn.complete(NOW)

    assert not turn.delivered_partially


def test_completar_nao_exige_trecho() -> None:
    """A cascata é como o worker trabalha, não invariante da entidade."""
    turn = make_processing_turn()
    turn.attach_transcript("I go to the beach", NOW)
    turn.attach_reply("Which beach?", NOW)
    turn.attach_reply_audio("dev/resposta.mp3", NOW)

    turn.complete(NOW)

    assert turn.status is TurnStatus.COMPLETED
    assert turn.audio_chunks == []


def test_trecho_e_imutavel_depois_de_entregue() -> None:
    """`frozen=True`: o que o aluno ouviu não muda de conteúdo nem de posição."""
    turn = make_processing_turn()
    fala(turn, 0)

    with pytest.raises(AttributeError):
        turn.audio_chunks[0].index = 7  # type: ignore[misc]  # é o que se testa


def test_dois_turns_nao_compartilham_a_lista_de_trechos() -> None:
    """`field(default_factory=list)`: default mutável compartilhado é bug clássico."""
    um = make_processing_turn()
    outro = make_processing_turn()

    fala(um, 0)

    assert outro.audio_chunks == []
