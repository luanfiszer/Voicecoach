# Análise: o caminho até 1–2 s de latência percebida

- **Data:** 2026-08-19
- **Origem:** sessão de medição de latência, depois que a meta mudou
- **Status:** análise — **alvo e pré-requisitos aprovados** em 2026-08-19 (§8)
- **Depende de:** [`medicao-latencia.md`](medicao-latencia.md) (todos os números
  medidos), [ADR-0003](adr/0003-interacao-v1-turn-based-preparada-para-v2-realtime.md)

---

## 0. A meta nova, e uma ambiguidade que precisa ser resolvida

O orçamento da visão §D (texto ≤ ~6 s, áudio ≤ ~12–15 s) foi **medido e está
folgado**: o pior caso fecha em 6,64 s. A meta mudou: o desenvolvedor quer
**1–2 s**.

**Antes de qualquer análise, uma distinção que muda tudo:**

| Interpretação | Viável? |
|---|---|
| **Primeiro áudio** em 1–2 s (o professor começa a falar) | **Sim** — é o objeto desta análise |
| **Turno completo** em 1–2 s (a resposta inteira tocada) | **Não, e nunca será** — a resposta típica tem **17 s de áudio**. O limite é a duração da fala, não o processamento |

Esta análise assume a primeira. Se a intenção for a segunda, o problema não é de
engenharia — é de tamanho da resposta, e cai na zona congelada até o eval.

---

## 1. Por que 1–2 s é fisicamente possível

Em streaming a métrica vira **tempo entre o aluno parar de falar e o primeiro
áudio sair**:

| Componente | Tempo | Origem |
|---|---|---|
| VAD detectar fim de fala | ~0,3 s | inerente — é preciso esperar silêncio para saber que parou |
| STT da cauda (o resto foi transcrito durante a fala) | ~0,2 s | estimado |
| **LLM até o primeiro token** | **0,60–0,73 s** | **medido** (§5.1 da medição) |
| TTS do primeiro trecho | ~0,2–0,4 s | medido: 0,41 s para uma frase inteira |
| **Total** | **~1,3–1,6 s** | |

O termo dominante é o **TTFT, e ele já está medido: 0,6–0,7 s, praticamente
constante** e independente do tamanho da resposta. A conta fecha com folga
dentro da faixa pedida.

---

## 2. Por que antecipar o V2 **não** é o caminho barato

O [ADR-0003](adr/0003-interacao-v1-turn-based-preparada-para-v2-realtime.md)
estima que o V2 descarta ~15–20% do backend: endpoints de upload/polling,
variante batch dos adapters, orquestração do worker. **Ele não substitui o
resto** — adapters de STT/LLM/TTS, autenticação, persistência, quotas e cobrança
continuam necessários, idênticos.

E o ponto decisivo: **não existe V1 para pular.** Hoje o repositório tem domínio,
migrations e health check. Não há adapter, worker, endpoint nem app.

Antecipar o V2 não economiza trabalho — **adiciona** o trabalho mais difícil
sobre uma fundação que ainda não foi construída:

- VAD contínuo e detecção de fim de turno;
- STT incremental com hipóteses parciais (os adapters medidos são **batch**);
- TTS em stream por chunk (o Kokoro medido é **batch**);
- interrupção (*barge-in*): supressão de eco, VAD durante playback,
  cancelamento de geração em voo;
- WebSocket/WebRTC e a superfície operacional que o ADR-0003 cortou de propósito;
- módulo nativo de áudio no cliente, saindo do Expo Go para dev build.

