# Reconstrução do backlog em torno do alvo de produto

- **Data:** 2026-08-19
- **Executa:** [`prompts/rebuild-backlog.md`](prompts/rebuild-backlog.md)
- **Alvo:** *o aluno fala; em ~1,8 s o professor começa a responder em áudio; e
  o aluno paga por isso*
- **Regra de desempate:** se algo tiver que ceder para caber, cede **escopo** —
  nunca latência

---

## 0. Premissas desta sessão, e o que foi decidido nela

Declaradas na abertura (LEARNING-0002) e confirmadas pelo desenvolvedor:

| # | Premissa | Estado |
|---|---|---|
| 1 | Primeiro áudio em ~1,8 s; escopo cede, latência não | confirmada (análise §8) |
| 2 | `spoken_reply` como primeiro campo do JSON | **ADR-0022, aceito** |
| 3 | ADR-0016 e ADR-0006 ganham sucessores | consequência necessária |
| 4 | V2 (realtime, VAD, barge-in, WebSocket) fora | gatilho do ADR-0003 intacto |
| 5 | **Cobrar por assinatura** | **confirmada nesta sessão (2026-08-19)** |

> **Correção de número durante a sessão.** Esta reconstrução foi escrita
> primeiro contra um alvo de **~1,4 s**, derivado de `mlx-whisper base.en` a
> 0,20 s. Ao transformar os benchmarks em instrumento reexecutável, esse número
> **não reproduziu** (0,78 s, estável em três execuções — medição §3.3). Todos
> os artefatos desta sessão foram corrigidos para **~1,8 s**, com `small.en`,
> que é o número confirmado. O alvo continua dentro da faixa de 1–2 s pedida,
> mas na parte alta dela — e a regra de desempate fica **mais** apertada, não
> menos.

Três decisões do desenvolvedor abriram o trabalho:

1. **Monetização confirmada** → o épico comercial (CARDs 020–023) existe, o
   CARD-015 vira bloqueante de lançamento e o `CLAUDE.md` precisa de emenda (§5).
2. **ADRs estruturais escritos agora; os de produto, propostos** (§4).
3. **STT/TTS no aparelho vira spike** (CARD-019), *depois* do CARD-012 — a regra
   de desempate proíbe atrasar a fatia vertical, e sem o número ponta a ponta o
   spike compararia contra estimativa.

**Dívida do explicador:** as 8 perguntas abertas (`perguntas-em-aberto.md`)
foram reapresentadas na abertura. Nenhuma fecha aqui — esta sessão não escreve
código. **Q7** (`Protocol` e o momento em que um fake não satisfaz a porta)
está explicitamente marcada no CARD-006, onde nasce o primeiro fake de porta.

---

## 1. Diagnóstico do backlog atual, card a card

