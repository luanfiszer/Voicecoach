# ADR-0010 — Política de custo: infra a dinheiro zero, gasto restrito à IA com teto mensal

- **Status:** aceito
- **Data:** 2026-08-17
- **Ajusta:** ADR-0007 (momento da verificação de e-mail), ADR-0009 (defaults de desenvolvimento)

## Contexto

Após o P2, o desenvolvedor pediu reavaliação explícita: este é um projeto
pessoal e o custo deve ser mínimo — idealmente **o único gasto sendo a IA**.
Auditoria do que o P2 realmente custa em dinheiro:

| Item do P2 | Custo real |
|---|---|
| Postgres, Redis, MinIO, Jaeger (Docker Compose local) | **R$ 0** (roda na máquina) |
| API + worker (processos locais) | R$ 0 |
| Expo dev build / APK | R$ 0 (loja já adiada — visão §E) |
| Provedor de e-mail transacional (verificação de cadastro) | R$ 0 em free tier, mas é conta/dependência a mais |
| **APIs de IA (Whisper + Claude + TTS)** | **~US$ 0,023–0,028/turn — o único custo real** |

Conclusão da auditoria: o medo de custo não vem da infra (já é zero) — vem
do gasto recorrente de IA e do risco de ele fugir de controle.

## Decisão

1. **Infra jamais custa dinheiro sem ADR novo.** Tudo roda em Docker Compose
   local. Se um dia houver demo remota, apenas free tiers já mapeados
   (Postgres: Neon/Supabase; Redis: Upstash; S3: Cloudflare R2 10GB; app:
   Fly/Render free) — e a adoção de qualquer plano pago exige ADR.
2. **Gasto de IA restrito ao Claude por padrão**: STT e TTS rodam localmente
   em desenvolvimento (ADR-0011). Elimina inclusive a necessidade de conta
   OpenAI no dia a dia — um único provedor pago (Anthropic).
3. **Teto mensal duplo**: spend limit configurado no console da Anthropic
   (ex.: US$ 10/mês) **e** `MONTHLY_BUDGET_USD` na aplicação — o kill switch
   já desenhado (visão §D) passa a ser mensal além de diário. Auto-reload
   desligado.
4. **Defaults de desenvolvimento baratos** (ajusta ADR-0009):
   `TEACHER_MODEL=claude-haiku-4-5` no ambiente de desenvolvimento; Sonnet
   reservado para sessões de avaliação de qualidade e para o eval (P5). A
   recomendação de produto do ADR-0009 (Sonnet para pedagogia) permanece —
   ela vale para o modo "qualidade", não para cada iteração de debug.
5. **Cadastro por código de convite no MVP** (ajusta ADR-0007): registro
   exige `INVITE_CODE` (config). Elimina a superfície de abuso de cadastro
   aberto (diagnóstico §7.3) **e** a dependência de provedor de e-mail agora.
   A verificação de e-mail obrigatória do ADR-0007 move-se para o gatilho
   "beta aberto a desconhecidos". Quotas por conta permanecem como backstop.
6. Jaeger no Compose fica em **profile opcional** (`--profile observability`)
   — sobe só quando se está estudando traces.

### O custo esperado com esta política

| Cenário (uso pessoal: ~30 turns/dia) | Custo/turn | Custo/mês |
|---|---|---|
| Dev (STT/TTS locais + Haiku) | ~US$ 0,004 | **~US$ 3,6** |
| Qualidade (STT local + Sonnet + TTS OpenAI) | ~US$ 0,017 | ~US$ 15 |
| Protótipo WhatsApp (referência) | ~US$ 0,033 | ~US$ 30 + risco aberto |

## Alternativas consideradas

### Alternativa A — Remover Redis/MinIO para "economizar"
- O que é: SQLite + fila em Postgres (ex.: procrastinate) + áudio no
  filesystem, minimizando serviços.
- Por que foi rejeitada: não economiza **dinheiro** (os serviços locais já
  custam zero) — economizaria apenas RAM/complexidade ao preço de perder o
  aprendizado de Redis/S3 (objetivo de primeira classe) e de reintroduzir os
  padrões condenados no diagnóstico (F5/F6). Corte errado para o problema
  certo.

### Alternativa B — Manter cadastro aberto com verificação de e-mail (como ADR-0007 original)
- O que é: proteção por verificação + quotas desde o MVP.
- Por que foi rejeitada agora: para um projeto pessoal sem lançamento, a
  proteção mais barata contra abuso é **não ter cadastro aberto**. O convite
  custa uma comparação de string; a verificação de e-mail custa integração,
  templates e um provedor. O aprendizado do fluxo completo não some — muda
  de fase (gatilho: beta aberto).

### Alternativa C — Cortar o gasto de IA a zero também (LLM local)
- O que é: modelo open-weights local (ex.: via Ollama) como professor.
- Por que foi rejeitada: a qualidade pedagógica é o produto; LLMs locais no
  hardware disponível degradam exatamente o que o eval (P5) vai medir, e a
  integração Anthropic faz parte do portfólio pretendido. US$ 3–15/mês é o
  custo aceito do projeto. Gatilho para reavaliar: eval harness pronto — aí
  um modelo local pode ser **medido** contra o baseline em vez de adotado no
  escuro.

## Consequências

**Positivas**: gasto mensal previsto de US$ 3,6–15 com teto duro; um único
provedor pago; zero contas de infra; superfície de abuso eliminada no MVP;
nenhuma mudança estrutural na arquitetura (as portas absorvem tudo).

**Negativas — o preço aceito**: desenvolvimento diário roda com modelo mais
fraco (Haiku) — feedback pedagógico do dia a dia não representa o modo
qualidade (mitigado pelo eval do P5, que roda com o modelo de produto);
convite = nenhum usuário externo espontâneo (irrelevante nesta fase);
verificação de e-mail vira dívida documentada com gatilho.

**Equivalente mental .NET:** ambiente de desenvolvimento com LocalStack +
SKUs mínimos e budget alert na assinatura — custo é requisito arquitetural
com gate, não consequência descoberta na fatura.
