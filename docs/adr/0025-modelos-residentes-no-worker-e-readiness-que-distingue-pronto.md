# ADR-0025 — Modelos de IA residentes no worker, e um readiness que distingue "subiu" de "pronto"

- **Status:** aceito
- **Data:** 2026-08-19
- **Complementa:** [ADR-0005](0005-fila-e-worker-arq-sobre-redis.md) (arq),
  [ADR-0014](0014-health-check-liveness-readiness.md) (health check),
  ADR-0011 (STT/TTS locais)
- **Consome:** [`medicao-latencia.md`](../medicao-latencia.md) §3.1 e §4.1
- **Critérios de obrigatoriedade:** **5 — difícil de reverter** (mexe em ciclo
  de vida do worker, no significado do readiness e no desenho de deploy) e
  **2 — define uma fronteira** (quem é dono do modelo carregado).

## Contexto

A medição desta semana produziu o número mais desproporcional da sessão:

| Carga | Tempo medido |
|---|---|
| Modelo de STT em disco (`faster-whisper base.en`) | **0,24–0,46 s** |
| `import kokoro` + construção do `KPipeline` | **5,63 s** |
| **Total até o worker poder processar** | **~6 s** |

Comparado com o turn inteiro em regime (STT 0,59 s + LLM 1,86 s + TTS 1,68 s =
~4,1 s), **carregar modelo por job custa mais que todo o resto somado** — e sob
o alvo de ~1,8 s de primeiro áudio, custa **mais de 3× o orçamento inteiro**.

O ADR-0005 escolheu `arq` mas não disse quem é dono do modelo. Sem decisão
escrita, o caminho natural em Python (instanciar dentro da função da task) é
exatamente o que paga os 6 s toda vez.

## Decisão

**Os modelos de STT e TTS são carregados uma única vez, na subida do worker, e
vivem no contexto compartilhado. O worker só é considerado pronto depois disso,
e o readiness da API sabe a diferença.**

1. **Carga no `on_startup` do `arq`**, populando o `ctx` que toda task recebe.
   O `arq` **não consome job enquanto o `on_startup` não retorna** — a barreira
   que precisamos já é o comportamento da biblioteca, e não há mecanismo novo a
   inventar. As tasks leem `ctx["stt"]` / `ctx["tts"]`, nunca constroem.
2. **Descarga no `on_shutdown`**, simétrica, para o teste de integração poder
   subir e derrubar o worker sem vazar memória entre casos.
3. **O worker publica prontidão em Redis**: chave `voicecoach:worker:ready`
   gravada depois da carga, com TTL e renovação periódica (heartbeat). Worker
   morto para de renovar e a chave expira sozinha — não existe estado "pronto"
   mentindo sobre processo morto.
4. **`GET /health/ready` (ADR-0014) ganha uma quarta entrada, `worker`**, com o
   mesmo corpo e a mesma semântica das outras três: **200 só se tudo responder,
   503 caso contrário**. "Subiu" (o processo existe) deixa de ser confundível
   com "pronto" (os modelos estão carregados).
5. **~1–2 GB residentes é requisito documentado**, não detalhe de execução: é o
   número que dimensiona a máquina do worker, hoje na máquina de dev e amanhã
   hospedada. Vai para o `backend/README.md`.
6. **Todo restart custa ~6 s de indisponibilidade do worker.** Consequência
   aceita e explícita: deploy do worker **não** é rolling sem sobreposição, e um
   crash-loop de worker é um incidente de latência, não só de disponibilidade.
7. **Se o `mlx-whisper` for o adapter ativo (ADR-0027), a conta muda e ainda não
   foi medida** — a carga dele não foi cronometrada em separado. O grosso dos
   6 s é o Kokoro de qualquer forma; o CARD-009 mede e registra.

**Equivalente mental .NET:** é registrar o modelo como **singleton no
container do host** e resolvê-lo no `BackgroundService`, em vez de dar `new` a
cada `ExecuteAsync`. O `on_startup` do arq é o `IHostedService.StartAsync`, e o
`ctx` é o service provider do job — com a diferença de que aqui não há
container: o `ctx` é um dicionário, e a disciplina de não construir dentro da
task é regra escrita, não erro de compilação.

## Alternativas consideradas

### Alternativa A — Carregar sob demanda com cache de módulo (`@lru_cache`)

- **O que é:** a função da task pede o modelo a um factory memoizado; o primeiro
  job paga os 6 s, os seguintes não.
- **Por que foi rejeitada:** o custo não some, **muda de vítima** — quem paga é
  o primeiro aluno depois de cada restart, e é justamente ele que o produto não
  pode decepcionar. Pior: o readiness continuaria dizendo 200 com o worker
  incapaz de responder em tempo, que é a mentira que este ADR existe para
  matar. Fica registrada como o que **não** fazer, porque é o caminho de menor
  resistência em Python.

### Alternativa B — Processo dedicado de inferência (modelo atrás de um serviço)

- **O que é:** um serviço separado só para STT/TTS, chamado pelo worker por
  HTTP/gRPC.
- **Por que foi rejeitada:** resolve um problema que ainda não temos (escalar
  inferência independente da orquestração) e adiciona serialização de áudio na
  rede dentro de um orçamento de 1,8 s. É a peça que a visão §F corta por
  antecipação. **Gatilho para entrar:** precisar de mais de uma réplica de
  worker por motivo de CPU de inferência, ou o worker deixar de caber em memória.

### Alternativa C — Manter os modelos fora do worker, usando APIs pagas

- **O que é:** desistir do local (ADR-0011) e chamar OpenAI para STT e TTS.
- **Por que foi rejeitada:** troca 6 s de carga única por custo recorrente **e**
  latência de rede em todo turn, contra a política do ADR-0010 e a economia
  unitária (STT/TTS locais são 0% do custo variável hoje). Continua disponível
  por configuração, como o ADR-0011 já previa.

## Consequências

**Positivas**

- Elimina o maior item de latência do pipeline sem escrever otimização nenhuma:
  é decisão de ciclo de vida, não de código quente.
- O readiness passa a significar o que o nome promete, e a fila deixa de ser
  aceita por um worker que não pode honrá-la.
- Dá ao CARD-009 um critério de aceite verificável: dois jobs seguidos, o
  segundo sem custo de carga.

**Negativas — o preço aceito**

- **~1–2 GB de RAM ocupados o tempo todo**, mesmo com a fila vazia. Numa máquina
  hospedada barata, isso é a diferença entre caixas.
- **Restart custa ~6 s de fila parada.** Deploy fica mais caro de coordenar, e
  autoscaling por réplica efêmera fica inviável sem sobreposição.
- **Estado global no worker.** O `ctx` vira dependência implícita de toda task;
  esquecer de lê-lo e instanciar localmente **não quebra teste nenhum** — só a
  latência sobe. É a mesma classe de falha silenciosa do ADR-0021 e do
  ADR-0022, e pela mesma razão precisa de verificação executável.
- **O teste do worker fica mais lento ou mais falso:** ou paga a carga real, ou
  injeta fake no `ctx`. A escolha (fake por default, um teste marcado `slow` com
  o modelo real) é do CARD-009.
- **Uma dependência nova de operação:** a chave de heartbeat em Redis é mais uma
  coisa que pode ficar velha e mentir. TTL curto é o que impede.