| Card | Veredito | Motivo (ancorado) |
|---|---|---|
| **001** Monorepo | **mantém** | concluído; nada no alvo novo o toca |
| **002** Compose/config/health | **mantém, com dívida** | concluído; o readiness ganha a entrada `worker` no CARD-009 (ADR-0025) e o `head_bucket` no CARD-008 (dívida do ADR-0014) |
| **003** Quality gates | **mantém** | concluído; ADR-0015/0019 sobrevivem à virada — sai verificação pedagógica, fica verificação de engenharia |
| **004** Skill de arquitetura | **mantém, com atualização** | a skill precisa absorver ADRs 0023–0027; regra da skill que não bate com ADR é bug |
| **005** Domínio mínimo | **mantém; delta vira card novo** | concluído e não se reabre. O ADR-0023 muda o `Turn` ⇒ **CARD-018** |
| **006** STT | **reescreve** | achados 3, 4 e 5: dois adapters (`mlx`/`faster`), `float32` (não `int8`), **escolha de modelo bloqueada** por falta de voz de aprendiz |
| **007** TeacherLlm | **reescreve — é o coração** | streaming + parse incremental. Batch não se converte em cascata: muda a forma da porta. ADR-0022 |
| **008** TTS + storage | **reescreve** | síntese por sentença; storage por trecho (ADR-0024); Piper avaliado contra Kokoro por causa das três dependências escondidas (achado 6) |
| **009** Worker | **reescreve** | cascata, não cadeia; modelos residentes (ADR-0025, ~6 s/turn); caminho triste da entrega parcial |
| **010** Endpoints | **reescreve** | SSE como principal, polling preservado como recuo (ADR-0026); `chunks[]` aditivo (ADR-0008) |
| **011** App Expo | **mantém + 1 requisito** | gravação não muda; acrescenta verificar SSE dentro do Expo Go, para o CARD-012 não descobrir tarde |
| **012** Cliente | **reescreve** | playback encadeado sem buraco audível; é o card que **mede** se 1,8 s foi entregue |
| **013** Corrections | **mantém, reprioriza para depois** | pedagogia depois de sobrevivência comercial (margem de 1,49× no pesado) |
| **014** UsageEvent | **antecipa** | pré-requisito do kill switch e detector de regime do caching (ADR-0021) |
| **015** Quotas/kill switch | **reprioriza — bloqueante** | margem 3,0× no engajado, 1,49× no pesado: sem cota, a margem é definida pelo usuário mais entusiasmado |
| **016** UI de correções | **mantém, reprioriza** | ajuste: o áudio começa antes do feedback (ADR-0022) |
| **017** Retenção | **mantém, escopo cresce** | ADR-0024: três TTLs (trecho 1 dia, `full` 90, input 7) e novo caso de degradação |
| — | **novos** | **018** (Turn com trechos), **019** (spike on-device), **020–023** (comercial) |

**Nenhum card foi morto.** A cascata forçou reescrita real em 006–012, como o
prompt previa; o resto sobreviveu com ajuste ou mudança de posição.

---

## 2. A ordem, e a dependência que justifica cada mudança

**Ordem anterior:** `001 → 002/003 → 005 → 009 → 010 → 012`, com 006/007/008 e
011 paralelos.

**Ordem nova:**

```
018 → 006 → 007 → 008 → 009 → 010 → 012        (011 em paralelo, desde já)
   → 014 → 015 → [auth] → 020 → 021 → 022 → 023
```

As quatro mudanças, cada uma com a dependência que a obriga:

1. **018 entra antes de tudo.** O CARD-008 não tem onde gravar a frase
   sintetizada e o CARD-009 não tem o que emitir sem `TurnAudioChunk`. É
   dependência de dados, não de preferência — e é o momento mais barato: nenhum
   turn existe em banco.
2. **007 deixa de ser paralelo e vira pré-requisito de 008 e 009.** Antes, os
   três adapters eram independentes porque cada um era batch. Agora o CARD-008 é
   consumidor do `AsyncIterator` do CARD-007: a granularidade da síntese é
   definida por quem produz as sentenças.
3. **014 e 015 sobem para antes do pedagógico (013/016).** Dependência de
   negócio, não técnica: cobrar sem cota é vender risco ilimitado por preço fixo
   (margem 1,49× no perfil pesado). O CARD-015 depende do CARD-014 porque quota
   sem medição opera no escuro.
4. **Auth real sobe para antes do comercial.** Não se cobra de um token fixo de
   dev. É a dependência mais óbvia e a mais fácil de esquecer, porque no roadmap
   antigo auth vinha depois de tudo que não a exigia.

**019 (spike) fica fora do caminho crítico, depois do 012**, de propósito: a
regra de desempate proíbe atrasar a entrega de latência, e o spike precisa do
número ponta a ponta como baseline.

---

## 3. O que o backlog agora diz, e que antes não dizia

Três coisas ficaram escritas para não serem descobertas tarde:

- **Barge-in não vem.** Um produto com ~1,8 s de primeiro áudio **sem**
  interrupção ainda é um walkie-talkie — só que ágil. Está nos CARDs 007, 009 e
  012 como fronteira, não como pendência.
- **~1,8 s é o *primeiro áudio*.** A resposta típica tem **17 s de áudio** para
  tocar. Nenhum card promete turno completo em 1–2 s.
- **A latência medida vale num Apple M4.** Em x86 sem Neural Engine o
  `mlx-whisper` não roda e os demais números não transferem (ADR-0027).

---

## 4. Os ADRs

### Escritos nesta sessão

