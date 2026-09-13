# CARD-057 — A imagem do MinIO saiu do Docker Hub: o CI do backend quebrou e o compose não sobe numa máquina nova

- **ID:** CARD-057
- **Épico:** Infraestrutura de desenvolvimento e CI (achado do fechamento do CARD-042)
- **Esforço:** M
- **Status:** backlog
- **Dependências:** nenhuma de card. **ADR novo antes da implementação** (origem da
  imagem). Relacionados: ADR-0006, ADR-0010, ADR-0024, ADR-0034, CARD-055

## Contexto

Achado no merge do PR #29 (CARD-042), em 2026-09-12. O job **backend (ruff, mypy,
pytest, contratos)** falhou num PR que não tem **nenhum** arquivo em `backend/`.

**Débito técnico, não de negócio.** A regra continua certa: o ADR-0006 decidiu
storage S3-compatível com MinIO local, o ADR-0010 exige infra a dinheiro zero, e
o comentário em `test_s3_media_storage.py:54-55` exige que teste e compose usem
**a mesma** imagem. O que envelheceu foi a **origem** da imagem: um fornecedor
externo retirou o artefato, sem nenhuma mudança no repositório.

O código é usado, e muito: 15 testes de adapter, o `docker compose up` de
qualquer sessão e, potencialmente, o compose de produção do CARD-055.

## Problema

**`minio/minio` deixou de ser público no Docker Hub.** Verificado em 2026-09-12:

| Referência | Resultado |
|---|---|
| `minio/minio:RELEASE.2025-09-07T16-13-09Z` (a tag fixada) | `denied: requested access to the resource is denied` |
| `minio/minio:latest` | idem |
| `redis:7-alpine` (controle, mesmo registry) | disponível — o Docker Hub responde |
| `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z` | **disponível** |
| `quay.io/minio/minio:latest` | disponível |
| `bitnami/minio:latest` | `no such manifest` |
| `chrislusf/seaweedfs:latest` | disponível |

A referência está fixada em **três lugares**:

- `backend/tests/adapters/test_s3_media_storage.py:56` — `MINIO_IMAGE`
- `docker-compose.yml:50` — serviço `minio`
- `docker-compose.yml:79` — serviço `createbuckets` (reusa a imagem pelo `mc`)

Consequências:

