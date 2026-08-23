"""A porta de storage vista de `application`: um dict no lugar do MinIO.

O adapter real tem teste de integração contra MinIO em container (ADR-0018).
Aqui o que se exercita é o **contrato**: o que o caso de uso do CARD-009 pode
assumir sobre qualquer implementação.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from voicecoach.application.ports.media_storage import (
    MediaStorage,
    MediaStorageError,
)
from voicecoach.domain.media_keys import (
    reply_chunk_key,
    reply_prefix,
    student_prefix,
)

STUDENT = UUID("11111111-1111-1111-1111-111111111111")
SESSION = UUID("22222222-2222-2222-2222-222222222222")
TURN = UUID("33333333-3333-3333-3333-333333333333")


class FakeMediaStorage:
    """Storage em memória. Um `dict` ordenado de chave para (bytes, content-type).

    Ele imita a **única** propriedade do S3 de que o contrato depende: a
    listagem por prefixo sai ordenada por byte. Imitar mais que isso seria
    escrever um MinIO ruim e fingir que o teste prova algo sobre o real.
    """

    def __init__(self) -> None:
        self.objetos: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objetos[key] = (data, content_type)

    async def presigned_get_url(self, key: str, ttl: timedelta) -> str:
        if key not in self.objetos:
            message = f"chave inexistente: {key}"
            raise MediaStorageError(message)
        return f"https://storage.test/{key}?expires={int(ttl.total_seconds())}"

    async def delete_prefix(self, prefix: str) -> int:
        alvos = [k for k in self.objetos if k.startswith(prefix)]
        for k in alvos:
            del self.objetos[k]
        return len(alvos)

    def listar(self, prefix: str) -> list[str]:
        return sorted(k for k in self.objetos if k.startswith(prefix))


def test_o_fake_satisfaz_a_porta() -> None:
    """De novo, a anotação é a asserção — e quem a verifica é o `mypy`."""
    porta: MediaStorage = FakeMediaStorage()

    assert porta is not None


async def test_listagem_por_prefixo_devolve_os_trechos_na_ordem() -> None:
    """Critério de aceite do card, agora sobre a porta.

    Os trechos são gravados **fora de ordem** de propósito: o que ordena é a
    chave, não a sequência de escrita — e, em produção, dois trechos podem ficar
    prontos no mesmo milissegundo.
    """
    storage = FakeMediaStorage()
    for i in (3, 0, 11, 1, 2, 10):
        chave = reply_chunk_key(STUDENT, SESSION, TURN, i, "aac")
        await storage.put(chave, b"\x00\x00", "audio/aac")

    listadas = storage.listar(reply_prefix(STUDENT, SESSION, TURN))

    assert listadas == [
        reply_chunk_key(STUDENT, SESSION, TURN, i, "aac") for i in (0, 1, 2, 3, 10, 11)
    ]


async def test_url_assinada_carrega_o_ttl_pedido() -> None:
    storage = FakeMediaStorage()
    chave = reply_chunk_key(STUDENT, SESSION, TURN, 0, "aac")
    await storage.put(chave, b"\x00\x00", "audio/aac")

    url = await storage.presigned_get_url(chave, timedelta(minutes=5))

    assert chave in url
    assert "expires=300" in url


async def test_delete_prefix_leva_tudo_do_aluno_e_diz_quantos() -> None:
    """O que o delete de conta (CARD-017) vai chamar — aqui só a porta."""
    storage = FakeMediaStorage()
    for i in range(4):
        await storage.put(
            reply_chunk_key(STUDENT, SESSION, TURN, i, "aac"), b"\x00\x00", "audio/aac"
        )
    outro_aluno = UUID("99999999-9999-9999-9999-999999999999")
    await storage.put(f"{outro_aluno}/x/y/input.m4a", b"\x00\x00", "audio/mp4")

    removidos = await storage.delete_prefix(student_prefix(STUDENT))

    assert removidos == 4
    assert storage.listar("") == [f"{outro_aluno}/x/y/input.m4a"]


async def test_falha_do_storage_e_capturavel_por_quem_orquestra() -> None:
    storage: MediaStorage = FakeMediaStorage()

    with pytest.raises(MediaStorageError):
        await storage.presigned_get_url("nao/existe.aac", timedelta(minutes=1))
