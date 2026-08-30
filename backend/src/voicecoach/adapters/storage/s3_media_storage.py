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
from concurrent.futures import ThreadPoolExecutor
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

    def __init__(
        self,
        client: Any,  # noqa: ANN401 — ver abaixo
        bucket: str,
        signer: Any = None,  # noqa: ANN401 — mesmo motivo do `client`
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        # `Any` é deliberado e não preguiça: o `boto3` monta os clientes em
        # RUNTIME a partir de arquivos JSON de serviço, então `client("s3")` não
        # tem um tipo estático que se possa nomear sem o pacote `types-boto3`.
        # A alternativa (mais uma dependência só para tipar um atributo privado)
        # não paga o próprio custo — o contrato que importa é o da porta, e esse
        # está tipado.
        self._client = client
        self._bucket = bucket
        # O cliente que ASSINA. Quase sempre é o mesmo que fala com o storage;
        # ele se separa quando o host que o servidor usa não é o host que o
        # aparelho do aluno alcança (ADR-0045). Default `None` = o mesmo, para
        # que nada mude onde a separação não existe.
        self._signer = signer if signer is not None else client
        # **O bulkhead** (ADR-0053, decisão 4). `None` = o pool default do event
        # loop, que é o que os testes usam e o que este adapter fazia antes.
        # Em produção quem passa um pool próprio é `create_media_storage`, e
        # quem o FECHA é o `close()` aqui embaixo, chamado pela composition root.
        self._executor = executor

    def close(self) -> None:
        """Encerra o pool próprio, se houver. Chamado pela composition root.

        **Um executor sem `shutdown()` mantém threads vivas e o processo não
        termina** — e o sintoma não é uma falha, é a suíte de testes demorando
        para encerrar. Por isso o dono é explícito: `api/lifespan.py` na API e
        `worker/main.py:shutdown` no worker, ao lado do `engine.dispose()` que
        já existia.

        `wait=False`: no desligamento não se espera um upload pendurado nos
        segundos do timeout. `cancel_futures=True` descarta o que ainda nem
        começou. Idempotente — chamar duas vezes não levanta.
        """
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)

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
            self._signer.generate_presigned_url,
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
            return await loop.run_in_executor(self._executor, fn)
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
            return await loop.run_in_executor(
                self._executor, functools.partial(fn, **kwargs)
            )
        except (ClientError, BotoCoreError) as exc:
            message = f"storage falhou em {getattr(fn, '__name__', fn)}: {exc}"
            raise MediaStorageError(message) from exc


def create_media_storage(settings: Settings) -> S3MediaStorage:
    """Monta o adapter a partir da configuração — chamado no composition root.

    `signature_version="s3v4"` é explícito porque o default varia com a região e
    o MinIO só aceita v4: deixar implícito é como se descobre, em produção, que
    a URL assinada localmente não vale no provedor real.

    **Podem sair DOIS clientes** (ADR-0045). Um fala com o storage; o outro só
    assina, com o host que o aparelho do aluno alcança. Assinar é HMAC local —
    o segundo cliente nunca abre conexão nenhuma —, e o objeto é o mesmo para os
    dois porque quem o identifica é `(bucket, key)`, não o endpoint: `endpoint`
    é para onde a requisição VAI, e a URL assinada descreve a requisição que o
    **leitor** fará.
    """

    # **Os três parâmetros de resiliência andam juntos, ou não andam**
    # (ADR-0053, decisão 3). Configurar timeout e deixar `retries` no default é
    # a armadilha do card: medido contra um socket que aceita e nunca responde,
    # `read_timeout=2` sozinho dá **21 s** de tempo de parede, não 2 s.
    #
    # A lei, medida nos dois modos: **conexões que saem = `max_attempts` + 1**,
    # e cada tentativa custa `read_timeout` + ~1,2 s no `put_object` (o
    # `Expect: 100-continue` do upload). O `urllib3` está fora disto — o
    # botocore o chama com `Retry(False)`, então quem retenta é só o botocore.
    #
    # `mode="standard"` e não `legacy`: o legacy tem outra lista de erros
    # retentáveis e um teto próprio de 5 tentativas. Escolha, não default.
    resiliencia = Config(
        signature_version="s3v4",
        connect_timeout=settings.s3_connect_timeout,
        read_timeout=settings.s3_read_timeout,
        retries={"max_attempts": settings.s3_max_attempts, "mode": "standard"},
    )

    def montar(endpoint: str) -> Any:  # noqa: ANN401 — o boto3 não é tipado
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=resiliencia,
        )

    client = montar(settings.s3_endpoint_url)
    assinatura = settings.s3_signing_endpoint_url
    signer = client if assinatura == settings.s3_endpoint_url else montar(assinatura)
    # **O pool próprio nasce aqui e é fechado por quem chamou** — `close()`.
    # `thread_name_prefix` não é cosmético: num `py-spy` ou num dump de threads
    # é o que distingue "travado subindo áudio" de "travado transcrevendo".
    executor = ThreadPoolExecutor(
        max_workers=settings.s3_executor_workers,
        thread_name_prefix="voicecoach-storage",
    )
    return S3MediaStorage(client, settings.s3_bucket, signer, executor)
