# CLAUDE.md — Constituição do projeto

> Este arquivo é a fonte de verdade para qualquer sessão de trabalho neste
> repositório. Leia-o integralmente antes de editar qualquer coisa.
> Ele deve ficar mais rigoroso com o tempo, não maior à toa: se duas regras
> se sobrepõem, consolide.

---

## CONTEXTO DO DESENVOLVEDOR

Sou desenvolvedor C#/.NET com experiência em projetos robustos de produção.
Domino: DDD, CQS/CQRS, Result Pattern, SOLID, EF Core, RabbitMQ, Redis,
OpenTelemetry, testes com xUnit, arquitetura em camadas (Domain / Data /
Application / Presentation / API).

Sou INICIANTE em Python e não conheço o ecossistema de bibliotecas.
Não sou iniciante em arquitetura de software.

Consequência prática para o agente:

- NÃO explique o que é injeção de dependência, repositório ou unidade de trabalho.
- SEMPRE explique qual biblioteca Python resolve o problema, por que ela e não
  a alternativa, e qual o equivalente mental no mundo .NET.
- Quando propuser um idioma de Python que não tem paralelo em C#
  (context managers, decorators, generators, async sem Task, duck typing,
  protocols, dataclasses, descritores), pare e explique em 3 linhas.

## CONTEXTO DO PRODUTO

Produto: professor de inglês por conversa de áudio.
Protótipo atual (a ser descontinuado como canal — ver ESCOPO DO CANAL):
áudio no WhatsApp → Twilio → webhook FastAPI → Whisper (STT)
→ Claude (resposta + correções) → OpenAI TTS → Twilio → áudio de volta.

Stack atual do protótipo:
- FastAPI 0.115.0, Uvicorn 0.30.6, python-multipart, httpx 0.27.2, python-dotenv
- SDK anthropic 0.34.0 (modelo claude-sonnet-4-20250514, configurável por .env)
- SDK openai 1.51.0 (whisper-1 para STT, tts-1 voz "nova" para TTS)
- SDK twilio 9.3.3 (WhatsApp Sandbox)
- ngrok para expor o webhook local
- MP3 gerados em temp_audio/, servidos estaticamente em /audio/

Estado atual da arquitetura:
- NÃO há banco de dados
- Histórico de conversa em memória (teacher.py)
- Rate limiting e cotas diárias em memória (limits.py)
- Allowlist de números via .env
- Sem testes, sem CI, sem observabilidade, sem camadas

## ESCOPO DO CANAL

O WhatsApp e o Twilio SERÃO DESCONTINUADOS (decisão registrada no ADR-0001).
Eles foram o andaime do protótipo, não o produto.

Destino:
- **App mobile (iOS e Android)** — este é o CARRO-CHEFE. É onde a conversa por
  áudio acontece e é a experiência principal do produto.
- **App web** — companion. Progresso, histórico de sessões, correções
  acumuladas, erros recorrentes, onboarding, gestão de conta. Pode também
  permitir prática por áudio no browser, mas não é o foco.
- **Backend Python** — API própria consumida pelos dois clientes.

Consequências que o agente deve tratar explicitamente, não assumir:
- **Some:** webhook público, validação de assinatura Twilio, idempotência por
  MessageSid, allowlist por número de telefone, limites do Sandbox.
- **Entra:** autenticação real, captura e playback de áudio no cliente,
  permissões de microfone, upload com retry, comportamento offline, push
  notifications, ciclo de publicação em App Store e Play Store, proteção
  contra abuso de custo por conta criada.

O que NÃO muda e deve ser preservado na migração: o núcleo pedagógico
(prompt do professor, lógica de correção, fluxo STT → LLM → TTS) e as
lições de arquitetura assíncrona. O canal era um adapter; troque o adapter,
preserve o domínio.

## OBJETIVO

Migrar este protótipo para um produto próprio, multiplataforma, escalável e
defensável em entrevista técnica. Prioridade dupla e explícita:
1. meu aprendizado real de Python/React,
2. qualidade de engenharia do produto.

Velocidade de entrega NÃO é prioridade.

---

## Convenções de código

Decididas no CARD-003 ([ADR-0015](docs/adr/0015-quality-gates-tres-aneis.md)).
O que ainda é TBD está marcado como tal, com o card que resolve.

- **Formatação e lint:** `ruff` (formatter + linter), 88 colunas, alvo `py312`.
  Conjunto de regras curado — além dos erros, as famílias que corrigem *idioma*
  (`UP`, `B`, `C4`, `SIM`, `PT`, `N`) e exigem anotação de tipo (`ANN`).
  Configuração em `backend/pyproject.toml`.
- **Tipagem estática:** `mypy --strict` sobre `src/` e `tests/`. Override de
  módulo é permitido quando a biblioteca não publica `py.typed` — mas **sempre
  pontual e comentado com o motivo e o gatilho para remover**; afrouxar o modo
  global, não.
