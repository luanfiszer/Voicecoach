"""Onde cada artefato de mídia de um turn mora no storage (ADR-0024).

**Por que isto é domínio e não adapter.** A chave parece detalhe de
infraestrutura, mas duas regras do produto vivem dentro dela:

1. **A ordem lexicográfica do bucket É a ordem de playback.** Por isso o índice
   é zero-padded em três dígitos: sem isso, `10` viria antes de `2` numa
   listagem por prefixo, e o aluno ouviria a resposta fora de ordem. O modo de
   falha é *audível*, não uma exceção — exatamente como a taxa de amostragem
   errada.
2. **Tudo de um turn vive sob o mesmo prefixo**, e tudo de um aluno sob o dele.
   É o que faz o `delete_prefix` do delete de conta (CARD-017) ser uma operação
   e não uma varredura.

O adapter de storage não decide nada disso; ele recebe a chave pronta. Módulo
puro: só stdlib, nenhum IO, testável sem MinIO.

O contrato completo, do ADR-0024:

    {student_id}/{session_id}/{turn_id}/input.{ext}
    {student_id}/{session_id}/{turn_id}/reply/{index:03d}.{ext}
    {student_id}/{session_id}/{turn_id}/reply/full.{ext}
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

# Três dígitos cobrem 1.000 trechos. Uma resposta do professor tem 3 a 6
# (ADR-0023); mil é folga de duas ordens de grandeza sobre o pior caso, e o
# número aparece no ADR-0024 como parte do contrato — mudá-lo quebraria a
# ordenação de tudo que já está gravado.
INDEX_DIGITS = 3
_MAX_INDEX = 10**INDEX_DIGITS - 1


class AudioChunkIndexOverflowError(ValueError):
    """Mais trechos do que o esquema de chaves comporta.

    ``ValueError`` e não ``DomainError``: não é invariante de negócio violada
    (ADR-0017), é o limite do formato da chave. Existe para que o estouro seja
    uma exceção no ponto exato, e não uma chave de quatro dígitos gravada em
    silêncio — que ordenaria errado e só apareceria como áudio embaralhado.
    """


def turn_prefix(student_id: UUID, session_id: UUID, turn_id: UUID) -> str:
    """O prefixo sob o qual vive **tudo** de um turn."""
    return f"{student_id}/{session_id}/{turn_id}"


def student_prefix(student_id: UUID) -> str:
    """O prefixo do aluno — o alvo do `delete_prefix` no delete de conta."""
    return f"{student_id}/"


def input_key(student_id: UUID, session_id: UUID, turn_id: UUID, extension: str) -> str:
    """O áudio que o aluno enviou. Retenção curta: 7 dias (ADR-0024)."""
    return f"{turn_prefix(student_id, session_id, turn_id)}/input.{extension}"


def reply_chunk_key(
    student_id: UUID, session_id: UUID, turn_id: UUID, index: int, extension: str
) -> str:
    """Um trecho da resposta. Retenção de 1 dia: `full` é a cópia longa.

    O ``index`` é o mesmo que `Turn.append_audio_chunk` recebe — denso e
    0-based. Ele vem de fora, e não é contado aqui, porque quem grava precisa da
    chave **antes** de o trecho existir na entidade.
    """
    if index < 0 or index > _MAX_INDEX:
        message = (
            f"índice de trecho fora do esquema de chaves: {index} "
            f"(o ADR-0024 fixou {INDEX_DIGITS} dígitos, 0..{_MAX_INDEX})"
        )
        raise AudioChunkIndexOverflowError(message)
    prefix = turn_prefix(student_id, session_id, turn_id)
    return f"{prefix}/reply/{index:0{INDEX_DIGITS}d}.{extension}"


def reply_full_key(
    student_id: UUID, session_id: UUID, turn_id: UUID, extension: str
) -> str:
    """A resposta inteira concatenada — o que o histórico reproduz (90 dias).

    Mora **dentro** de `reply/`, junto dos trechos, e não ao lado: assim um
    `delete_prefix` de `reply/` leva os dois, e a listagem do turn é um prefixo
    só. `full` ordena depois de qualquer `NNN` em ASCII (`f` > `0`-`9`), então
    ele não se intromete no meio da sequência de playback.
    """
    return f"{turn_prefix(student_id, session_id, turn_id)}/reply/full.{extension}"


def reply_prefix(student_id: UUID, session_id: UUID, turn_id: UUID) -> str:
    """O prefixo que lista os trechos de uma resposta **já em ordem**."""
    return f"{turn_prefix(student_id, session_id, turn_id)}/reply/"


class RetentionClass(StrEnum):
    """A que regra de retenção um objeto pertence (ADR-0024, item 4).

    **Por que isto existe, e por que é uma tag e não um prefixo.** O ADR-0024
    decidiu três retenções diferentes — `input` 7 dias, trecho 1 dia, `full` 90
    dias — e fixou um esquema de chaves que começa pelo `student_id`. As duas
    decisões, juntas, produzem um problema que nenhuma delas tinha sozinha:
    **não existe prefixo comum** que selecione "todos os inputs" ou "todos os
    trechos", porque cada aluno tem o seu. E o lifecycle do S3 filtra por
    prefixo ou por **tag** — não por sufixo, não por padrão.

    Logo, a retenção assimétrica exige uma tag por objeto. Ela é derivada da
    chave (a chave já carrega a informação) para que ninguém precise lembrar de
    passá-la: esquecer a tag não daria erro, só faria o objeto viver para sempre
    — um vazamento de retenção silencioso, no dado mais sensível do produto.
    """

    INPUT = "input"
    REPLY_CHUNK = "reply-chunk"
    REPLY_FULL = "reply-full"


def retention_class(key: str) -> RetentionClass:
    """Deduz a classe de retenção da própria chave.

    A chave é contrato (ADR-0024), então ela é a fonte da verdade — e derivar
    em vez de exigir um parâmetro mantém as duas coisas impossíveis de divergir.
    """
    nome = key.rsplit("/", 1)[-1]
    if "/reply/" in key:
        return (
            RetentionClass.REPLY_FULL
            if nome.startswith("full.")
            else RetentionClass.REPLY_CHUNK
        )
    if nome.startswith("input."):
        return RetentionClass.INPUT
    message = (
        f"chave fora do esquema do ADR-0024, sem retenção definível: {key!r}. "
        f"Objeto sem classe de retenção viveria para sempre."
    )
    raise ValueError(message)
