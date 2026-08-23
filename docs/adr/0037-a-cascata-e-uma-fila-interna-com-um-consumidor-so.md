# ADR-0037 — A cascata é uma fila interna com um consumidor só, não uma task por sentença

- **Status:** aceito
- **Data:** 2026-08-23
- **Complementa:** [ADR-0023](0023-ciclo-de-vida-do-turn-com-entrega-em-cascata.md)
  (trechos e índice denso), [ADR-0031](0031-o-que-atravessa-a-porta-do-professor-e-um-fluxo-de-eventos.md)
  (o fluxo do professor e o cancelamento), [ADR-0003](0003-interacao-v1-turn-based-preparada-para-v2-realtime.md)
  (costura 4: passos componíveis)
- **Critérios de obrigatoriedade:** **5 — seria difícil de reverter**. A forma da
  concorrência entre síntese e gravação vira contrato assim que houver consumidor
  (CARD-010/012), e o modo de falha da forma errada é intermitente.

## Contexto

O CARD-009 introduz **um único paralelismo**: *"a síntese da sentença N+1 não
espera o envio da N"*. É de onde vem o ganho de latência da cascata — e é a única
decisão de concorrência do V1.

Ela tem duas formas possíveis, e a mais curta é a errada. `asyncio.create_task`
por sentença é o que qualquer pessoa escreve primeiro: três linhas, paralelismo
óbvio. Mas **não preserva ordem nenhuma** — e a ordem aqui é invariante de
domínio: `Turn.append_audio_chunk` exige índice **denso e crescente**
(ADR-0023), e a chave `reply/{index:03d}.aac` do ADR-0024 codifica a ordem de
playback na ordenação lexicográfica do bucket.

**O modo de falha foi medido nesta sessão, e são dois, não um.** Rodando a
variante com `create_task` e atrasos de TTS invertidos:

```
create_task, append imediato : SEM ERRO — ordem gravada = ['segunda', 'terceira', 'primeira']
create_task, await no meio   : OutOfOrderAudioChunkError: esperado índice 1, recebido 0
```

O erro só aparece quando duas sínteses terminam no **mesmo instante**, porque é
só aí que duas corrotinas ficam simultaneamente entre "ler o índice" e "gravar"
— e no código real há dois `await` nesse meio (`encoder.encode` e `storage.put`).
Quando os tempos não empatam, **não há exceção nenhuma**: os trechos gravam
densos, na ordem errada, e o aluno ouve a resposta embaralhada. A cara mais
provável do bug é a silenciosa, e ela depende do tamanho do texto — o pior tipo
de defeito para descobrir em produção.

## Decisão

**A cascata são duas corrotinas ligadas por uma `asyncio.Queue`, dentro de um
`asyncio.TaskGroup`. A ordem é preservada por construção, não por coordenação.**

```
sintetizar()  async for evento in teacher.respond_streaming(history):
                  SpokenSentence → await tts.synthesize(txt) → fila.put(...)
                  FeedbackReady  → guarda
gravar()      while item := await fila.get():
                  encoder.encode → storage.put → turn.append_audio_chunk → publica
```

1. **Um consumidor, fila FIFO.** Nada coordena a ordem porque nada pode
   desordená-la: existe um único chamador de `append_audio_chunk`, e ele é
   sequencial. O índice é calculado **dentro** do consumidor
   (`len(turn.audio_chunks)`), nunca no produtor.
2. **O paralelismo que interessa continua existindo**, e é exatamente o que o
   card pediu: enquanto o trecho N é codificado e sobe para o storage, a síntese
   de N+1 já está correndo. O que **não** existe é paralelismo entre gravações.
3. **`TaskGroup` e não `gather`:** quando uma corrotina falha, a irmã é
   cancelada e o `async with` só sai depois que as duas terminaram. Cancelar a
   produtora é o que **fecha o gerador do professor** — e é assim que o produto
   para de pagar por tokens que ninguém vai ouvir (ADR-0031, item 6). Não há
   `CancellationToken` a repassar: o cancelamento é o próprio protocolo do
   gerador assíncrono.
4. **A sentinela vai no `finally` da produtora.** Se o professor levantar, o
   consumidor precisa acordar e terminar; sem isso o `TaskGroup` esperaria para
   sempre por uma fila que ninguém mais alimenta.
5. **O `ExceptionGroup` é desempacotado antes de subir.** O `TaskGroup` sempre
   agrupa, mesmo com uma falha só, e grupos podem aninhar. Quem chama o caso de
   uso espera `TtsError`, não `ExceptionGroup[TtsError]` — deixar o grupo subir
   obrigaria todo chamador e todo teste a saber que existe concorrência aqui
   dentro, que é o detalhe que este desenho encapsula.
