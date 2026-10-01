# Resumo do loop autônomo — 2026-10-01

> Sessão retomada a pedido do desenvolvedor: *"validar tudo que foi feito com
> o loop para ver se está íntegro e funcional; em seguida continuar. Toda
> decisão que precisar ser tomada, vá pela recomendada e registre."*
> Continuação de [`loop-autonomo-2026-09-13-resumo.md`](loop-autonomo-2026-09-13-resumo.md).

## 1. A validação: o que estava quebrado em `main` com todos os gates verdes

Os gates estavam verdes (653 testes, cobertura 93%). Um **roteiro de QA contra
a stack real** — API e worker de verdade, Postgres/Redis/MinIO, chamadas HTTP
do cadastro ao delete de conta, mais um segundo aluno tentando acessar o
primeiro — achou em minutos:

| # | Defeito | Gravidade | Corrigido em |
|---|---|---|---|
| 1 | **Todo cadastro por e-mail falhava**: `INSERT` de `credentials` antes de `students` (falta de `relationship()`), traduzido em silêncio como "e-mail já existe" → `202` sem conta | crítica | PR #63 (CARD-060) |
| 2 | **Isolamento entre alunos ausente**: `GET /v1/turns/{id}` e o SSE sem autenticação (`Bearer lixo` → `200` com dados alheios); gravar e encerrar na sessão de outro aluno | crítica (vazamento de dado) | PR #65 (CARD-062) |
| 3 | **Retenção nunca aplicada**: as regras de lifecycle existiam e eram testadas, mas nada as aplicava — voz dos alunos guardada para sempre | alta (LGPD) | PR #68 (CARD-017) |
| 4 | Tradutor **respondia** à pergunta do professor em vez de traduzir — 11% das vezes, medido | média | PR #66 (CARD-063) |
| 5 | Redis fora → `500 text/plain` (barrava por acidente, não por decisão) | média | PR #67 (CARD-054) |
| 6 | Drift `models.py` × migrations (8 operações no `alembic check`) | baixa | PR #63 |
| 7 | CI de todo PR quebrado: `quay.io/minio/minio` fechou | bloqueante | PR #64 (CARD-061) |

Por que os gates não pegaram: [LEARNING-0009](learnings/0009-o-loop-mergeou-com-gates-verdes-o-que-so-o-uso-real-mostrava.md).
O roteiro virou artefato: [`backend/qa/ponta_a_ponta.py`](../backend/qa/ponta_a_ponta.py)
(31 verificações).

## 2. PRs mergeados nesta sessão

| PR | Card | O que entregou |
|---|---|---|
| [#63](https://github.com/luanfiszer/Voicecoach/pull/63) | CARD-060 (retomada) | Login Google no app (trabalho do desenvolvedor de 09-14, validado); correção do cadastro; drift; ADR-0071 |
| [#64](https://github.com/luanfiszer/Voicecoach/pull/64) | CARD-061 | MinIO → `pgsty/minio` com tag fixa; ADR-0072 (substitui o 0062) |
| [#65](https://github.com/luanfiszer/Voicecoach/pull/65) | CARD-062 | Dono do turn/sessão checado no caso de uso; ADR-0073; LEARNING-0009 |
| [#66](https://github.com/luanfiszer/Voicecoach/pull/66) | CARD-063 | Tradução delimitada como material: 10/90 → 0/90 respostas indevidas; testes do adapter (tinha zero) |
| [#67](https://github.com/luanfiszer/Voicecoach/pull/67) | CARD-054 (parcial) | Contadores de custo fail-closed (503); view `account_costs`; ADR-0074 |
| [#68](https://github.com/luanfiszer/Voicecoach/pull/68) | CARD-017 | `voicecoach-storage-setup`; worker recusa subir sem retenção; GET degrada após o prazo; matriz de retenção; ADR-0075 |
| [#69](https://github.com/luanfiszer/Voicecoach/pull/69) | CARD-024 | Dockerfile com alvos `api`/`worker`, pesos no build, profile `app`; latência medida; ADR-0076 |

Estado final: backend 686 testes (núcleo 99%), cliente 87, CI verde.

## 3. PENDENTE DE REVISÃO HUMANA — tudo num lugar só

1. **Regra nova para o CLAUDE.md** (LEARNING-0009): "gesto real antes de
   fechar, e sempre com dois alunos" — **proposta, não aplicada** (o
   `/postmortem` exige aprovação do texto).
2. **Imagem do MinIO** (ADR-0072): `pgsty/minio` (fork comunitário, tag fixa)
   em vez de Chainguard (só `latest` grátis). Plano B escrito.
3. **Botão "Continuar com a Apple (em breve)"** desabilitado na tela de entrada
   (ADR-0071) — não é publicável assim (Guideline 4.8).
4. **Trecho de áudio vencido sai da lista `chunks`** em vez de ter `url` nula
   (ADR-0075) — para não quebrar o tipo gerado do cliente.
5. **Achado que muda o CARD-055:** `faster-whisper` em container custa
   **+2,9 s** no p50 até o primeiro trecho (4,84 s vs 1,91 s com `mlx`) — o
   dobro da estimativa pessimista do ADR-0060, numa CPU de M4. O alvo de 4,5 s
   está em risco antes de existir servidor ([medicao-latencia §14](medicao-latencia.md)).

## 4. Mudança no fluxo local de desenvolvimento

- `uv run voicecoach-storage-setup` uma vez (e a cada mudança de
  `RETENTION_*`) — **o worker não sobe sem isso**.
- `uv sync --extra mlx` no Mac (um `uv sync` puro remove o `mlx-whisper`).
- `docker compose --profile app up -d --build` sobe tudo em container (API em
  `:8001`); não rodar junto com o worker do host.

## 5. Por que o loop parou aqui

Não há card restante que dependa só de código:

| Card | Trava |
|---|---|
| 055, 056 | servidor (VPS pago) e destinos externos de backup/log/alarme |
| 052 | texto jurídico (a matriz técnica já existe: [`retencao-de-dados.md`](retencao-de-dados.md)) |
| 053, metade Apple do 060 | conta Apple Developer |
| 054 (resto), 020–023 | "pagante" não existe; tamanho da cota gratuita é decisão de produto |
| 035, 044, 019 | escuta / aparelho físico |
| 041, 045 | decisão de produto sobre o ADR-0057 (045 não está mais travado por auth) |
| 043 | adiado pelo ADR-0058 (o motivo "sem auth" já não vale) |
| 046 | pede quebra antes de começar |

**Próximo passo sugerido:** decidir o servidor do CARD-055 com o número do §14
na mão — ou, antes disso, medir o `faster-whisper` `int8`/`base` em x86, que é
o primeiro plano B do próprio card.
