# ADR-0005 — Fila e worker: arq sobre Redis

- **Status:** aceito
- **Data:** 2026-08-17

## Contexto

O diagnóstico (F3, seção 1) mostrou o pipeline STT→LLM→TTS rodando dentro do
request. O V1 (ADR-0003) exige: API responde 202 rápido, worker processa em
background, cliente consulta status. Redis já entra no stack para rate
limit/idempotência. Necessidade real: 1 produtor, 1 tipo de consumidor,
retry e visibilidade de falha.

## Decisão

**arq** (async-redis-queue): fila sobre Redis, worker asyncio como processo
separado (`worker/`), jobs com retry configurável e resultado consultável.
O enfileiramento fica atrás da porta `TurnQueue` — trocar de tecnologia de
fila não toca application/domain.

## Alternativas consideradas

### Alternativa A — Celery (+ Redis ou RabbitMQ)
- O que é: o padrão histórico de task queue em Python (≈ Hangfire em
  onipresença).
- Por que foi rejeitada: async é cidadão de segunda classe (workers
  prefork/threads; rodar corrotinas exige contorção), configuração e
  vocabulário grandes para uma fila de um job, e o aprendizado relevante
  (fila, retry, idempotência) vem igualmente do arq com 10% da superfície.
  Gatilho para reavaliar: necessidade de canvas/chains complexos ou beat
  scheduling pesado.

### Alternativa B — RabbitMQ + aio-pika
- O que é: broker dedicado (o par natural de quem vem de MassTransit).
- Por que foi rejeitada: infraestrutura nova (mais um serviço, mais conceitos
  de operação) para necessidades que Redis já instalado cobre. O aprendizado
  de AMQP não está no currículo declarado. Gatilho: múltiplos consumidores
  heterogêneos, routing por tópico, ou garantias de entrega que Redis não dê.

### Alternativa C — BackgroundTasks do FastAPI / asyncio.create_task
- O que é: processar em background dentro do mesmo processo da API.
- Por que foi rejeitada: repete o F5 em nova roupagem — trabalho perdido em
  restart/deploy, sem retry, sem visibilidade, e acopla capacidade de
  processamento à API. É a solução de protótipo que estamos aposentando.

## Consequências

**Positivas**: zero infra nova além do Redis já decidido; worker async
alinhado ao stack; superfície pequena = menos mágica para depurar; a porta
`TurnQueue` preserva a trocabilidade.

**Negativas — o preço aceito**: arq é projeto pequeno (menos batteries que
Celery: sem UI de monitoramento pronta, ecossistema menor) — mitigado pela
porta e pelo escopo modesto; Redis como broker não dá as garantias de um AMQP
(ack fino, DLQ nativa) — retry + idempotência por Turn cobrem o caso de uso;
observabilidade do job é nossa responsabilidade (spans OTel no worker).

**Equivalente mental .NET:** BackgroundService consumindo uma fila simples
(ex.: Azure Storage Queue) em vez de MassTransit+RabbitMQ — a escolha
deliberada do degrau mais simples que atende.
