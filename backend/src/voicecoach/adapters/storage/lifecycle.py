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