| ADR | Título | Critério de obrigatoriedade citado |
|---|---|---|
| **0023** | Ciclo de vida do Turn com entrega em cascata *(substitui 0016)* | 2 (fronteira: formato persistido e contrato) e 5 (migration) |
| **0024** | Mídia por trecho: chave, URL junto do evento, retenção assimétrica *(substitui 0006)* | 2 (fronteira) e 4 (privacidade: exposição de mídia e retenção de voz) |
| **0025** | Modelos residentes no worker e readiness que distingue "pronto" | 5 (difícil de reverter: ciclo de vida, readiness, deploy) e 2 |
| **0026** | Entrega progressiva por SSE, com polling como recuo | 2 (contrato/transporte) e 1 (`sse-starlette`, polyfill no cliente) |
| **0027** | Adapter duplo de STT, default resolvido pela plataforma | 1 (`mlx-whisper`) e 2 (uma porta, duas implementações) |

Os ADRs 0006 e 0016 tiveram **apenas o status atualizado**, com uma nota do que
neles sobrevive — nunca a decisão editada (regra do `docs/adr/README.md`).

### Propostos, não escritos — dependem de decisão de produto

| Tema | Critério | O que trava |
|---|---|---|
| **Canal de cobrança e provedor de pagamento** | 1 e 3 | CARD-021 está **bloqueado**. Vale 11–26 pontos de margem, e depende de pesquisa sobre regras de *steering* da App Store — pesquisa a fazer, não suposição |
| **Unidade da cota** (minutos vs. turns) | 2 (afeta o domínio) | CARD-015. Recomendação: **cobrar em minutos, limitar em ambos** |
| **Sucessor do ADR-0010** (política de custo sob receita) | 3 | depende dos dois acima; hoje o ADR-0010 está em tensão, não derrubado |

**O ADR-0011 continua incompleto de propósito** naquilo que o ADR-0027 não
cobre: a escolha entre Kokoro e Piper é do CARD-008 e vira ADR próprio quando
for feita (critério 1).

---

## 5. Emenda ao `CLAUDE.md` — PROPOSTA, não aplicada

> O `CLAUDE.md` é a constituição e a emenda é do desenvolvedor. **Nada abaixo
> foi aplicado.** Enquanto não for aceita, o texto vigente vence — por isso os
> cards desta sessão trazem **as duas coisas**: a seção "Por que agora" (nova) e
> o campo "Objetivo de aprendizado" (vigente), preenchido honestamente.

O que **não** muda, e vale reafirmar: quality gates (ADR-0015/0019), ADRs com o
critério escrito, camadas com portas (ADR-0012/0003), post-mortems. Sai a
verificação **pedagógica**; fica a verificação de **engenharia**.

