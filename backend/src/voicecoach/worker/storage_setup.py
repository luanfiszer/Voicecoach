"""``uv run voicecoach-storage-setup`` — aplica as regras de retenção ao bucket.

Comando de OPERADOR, como o ``createbuckets`` do compose (CARD-008): criar o
bucket e dizer quanto tempo cada áudio vive é administração, não algo que o
caminho de um turn faça. Mora no ``worker`` porque é ele quem grava áudio e
quem se recusa a subir sem as regras (CARD-017) — a mensagem de erro do boot
aponta para este comando.

Idempotente: substitui a configuração inteira, então rodar de novo depois de
mudar um TTL em ``Settings`` é exatamente como se atualiza a política.
"""

from __future__ import annotations

import logging

from voicecoach.adapters.storage.lifecycle import apply_lifecycle, ensure_lifecycle
from voicecoach.adapters.storage.s3_media_storage import create_s3_admin_client
from voicecoach.config import get_settings

logger = logging.getLogger(__name__)


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    client = create_s3_admin_client(settings)
    apply_lifecycle(client, settings.s3_bucket, settings)
    # Lê de volta: o critério é o que o bucket DIZ que tem, não o que se pediu.
    ensure_lifecycle(client, settings.s3_bucket, settings)
    logger.info(
        "retenção aplicada ao bucket %s: input=%s, trecho=%s, inteiro=%s",
        settings.s3_bucket,
        settings.retention_input,
        settings.retention_reply_chunk,
        settings.retention_reply_full,
    )