- **Nomenclatura:** PEP 8 imposta por `ruff` (`N`) — `snake_case` para funções e
  variáveis, `PascalCase` para classes, `UPPER_CASE` para constantes de módulo.
  Nome de porta é a **capacidade**, sem sufixo `Port` (`SpeechToText`,
  `MediaStorage` — visão §D).
- **Suprimir um aviso é uma decisão, não um atalho:** todo `# noqa: XXX` e
  `# type: ignore[...]` deve ser **específico** (com o código do erro) e vir
  acompanhado do motivo na mesma linha ou logo acima.
- **Camadas e o que é proibido em cada uma:** [ADR-0012](docs/adr/0012-regra-de-camada-como-contrato-executavel.md)
  e [ADR-0013](docs/adr/0013-configuracao-tipada-fora-das-camadas.md), verificados
  por `uv run lint-imports`. Resumo em `backend/README.md`.
- **Padrão de erro: decidido por inteiro.** A metade antiga é o
  [ADR-0017](docs/adr/0017-erro-de-dominio-e-excecao-result-fica-para-o-caso-de-uso.md)
  (**invariante de domínio violada levanta exceção**, `DomainError` como raiz); a
  outra metade fechou no CARD-010 com o
  [ADR-0039](docs/adr/0039-result-minimo-para-desfecho-esperado-de-caso-de-uso.md)
  (**`Result` mínimo próprio** — `Ok`/`Err`, união fechada, `match` +
  `assert_never` — para o desfecho **esperado** de caso de uso). A pergunta que
  separa os dois não é *"deu erro?"*, é **"quem chamou tem um bug?"**. Toda
  tradução para HTTP acontece num lugar só, em Problem Details
  ([ADR-0040](docs/adr/0040-formato-de-erro-da-api-problem-details.md)).
- **Não persistir o que se consegue derivar**
  ([ADR-0016](docs/adr/0016-ciclo-de-vida-do-turn-estado-grosso-e-etapa-derivada.md)):
  a etapa exibida de um `Turn` e o "sessão ativa?" são calculados, não colunas.
  Dado duplicado é dado que sai de sincronia.

---

## Convenções de commit

- Commits neste repositório **NUNCA** devem incluir o trailer
  `Co-Authored-By: Claude` (ou qualquer variação com nome de modelo). A
  autoria é exclusivamente do desenvolvedor humano, mesmo quando o agente
  redige a mensagem ou parte do código.

---

## Regras de trabalho

- **Premissas de escopo antes de análise** (origem: [LEARNING-0002]): toda
  sessão de análise ou planejamento (diagnóstico, arquitetura, roadmap) começa
  declarando as premissas de escopo de produto das quais as conclusões
  dependem — em especial **o que é permanente vs. andaime** no sistema atual —
  e as confirma com o desenvolvedor antes de produzir o artefato. Premissa não
  confirmada é anotada como tal no próprio artefato.
- **A skill de arquitetura é de consulta obrigatória** (CARD-004): antes de
  criar um módulo novo no `backend/`, decidir em que camada algo mora ou julgar
  se uma dependência pode entrar numa camada, carregue a skill
  `voicecoach-arquitetura` (`.claude/skills/`). Ela destila os ADRs em regra
  operacional — **nenhuma regra lá existe sem ADR de origem**, e a hierarquia
  quando as fontes divergirem está no topo do `SKILL.md`
  (`pyproject.toml` é lei executável; a skill orienta, nunca contradiz).
  Se uma regra da skill não bater com o código, é sinal de ADR novo ou de bug —
  **nunca de afrouxar a regra em silêncio**. A skill cresce por postmortem, com
  linha no log de decisões do `REFERENCE.md`; o cliente (Expo/web) tem skill
  própria a partir do CARD-011.

---

## Definition of Done

Uma tarefa só está concluída quando **todos** os itens abaixo forem verdade:

- [ ] O código roda localmente sem erro no fluxo afetado
- [ ] **Os quality gates passam localmente** ([ADR-0015](docs/adr/0015-quality-gates-tres-aneis.md)):
      `uv run ruff format --check src tests`, `uv run ruff check src tests`,
      `uv run mypy`, `uv run lint-imports` e `uv run pytest --cov
      --cov-fail-under=80` — todos verdes, em `backend/`. Gate vermelho
      contornado com `--no-verify` **não** conta como cumprido
- [ ] Há teste cobrindo o comportamento novo. A cobertura do núcleo
      (`domain` + `application`) não pode cair abaixo de **90%**
