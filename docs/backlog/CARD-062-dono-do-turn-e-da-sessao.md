# CARD-062 — Um aluno não lê nem mexe no turn ou na sessão de outro

- **ID:** CARD-062
- **Épico:** Contas e auth de verdade (bloqueante de V1.0 — é vazamento de dado de aluno)
- **Esforço:** P
- **Status:** concluído (2026-10-01)
- **Dependências:** CARD-049, [ADR-0073](../adr/0073-dono-do-recurso-checado-no-caso-de-uso-404-identico.md), [LEARNING-0009](../learnings/0009-o-loop-mergeou-com-gates-verdes-o-que-so-o-uso-real-mostrava.md)

## Contexto

Achado pela validação do loop autônomo (2026-10-01), num roteiro de QA contra
a stack real: `GET /v1/turns/{id}` com `Authorization: Bearer lixo` devolveu
`200` com a transcrição, a resposta e as URLs assinadas do áudio de **outro
aluno**. A auditoria das rotas mostrou quatro sem isolamento:

| Rota | Auth | Dono checado |
|---|---|---|
| `GET /v1/turns/{id}` | ❌ | ❌ |
| `GET /v1/turns/{id}/events` (SSE) | ❌ | ❌ |
| `POST /v1/sessions/{id}/end` | ❌ | ❌ |
| `POST /v1/sessions/{id}/turns` | ✅ | ❌ — A gravava na sessão de B, gastando a cota de B |

## Critérios de aceite

- **Dado** um turn do aluno A, **quando** o aluno B o pede (polling ou SSE),
  **então** `404` idêntico ao do turn inexistente.
- **Dado** nenhum token ou token inválido, **quando** se pede um turn ou o
  SSE, **então** `401`.
- **Dado** uma sessão de A, **quando** B grava nela ou a encerra, **então**
  `404` e nada muda (nenhum turn, nenhum objeto, nenhuma fila, sessão ativa).
- **Dado** a `Idempotency-Key` de um turn de A, **quando** B a reenvia, **então**
  `404`, sem o `turn_id` de A na resposta.

## Objetivo de aprendizado

Autorização por recurso (o "dono") é diferente de autenticação (o "quem") — e
teste com um usuário só não exercita nenhuma das duas. No .NET o equivalente é
a diferença entre `[Authorize]` e um `IAuthorizationHandler` baseado em
recurso; aqui a regra mora no caso de uso.

## Execução (2026-10-01)

### O que mudou

- `StartTurn`/`EndSession` ganharam `student_id`; sessão alheia →
  `SessionNotFound`. No `StartTurn` o dono é checado **antes** do replay
  idempotente; o replay legítimo (mesmo aluno, outra sessão) segue igual.
- `GetTurn` (caso de uso novo, `application/use_cases/get_turn.py`) serve o
  polling e o SSE; no SSE roda na rota antes do primeiro byte (ADR-0040).
- Rotas passam o `student_id` do token. `openapi.json`/`schema.d.ts`
  regenerados: só o header `authorization` opcional nas quatro rotas
  (aditivo, ADR-0008) — o cliente já mandava o token em todas.
- **ADR-0073** (critérios **4** — segurança/privacidade — e **2** — contrato).
- **LEARNING-0009** com a regra proposta para o CLAUDE.md; skill
  `voicecoach-arquitetura` com a regra nova e linha no log de decisões.
- Roteiro de QA versionado em `backend/qa/ponta_a_ponta.py`.

### Testes

- Aplicação: `test_get_turn.py` (novo), 3 casos novos em `test_start_turn.py`
  (sessão alheia, chave alheia, replay legítimo em outra sessão), 1 em
  `test_end_session.py`.
- Rota: 5 casos novos em `tests/api/test_turns.py`. **Verificado que os 5
  falham sem a correção** (`git stash push src` → `5 failed`).

### QA contra a stack real (API + worker + Postgres/Redis/MinIO)

```
$ uv run python qa/ponta_a_ponta.py tests/fixtures/stt/amazing-project.wav api.log
OK   register 202 … OK   token inválido 401
OK   B lê turn de A → 404
OK   B acompanha SSE de A → 404
OK   B grava na sessão de A → 404
OK   B com a chave de A → 404 (sem turn_id)
OK   B encerra sessão de A → 404
OK   SSE sem token → 401
… OK   login após delete 401
FALHAS: nenhuma          (31 verificações)
```

### Gates

Backend: `ruff format/check`, `mypy --strict`, `lint-imports` verdes; pytest
completo verde (ver PR). Cliente: `pnpm run gates` verde.

### Regra do explicador (modo autônomo)

Decisões técnicas, registradas sem pergunta: checagem no caso de uso e não na
rota; 404 e não 403; duas leituras por PK em vez de JOIN no repositório —
alternativas e gatilhos no ADR-0073.

> **Decisão autônoma (2026-10-01):** aplicar a regra proposta no CLAUDE.md
> pelo LEARNING-0009? → **não aplicada**, só proposta → o `/postmortem` exige
> aprovação explícita do texto antes de editar o CLAUDE.md. → **PENDENTE DE
> REVISÃO HUMANA**.
