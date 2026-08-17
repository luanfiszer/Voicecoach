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

Produto: professor de inglês por áudio no WhatsApp.
Fluxo atual: áudio no WhatsApp → Twilio → webhook FastAPI → Whisper (STT)
→ Claude (resposta + correções) → OpenAI TTS → Twilio → áudio de volta.

Stack atual:
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

## OBJETIVO

Transformar isto em um produto fullstack (Python + React) escalável e
defensável em entrevista técnica. Prioridade dupla e explícita:
1. meu aprendizado real de Python/React,
2. qualidade de engenharia do produto.

Velocidade de entrega NÃO é prioridade.

---

## Convenções de código

> **TBD** — serão definidas após P1 (diagnóstico) e P2 (arquitetura alvo),
> e consolidadas em ADRs + skill de arquitetura (P4). Não invente convenções
> antes disso; siga o estilo do código existente até lá.

- Formatação e lint: TBD (P4)
- Tipagem estática: TBD (P4)
- Padrão de erro/Result: TBD (ADR em P2)
- Camadas e o que é proibido em cada uma: TBD (ADR em P2)
- Nomenclatura: TBD (P4)

---

## Convenções de commit

- Commits neste repositório **NUNCA** devem incluir o trailer
  `Co-Authored-By: Claude` (ou qualquer variação com nome de modelo). A
  autoria é exclusivamente do desenvolvedor humano, mesmo quando o agente
  redige a mensagem ou parte do código.

---

## Definition of Done

Uma tarefa só está concluída quando **todos** os itens abaixo forem verdade:

- [ ] O código roda localmente sem erro no fluxo afetado
- [ ] Há teste cobrindo o comportamento novo (quando a infraestrutura de testes existir — antes disso, o card deve registrar a dívida explicitamente)
- [ ] Decisões arquiteturais relevantes viraram ADR em `docs/adr/`
- [ ] O card correspondente em `docs/backlog/` foi atualizado (status + pendências)
- [ ] A **regra do explicador** foi cumprida (abaixo)
- [ ] Nenhuma regra deste CLAUDE.md foi violada

> Esta lista será expandida em P4 com os quality gates automatizados.

---

## A regra do explicador

Ao final de qualquer implementação, **antes de considerar a tarefa concluída**,
o agente deve me fazer **2 perguntas** sobre o código que acabou de escrever.

Se eu não souber responder, a tarefa **NÃO** está concluída: reescreva de forma
mais simples ou me explique até eu conseguir defender aquele código em uma
entrevista técnica.

O produto deste projeto é o meu conhecimento; o código é subproduto.

---

## Artefatos do harness

| Local | O que é |
|---|---|
| `docs/adr/` | Architecture Decision Records — decisões com alternativas e trade-offs |
| `docs/backlog/` | Um card por arquivo, com objetivo de aprendizado obrigatório |
| `docs/learnings/` | Post-mortems de erros, cada um gerando uma regra nova aqui |
| `.claude/commands/` | Slash commands: `/card`, `/adr`, `/postmortem`, `/review`, `/explica` |
