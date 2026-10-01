"""As três regras de retenção do bucket (ADR-0024, item 4).

**Por que é código de setup e não uma linha no `docker-compose.yml`.** Os TTLs
moram em `Settings` (o ADR-0024 os fixou como configuração, não como constante),
e o compose não lê `Settings` — duplicá-los ali criaria duas fontes de verdade
para a única política do projeto que é obrigação legal (LGPD), com a divergência
aparecendo só quando alguém fosse auditar.

**Por que filtro por tag e não por prefixo.** Ver `domain/media_keys.py`: o
esquema de chaves do ADR-0024 começa pelo `student_id`, então não existe prefixo
comum que selecione "todos os inputs". O lifecycle do S3 filtra por prefixo ou
tag; sobra a tag, aplicada pelo adapter a cada `put`.

**MinIO não é S3** (ressalva do ADR-0006, e o ADR-0024 acrescentou que agora há
três regras para divergir): esta configuração é verificada contra o MinIO. No
provedor real ela precisa ser reconferida — em particular o momento em que a
expiração roda, que na AWS é assíncrono e pode levar até 48 h além do prazo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from botocore.exceptions import ClientError

from voicecoach.domain.media_keys import RetentionClass

if TYPE_CHECKING:
    from voicecoach.config import Settings


def build_rules(settings: Settings) -> list[dict[str, Any]]:
    """Traduz os TTLs da configuração nas regras do bucket.

    Separada de quem aplica para poder ser testada sem storage nenhum, e para
    que o teste de integração compare o que foi **pedido** com o que o bucket
    devolve — em vez de comparar a configuração consigo mesma.
    """
    return [
        {
            "ID": classe.value,
            "Status": "Enabled",
            "Filter": {"Tag": {"Key": "retention", "Value": classe.value}},
            # O S3 expira em DIAS inteiros; não há granularidade menor. Um TTL de
            # menos de um dia arredondaria para zero e a regra seria recusada —
            # por isso o mínimo de 1.
            "Expiration": {"Days": max(1, ttl.days)},
        }
        for classe, ttl in (
            (RetentionClass.INPUT, settings.retention_input),
            (RetentionClass.REPLY_CHUNK, settings.retention_reply_chunk),
            (RetentionClass.REPLY_FULL, settings.retention_reply_full),
        )
    ]


def apply_lifecycle(client: Any, bucket: str, settings: Settings) -> None:  # noqa: ANN401
    """Grava as três regras no bucket. Idempotente: substitui a configuração.

    Síncrona de propósito — roda no setup do ambiente, não no caminho de um
    turn, e um `async` aqui só serviria para contaminar quem a chama.
    """
    client.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={"Rules": build_rules(settings)},
    )


class LifecycleNotAppliedError(RuntimeError):
    """O bucket não tem as regras de retenção que a configuração pede.

    Existe por causa do CARD-017: as regras foram escritas e testadas no
    CARD-008, mas nada as aplicava — o bucket real não tinha lifecycle
    nenhum, e a voz dos alunos ficava guardada para sempre, em silêncio. Quem
    recebe isto (o boot do worker) **não sobe**: gravar áudio sem prazo de
    validade é pior que não gravar.
    """


def _assinatura(regras: list[dict[str, Any]]) -> set[tuple[str, str, int]]:
    """O que importa comparar: id, tag do filtro e dias. O resto o storage
    pode devolver normalizado (ordem, campos extras) sem que seja divergência.
    """
    return {
        (
            r.get("ID", ""),
            r.get("Filter", {}).get("Tag", {}).get("Value", ""),
            int(r.get("Expiration", {}).get("Days", -1)),
        )
        for r in regras
        if r.get("Status") == "Enabled"
    }


def ensure_lifecycle(client: Any, bucket: str, settings: Settings) -> None:  # noqa: ANN401
    """Levanta ``LifecycleNotAppliedError`` se o bucket não bate com a config.

    "Não bate" inclui TTL alterado em ``Settings`` sem reaplicar: a política
    que vale é a que está no bucket, e uma config que diz outra coisa é uma
    promessa falsa na política de privacidade.
    """
    try:
        lidas = client.get_bucket_lifecycle_configuration(Bucket=bucket)["Rules"]
    except ClientError as exc:
        codigo = exc.response.get("Error", {}).get("Code", "")
        if codigo != "NoSuchLifecycleConfiguration":
            raise
        lidas = []
    if _assinatura(lidas) != _assinatura(build_rules(settings)):
        message = (
            f"o bucket {bucket!r} não tem as regras de retenção da configuração "
            "(ADR-0024). Rode, de backend/:  uv run voicecoach-storage-setup"
        )
        raise LifecycleNotAppliedError(message)
