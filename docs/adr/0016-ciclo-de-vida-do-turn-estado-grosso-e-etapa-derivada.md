# ADR-0016 — Ciclo de vida do Turn: estado grosso persistido, etapa derivada dos artefatos

- **Status:** aceito
- **Data:** 2026-08-18

## Contexto

O CARD-005 cria a entidade `Turn` e sua primeira migration. A sessão de
reconciliação entre as telas desenhadas e o domínio
([`docs/reconciliacao-telas-dominio.md`](../reconciliacao-telas-dominio.md))
encontrou uma **contradição interna já escrita no backlog**, anterior a qualquer
tela:

- **visão §D**: *"O status do Turn é por etapa com payload parcial — o app mostra
  o texto assim que o LLM termina, enquanto o TTS sintetiza."*
- **CARD-010** já especifica `GET /v1/turns/{id}` com
  `transcribing → thinking → speaking → completed` e payload parcial progressivo.
- **CARD-005** propunha `pending → processing → completed | failed`.

Com quatro estados, `processing` cobre STT + LLM + TTS inteiros: **o cliente não
tem como distinguir "transcrevendo" de "professor pensando"**. Teria que inventar
a diferença com um temporizador — mentira de UI. O `Design.pdf` (pág. 3) mostra o
requisito de forma literal: **"Passo 1 de 3"** e **"Passo 2 de 3"** com barra de
progresso proporcional, e um estado em que o texto já é legível enquanto o áudio
não chegou. *(O design é exploração, não decisão congelada — mas aqui ele apenas
ilustra o que a visão §D e o CARD-010 já exigiam.)*

Restrições que moldam a escolha:

- **ADR-0008** — o contrato `/v1` evolui **apenas aditivamente**. Acrescentar
  valor a uma enum de status **quebra** cliente antigo que trate os casos de
  forma exaustiva; e cliente mobile não atualiza quando queremos.
- **ADR-0003** — o V2 realtime reescreve a **orquestração** (~15–20% de descarte)
  mas promete que **a entidade sobrevive**. No V2 as etapas deixam de ser
  sequenciais: STT incremental e TTS em stream se sobrepõem.
- **ADR-0004** — mudar o formato depois custa migration + backfill.
- **CARD-012** exige medição ponta a ponta (gravei → texto visível → áudio
  tocável) para achar o gargalo real antes de otimizar.

## Decisão

**O `Turn` persiste um estado grosso de execução; a etapa exibida ao cliente é
derivada dos artefatos já produzidos, e calculada no servidor.**

1. **Estado persistido** (`TurnStatus`, enum pequena e estável):
   `queued → processing → completed | failed`. Ele responde uma pergunta só:
   *o trabalho terminou, e como terminou?*
2. **Artefatos com o instante em que ficaram prontos**, cada um nulo até existir:
   `transcript`/`transcribed_at`, `reply_text`/`replied_at`,
   `audio_ref`/`synthesized_at`.
3. **A etapa é função dos dados, não um campo a manter em sincronia:**

   | Artefato mais recente presente | Etapa |
   |---|---|
   | `audio_ref` | `completed` |
   | `reply_text` | `speaking` |
   | `transcript` | `thinking` |
   | nenhum | `transcribing` |

4. **A derivação mora no servidor**, na borda (`api/schemas`, CARD-010), **nunca
   no cliente** — senão a mesma regra é reimplementada no mobile e na web e as
   duas divergem.
5. **O domínio não expõe `queued` como etapa.** Nenhuma tela distingue "na fila"
   de "transcrevendo"; expor isso é vazar mecânica de infraestrutura no contrato.
6. **`failed` carrega o motivo e a etapa em que parou** — que a própria tabela
   acima entrega de graça, sem campo extra.

### O que isto torna impossível por construção

Não existe `status = speaking` com `reply_text` nulo. **O status não tem como
mentir sobre o payload**, porque não é um segundo registro da mesma verdade.

## Alternativas consideradas

### Alternativa A — Enum fina: mais estados na máquina do Turn

`queued → transcribing → thinking → synthesizing → completed | failed`.

- **O que é:** cada etapa vira um valor do estado persistido; o contrato é
  projeção direta da coluna.
- **A favor:** um campo só; consulta operacional trivial (`WHERE status =
  'synthesizing'` responde "quantos travaram no TTS?"); ordem total explícita.
