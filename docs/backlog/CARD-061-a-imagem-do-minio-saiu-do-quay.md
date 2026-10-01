# CARD-061 — A imagem do MinIO saiu do quay.io

- **ID:** CARD-061
- **Épico:** Infra local e CI
- **Esforço:** P
- **Status:** concluído (2026-10-01)
- **Dependências:** [ADR-0062](../adr/0062-a-imagem-do-minio-migra-do-docker-hub-para-o-quay-io.md) (substituído), [ADR-0072](../adr/0072-a-imagem-do-minio-sai-do-quay-para-o-fork-pgsty.md)

## Contexto

Nasceu na validação do loop autônomo (2026-10-01): o CI do PR #63 reprovou no
`docker compose pull minio createbuckets` com `unauthorized`. O
`quay.io/minio/minio` deixou de ser público — segunda vez que a MinIO fecha um
canal de distribuição (CARD-057 foi a primeira). Bloqueava o CI de todo PR.

## Critérios de aceite

- **Dado** um runner sem cache, **quando** o CI puxa a imagem, **então** o
  pull funciona sem credencial.
- **Dado** o volume de dados existente, **quando** a imagem nova sobe, **então**
  os objetos antigos continuam legíveis.

## Objetivo de aprendizado

Dependência de infraestrutura também é dependência: imagem de container tem
fornecedor, licença e canal de distribuição, e pode sumir sem mudança no
repositório. O passo de `pull` explícito no CI (ADR-0062) é o detector.

## Execução (2026-10-01)

- Evidência do problema: `curl https://quay.io/api/v1/repository/minio/minio`
  → `401 Requires authentication`; `docker pull` → `401 Unauthorized`.
- Candidatas medidas: `cgr.dev/chainguard/minio` e `pgsty/minio` (ambas com
  `mc` e `sh`). Escolhida `pgsty/minio:RELEASE.2026-08-04T00-00-00Z` —
  alternativas e porquê no [ADR-0072](../adr/0072-a-imagem-do-minio-sai-do-quay-para-o-fork-pgsty.md)
  (critérios **1** e **5**).
- Local: `docker compose up -d minio createbuckets` sobre o volume antigo →
  `mc ls --recursive` lista os 99 objetos anteriores;
  `pytest tests/adapters/test_s3_media_storage.py` → 21 passed.

### Decisão autônoma — PENDENTE DE REVISÃO HUMANA

> **Decisão autônoma (2026-10-01):** qual imagem substitui a do quay? →
> `pgsty/minio` com tag fixa → é a única candidata gratuita que permite fixar
> versão por tag; Chainguard fica como plano B (ADR-0072). → **PENDENTE DE
> REVISÃO HUMANA**.
