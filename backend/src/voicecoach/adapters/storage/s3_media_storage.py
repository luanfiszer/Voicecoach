"""Adapter S3 da porta `MediaStorage` — MinIO local, S3 real por configuração.

**Por que `boto3` num app async, e por que em executor.** O `boto3` é síncrono:
ele bloqueia a thread durante o IO de rede. Dentro de uma corrotina isso é pior
do que parece, e o argumento do adapter de STT **não transfere**: lá o
`run_in_executor` existe porque o CTranslate2 é CPU-bound e solta o GIL em código
nativo. Aqui o problema é outro — `await` é cooperativo, e uma chamada síncrona
nunca coopera. O GIL até é solto pelo IO, mas a **corrotina** não cede o
controle, e o event loop inteiro para.

Medido nesta máquina, contra o MinIO do compose, com 5 objetos de 2 MB e um
heartbeat que deveria acordar a cada 10 ms:

    put_object na corrotina   upload 122 ms | heartbeat:  0 voltas | NUNCA RODOU
    put_object em executor    upload  93 ms | heartbeat: 10 voltas | pior 1,0 ms

Durante os 122 ms, nenhuma outra corrotina do worker existiu. Num worker que
processa turns em cascata, é exatamente o intervalo em que o próximo trecho de
fala deveria estar sendo sintetizado.

**Por que não `aioboto3`.** Ele faz IO async de verdade e dispensaria a thread.
O custo é uma dependência a mais que arrasta o `aiobotocore`, que por sua vez
**fixa a versão do `botocore`** — o conflito de resolução mais comum desse
ecossistema. Para 3 a 6 uploads por turn, com o executor entregando 1 ms de
atraso máximo, a thread é mais barata que o acoplamento de versões.
**Gatilho para reavaliar:** upload deixar de ser some-and-forget (ex.: subir o
áudio inteiro em paralelo com dezenas de turns simultâneos), ou o `aiobotocore`
passar a acompanhar o `botocore` sem defasagem.
"""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from voicecoach.application.ports.media_storage import MediaStorageError
from voicecoach.domain.media_keys import retention_class

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import timedelta

    from voicecoach.config import Settings

# O S3 lista no máximo 1.000 chaves por página e apaga no máximo 1.000 por
# chamada. O `delete_prefix` respeita os dois limites paginando — um prefixo de
# aluno com anos de uso passa disso com folga.
_DELETE_BATCH = 1000


