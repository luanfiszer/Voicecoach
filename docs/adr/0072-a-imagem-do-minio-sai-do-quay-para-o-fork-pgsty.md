# ADR-0072 — A imagem do MinIO sai do quay.io para o fork `pgsty/minio`

- **Status:** aceito · **substitui** o [ADR-0062](0062-a-imagem-do-minio-migra-do-docker-hub-para-o-quay-io.md)
- **Data:** 2026-10-01
- **Relacionado:** ADR-0010 (custo zero, tudo local), ADR-0018 (testcontainers com tag fixada), ADR-0034 (storage), CARD-057, CARD-061
- **Critérios de obrigatoriedade:** **1 — troca de dependência externa** (origem e mantenedor da imagem do storage) e **5 — difícil de reverter** (o volume de dados do desenvolvedor passa a ser escrito por outro binário).

## Contexto

Em 2026-10-01 o CI do PR #63 reprovou no passo "Puxa a imagem do MinIO" com
`unauthorized: access to the requested resource is not authorized`.
Verificado: `quay.io/minio/minio` responde **401 até na API pública de
metadados** (`/api/v1/repository/minio/minio`) — o repositório deixou de ser
público. É o segundo canal que a MinIO fecha em um mês (o Docker Hub foi o
primeiro, ADR-0062). A máquina do desenvolvedor só funcionava por cache local.
O passo de `pull` explícito que o ADR-0062 pôs no CI fez exatamente o que
prometia: o erro saiu nomeado, não como 21 falhas de fixture.

## Decisão

`pgsty/minio:RELEASE.2026-08-04T00-00-00Z`, no Docker Hub público, nos três
lugares que já andavam juntos (serviços `minio` e `createbuckets` do compose,
`MINIO_IMAGE` do teste — o teste de igualdade do ADR-0062 continua valendo).

Verificado antes de decidir: imagem multi-arquitetura (`amd64` para o CI,
`arm64` para o Mac), traz `mc` e `sh` (o healthcheck e o `createbuckets`
dependem dos dois), entrypoint compatível com o da imagem oficial
(`server /data` funciona sem mudança), e subiu sobre o **volume existente**
lendo os 99 objetos gravados pela imagem anterior. `test_s3_media_storage.py`:
21 verdes.

## Alternativas consideradas

### A — `cgr.dev/chainguard/minio` (Chainguard)
- **Prós:** fornecedor comercial estabelecido, rebuild diário, imagem mínima.
- **Por que foi rejeitada:** o plano gratuito só publica `latest`; fixar
  versão exige digest, e digests antigos do plano gratuito não têm garantia
  de permanecer disponíveis — o mesmo modo de falha que este ADR corrige.
  Também roda como usuário `65532`, e o volume existente foi escrito como
  root. **É o plano B** se o `pgsty` sumir.

### B — Trocar o MinIO por outro S3 local (Garage, SeaweedFS, LocalStack)
- **Prós:** sair de vez de um fornecedor que vem fechando a distribuição.
- **Por que foi rejeitada (por ora):** muda o servidor, não só a origem do
  binário — exigiria revalidar presigned URL, tags de retenção (ADR-0034) e o
  lifecycle. Desproporcional para um problema de distribuição.
  **Gatilho para reabrir:** o fork `pgsty` parar de publicar ou divergir do
  protocolo que o `boto3` usa.

### C — Compilar a imagem a partir do código-fonte (AGPL) no próprio repositório
- **Por que foi rejeitada:** um Dockerfile e um build Go a manter, para
  repor algo que um fork já publica.

## Consequências

- Dependência de um mantenedor comunitário (Pigsty) — risco aceito e nomeado;
  o passo de `pull` no CI continua sendo o detector.
- A versão subiu de `2025-09-07` para `2026-08-04` (o fork não republica a tag
  antiga). Formato de disco compatível, verificado sobre o volume real.
- **Decisão autônoma (loop, 2026-10-01): `pgsty` em vez de Chainguard →
  PENDENTE DE REVISÃO HUMANA.**
