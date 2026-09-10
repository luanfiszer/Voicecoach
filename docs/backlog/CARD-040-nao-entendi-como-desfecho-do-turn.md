# CARD-040 — "Não entendi, pode repetir?" vira desfecho de turn, e custa zero

- **ID:** CARD-040
- **Épico:** Qualidade da conversa (briefing 2026-09-09, ponto 3 — segunda metade)
- **Esforço:** M
- **Status:** backlog
- **Dependências:** CARD-039, ADR-0057, ADR-0039, ADR-0040

## Contexto

O pedido, em palavras do desenvolvedor: *"quando não entender, **não deduzir**"*.

O CARD-039 tira a causa estrutural (modelo que não conseguia transcrever
português). **Sobra a alucinação por insumo ruim**, que todo Whisper tem: fala
inaudível, gravação de silêncio, microfone abafado, tosse. Hoje o produto não
tem como recusar — qualquer texto que saia do STT vira prompt do professor.

**Débito de negócio.** Nunca houve regra de recusa; o caminho feliz foi o único
construído.

## Problema

O caso de uso do turn não distingue "transcrevi bem" de "transcrevi mal": a
única fronteira que existe é `SttError`, e ela significa *o motor falhou*, o que
não é o caso — o motor funcionou e produziu resultado ruim. O resultado é o
sintoma relatado: **o professor responde com convicção a algo que o aluno não
disse**, e o turn custa US$ 0,002678 (CARD-014) para isso.

## Proposta técnica

Decisão em **ADR-0057** (aceito). Este card a executa.

1. Dois limiares em `config.py`, com o número medido no comentário:
   `stt_min_confidence: float = -1.0` e `stt_max_no_speech: float = 0.6`. São
   **dois** porque os casos são diferentes — "não entendi o que você disse" e
   "não ouvi nada" merecem mensagens diferentes.
2. O corte acontece **antes do professor**, no caso de uso: turn recusado não
   chama LLM nem TTS. É a única operação do produto que economiza dinheiro
   melhorando a experiência.
3. O desfecho é um `Err` do `Result` (ADR-0039) — **união fechada, `match` +
   `assert_never`**. Não é exceção (ninguém tem bug), não é `failed` (não houve
   falha de infra, e marcá-lo assim contaminaria o CARD-025 e a taxa de erro).
4. A borda traduz num lugar só, em Problem Details (ADR-0040) — ou no evento de
   SSE equivalente, já que o turn é entregue em cascata (ADR-0023). **A forma
   exata do estado é decisão deste card**, e o ADR-0028 manda que a derivação
   more no domínio.
5. `confidence` e `no_speech` passam a ser registrados no `UsageEvent`
   (ADR-0051), **inclusive nos turns aceitos**. É o instrumento que permite
   recalibrar o limiar com a distribuição real em vez de adivinhar — o mesmo
   truque do ADR-0021, que mediu antes de decidir.

## Refinamento obrigatório — cache e limites

**Cache:** não se aplica.

**Endpoint:** nenhum endpoint novo, mas o `POST /v1/turns` ganha um desfecho
novo. O limite existente não muda — e vale registrar o efeito contrário ao
usual: **recusar barateia**, então este card reduz a pressão de custo por conta,
não aumenta.

**Dependência externa:** não se aplica — o card **remove** chamadas externas do
caminho recusado. O que muda é que o professor e o TTS deixam de ser chamados
num caso; nenhuma política de timeout/retry nova.

## Escopo

- **In:** limiares configuráveis; a decisão no caso de uso antes do professor; o
  desfecho `nao_entendido` no domínio e no contrato de `/v1`; o evento
  correspondente no SSE; `confidence`/`no_speech` no `UsageEvent`; a tela do
  aluno.
- **Out:** a mensagem falada. O turn recusado **não gera áudio** — o convite a
  repetir é texto na tela, e não custa TTS. Ler em voz alta é melhoria futura
  com gatilho próprio. Também fora: recalibrar o limiar (precisa de dados que
  este card começa a coletar).

## Critérios de aceite

- **Dado** um áudio cuja transcrição tem `confidence` abaixo do limiar,
  **quando** o turn é processado, **então** o desfecho é `nao_entendido`,
  **e o adapter do professor não é chamado nenhuma vez** — verificado com fake
  que registra chamadas, não com mock framework.
- **Dado** o mesmo turn, **quando** o `UsageEvent` é lido, **então** o custo de
  LLM e de TTS é zero e o de STT não é.
- **Dado** um áudio de silêncio (`no_speech` acima do limiar), **quando**
  processado, **então** o desfecho é `nao_entendido` com motivo **distinto** do
  de confiança baixa.
- **Dado** uma transcrição boa, **quando** processada, **então** o fluxo segue
  idêntico ao de hoje — o caminho feliz não regride, e há teste que o prova.
- **Dado** o `Result` do caso de uso, **quando** um caso novo for adicionado à
  união, **então** o `assert_never` quebra a compilação do `mypy`. É o teste do
  mecanismo, não do caso.
- **Dado** um turn recusado, **quando** o aluno o vê no app, **então** é um
  convite a repetir, **não** uma tela de erro — e o histórico o mostra sem
  contá-lo como falha.

## Riscos

- **Falso positivo é pior que o sintoma que estamos curando.** Recusar fala boa
  insulta de um jeito que responder errado não insulta. O limiar vem de vozes
  sintéticas. Plano B: `-1.0` é configuração; afrouxar é uma linha, e a
  distribuição registrada no `UsageEvent` diz para onde mover.
- **Um turn sem áudio nenhum é caminho que o app nunca exercitou.** A fila de
  playback (ADR-0047) nunca recebeu zero trechos. Precisa de teste de cliente,
  não só de servidor.
- **Tentação de reaproveitar `failed`.** Seria menos código hoje e mentira nas
  métricas para sempre. O ADR-0057 já rejeitou; o risco é a implementação
  esquecer.

## Objetivo de aprendizado

Entender o `Result` como **união fechada verificada em tempo de tipagem** —
`match` + `assert_never` sobre uma união de dataclasses é o que em C# se faria
com um `switch` sobre hierarquia selada, com uma diferença que importa: em
Python nada impede o caso novo em runtime, e o que garante a exaustividade é
**exclusivamente o `mypy --strict`**. Ver o gate quebrar ao adicionar um caso é
o exercício.