- [ ] Decisões arquiteturais relevantes viraram ADR em `docs/adr/` — **verificado
      contra critério escrito, não de memória** (origem: [LEARNING-0003]): o
      fechamento consulta a lista "Quando um ADR é OBRIGATÓRIO" de
      `docs/adr/README.md` e **cita o critério** que se aplicou, ou registra por
      escrito por que nenhum se aplica. Decisão descrita apenas na seção de
      execução de um card **não** conta como ADR: card é registro de trabalho,
      ADR é registro de decisão
- [ ] O card correspondente em `docs/backlog/` foi atualizado (status + pendências)
- [ ] A **regra do explicador** foi cumprida **nesta sessão** (abaixo): cada
      pergunta feita no ponto da decisão tem desfecho registrado no card
      (respondida / dispensada por mim). Item fechado pelo agente com a própria
      explicação **não** conta (origem: [LEARNING-0004]). A fila de
      `docs/perguntas-em-aberto.md` é **arquivo** e não mantém este item
      vermelho (origem: [LEARNING-0005])
- [ ] Nenhuma regra deste CLAUDE.md foi violada

> Os quality gates automatizados entraram no CARD-003 (P4). O que roda sozinho
> — pre-commit, CI e o hook de edição do agente — está descrito no ADR-0015.

---

## A regra do explicador

O produto deste projeto é o meu conhecimento; o código é subproduto. Esta regra
existe para **verificar** isso — e verificação que o agente pode fechar sozinho
não é verificação (reescrita no CARD-005; origem: [LEARNING-0004], depois de
quatro fechamentos não-verdes seguidos).

**1. Perguntar no ponto da decisão, não no fim.** Quando a implementação chegar
a uma decisão não-óbvia — dependência nova, fronteira, idioma de Python sem
paralelo em C#, gate que passa a morder —, o agente **para antes de escrever o
código** e faz **uma** pergunta curta de previsão: *"o que você acha que
acontece se…"*. Só depois implementa e explica. No máximo **2 por sessão**: as
duas decisões mais caras de errar.

**2. A pergunta é sobre consequência observável.** Prefira *"o que quebra, e com
que mensagem, se eu remover X?"* a *"o que é Y?"*. Sempre que possível a
resposta é conferida **rodando o comando na hora**: errar vira demonstração com
evidência, e pergunta mal formulada pelo agente é desmascarada pela execução
(aconteceu no CARD-003).

**3. Quem fecha o item sou eu, não o agente.** Três desfechos, e o agente
registra no card o que de fato ocorreu:

- **respondida** → item verde;
- **errada ou "não sei"** → o agente explica e **reformula a pergunta na mesma
  sessão**, uma vez. Se ainda assim não fechar, ela volta **uma** vez, na
  abertura da sessão seguinte;
- **dispensada por mim** → registrada como **"dispensado pelo desenvolvedor"**,
  nunca como cumprida nem como "parcial".

**4. O item da DoD é sobre as perguntas DESTA sessão** (origem:
[LEARNING-0005], depois de oito sessões em que uma fila antiga manteve vermelho
um item que a sessão corrente tinha cumprido). Ele fica verde quando cada
pergunta feita no ponto da decisão teve desfecho registrado. Pergunta antiga
**não** o mantém vermelho: um item que nunca pode ficar verde não governa nada —
é o defeito do LEARNING-0004 de cabeça para baixo.

**5. A fila é arquivo, não cobrança.** `docs/perguntas-em-aberto.md` guarda o
histórico e **o que a execução demonstrou** sobre cada pergunta. Só é
reapresentada na abertura a pergunta da sessão **imediatamente anterior** que
ficou sem desfecho; sem resposta na segunda vez, é arquivada com a evidência.
Pergunta arquivada volta quando um card novo tocar a mesma decisão — refeita
**no ponto da decisão daquele card**, que é onde ela nasceu certa.

---

## Artefatos do harness

| Local | O que é |
|---|---|
| `docs/adr/` | Architecture Decision Records — decisões com alternativas e trade-offs |
| `docs/backlog/` | Um card por arquivo, com objetivo de aprendizado obrigatório |
| `docs/learnings/` | Post-mortems de erros, cada um gerando uma regra nova aqui |
| `docs/perguntas-em-aberto.md` | Arquivo da regra do explicador: o que cada pergunta demonstrou, e a única da sessão anterior que volta na abertura |
| `.claude/commands/` | Slash commands: `/executa-card`, `/card`, `/adr`, `/postmortem`, `/review`, `/explica` |
| `.claude/skills/` | Skills de arquitetura: `voicecoach-arquitetura` (backend), derivada dos ADRs |
| `docs/referencias/` | Análises de projetos externos usados como referência, com o que foi aproveitado e o que foi recusado |

> **Toda execução de card começa por `/executa-card <número>`** — ele carrega o
> protocolo de sessão (ordem de leitura, premissas antes do plano, DoD item a
> item, regra do explicador, convenção de commit). Quando um erro novo virar
> regra, a regra entra lá também, não só aqui.