6. **Storage antes do banco, banco antes do evento.** O app recebe o evento e vai
   buscar o áudio; uma linha apontando para objeto que ainda não subiu é um 404
   na mão do aluno. Na ordem inversa o pior caso é um objeto órfão no bucket, que
   a retenção de 1 dia (ADR-0024) recolhe sozinha.

**Equivalente mental .NET:** um `Channel<T>` com um produtor e um consumidor —
o pipeline clássico de `System.Threading.Channels`. `TaskGroup` é o mais perto de
`Parallel.ForEachAsync` com `CancellationToken` solidário, com a diferença de que
o erro sai empacotado num `ExceptionGroup` (o parente do `AggregateException`,
com sintaxe própria: `except*`).

## Alternativas consideradas

### Alternativa A — `asyncio.create_task` por sentença

- **O que é:** disparar síntese+gravação de cada sentença como task
  independente, aguardando todas no fim.
- **Por que foi rejeitada:** não preserva ordem, e a ordem é invariante de
  domínio. Demonstrado por execução (saída acima): ou levanta
  `OutOfOrderAudioChunkError` de forma intermitente, ou — pior — grava tudo
  densamente **fora de ordem**, sem exceção nenhuma, e o defeito só é audível.
  Nenhuma verificação de tipo, teste de status ou revisão de código pega a
  segunda forma.

### Alternativa B — `create_task` com índice reservado antes do `await`

- **O que é:** manter as tasks, mas atribuir o índice no momento em que a
  sentença é emitida (no produtor), antes de qualquer `await`.
- **Por que foi rejeitada:** conserta o índice e **não** conserta o resto. Os
  trechos continuariam sendo acrescentados à coleção fora de ordem (o `append`
  do índice 1 chegando antes do 0 ainda viola a invariante do ADR-0023), e os
  eventos `chunk` chegariam ao cliente embaralhados — o app teria que reordenar,
  o que empurra a complexidade para a ponta que menos pode pagá-la. Trocaria uma
  invariante de domínio por uma convenção de cliente.

### Alternativa C — Sequencial puro: sintetizar, gravar, sintetizar, gravar

- **O que é:** nada de concorrência; o laço faz tudo em ordem.
- **Por que foi rejeitada:** é o que o card explicitamente não permite cortar. O
  upload de cada trecho (93 ms medidos no ADR-0034) entraria inteiro no caminho
  crítico entre uma frase e a seguinte, num orçamento de 1,8 s. É a única
  alternativa **correta** das três, e ainda assim rejeitada — por latência, sob a
  regra de desempate "cede escopo, nunca latência".

## Consequências

**Positivas**

- **A ordem é irrepresentavelmente errada**, não "garantida por cuidado": não
  existe caminho no código em que dois `append_audio_chunk` corram concorrentes.
- Testável com fakes e atrasos invertidos, em milissegundos — o teste
  `test_a_segunda_sentenca_terminando_antes_da_primeira_nao_embaralha` falharia
  com qualquer das alternativas A ou B.
- O cancelamento do professor sai de graça do `TaskGroup`, sem token nem flag.
- Medição real (Apple Silicon, `mlx-whisper small.en` + Piper + `claude-haiku-4-5`):
  **1,56–1,61 s até o primeiro trecho gravado**, dentro do alvo de 1,8 s.

**Negativas — o preço aceito**

- **A síntese é serializada.** Duas sentenças nunca são sintetizadas ao mesmo
  tempo, ainda que houvesse CPU sobrando. É deliberado (o TTS é CPU-bound e
  disputa com o STT — ADR-0025), mas é um teto: se um dia o TTS for para GPU, o
  ganho não vem de graça.
- **Concorrência escondida atrás de uma fachada síncrona.** O caso de uso parece
  sequencial de fora, e o desempacotamento do `ExceptionGroup` é o que sustenta
  a ilusão. Quem mexer aqui precisa saber que ela existe — daí o docstring longo.
- **Uma fila sem limite de tamanho.** Um professor extraordinariamente rápido e
  um storage extraordinariamente lento acumulariam áudio em memória. Com 3 a 6
  trechos por turn (ADR-0023) é irrelevante; com TTS intra-frase do V2, não
  seria. **Gatilho para pôr `maxsize`:** o V2, ou qualquer mudança que faça o
  produtor emitir mais que dezenas de itens por turn.
