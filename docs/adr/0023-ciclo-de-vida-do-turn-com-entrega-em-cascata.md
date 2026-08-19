# ADR-0023 — Ciclo de vida do Turn com entrega em cascata: o áudio vira uma sequência de trechos

- **Status:** aceito
- **Data:** 2026-08-19
- **Substitui:** [ADR-0016](0016-ciclo-de-vida-do-turn-estado-grosso-e-etapa-derivada.md)
- **Relacionado:** ADR-0003 (costura 4), ADR-0008 (contrato aditivo),
  ADR-0022 (ordem dos campos), ADR-0024 (mídia por trecho)
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **2 — altera uma
  fronteira** (formato de dados persistidos e contrato do `GET /v1/turns/{id}`)
  e **5 — difícil de reverter** (migration + backfill sobre `turns`).

## Contexto

O ADR-0016 decidiu, e continua certo no princípio: **estado grosso persistido,
etapa derivada dos artefatos**, porque dado derivado que vira coluna sai de
sincronia. Ele foi escrito sob uma premissa que a virada de alvo derrubou:

> *"Artefatos com o instante em que ficaram prontos"* — cada artefato é **um**
> objeto, produzido **inteiro**, uma vez.

Com o alvo de **primeiro áudio em ~1,8 s**
([`analise-caminho-para-1-2s.md`](../analise-caminho-para-1-2s.md)), o pipeline
deixa de ser cadeia e vira **cascata**: o LLM gera `spoken_reply` em streaming
(ADR-0022), o parse fecha frase a frase, e cada frase é sintetizada e entregue
enquanto o resto ainda está sendo gerado.

Três premissas do ADR-0016 quebram:

1. **`audio_ref` singular.** Passa a existir uma sequência ordenada de trechos.
2. **A tabela de derivação.** No ADR-0016, `speaking` significa *"o texto da
   resposta está pronto, o TTS ainda não"*. Na cascata o **primeiro áudio
   existe antes de `reply_text` estar completo** — a ordem dos artefatos se
   inverte, e a tabela como está passa a mentir.
3. **`failed` como desfecho limpo.** Falhar depois de o aluno já ter ouvido duas
   frases não é o mesmo que falhar antes de ele ouvir qualquer coisa. O
   `Turn.fail()` do CARD-005 não distingue os dois.

## Decisão

**O `Turn` continua com estado grosso persistido e etapa derivada. O áudio da
resposta passa a ser uma coleção ordenada de trechos (`TurnAudioChunk`), e a
entrega parcial é derivada da existência de trechos — nunca de um campo novo de
status.**

1. **Estado persistido, inalterado:** `queued → processing → completed | failed`.
   A enum não ganha valor nenhum — é o que protege o ADR-0008.
2. **`TurnAudioChunk`**: entidade filha de `Turn`, com
   `index` (0-based, denso), `storage_key`, `duration_seconds`, `text`
   (a frase que gerou o trecho) e `created_at`. Ordenação por `index`, não por
   timestamp: o instante de criação é medição, a ordem é contrato de playback.
3. **`reply_audio_ref` continua existindo** e passa a apontar para o **áudio
   inteiro concatenado**, gravado ao completar o turn. Ele não é redundância
   descuidada: é o que mantém o contrato antigo verdadeiro (ADR-0008), o que o
   histórico (CARD-013/016) reproduz e o que a retenção (CARD-017) guarda depois
   que os trechos expiram (ADR-0024).
4. **Tabela de derivação nova** — a ordem dos artefatos mudou:

   | Condição (avaliada de cima para baixo) | Etapa |
   |---|---|
   | `reply_audio_ref` presente | `completed` |
   | existe ao menos um `TurnAudioChunk` | `speaking` |
   | `transcript` presente | `thinking` |
   | nenhum dos anteriores | `transcribing` |

   O vocabulário de etapas é **o mesmo** do ADR-0016. Um cliente antigo que
   ignore `chunks[]` continua correto: ele vê `speaking` e espera `completed`
   para tocar o áudio inteiro. A entrega progressiva é **aditiva**.
5. **Entrega parcial é derivada, não persistida:**
   `delivered_partially := status is failed and chunks is not empty`.
   Nada de coluna nova — é a mesma regra do ADR-0016 aplicada ao caso novo.
6. **`Turn.fail(reason)` continua sendo a única forma de falhar**, e passa a ser
   legal com trechos já gravados. O que o domínio ganha não é um estado — é uma
   **invariante**: *trecho entregue não é apagado por falha posterior*. O aluno
   ouviu; o registro tem de continuar dizendo que ele ouviu.
