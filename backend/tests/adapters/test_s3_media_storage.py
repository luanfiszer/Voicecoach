"""Adapter S3 contra um MinIO real, descartável (ADR-0018).

**Por que `DockerContainer` genérico e não `testcontainers.community.minio`.**
O helper pronto faz `from minio import Minio` — um SEGUNDO SDK de S3, que o
produto não usa. O que estes testes precisam provar é sobre o **boto3**: que a
URL que ele assina é aceita, que o objeto é ilegal sem assinatura, que a
paginação do `delete_prefix` funciona. Um teste que exercitasse outro cliente
provaria coisa diferente da que está em produção. (O módulo `testcontainers.minio`
antigo, além disso, está depreciado.)

**MinIO não é S3** (nota herdada do ADR-0006 e reforçada no ADR-0024): estes
testes cobrem o comportamento do MinIO. Passar aqui **não** é evidência sobre
AWS S3, R2 ou B2 — em particular quanto a lifecycle e IAM, onde as
implementações divergem mais.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import boto3
import httpx
import pytest
from botocore.config import Config as BotoConfig
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy

from voicecoach.adapters.storage.lifecycle import apply_lifecycle
from voicecoach.adapters.storage.s3_media_storage import S3MediaStorage
from voicecoach.application.ports.media_storage import (
    MediaStorage,
    MediaStorageError,
)
from voicecoach.config import Settings
from voicecoach.domain.media_keys import (
    RetentionClass,
    input_key,
    reply_chunk_key,
    reply_full_key,
    reply_prefix,
    student_prefix,
)

# Mesma imagem e mesma tag do `docker-compose.yml`: o teste e o ambiente de
# desenvolvimento não podem divergir de versão sem que alguém decida isso.
MINIO_IMAGE = "minio/minio:RELEASE.2025-09-07T16-13-09Z"
ACCESS_KEY = "voicecoach"
SECRET_KEY = "voicecoach-dev-secret"
BUCKET = "test-media"

STUDENT = UUID("11111111-1111-1111-1111-111111111111")
SESSION = UUID("22222222-2222-2222-2222-222222222222")
TURN = UUID("33333333-3333-3333-3333-333333333333")


@pytest.fixture(scope="session")
def minio_endpoint() -> Iterator[str]:
    """Um MinIO descartável por execução da suíte."""
    # `waiting_for` com o probe HTTP do próprio MinIO, e não espera por linha de
    # log: mensagem de log é contrato acidental — muda de release em release e o
    # teste quebra por um motivo que não tem a ver com o que ele testa.
    container = (
        DockerContainer(MINIO_IMAGE)
        .with_command("server /data --address :9000")
        .with_env("MINIO_ROOT_USER", ACCESS_KEY)
        .with_env("MINIO_ROOT_PASSWORD", SECRET_KEY)
        .with_exposed_ports(9000)
        .waiting_for(HttpWaitStrategy(9000, "/minio/health/live"))
    )
    with container:
        host = container.get_container_host_ip()
        porta = container.get_exposed_port(9000)
        yield f"http://{host}:{porta}"


@pytest.fixture(scope="session")
def s3_client(minio_endpoint: str) -> Any:
    client = boto3.client(
        "s3",
        endpoint_url=minio_endpoint,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name="us-east-1",
        config=BotoConfig(signature_version="s3v4"),
    )
    client.create_bucket(Bucket=BUCKET)
    return client


@pytest.fixture
def storage(s3_client: Any) -> S3MediaStorage:
    return S3MediaStorage(s3_client, BUCKET)


async def test_o_adapter_satisfaz_a_porta(storage: S3MediaStorage) -> None:
    """A anotação com o tipo da PORTA é o que faz o mypy verificar o adapter."""
    porta: MediaStorage = storage

    assert porta is not None


async def test_grava_e_a_url_assinada_baixa_o_mesmo_conteudo(
    storage: S3MediaStorage,
) -> None:
    """Critério de aceite: o trecho existe e a URL assinada **toca**."""
    chave = reply_chunk_key(STUDENT, SESSION, TURN, 0, "aac")
    conteudo = b"\xff\xf1audio-falso"

    await storage.put(chave, conteudo, "audio/aac")
    url = await storage.presigned_get_url(chave, timedelta(minutes=5))

    async with httpx.AsyncClient() as client:
        resposta = await client.get(url)

    assert resposta.status_code == 200
    assert resposta.content == conteudo
    assert resposta.headers["content-type"] == "audio/aac"


async def test_get_devolve_os_bytes_para_o_worker_mandar_ao_stt(
    storage: S3MediaStorage,
) -> None:
    """O método que o CARD-009 acrescentou à porta (ADR-0034 + nota do canal).

    O worker não é intermediário do aluno: ele é o destinatário dos bytes. Uma
    URL assinada só o faria baixar de si mesmo por HTTP.
    """
    chave = input_key(STUDENT, SESSION, TURN, "aac")
    conteudo = b"\xff\xf1audio-do-aluno"
    await storage.put(chave, conteudo, "audio/aac")

    assert await storage.get(chave) == conteudo


async def test_get_de_chave_inexistente_vira_erro_da_porta(
    storage: S3MediaStorage,
) -> None:
    """Não há `None`: o input de um turn que existe no banco tem de existir.

    Ausência aqui não é caso esperado — é o storage tendo perdido o objeto, e o
    caso de uso trata isso como falha de infraestrutura.
    """
    with pytest.raises(MediaStorageError):
        await storage.get(input_key(STUDENT, SESSION, uuid4(), "aac"))


async def test_objeto_nao_e_legivel_sem_assinatura(
    storage: S3MediaStorage, minio_endpoint: str
) -> None:
    """Critério de aceite: bucket privado, acesso direto negado."""
    chave = reply_chunk_key(STUDENT, SESSION, TURN, 1, "aac")
    await storage.put(chave, b"segredo", "audio/aac")

    async with httpx.AsyncClient() as client:
        resposta = await client.get(f"{minio_endpoint}/{BUCKET}/{chave}")

    assert resposta.status_code == 403


async def test_url_assinada_expira(storage: S3MediaStorage) -> None:
    """Critério de aceite: a URL morre depois do TTL.

    **Nota honesta sobre flakiness:** este é o único teste da suíte que depende
    de tempo de parede. Ele dorme 2 s para um TTL de 1 s — a folga de 100% existe
    porque a expiração é avaliada pelo relógio do MinIO, não pelo nosso, e num CI
    carregado os dois podem estar a centenas de milissegundos de distância. Se um
    dia ele piscar, a correção é aumentar a folga, **nunca** remover o teste: o
    modo de falha que ele cobre (URL que nunca expira) é o achado F6 do
    diagnóstico, e é o motivo de o ADR-0006 existir.
    """
    chave = reply_chunk_key(STUDENT, SESSION, TURN, 2, "aac")
    await storage.put(chave, b"efemero", "audio/aac")

    url = await storage.presigned_get_url(chave, timedelta(seconds=1))
    async with httpx.AsyncClient() as client:
        antes = await client.get(url)
        await asyncio.sleep(2)
        depois = await client.get(url)

    assert antes.status_code == 200
    assert depois.status_code == 403


async def test_listagem_por_prefixo_devolve_os_trechos_na_ordem_de_playback(
    storage: S3MediaStorage, s3_client: Any
) -> None:
    """Critério de aceite, agora contra o storage de verdade.

    Os trechos são gravados **fora de ordem** e passam de 9 de propósito: é no
    décimo que o zero-padding do ADR-0024 começa a importar.
    """
    prefixo = reply_prefix(STUDENT, SESSION, TURN)
    for i in (5, 0, 11, 3, 10, 1, 2, 4, 6, 7, 8, 9):
        await storage.put(
            reply_chunk_key(STUDENT, SESSION, TURN, i, "aac"), b"\x00", "audio/aac"
        )
    await storage.put(
        reply_full_key(STUDENT, SESSION, TURN, "aac"), b"\x00", "audio/aac"
    )

    resposta = s3_client.list_objects_v2(Bucket=BUCKET, Prefix=prefixo)
    chaves = [o["Key"] for o in resposta["Contents"]]

    esperado = [reply_chunk_key(STUDENT, SESSION, TURN, i, "aac") for i in range(12)]
    assert chaves[: len(esperado)] == esperado
    # E o `full` não se intromete no meio da sequência:
    assert chaves[-1].endswith("full.aac")


async def test_delete_prefix_remove_tudo_do_aluno_e_conta(
    storage: S3MediaStorage,
) -> None:
    outro = UUID("99999999-9999-9999-9999-999999999999")
    await storage.put(f"{outro}/s/t/input.m4a", b"\x00", "audio/mp4")
    for i in range(3):
        await storage.put(
            reply_chunk_key(STUDENT, SESSION, TURN, i, "aac"), b"\x00", "audio/aac"
        )

    removidos = await storage.delete_prefix(student_prefix(STUDENT))
    restante = await storage.presigned_get_url(
        f"{outro}/s/t/input.m4a", timedelta(minutes=1)
    )

    assert removidos >= 3
    assert restante  # o prefixo do outro aluno sobreviveu
    assert await storage.delete_prefix(student_prefix(STUDENT)) == 0


async def test_falha_do_sdk_vira_erro_da_porta(s3_client: Any) -> None:
    """`ClientError` do botocore não pode vazar para quem orquestra."""
    storage = S3MediaStorage(s3_client, "bucket-que-nao-existe")

    with pytest.raises(MediaStorageError):
        await storage.put(
            reply_chunk_key(STUDENT, SESSION, TURN, 0, "aac"), b"\x00", "audio/aac"
        )


async def test_o_upload_nao_bloqueia_o_event_loop(storage: S3MediaStorage) -> None:
    """A prova executável da decisão "executor, não chamada direta".

    Um heartbeat tenta acordar a cada 10 ms enquanto o upload corre. Com
    `put_object` chamado direto de dentro da corrotina, ele **não roda nenhuma
    vez** (medido: 122 ms de upload, 0 voltas). Com o executor, ele roda.

    É a diferença entre "o GIL é solto" e "a corrotina cede o controle": `await`
    é cooperativo, e uma chamada síncrona nunca coopera.
    """
    voltas = 0
    parar = asyncio.Event()

    async def heartbeat() -> None:
        nonlocal voltas
        while not parar.is_set():
            await asyncio.sleep(0.01)
            voltas += 1

    batedor = asyncio.create_task(heartbeat())
    inicio = time.perf_counter()
    # 4 MB: grande o bastante para o upload durar mais que algumas batidas.
    await storage.put(
        reply_full_key(STUDENT, SESSION, TURN, "aac"),
        b"\x00" * 4 * 1024 * 1024,
        "audio/aac",
    )
    decorrido = time.perf_counter() - inicio
    parar.set()
    await batedor

    assert decorrido > 0.02, "upload rápido demais para o teste significar algo"
    assert voltas > 0, "o event loop ficou bloqueado durante o upload"


# -- retenção ----------------------------------------------------------------


async def test_put_marca_o_objeto_com_a_classe_de_retencao(
    storage: S3MediaStorage, s3_client: Any
) -> None:
    """Sem a tag, o lifecycle não alcança o objeto e ele vive para sempre."""
    chunk = reply_chunk_key(STUDENT, SESSION, TURN, 0, "aac")
    full = reply_full_key(STUDENT, SESSION, TURN, "aac")
    entrada = input_key(STUDENT, SESSION, TURN, "m4a")
    for chave in (chunk, full, entrada):
        await storage.put(chave, b"\x00", "audio/aac")

    def tag(chave: str) -> str:
        resposta = s3_client.get_object_tagging(Bucket=BUCKET, Key=chave)
        return str(resposta["TagSet"][0]["Value"])

    assert tag(chunk) == RetentionClass.REPLY_CHUNK.value
    assert tag(full) == RetentionClass.REPLY_FULL.value
    assert tag(entrada) == RetentionClass.INPUT.value


async def test_chave_fora_do_esquema_nao_e_gravada_sem_retencao(
    storage: S3MediaStorage,
) -> None:
    """Melhor falhar na gravação que guardar voz sem prazo de validade."""
    with pytest.raises(ValueError, match="viveria para sempre"):
        await storage.put("chave/qualquer.bin", b"\x00", "audio/aac")


def test_as_tres_regras_de_lifecycle_existem_com_os_ttls_da_config(
    s3_client: Any,
) -> None:
    """Critério de aceite: as três regras, lidas de volta do storage.

    Compara o que o bucket devolve com o que a **configuração** diz — não com
    números escritos no teste, que só provariam que alguém copiou duas vezes.
    """
    settings = Settings(anthropic_api_key="x", _env_file=None)  # type: ignore[call-arg]

    apply_lifecycle(s3_client, BUCKET, settings)
    lidas = s3_client.get_bucket_lifecycle_configuration(Bucket=BUCKET)["Rules"]

    por_id = {r["ID"]: r for r in lidas}
    assert set(por_id) == {c.value for c in RetentionClass}
    assert por_id["input"]["Expiration"]["Days"] == settings.retention_input.days
    assert (
        por_id["reply-chunk"]["Expiration"]["Days"]
        == settings.retention_reply_chunk.days
    )
    assert (
        por_id["reply-full"]["Expiration"]["Days"] == settings.retention_reply_full.days
    )
    assert all(
        r["Filter"]["Tag"] == {"Key": "retention", "Value": r["ID"]} for r in lidas
    )