Além disso, o gatilho escrito do V2 (*"V1 estável + eval com baseline + uso
próprio regular"*) não tem **nenhuma** das três condições satisfeitas.

---

## 3. O intermediário: streaming do LLM + TTS em cascata, dentro do turn-based

| | Hoje (medido) | Com cascata (estimado) |
|---|---|---|
| STT (`mlx-whisper base.en`) | 0,20 s | 0,20 s |
| LLM | 1,86 s (JSON completo) | **~0,8 s** (até fechar a 1ª frase) |
| TTS | 1,68 s (resposta toda) | **0,41 s** (1ª frase) |
| **Até o primeiro áudio** | **3,74 s** | **~1,4 s** + transporte |

### De onde sai o ~0,8 s do LLM

Derivado dos números medidos, para ser auditável:

- taxa de geração = (total − TTFT) ÷ tokens de saída
  - fala curta: (1,86 − 0,73) ÷ 145 = **128 tok/s**
  - fala longa: (3,48 − 0,60) ÷ 388 = **135 tok/s**
  - consistente em **~130 tok/s**;
- com `spoken_reply` como **primeiro** campo do JSON, a primeira frase custa a
  abertura do objeto (~6 tokens) + ~20 tokens de frase ≈ **26 tokens ≈ 0,2 s**;
- TTFT 0,6 s + 0,2 s ≈ **0,8 s**.

**Isto não precisa de WebSocket, VAD, barge-in nem módulo nativo.**

---

## 4. Registro de reversão — a recomendação anterior caiu

Nesta mesma sessão eu recomendei **não** fazer a cascata, e a
[medição §6](medicao-latencia.md) registra o argumento:

> *"A cascata LLM→TTS por sentença: desnecessária. Economizaria ~1,3 s num
> orçamento com 6 s de folga."*

**Esse argumento estava condicionado à meta ser "caber no orçamento de
12–15 s".** Com a meta em 1–2 s, ele não se sustenta: a cascata deixa de ser
otimização marginal e vira **a principal alavanca disponível**.

Fica registrado como reversão explícita, e não como se a recomendação sempre
tivesse sido esta. O que mudou foi a meta, não a medição.

O mesmo vale para o **SSE**, que eu havia descartado como "a menor alavanca da
lista": entrega de áudio progressivo sobre polling é desconfortável, e com a meta
nova o SSE volta à mesa.

---

## 5. O que a cascata custa

- **Reabre o [ADR-0016](adr/0016-ciclo-de-vida-do-turn-estado-grosso-e-etapa-derivada.md)**
  — o áudio deixa de ser um objeto só, e a etapa derivada dos artefatos precisa
  acomodar áudio parcial. ADR novo que substitui, nunca edição do antigo.
- **Reabre o [ADR-0006](adr/0006-storage-de-midia-s3-url-assinada.md)** — chaves e
  URLs assinadas passam a ser por chunk, não por turn.
- **Exige reordenar os campos do JSON** para `spoken_reply` vir antes de `tip` e
  `translation_pt` — **aprovado**, ver [ADR-0022](adr/0022-ordem-dos-campos-da-resposta-do-professor-e-contrato-de-latencia.md).
  O congelamento do prompt segue valendo para conteúdo, tom e tamanho.
- **Provavelmente empurra polling → SSE**, com a superfície de transporte que a
  visão §F tinha cortado.
- **Complica o caminho triste:** falha no meio da cascata deixa um turn com áudio
  parcial já entregue ao aluno. O `Turn.fail()` atual não modela isso.

## 6. O que a cascata **não** entrega

**Interrupção.** O aluno falar por cima do professor exige VAD durante o
playback, supressão de eco e cancelamento de geração em voo. Isso é V2 de
verdade, e nenhum atalho o entrega.

Vale ser explícito porque é a diferença entre "responde rápido" e "conversa": um
sistema com 1,4 s de primeiro áudio **mas sem barge-in** ainda é walkie-talkie,
só que um walkie-talkie ágil.

---

## 7. Recomendação

**Não antecipar o V2. Adotar a cascata como meta explícita do V1.**

Chega-se a ~1,4 s de primeiro áudio pagando dois ADRs reabertos, em vez de pagar
reescrita de transporte, módulo nativo e a fundação que ainda não existe.

Há um argumento de sequenciamento a favor: a cascata é exatamente a **costura 4**
que o ADR-0003 já mandava pagar —

> *"Pipeline do worker como passos componíveis (STT → LLM → TTS como funções
> encadeadas, não um bloco monolítico) — o V2 rearranja os mesmos passos em modo
> streaming."*

Fazê-la agora não é antecipar o V2: é cobrar um investimento que o ADR-0003 já
tinha decidido fazer.

---

## 8. O que depende de decisão do desenvolvedor

1. ~~Confirmar a meta~~ — **CONFIRMADO:** primeiro áudio em ~1,4 s, com
   performance como regra de desempate ("se algo ceder, cede escopo, nunca
   latência"). Turno completo em 1–2 s segue impossível (§0).
2. ~~Levantar o congelamento da ordem dos campos do JSON?~~ — **APROVADO em
   2026-08-19.** Registrado no [ADR-0022](adr/0022-ordem-dos-campos-da-resposta-do-professor-e-contrato-de-latencia.md):
   `spoken_reply` passa a ser o primeiro campo, e a ordem vira contrato de
   latência. O congelamento segue valendo para conteúdo e tamanho da resposta.
3. **Aceitar reabrir ADR-0016 e ADR-0006?** — consequência necessária da
   cascata; ADR novo que substitui, nunca edição.

A decisão 3 é processo, não escolha: **a cascata está destravada.**

## 9. Impacto no backlog — proposto, NÃO aplicado

> O backlog não foi tocado, por instrução explícita.

- **CARD-007** — adapter do professor com resposta em **streaming**, e parse
  incremental que libere `spoken_reply` frase a frase.
- **CARD-008** — TTS por sentença, com storage e URL assinada por chunk.
- **CARD-009** — pipeline do worker como cascata, não como cadeia sequencial; e o
  caminho triste do turn parcialmente entregue.
- **CARD-010/012** — entrega progressiva (SSE a avaliar contra polling) e
  playback encadeado no cliente.
- **ADRs novos** substituindo 0016 e 0006.
