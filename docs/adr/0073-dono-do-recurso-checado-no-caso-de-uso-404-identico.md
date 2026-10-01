# ADR-0073 — O dono do recurso é checado no caso de uso, e o recurso alheio é o mesmo 404 do inexistente

- **Status:** aceito
- **Data:** 2026-10-01
- **Relacionado:** ADR-0007 (auth), ADR-0039 (`Result`), ADR-0040 (Problem Details; 4xx de stream decidido na rota), CARD-032 (RNF2, `DiscardTurn`), CARD-049, CARD-062, [LEARNING-0009]
- **Critérios de obrigatoriedade:** **4 — segurança e privacidade** (quem lê a transcrição e o áudio de quem) e **2 — contrato de API** (quatro rotas passam a exigir `Authorization`).

## Contexto

A validação do loop autônomo (2026-10-01) achou quatro rotas sem isolamento
entre alunos: `GET /v1/turns/{id}` e `GET /v1/turns/{id}/events` sem
autenticação nenhuma; `POST /v1/sessions/{id}/turns` e
`POST /v1/sessions/{id}/end` autenticadas (ou nem isso) mas sem conferir de
quem é a sessão. A regra certa já existia num lugar só — o `DiscardTurn` do
CARD-032 (RNF2) — e nunca virou decisão escrita, por isso não foi replicada
quando o CARD-049 trocou o aluno fixo pelo token.

## Decisão

1. **Todo caso de uso que recebe o id de um recurso do aluno recebe também o
   `student_id` de quem pede**, e a comparação com o dono mora **no caso de
   uso** (`application`), não na rota. É regra de negócio, testável com fakes,
   e uma rota nova não tem como esquecê-la sem mudar a assinatura do comando.
2. **Alheio e inexistente são o mesmo `Err`** (`SessionNotFound`,
   `TurnNotFound`) — um 404 idêntico, sem oráculo de "este id existe".
3. **Leitura também é caso de uso:** `GetTurn` serve o polling e o SSE. No
   SSE a checagem roda **na rota, antes do primeiro byte** (ADR-0040).
4. **No `StartTurn`, o dono vem antes do replay idempotente:** a
   `Idempotency-Key` é única no banco inteiro, e o replay devolveria o
   `turn_id` de quem acertasse a chave alheia. O replay legítimo (mesmo aluno,
   outra sessão dele) segue igual.
5. **Teste obrigatório** em toda rota desse tipo: sem token → `401` (com o
   `requesting_student_id` real, sem o override do fixture) e outro aluno →
   `404`.

## Alternativas consideradas

### A — Checar o dono na rota (dependência FastAPI `turn_do_aluno`)
- **Prós:** uma linha por rota; nenhum comando muda.
- **Por que foi rejeitada:** é exatamente o desenho que falhou — a regra
  dependia de lembrar de pôr a dependência em cada rota. No caso de uso, o
  `student_id` é campo obrigatório do comando e o `mypy` recusa a chamada
  sem ele.

### B — `403` para o recurso alheio
- **Prós:** semanticamente "proibido".
- **Por que foi rejeitada:** distingue "existe, mas não é seu" de "não existe"
  — o oráculo que o RNF2 proíbe.

### C — Filtrar no repositório (`get(turn_id, student_id)`)
- **Prós:** uma consulta só (JOIN), em vez de duas.
- **Por que foi rejeitada (por ora):** espalharia a regra por cada método de
  cada repositório e pelos fakes. As duas leituras por PK custam
  microssegundos na escala do V1. **Gatilho para reabrir:** a leitura do turn
  aparecer no perfil de latência do polling.

## Consequências

- `openapi.json` ganha o header `authorization` nas quatro rotas — mudança
  aditiva (ADR-0008); o cliente já mandava o token em todas.
- Rota nova que recebe id de recurso do aluno e não passa `student_id` ao caso
  de uso é defeito de revisão, a conferir no checklist da skill de
  arquitetura.