1. **Todo PR fica com o backend vermelho.** No CI do PR #29: `363 passed, 15
   errors`, todos `docker.errors.ImageNotFound` em `test_s3_media_storage.py`.
2. **Máquina nova não sobe o compose.** Na máquina de desenvolvimento tudo
   funciona **só porque a imagem já estava em cache** no daemon Docker. O runner
   do CI parte do zero, e foi por isso que o CI viu primeiro.
3. **Um segundo vermelho, anterior e de outra causa:** o último run do `main`
   antes deste achado (merge do #28, 2026-09-10) falhou com `1 failed, 377
   passed`, em `test_url_assinada_expira - assert 403 == 200`
   (`test_s3_media_storage.py:170-191`). O teste dorme **2 s fixos** para um TTL
   de 1 s, e a expiração é julgada pelo relógio do MinIO. O docstring já previa
   que ele podia piscar num CI carregado.

## Proposta técnica

1. **ADR antes do código** — critério **1** de `docs/adr/README.md` (introduz ou
   troca a origem de uma dependência externa) e critério **5** (difícil de
   reverter se a troca for de motor, não só de registry). Alternativas mínimas a
   pesar, sem decisão tomada neste card:
   - **mesma imagem por outro registry** (`quay.io/minio/minio`, com a mesma tag):
     a menor mudança; o risco é o mesmo fornecedor retirar este registry também;
   - **fixar por digest** (`@sha256:…`) em vez de tag: a referência vira imutável,
     mas continua dependendo de o registry manter o objeto;
   - **trocar de motor S3-compatível** (ex.: SeaweedFS): tira a dependência do
     fornecedor, mas o ADR-0024 e o ADR-0034 usam lifecycle e retenção **por
     tag**, e `mc` no `createbuckets` e no healthcheck. Se esta for a escolha, a
     implementação **não cabe neste card** e vira card próprio.
   - O ADR **precisa** dizer o que isso implica para o compose de **produção** do
     CARD-055.
2. **Uma referência só, num lugar só.** Hoje as três cópias só concordam por
   disciplina. Proposta: um teste que lê `docker-compose.yml` (com `pyyaml`, se já
   estiver no ambiente; senão, sem dependência nova, por leitura de texto) e
   afirma que as duas imagens do compose são **idênticas** a `MINIO_IMAGE`.
3. **O CI passa a detectar imagem que sumiu, antes dos testes.** Um passo
   `docker compose pull minio createbuckets` no job do backend: se a origem
   desaparecer de novo, o erro sai com o nome da imagem, e não como 15 erros de
   fixture.
4. **`test_url_assinada_expira` deixa de depender de um sono fixo.** Em vez de
   `sleep(2)` e uma única leitura, consultar a URL em intervalos até um prazo
   generoso (ex.: 10 s depois do TTL). Isso preserva o modo de falha que o teste
   cobre: uma URL que **nunca** expira ainda reprova, no fim do prazo. Continua
   valendo o docstring: **nunca remover o teste**.

## Refinamento obrigatório — cache e limites

**Cache:** este card **é** um problema de cache, e as duas perguntas mostram por
quê. A imagem ficou no cache local do daemon Docker:

1. **TTL:** indefinido — dura até alguém rodar `docker image prune`.
2. **Gatilho de invalidação:** nenhum automático. Foi exatamente isso que
   escondeu a remoção na máquina de desenvolvimento. O passo de `pull` no CI
   (proposta 3) **é** o gatilho que faltava.

**Endpoint:** não se aplica — nenhum endpoint é tocado.

**Dependência externa:** o **registry de imagens**.

4. **Timeout, retry e desfecho:** o `pull` do CI herda o timeout do job e **não**
   ganha retry — imagem ausente é sinal, não ruído, e repetir só atrasa o
   diagnóstico. `pull` é idempotente. O aluno não vê nada: é infra de
   desenvolvimento e teste. **A exceção é produção:** se o compose do CARD-055
   usar a mesma origem, uma imagem ausente vira **deploy que não sobe** — e o ADR
   decide isso.

## Escopo

- **In:** o ADR da origem da imagem; a troca da referência nos três lugares, se
  a decisão for mudar só registry, tag ou digest; o teste de consistência entre
  compose e teste; o passo de `pull` no CI; `test_url_assinada_expira` sem sono
  fixo.
- **Out:** trocar de motor S3-compatível (se o ADR escolher isso, vira card
  próprio, porque lifecycle e retenção por tag precisam ser revalidados); o
  storage de produção (CARD-055); cache de imagens no CI (só com ADR, e só se o
  tempo do job virar problema medido).

## Critérios de aceite

- **Dado** um daemon Docker **sem** nenhuma imagem do MinIO em cache, **quando** o
  CI roda o job do backend, **então** os 15 testes de
  `test_s3_media_storage.py` **executam e passam** — nenhum `ImageNotFound`,
  nenhum `skipped`.
- **Dado** uma máquina sem a imagem em cache (`docker rmi` da referência atual),
  **quando** se roda `docker compose up -d minio createbuckets`, **então** os dois
  serviços sobem e o bucket é criado (`bucket pronto: voicecoach-media` no log do
  `createbuckets`).
- **Dado** que alguém troca a imagem em **um** dos três lugares e esquece os
  outros, **quando** o `pytest` roda, **então** o teste de consistência reprova e
  nomeia as duas referências divergentes.
- **Dado** que a origem da imagem desaparece de novo, **quando** o CI roda,
  **então** o passo de `pull` falha **antes** do `pytest`, com o nome da imagem na
  mensagem.
- **Dado** o `test_url_assinada_expira` com consulta até prazo, **quando** a
  suíte roda 20 vezes seguidas, **então** passa nas 20; **e dado** um storage
  falso cuja URL nunca expira, **quando** o teste roda, **então** reprova no prazo.
- **Dado** o card concluído, **então** existe um ADR com pelo menos duas
  alternativas reais e "Consequências negativas" preenchida, incluindo o que muda
  para o compose de produção.

## Riscos

- **O `quay.io` pode seguir o mesmo caminho do Docker Hub.** O próprio achado é a
  prova de que um fornecedor pode retirar o artefato sem aviso ao projeto. Plano
  B: fixar por digest, com o passo de `pull` no CI como alarme; se o risco for
  julgado alto, o ADR escolhe trocar de motor, e isso vira card próprio.
- **Consertar os 15 erros esconde o outro vermelho.** O
  `test_url_assinada_expira` falhou no `main` por **outra** causa. Com a imagem
  corrigida, o job pode continuar piscando, e o card parecer inútil. Por isso os
  dois estão aqui, com critérios separados.
- **Tentação de desligar os testes de storage no CI** "até resolver". Não:
  desligá-los esconde exatamente o modo de falha que o ADR-0006 existe para
  cobrir.

## Objetivo de aprendizado

Entender **como o Docker e o `testcontainers-python` resolvem uma referência de
imagem**. Três pontos:

- `minio/minio` é abreviação de `docker.io/minio/minio`: o registry fica
  **implícito**.
- **Tag** é um ponteiro mutável, e **digest** é um endereço imutável de conteúdo —
  nenhum dos dois garante que o registry **continue servindo** o objeto.
- A máquina local e o CI divergiram porque o daemon local **já tinha** a imagem,
  enquanto o runner parte do zero.

**Equivalente mental no .NET:** um pacote NuGet despublicado continua compilando
na sua máquina por causa do cache em `~/.nuget/packages`, e quebra no agente de
build limpo. O `packages.lock.json` com hash é o paralelo do pin por digest.
Nenhum dos dois protege de o feed apagar o pacote; o que protege é **um passo que
falha cedo e com o nome certo**.
