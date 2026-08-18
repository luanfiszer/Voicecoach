# ADR-0018 — Teste de adapter contra Postgres real, com testcontainers

- **Status:** aceito
- **Data:** 2026-08-18

## Contexto

O CARD-005 traz os primeiros adapters de persistência (SQLAlchemy 2.0 async) e a
primeira migration Alembic. A estratégia de testes por camada da visão §D já
previa *"adapters: integração contra dependência real em container
(testcontainers) — **planejado, ainda não instalado**"*, e o CARD-003 registrou a
dívida apontando o CARD-005 como gatilho. O gatilho chegou.

O que precisa ser exercitado contra um banco de verdade, e **não** pode ser
exercitado contra um dublê:

- `TIMESTAMPTZ` — decisivo, porque a regra de reset de quota é por
  **dia-calendário em fuso fixo** (achado da reconciliação de telas);
- tipo `ENUM` nativo do Postgres e `INTERVAL`;
- as **migrations** em si: `alembic upgrade head` num banco vazio é critério de
  aceite do card;
- o roundtrip entidade ↔ linha com o dialeto `asyncpg`.

Restrição do ADR-0010: custo zero, nada de serviço gerenciado, imagem com tag
fixada.

## Decisão

**Adotar `testcontainers` (extra `postgres`) como dependência do grupo `dev`, e
rodar os testes de adapter contra um Postgres descartável subido pelo próprio
pytest.**

- Fixture de **escopo de sessão**: um container por execução da suíte, não por
  teste — o custo de startup (~5–10s) é pago uma vez.
- **Tag de imagem fixada**, a mesma do `docker-compose.yml`
  (`postgres:16.15-alpine`): o teste roda contra a mesma versão do
  desenvolvimento, e a imagem não muda debaixo do projeto (ADR-0010).
- O esquema é criado rodando **as migrations do Alembic**, não
  `metadata.create_all()`: assim o que o teste exercita é o mesmo caminho que
  produção usa, e uma migration quebrada reprova a suíte.
- Testes de domínio permanecem **unitários e sem IO** — nada de container ali.

## Alternativas consideradas

### Alternativa A — Postgres do `docker-compose`, com `skip` se não houver banco

- **O que é:** reaproveitar o serviço que já existe; sem banco, os testes de
  integração dão `skip`.
- **A favor:** zero dependência nova; nada sobe além do que já roda.
- **Por que foi rejeitada:** é **gate que se auto-desliga** — exatamente a classe
  de problema que o CARD-004 encontrou (verde por não estar medindo nada). Um
  `skip` silencioso na máquina de quem esqueceu de subir o compose transforma
  "0 falhas" em ausência de informação. Além disso, o CI precisaria de um serviço
  próprio configurado à parte, criando duas formas diferentes de rodar o mesmo
  teste — e a que roda localmente seria a que ninguém verifica.

### Alternativa B — SQLite em memória

- **O que é:** banco de arquivo/memória, sem infraestrutura.
- **A favor:** rápido, sem Docker, sem espera.
- **Por que foi rejeitada:** testaria contra um banco que **não é** o de
  produção: `TIMESTAMPTZ`, `ENUM` nativo, `INTERVAL` e as próprias migrations do
  Postgres não existem lá — ou seja, justamente os pontos de risco ficariam sem
  cobertura, e o teste passaria a dar falsa confiança. O ADR-0004 já havia
  rejeitado SQLite como banco do projeto pelos mesmos motivos.

### Alternativa C — Não testar adapter (só domínio + fakes das portas)

- **A favor:** suíte instantânea; o núcleo é onde mora a regra.
- **Por que foi rejeitada:** o mapeamento entidade ↔ linha e a migration são
  precisamente onde este card pode errar (o próprio card lista o mapeamento como
  risco). Fake de repositório não descobre coluna com tipo errado nem migration
  que não sobe.

## Consequências

**Positivas**

- O que roda no CI é o mesmo que roda na máquina, contra a mesma versão do
  Postgres do compose.
- `alembic upgrade head` passa a ser verificado por teste automatizado, não por
  inspeção manual.
- O teste de adapter fica honesto: falha quando o mapeamento está errado, em vez
  de pular.

**Negativas — o preço aceito**

- **Docker vira pré-requisito do `pytest`** para a suíte completa. Quem não tem o
  daemon rodando vê erro, não `skip` — decisão deliberada, mas é atrito real.
- ~5–10s de startup por execução da suíte; a suíte deixa de ser instantânea.
- Uma dependência de dev a mais para manter atualizada, e o pin da imagem passa a
  existir em dois lugares (compose e teste) — precisam ser conferidos juntos ao
  subir a versão do Postgres.

**Equivalente mental .NET:** `Testcontainers.PostgreSql` com uma fixture de
coleção do xUnit — o mesmo padrão, inclusive no detalhe de subir o container uma
vez por sessão em vez de por teste.
