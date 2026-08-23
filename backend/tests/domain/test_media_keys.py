"""Chaves de mídia: o zero-padding é contrato de playback (ADR-0024)."""

from __future__ import annotations

from uuid import UUID

import pytest

from voicecoach.domain.media_keys import (
    INDEX_DIGITS,
    AudioChunkIndexOverflowError,
    RetentionClass,
    input_key,
    reply_chunk_key,
    reply_full_key,
    reply_prefix,
    retention_class,
    student_prefix,
    turn_prefix,
)

STUDENT = UUID("11111111-1111-1111-1111-111111111111")
SESSION = UUID("22222222-2222-2222-2222-222222222222")
TURN = UUID("33333333-3333-3333-3333-333333333333")


def test_chave_do_trecho_segue_o_esquema_do_adr_0024() -> None:
    assert reply_chunk_key(STUDENT, SESSION, TURN, 0, "aac") == (
        f"{STUDENT}/{SESSION}/{TURN}/reply/000.aac"
    )


def test_input_e_full_seguem_o_esquema() -> None:
    assert input_key(STUDENT, SESSION, TURN, "m4a").endswith("/input.m4a")
    assert reply_full_key(STUDENT, SESSION, TURN, "aac").endswith("/reply/full.aac")


def test_ordem_lexicografica_do_bucket_e_a_ordem_de_playback() -> None:
    """O teste que o card pede: a listagem por prefixo já vem em ordem.

    `list_objects` do S3 devolve as chaves ordenadas por byte. Se essa ordem
    coincide com a ordem de playback, o cliente não precisa reordenar nada — e
    é isso que o zero-padding compra.
    """
    chaves = [reply_chunk_key(STUDENT, SESSION, TURN, i, "aac") for i in range(12)]

    assert sorted(chaves) == chaves


def test_sem_zero_padding_a_ordem_quebraria_no_decimo_trecho() -> None:
    """O par negativo do teste acima — prova que a regra MORDE.

    Sem o padding, `10` vem antes de `2` na ordenação por byte, e o aluno
    ouviria a décima frase logo depois da primeira. O modo de falha é audível,
    não uma exceção: nenhum teste que só olhasse "gravou?" pegaria isso.
    """
    sem_padding = [f"reply/{i}.aac" for i in range(12)]

    assert sorted(sem_padding) != sem_padding
    # E o ponto exato onde quebra:
    assert sorted(sem_padding)[1] == "reply/1.aac"
    assert sorted(sem_padding)[2] == "reply/10.aac"  # deveria ser o 2


def test_full_ordena_depois_de_todos_os_trechos() -> None:
    """`f` > `9` em ASCII, então `full` nunca se intromete no meio da sequência."""
    chaves = [reply_chunk_key(STUDENT, SESSION, TURN, i, "aac") for i in range(6)]
    chaves.append(reply_full_key(STUDENT, SESSION, TURN, "aac"))

    assert sorted(chaves)[-1].endswith("full.aac")


def test_indice_alem_do_esquema_levanta_em_vez_de_gravar_torto() -> None:
    limite = 10**INDEX_DIGITS
    with pytest.raises(AudioChunkIndexOverflowError, match="fora do esquema"):
        reply_chunk_key(STUDENT, SESSION, TURN, limite, "aac")


def test_indice_negativo_levanta() -> None:
    with pytest.raises(AudioChunkIndexOverflowError):
        reply_chunk_key(STUDENT, SESSION, TURN, -1, "aac")


def test_prefixos_aninham_do_aluno_ate_o_turn() -> None:
    """O que faz o delete de conta (CARD-017) ser uma operação, não uma varredura."""
    turno = turn_prefix(STUDENT, SESSION, TURN)
    trechos = reply_prefix(STUDENT, SESSION, TURN)

    assert turno.startswith(student_prefix(STUDENT))
    assert trechos.startswith(turno)
    assert reply_chunk_key(STUDENT, SESSION, TURN, 3, "aac").startswith(trechos)


# -- classe de retenção ------------------------------------------------------


def test_retencao_e_derivada_da_chave() -> None:
    """A chave já carrega a informação; um parâmetro extra poderia divergir dela."""
    assert (
        retention_class(input_key(STUDENT, SESSION, TURN, "m4a"))
        is RetentionClass.INPUT
    )
    assert (
        retention_class(reply_chunk_key(STUDENT, SESSION, TURN, 7, "aac"))
        is RetentionClass.REPLY_CHUNK
    )
    assert (
        retention_class(reply_full_key(STUDENT, SESSION, TURN, "aac"))
        is RetentionClass.REPLY_FULL
    )


def test_chave_fora_do_esquema_levanta_em_vez_de_virar_objeto_eterno() -> None:
    """O modo de falha que a exceção evita é vazamento de retenção, não crash."""
    with pytest.raises(ValueError, match="viveria para sempre"):
        retention_class("um/caminho/qualquer.bin")