- **Por que foi rejeitada:** cria **duas fontes para a mesma verdade** — o
  status e os artefatos. Um passo que falhe entre gravar o texto e atualizar o
  status deixa o registro em estado que a UI não sabe renderizar, e nada no
  banco impede `status='speaking'` com `reply_text` nulo. É a classe de bug que
  só existe porque escolhemos duplicar a informação. Some-se o **custo no V2**
  (ADR-0003): com STT incremental e TTS em stream sobrepostos, uma enum
  **linear** passa a mentir — é a alternativa que mais arrisca a promessa de que
  a entidade sobrevive à transição. E, sob o ADR-0008, mexer nessa enum depois é
  breaking change de contrato, não evolução aditiva.

### Alternativa B — `TurnStep` como entidade própria

`{turn_id, kind (stt|llm|tts), status, started_at, ended_at, error}`.

- **O que é:** cada etapa é uma linha, com histórico próprio.
- **A favor:** histórico completo; **retry por etapa** (refazer só o TTS sem
  repagar o LLM — economia real, ADR-0010); observabilidade rica; acomoda
  naturalmente as etapas concorrentes do V2.
- **Por que foi rejeitada:** uma tabela, um agregado e um join a mais para um
  pipeline de **três passos fixos e conhecidos**. É um workflow engine em
  miniatura — exatamente o tipo de peça que a Parte F da visão corta por
  antecipação. **Gatilho objetivo para entrar depois:** a primeira vez que
  precisarmos reprocessar **uma** etapa sem refazer as outras.

### Alternativa C — Manter `pending → processing → completed | failed` (o card original)

- **O que é:** não fazer nada; o cliente adivinha a etapa.
- **Por que foi rejeitada:** contradiz a visão §D e o CARD-010, que já estão
  escritos. A única forma de a UI mostrar "Passo 1 de 3" seria um temporizador —
  progresso falso, e o briefing de design proíbe explicitamente ("nunca spinner
  genérico parado"). Rejeitar aqui é mais barato que descobrir no CARD-012.

## Consequências

**Positivas**

- Status e payload não podem divergir: a etapa é **calculada** do que existe.
- Os timestamps por artefato entregam **de graça** duas coisas que já estavam
  pedidas: a medição ponta a ponta do CARD-012 e a detecção de "demorou mais que
  o normal" (o timeout de ~30s), que hoje não tem dono em card nenhum.
- Menor custo no V2 (ADR-0003): timestamp por artefato continua verdadeiro com
  pipeline sobreposto; só a função de derivação muda, e ela mora na borda —
  a camada que o ADR-0003 já assume descartável.
- A enum persistida é pequena e estável, o que combina com a evolução **aditiva**
  do `/v1` (ADR-0008): a granularidade fina vive no campo derivado, onde
  acrescentar um valor não exige migration.
- O CARD-010 entrega o que já prometeu, **sem mudar de escopo**.

**Negativas — o preço aceito**

- A derivação é lógica que precisa existir em algum lugar e ser testada; se um
  dia vazar para o cliente, o problema volta multiplicado por dois clientes.
- Consulta operacional fica mais verbosa: "travados no TTS" vira
  `status='processing' AND reply_text IS NOT NULL AND audio_ref IS NULL` em vez
  de um `=`. Aceitável enquanto isso for pergunta de dev, não de dashboard.
- Mais colunas nulas na tabela `turns` — nulo aqui **significa** "ainda não
  aconteceu", e é o que torna a derivação possível; mas exige disciplina para
  não confundir "não aconteceu" com "não se aplica".
- Não há histórico de etapa: se o TTS falhar e for refeito, o instante da
  primeira tentativa se perde. Quem quiser isso paga a Alternativa B, com o
  gatilho já escrito.

**Equivalente mental .NET:** é a diferença entre persistir um `enum Status` com
um valor por passo e persistir um agregado cujos campos opcionais (`Transcript`,
`ReplyText`, `AudioRef`) *são* o estado, com uma propriedade calculada
(`Stage => AudioRef is not null ? ... : ...`) projetada no DTO. A regra é a
mesma dos dois lados: **não persista o que você consegue derivar** — dado
derivado que vira coluna é o que sai de sincronia.
