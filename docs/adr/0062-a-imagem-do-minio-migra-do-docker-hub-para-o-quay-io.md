# ADR-0062 — A imagem do MinIO migra do Docker Hub para o quay.io

- **Status:** aceito
- **Data:** 2026-09-13

## Contexto

`minio/minio` (abreviação implícita de `docker.io/minio/minio`) deixou de ser
público no Docker Hub. Verificado em 2026-09-12 (CARD-057): tanto a tag fixada
(`RELEASE.2025-09-07T16-13-09Z`) quanto `latest` respondem `denied: requested
access to the resource is denied`, enquanto `redis:7-alpine` — controle, mesmo
registry — continua disponível. Não houve nenhuma mudança no repositório; o
fornecedor retirou o artefato.

A referência está fixada em três lugares que precisam concordar
(`docker-compose.yml` × 2 serviços, `backend/tests/adapters/test_s3_media_storage.py`),
e a queda derrubou 15 testes de adapter no CI (`docker.errors.ImageNotFound`) e
impede `docker compose up` numa máquina sem a imagem em cache — só não
apareceu antes porque o daemon local já tinha a imagem baixada.

Restrição do ADR-0010 (custo zero): a alternativa não pode introduzir conta
paga nem serviço gerenciado. Restrição do ADR-0006/ADR-0024/ADR-0034: o
storage precisa continuar S3-compatível, com lifecycle e retenção por **tag**
de objeto, e o `createbuckets` do compose depende do `mc` que a própria imagem
do MinIO traz.

## Decisão

**Trocar a origem da imagem para `quay.io/minio/minio`, mantendo a mesma tag**
(`RELEASE.2025-09-07T16-13-09Z`) nos três lugares onde ela está fixada.
Verificado em 2026-09-12: a mesma tag existe e está disponível nesse registry.

Isso é uma decisão tomada **antecipadamente pelo desenvolvedor**, registrada
em `docs/prompt-loop-autonomo-backlog.md` (2026-09-13) como a alternativa a
implementar por este card — não uma escolha autônoma do agente em modo loop.

Complementarmente (mitigação do risco de repetição, não parte da troca de
registry): o job de backend do CI ganha um passo `docker compose pull minio
createbuckets` antes do `pytest`, para que uma imagem que suma de novo falhe
com o nome dela na mensagem, e não como 15 erros de fixture.

## Alternativas consideradas

### Alternativa A — Fixar por digest (`@sha256:…`) em vez de tag
- O que é: trocar a referência por tag por um endereço de conteúdo imutável,
  no mesmo registry (Docker Hub) ou no novo.
- Por que foi rejeitada: um digest é imutável quanto ao **conteúdo**, mas não
  protege contra o registry **parar de servir o objeto** — que foi exatamente
  o que aconteceu aqui. Resolveria "a tag mudou debaixo do projeto" (um
  problema que não tínhamos), não "o fornecedor retirou o artefato" (o
  problema real). Fica como reforço possível *sobre* a tag do quay.io, não
  como solução isolada — não é este card que decide isso.

### Alternativa B — Trocar de motor S3-compatível (ex.: SeaweedFS)
- O que é: substituir o MinIO por outro storage self-hosted compatível com S3,
  eliminando a dependência deste fornecedor específico.
- Por que foi rejeitada: o ADR-0024 e o ADR-0034 usam lifecycle e retenção
  **por tag**, e o `createbuckets`/healthcheck do compose usam o `mc` que vem
  dentro da própria imagem do MinIO — nenhum dos dois foi validado contra
  outro motor. Trocar de motor exigiria revalidar as duas decisões, o que não
  cabe no esforço **M** deste card (a própria proposta técnica do CARD-057
  já antecipa isso: "se esta for a escolha, a implementação não cabe neste
  card e vira card próprio"). Fica registrado como opção futura caso o
  `quay.io` também venha a retirar o artefato.

## Consequências

- **Positivas:** o CI e o `docker compose up` voltam a funcionar numa máquina
  sem a imagem em cache, sem introduzir dependência paga (ADR-0010) nem exigir
  revalidar lifecycle/retenção. A mudança é de três linhas, no mesmo padrão de
  imagem fixada por versão exata que o resto do `docker-compose.yml` já segue.
- **Negativas:** a dependência continua sendo **um único fornecedor de
  registry para uma imagem de terceiro** — o mesmo modo de falha pode se
  repetir no `quay.io`. Isso não é hipotético: é o próprio achado deste card.
  A mitigação aceita é o passo de `pull` no CI como alarme cedo, não uma
  garantia — se o `quay.io` retirar o artefato, o time (eu) fica sabendo pelo
  CI vermelho com o nome certo, e decide então entre fixar por digest ou
  trocar de motor (Alternativa B).
- **O que muda para o compose de produção (CARD-055):** aquele card ainda não
  foi implementado, e vai herdar a mesma referência de imagem deste ADR
  (`quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z`) para o serviço MinIO de
  produção — não há decisão de storage gerenciado nem de outro motor prevista
  ali (CARD-055 troca só as credenciais de "brinquedo" por reais, não a
  origem da imagem). Se este risco negativo se materializar depois que a
  produção já estiver no ar, uma imagem ausente deixa de ser "CI vermelho" e
  vira "deploy que não sobe" — por isso o passo de `pull` como alarme cedo
  importa também lá, não só no CI de desenvolvimento.
- **Equivalente mental no .NET:** um pacote NuGet despublicado continua
  compilando na máquina que já tem o pacote em `~/.nuget/packages`, e quebra
  no agente de build limpo. `packages.lock.json` com hash é o paralelo do pin
  por digest (Alternativa A) — nenhum dos dois protege contra o feed apagar o
  pacote; o que protege é um passo que falha cedo e com o nome certo, que é o
  que o `pull` do CI faz aqui.