class S3MediaStorage:
    """Implementa `MediaStorage` sobre a API S3.

    Satisfaz a porta **estruturalmente**: não herda de `Protocol` nenhum, só
    tem os três métodos com a assinatura certa. Quem verifica isso é o `mypy`,
    e a verificação está escrita como uma anotação no teste da porta.
    """

    def __init__(self, client: Any, bucket: str) -> None:  # noqa: ANN401 — ver abaixo
        # `Any` é deliberado e não preguiça: o `boto3` monta os clientes em
        # RUNTIME a partir de arquivos JSON de serviço, então `client("s3")` não
        # tem um tipo estático que se possa nomear sem o pacote `types-boto3`.
        # A alternativa (mais uma dependência só para tipar um atributo privado)
        # não paga o próprio custo — o contrato que importa é o da porta, e esse
        # está tipado.
        self._client = client
        self._bucket = bucket

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """Grava o objeto **já com a tag de retenção** derivada da chave.

        A tag não é metadado decorativo: é o que faz o lifecycle do bucket saber
        se este objeto vive 1, 7 ou 90 dias (ADR-0024, item 4). Ela é derivada
        aqui, e não recebida por parâmetro, porque esquecer de passá-la não
        daria erro nenhum — só faria o áudio de voz de um aluno viver para
        sempre. Deriva-se do contrato de chave, que já carrega a informação.
        """
        await self._in_executor(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            Tagging=f"retention={retention_class(key).value}",
        )

    async def get(self, key: str) -> bytes:
        """Lê o objeto inteiro — o áudio do aluno, para o worker mandar ao STT.

        O `get_object` devolve um dicionário cujo `Body` é um stream **síncrono**
        do botocore. O `.read()` dele também bloqueia, então ele acontece dentro
        do executor, junto da chamada: lê-lo do lado de fora traria de volta
        exatamente o congelamento de event loop que o docstring do módulo mede
        em 122 ms.
        """

        def ler() -> bytes:
            resposta = self._client.get_object(Bucket=self._bucket, Key=key)
            corpo: bytes = resposta["Body"].read()
            return corpo

        # Variável intermediária anotada em vez de `return await ...`: o
        # `_in_executor_fn` devolve `Any` (o `boto3` não é tipado), e o
        # `warn_return_any` do mypy strict reprova devolver `Any` de uma função
        # que promete `bytes`. A anotação é onde o `Any` para.
        conteudo: bytes = await self._in_executor_fn(ler)
        return conteudo

    async def presigned_get_url(self, key: str, ttl: timedelta) -> str:
        """Assinar é HMAC local — mas continua no executor. Ver o docstring.

        Não há rede aqui: o `generate_presigned_url` monta a URL e a assina com
        a chave secreta, em microssegundos. Passa pelo executor mesmo assim
        porque a diferença é irrelevante e a uniformidade evita a pergunta "este
        método bloqueia?" toda vez que alguém ler o arquivo.
        """
        url = await self._in_executor(
            self._client.generate_presigned_url,
            ClientMethod="get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=int(ttl.total_seconds()),
        )
        return str(url)

    async def delete_prefix(self, prefix: str) -> int:
        """Apaga tudo sob o prefixo, paginando, e devolve quantos saíram."""
        removidos = 0
        continuation: str | None = None

        while True:
            listagem = await self._in_executor(
                self._client.list_objects_v2,
                Bucket=self._bucket,
                Prefix=prefix,
                MaxKeys=_DELETE_BATCH,
                **({"ContinuationToken": continuation} if continuation else {}),
            )
            chaves = [{"Key": o["Key"]} for o in listagem.get("Contents", [])]
            if chaves:
                await self._in_executor(
                    self._client.delete_objects,
                    Bucket=self._bucket,
                    Delete={"Objects": chaves, "Quiet": True},
                )
                removidos += len(chaves)

            if not listagem.get("IsTruncated"):
                return removidos
            continuation = listagem.get("NextContinuationToken")

    async def _in_executor_fn(self, fn: Callable[[], Any]) -> Any:  # noqa: ANN401
        """Igual ao `_in_executor`, para quem já vem com os argumentos presos.

        Existe porque o `get` precisa rodar **duas** chamadas do SDK na mesma
        thread (`get_object` e o `.read()` do corpo), e `_in_executor` só sabe
        despachar uma função do cliente com kwargs.
        """
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, fn)
        except (ClientError, BotoCoreError) as exc:
            message = f"storage falhou em {getattr(fn, '__name__', fn)}: {exc}"
            raise MediaStorageError(message) from exc

    async def _in_executor(self, fn: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        """Roda a chamada síncrona numa thread e traduz a falha do SDK.

        `functools.partial` porque `run_in_executor` só aceita argumentos
        posicionais — é o idioma Python para "aplicação parcial", o equivalente
        de capturar os argumentos numa lambda em C#.

        A tradução de erro é o que impede o `botocore` de vazar para
        `application`: quem captura é o caso de uso, e ele conhece
        `MediaStorageError`, não `ClientError`.
        """
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, functools.partial(fn, **kwargs))
        except (ClientError, BotoCoreError) as exc:
            message = f"storage falhou em {getattr(fn, '__name__', fn)}: {exc}"
            raise MediaStorageError(message) from exc


def create_media_storage(settings: Settings) -> S3MediaStorage:
    """Monta o adapter a partir da configuração — chamado no composition root.

    `signature_version="s3v4"` é explícito porque o default varia com a região e
    o MinIO só aceita v4: deixar implícito é como se descobre, em produção, que
    a URL assinada localmente não vale no provedor real.
    """
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )
    return S3MediaStorage(client, settings.s3_bucket)
