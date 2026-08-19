# ADR-0006 — Storage de mídia: S3-compatível (MinIO local) com URL assinada e expiração

- **Status:** **substituído por [ADR-0024](0024-midia-por-trecho-chave-url-assinada-e-retencao-assimetrica.md)** (2026-08-19)
- **Data:** 2026-08-17

> S3 como contrato, bucket privado, URL assinada de TTL curto e retenção
> explícita continuam valendo — o sucessor os herda. O que caiu foi *um objeto
> de áudio por turn*: com a cascata, a resposta vira N trechos, e chave, emissão
> de URL e retenção mudam com isso.

## Contexto

O diagnóstico (F6) apontou MP3s servidos publicamente, sem expiração e sem
limpeza — vazamento de conteúdo de usuário e disco crescendo sem limite. O
produto processa voz (dado pessoal, LGPD) e roda com infra local + free tier.
Áudios: input do aluno (efêmero por natureza) e resposta do professor
(reproduzível pelo histórico).

## Decisão

- **API S3 como contrato**, atrás da porta `MediaStorage`; **MinIO** no Docker
  Compose local; qualquer S3-compatível (R2/B2/S3) quando houver demo remota.
- Chaves namespaced por usuário: `{student_id}/{session_id}/{turn_id}/...`.
- Download só por **URL pré-assinada com TTL curto** (minutos) emitida pela
  API a quem tem direito ao recurso — nunca bucket público, nunca URL eterna.
- **Retenção como regra explícita** (lifecycle): áudio de input expira curto
  (ex.: 7 dias — existe para reprocessamento/debug); áudio de resposta expira
  em prazo médio (ex.: 90 dias) — valores finais definidos na política de
  privacidade (visão §E). Delete de conta remove o prefixo do usuário.

## Alternativas consideradas

### Alternativa A — Filesystem do servidor + endpoint autenticado de download
- O que é: evolução direta do `temp_audio/` com auth na frente.
- Por que foi rejeitada: acopla mídia ao disco de um processo (quebra com 2+
  instâncias — mesmo padrão do F5), streaming de arquivo passa pela API
  (banda e CPU), lifecycle/expiração viram cron caseiro, e não ensina o
  padrão de mercado (presigned URLs).

### Alternativa B — BLOBs no Postgres (bytea/large objects)
- O que é: guardar áudio no banco já existente.
- Por que foi rejeitada: infla o banco e o backup com dados frios, streaming
  ruim, e URL assinada teria que ser reinventada na API. Banco relacional
  para relações; mídia para storage de objeto.

### Alternativa C — Storage gerenciado direto (S3/R2 pagos desde já)
- O que é: pular o MinIO e usar cloud real.
- Por que foi rejeitada: contraria a premissa de infra local/custo zero
  confirmada em P2. Como a porta e o protocolo são S3, a migração futura é
  configuração, não código — o MinIO compra o aprendizado sem a conta.

## Consequências

**Positivas**: F6 resolvido por desenho (auth + TTL + expiração automática);
LGPD viável (retenção declarada, delete por prefixo); paridade com produção
via protocolo S3; app baixa áudio direto do storage (API fora do caminho de
bytes).

**Negativas — o preço aceito**: mais um serviço no Compose; URLs assinadas
expiram — o cliente precisa lidar com "URL velha" pedindo outra (custo de
código real no app); MinIO ≠ S3 em 100% dos cantos (IAM/lifecycle têm
diferenças — testar lifecycle no provedor real quando migrar).

**Equivalente mental .NET:** Azure Blob Storage + SAS tokens com expiração —
mesmo padrão, mesmo raciocínio de retenção.