```diff
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ ## OBJETIVO
-Migrar este protótipo para um produto próprio, multiplataforma, escalável e
-defensável em entrevista técnica. Prioridade dupla e explícita:
-1. meu aprendizado real de Python/React,
-2. qualidade de engenharia do produto.
-
-Velocidade de entrega NÃO é prioridade.
+Fazer o Voicecoach funcionar ponta a ponta, rápido, e cobrar por isso:
+**o aluno fala; em ~1,8 s o professor começa a responder em áudio; e o aluno
+paga por assinatura.** Prioridade, em ordem de precedência explícita:
+
+1. **Latência percebida** — primeiro áudio em ~1,8 s. **Não é negociável na
+   primeira entrega:** se algo tiver que ceder para caber, cede ESCOPO.
+2. **Qualidade de engenharia** — é o que permite trocar provider (alavanca de
+   custo e de latência) e sustentar cobrança sem retrabalho.
+3. **Aprendizado de Python/React** — continua acontecendo, agora **por
+   consequência do trabalho**, não como critério de aceite de tarefa.
+
+Velocidade de entrega deixa de ser irrelevante: o produto precisa chegar ao
+aluno. O que continua proibido é velocidade comprada com gate vermelho.
@@ ## Definition of Done
-- [ ] A **regra do explicador** foi cumprida (abaixo), com o desfecho de cada
-      pergunta registrado no card (respondida / dispensada por mim / em aberto).
-      Item fechado pelo agente com a própria explicação **não** conta
-      (origem: [LEARNING-0004])
+- [ ] Quando o card introduziu um idioma de Python sem paralelo em C# ou uma
+      decisão não-óbvia, o agente **parou no ponto da decisão** e explicou em
+      até 5 linhas, com o equivalente mental em .NET. Sem quiz, sem item de
+      aceite pendurado no aprendizado
@@ ## A regra do explicador
-O produto deste projeto é o meu conhecimento; o código é subproduto. Esta regra
-existe para **verificar** isso — e verificação que o agente pode fechar sozinho
-não é verificação (reescrita no CARD-005; origem: [LEARNING-0004], depois de
-quatro fechamentos não-verdes seguidos).
+## A regra do explicador (reduzida a explicação, sem verificação)
+
+O produto deste projeto passou a ser o **Voicecoach**; o aprendizado é
+consequência. A verificação pedagógica (pergunta de previsão, desfecho
+registrado, fila de dívida) **sai** — ela existia para provar aprendizado, e o
+critério de sucesso agora é o produto funcionando.
+
+O que **fica**: quando aparecer um idioma de Python sem paralelo em C#
+(context managers, decorators, generators, async sem Task, duck typing,
+protocols, dataclasses) ou uma dependência nova, o agente **explica em até 5
+linhas, no ponto da decisão**, com o equivalente mental em .NET. Isso não é
+item de DoD verificável — é como o agente escreve.
+
+`docs/perguntas-em-aberto.md` **para de receber linhas novas** e fica como
+arquivo histórico. As 8 perguntas abertas seguem lá: são dívida real de
+conhecimento, e o desenvolvedor as puxa quando quiser, por vontade — não por
+cerimônia de fechamento de card.
@@ ## Artefatos do harness
-| `docs/perguntas-em-aberto.md` | Fila da regra do explicador: pergunta que não fechou, reapresentada na abertura da sessão seguinte |
+| `docs/perguntas-em-aberto.md` | **Histórico** da antiga regra do explicador. Congelado — não recebe linhas novas |
```

E no template de card:

```diff
--- a/docs/backlog/CARD-000-template.md
+++ b/docs/backlog/CARD-000-template.md
-## Objetivo de aprendizado
-
-> Obrigatório e específico.
-> Ruim: "aprender SQLAlchemy".
-> Bom: "entender a diferença entre session scope e unit of work no
-> SQLAlchemy 2.0 e por que difere do DbContext".
-
-O que EU vou aprender de Python/React ao executar este card.
+## Por que agora
+
+> Obrigatório e específico. Amarra o card ao caminho de produto:
+> *aluno fala → ouve em ~1,8 s → paga*.
+> Ruim: "é importante para a arquitetura".
+> Bom: "sem isto o CARD-009 não tem o que emitir antes do fim, e o alvo de
+> ~1,8 s não existe".
+
+O que este card desbloqueia no caminho crítico, e por que não pode esperar.
+Se a resposta não couber aqui, o card provavelmente não entra.
```

### Proposta de emenda ao documento de visão

A confirmação da monetização também torna falsa a premissa 4 da visão
(*"infra: local + free tiers"*, na parte em que ela implica projeto sem receita)
e a §A, que descreve o MVP sem plano pago. **Proposta:** acrescentar à visão uma
**Parte G — Modelo de negócio**, consumindo a análise de custo (âncoras de
mercado, dois planos, margem por perfil), em vez de editar as partes existentes.
Não aplicada — é decisão do desenvolvedor, e provavelmente merece sessão própria.

---

## 6. O que esta sessão deliberadamente não fez

- **Não escreveu código de produção** — é sessão de backlog.
- **Não editou o `CLAUDE.md`** nem o documento de visão.
- **Não decidiu** canal de cobrança, unidade da cota, nem Kokoro vs Piper. As
  três têm dono, critério e card.
- **Não antecipou o V2.** SSE é unidirecional sobre HTTP comum; nenhuma das três
  condições do gatilho do ADR-0003 foi atingida.
- **Não inventou feature.** Nenhum streak, nenhuma gamificação, nenhum CEFR novo.
  Crescer o produto hoje é fazê-lo funcionar ponta a ponta, rápido, e cobrar.