7. **`replied_at` passa a significar "o `spoken_reply` fechou por completo"**,
   e não mais "o texto ficou disponível ao cliente" — o texto agora sai por
   trecho, junto com o áudio.

### O que isto torna impossível por construção

Não existe turn `completed` sem áudio inteiro; não existe trecho com índice
furado; e não existe `failed` que apague o que já foi ouvido. Continua não
existindo status que minta sobre o payload, porque continua não havendo segundo
registro da mesma verdade.

## Alternativas consideradas

### Alternativa A — Manter `audio_ref` único e só entregar no fim

- **O que é:** não fazer nada; a cascata roda no worker mas o cliente só recebe
  o áudio completo.
- **Por que foi rejeitada:** joga fora exatamente o ganho que a cascata existe
  para produzir. O aluno voltaria a esperar ~4,1 s. É o alvo do produto trocado
  por não escrever uma tabela.

### Alternativa B — Estado por etapa persistido (`streaming_audio` como status)

- **O que é:** acrescentar um valor à enum de status para dizer "entregando".
- **Por que foi rejeitada:** duas fontes para a mesma verdade (é a Alternativa A
  do ADR-0016, com o mesmo defeito) **e** breaking change de contrato sob o
  ADR-0008 — cliente antigo que trate a enum exaustivamente quebra, e cliente
  mobile não atualiza quando queremos.

### Alternativa C — `TurnStep` como entidade (a Alternativa B do ADR-0016)

- **O que é:** modelar cada passo do pipeline como linha própria.
- **Por que foi rejeitada:** o gatilho escrito no ADR-0016 (*"a primeira vez que
  precisarmos reprocessar **uma** etapa sem refazer as outras"*) continua sem
  disparar. Trecho de áudio é **artefato**, não passo de workflow: ele tem
  conteúdo, chave de storage e duração. Modelá-lo como passo confundiria as duas
  coisas e traria o workflow engine que a visão §F corta.

### Alternativa D — Trechos só em memória/Redis, sem persistir

- **O que é:** o worker emite os trechos pelo transporte (ADR-0026) e só grava o
  áudio inteiro.
- **Por que foi rejeitada:** um cliente que reconecta no meio do turn perde o que
  já passou, e a medição ponta a ponta do CARD-012 (quando cada trecho ficou
  pronto) deixa de ter fonte. Persistir o trecho é o que torna a entrega
  **retomável** em vez de efêmera.

## Consequências

**Positivas**

- Desbloqueia o alvo de ~1,8 s sem tocar na enum de status e sem quebrar o
  contrato `/v1` (ADR-0008).
- `created_at` por trecho entrega de graça a métrica que o CARD-012 precisa:
  *quando o aluno pôde ouvir a primeira palavra* — que é a métrica do produto,
  não a soma das etapas.
- A falha depois da entrega parcial deixa de ser silenciosa: vira caso de uso
  explícito (o `Result` do ADR-0017 ganha o desfecho que faltava).

**Negativas — o preço aceito**

- **Uma tabela e um relacionamento a mais** (`turn_audio_chunks`), com migration
  e backfill trivial (nenhum turn existe ainda — este é o momento mais barato
  possível para pagar).
- **Áudio duplicado em storage**: os trechos e o inteiro coexistem por um
  tempo. Mitigado pela retenção assimétrica do ADR-0024 (trecho expira cedo,
  inteiro dura), mas é custo real de bytes.
- **A concatenação é trabalho novo no worker** e um ponto de falha novo: pode
  falhar *depois* de o aluno ter ouvido tudo. Nesse caso o turn é `failed` com
  os trechos intactos — que é feio de explicar e por isso está escrito aqui.
- **A derivação ficou mais sutil.** "Existe trecho" é uma condição sobre uma
  coleção, não sobre uma coluna; a consulta operacional piora de novo, e o teste
  da tabela de derivação passa a ser obrigatório, não recomendável.
- **`replied_at` mudou de significado** em relação ao ADR-0016. Quem ler o
  código sem ler este ADR vai supor o antigo.

**Equivalente mental .NET:** sai um `AudioRef?` no agregado e entra uma
`IReadOnlyList<TurnAudioChunk>` com `Stage` continuando propriedade calculada —
o mesmo movimento de "não persista o que você consegue derivar", agora com a
coleção fazendo o papel que uma coluna nullable fazia.
