# ADR-0049 — `Correction` é entidade persistida, e os quatro campos texto do `/v1` viram derivação

- **Status:** aceito
- **Data:** 2026-08-26
- **Complementa:** [ADR-0008](0008-contrato-api-versionamento-e-tipos-gerados.md)
  (evolução aditiva), [ADR-0022](0022-ordem-dos-campos-da-resposta-do-professor-e-contrato-de-latencia.md)
  (a ordem dos campos é contrato de latência),
  [ADR-0028](0028-derivacao-da-etapa-do-turn-mora-no-dominio.md) (derivação mora
  no domínio) e [ADR-0031](0031-o-que-atravessa-a-porta-do-professor-e-um-fluxo-de-eventos.md)
  (o que atravessa a porta do professor)
- **Critérios de obrigatoriedade** (`docs/adr/README.md`):
  - **2 — define ou altera uma fronteira**: cria um formato de dados
    persistidos (tabela `turn_corrections`, dois tipos enum) e altera o contrato
    de API (`corrections[]` no `GET /v1/turns/{id}` e no evento SSE `feedback`);
  - **5 — seria difícil de reverter**: a escala de `severity` e os valores de
    `CorrectionType` viram dado gravado, e renomear um membro depois invalida
    todas as linhas existentes **e** quebra o cliente (ADR-0008).

## Contexto

A visão §A diz que `Correction` é a entidade mais valiosa do produto. Até este
card ela só **transitava**: nascia no LLM, virava um evento SSE, aparecia na tela
e sumia. Nada era guardado — o que travava o histórico (CARD-016), o padrão de
erro recorrente (pós-MVP) e a retomada completa do SSE (ADR-0041 item 5).

A forma herdada do protótipo era quatro campos texto no `TeacherFeedback` e no
`FeedbackPayload`:

```
has_mistakes: bool
original: str        # a frase inteira do aluno, verbatim
corrected: str       # a mesma frase com ~tildes~ e *asteriscos*
tip: str             # uma dica
```

Isso responde "houve erro?" e não responde nada do que o produto precisa: que
**tipo** de erro, **quanto** ele pesa, e **quais** foram, quando há mais de um. E
a marcação com til e asterisco é apresentação embutida no dado — o cliente não
pode renderizar de outro jeito sem fazer parsing de texto.

A restrição que dá forma a esta decisão é o **ADR-0008**: dentro de `/v1` é
proibido remover ou renomear campo, porque o app na loja não atualiza quando
queremos. Os quatro campos não podem simplesmente sair.

## Decisão

**`Correction` vira entidade de domínio persistida como coleção filha do `Turn`,
e os quatro campos texto do contrato `/v1` continuam existindo — derivados dela
por uma função pura no domínio, `legacy_summary`.**

1. **A entidade.** `Correction(index, type, original_excerpt, corrected_form,
   explanation, severity)`, `@dataclass(frozen=True, slots=True)`. `index` é
   0-based e denso e carrega **dois** significados: é a identidade natural
   dentro do turn (dispensando id surrogate, como o `TurnAudioChunk` do
   ADR-0023) **e** é a ordem pedagógica em que o professor priorizou as
   correções.
2. **Dois enums fechados.** `CorrectionType` (`grammar`, `vocabulary`,
   `preposition`, `word_order`, `other`) e `Severity` (`minor`, `moderate`,
   `major`), ambos `StrEnum` com `values_callable` no modelo — o Postgres guarda
   `word_order`, não `WORD_ORDER`, para que o valor no banco seja o mesmo que
   trafega no JSON. **Acrescentar membro é aditivo e permitido; renomear não é**,
   e renomear aqui é pior que na API porque invalida linha gravada.
   Três níveis de severidade porque a UI apresenta severidade em **palavras**
   (CARD-016): dois perdem o meio-termo, quatro exigem definir "critical" num
   tutor de conversa, o que nem o produto nem o modelo sabem fazer sem eval.
3. **Escrita write-once, no `attach_reply`.** As correções chegam todas juntas
   no `FeedbackReady`, que é o último evento do fluxo do professor. Elas entram
   na entidade **antes do `_gravar` que já existia** — viram N inserts na mesma
   escrita, não numa nova. Um segundo `attach_corrections` levanta: substituir
   apagaria a correção que o aluno já viu na tela.
4. **Os quatro campos velhos passam a ser derivados de `corrections[0]`**, por
   `legacy_summary`, no **domínio** e não na borda (ADR-0028). `has_mistakes`
   vira `bool(corrections)`. A regra é "a primeira", e não "a mais severa",
   porque o prompt v2 ordena o array por prioridade pedagógica — o índice 0 já
   **é** a correção que o professor destacaria. Escolher pela severidade
   acoplaria o campo legado à escala do enum, e acrescentar um nível (movimento
   aditivo e permitido) passaria a mudar o que um cliente antigo lê.
5. **Consequentemente, o modelo deixa de gerar os quatro campos.** Eles saem do
   `TeacherFeedback` e do schema da tool. Isso **não** fere o ADR-0008: aquela
   política protege o contrato HTTP, e `TeacherFeedback` é porta interna, com
   todos os consumidores no mesmo repositório — o `mypy` reprovou os 17 pontos
   que precisavam se pronunciar, no mesmo instante.
6. **`corrections` é o último campo da resposta do professor.** O ADR-0022
   fixou `spoken_reply` primeiro (único no caminho crítico) e `translation_pt`
   por último (mais descartável). O critério não mudou; o campo que ele aponta
   mudou, porque `corrections` é agora o mais longo de gerar, e cada byte gerado
   antes de `spoken_reply` fechar é atraso no primeiro áudio audível.
7. **Quando os campos velhos morrem:** no `/v2`, ou antes disso, quando o app
   mínimo suportado já ler `corrections[]` — pergunta que o `GET /v1/meta` sabe
   responder. Até lá, `legacy_summary` é a única tradução entre os dois.

## Alternativas consideradas

### Alternativa A — Persistir também as quatro colunas texto

- **O que é:** `turns` ganha `has_mistakes`, `original`, `corrected`, `tip`, e a
  API lê direto delas. Nenhuma derivação, nenhuma regra a escrever.
- **A favor:** o `GET` e a retomada ficam triviais; nenhuma pergunta sobre "quem
  preenche o campo velho quando há duas correções".
- **Por que foi rejeitada:** é a **mesma verdade gravada duas vezes**, e é
  exatamente o que o ADR-0016 recusou ao derivar a etapa do Turn em vez de
  gravá-la. Duas fontes saem de sincronia: bastaria uma correção ser editada (o
  que o CARD-016 pode pedir) para o campo texto passar a mentir, sem que nenhum
  teste de status percebesse. E o custo de não gravar é uma função de dez linhas
  com teste.

### Alternativa B — Manter os quatro campos gerados pelo modelo, ao lado de `corrections[]`

- **O que é:** o prompt v2 devolve as duas formas; a API entrega as duas.
- **A favor:** nenhuma regra de derivação a decidir, e o modelo escreve o resumo
  em prosa melhor do que uma função escolhe.
- **Por que foi rejeitada:** duas fontes que **podem se contradizer** — o
  `original` do modelo poderia não bater com nenhum `original_excerpt` da
  lista —, e ninguém sabe qual vence. Além disso é o pior desfecho de latência:
  o modelo gera o array **e** três strings a mais no mesmo caminho crítico. A
  medição confirmou o ganho de tirar: **1.425 tokens de saída no v2 contra 1.558
  no v1** nos mesmos seis casos.

### Alternativa C — `severity` como inteiro (1–5)

- **O que é:** uma escala numérica em vez de enum.
- **A favor:** ordenável no banco sem `CASE`, e cresce sem migration.
- **Por que foi rejeitada:** a UI apresenta severidade em **palavras**, e
  traduzir 1–5 para palavras exige uma tabela em algum lugar — que é o enum, só
  que implícito e sem verificação. Um número também convida a média ("severidade
  média do aluno: 2,7"), que é uma métrica sem significado pedagógico.

## Consequências

**Positivas**

- O histórico (CARD-016), o ErrorPattern (pós-MVP) e a retomada completa do SSE
  (ADR-0050) passam a ter insumo. Eram três coisas travadas pela mesma ausência.
- **Uma regra, um lugar.** "Quem preenche os campos velhos" tem resposta escrita,
  testada, e usada pelos dois caminhos (evento ao vivo e retomada). Antes disto a
  pergunta não tinha dono e cada chamador inventaria a sua.
- **O contrato ficou mais preciso sem ficar mais caro.** `original_excerpt` é o
  menor trecho verbatim com o erro, em vez da frase inteira; `corrected_form` é
  texto limpo, sem `~til~` e `*asterisco*` — o cliente renderiza como quiser em
  vez de fazer parsing.
- O app compila **sem nenhuma mudança**, o que é a prova operacional de que a
  evolução foi aditiva de fato.

**Negativas — o preço aceito**

- **A latência do primeiro áudio piorou.** Nos seis casos fixos, a primeira
  sentença falável saiu em **0,845 s de média no v2 contra 0,771 s no v1** —
  **+74 ms**. É o preço de um objeto estruturado ser mais lento de começar a
  fechar que uma string. Está medido e escrito porque o ADR-0022 existe
  justamente para que este número não se degrade em silêncio.
- **O custo por chamada subiu ~5%.** O prompt v2 é maior (8.927 tokens de
  entrada contra 7.451 nos seis casos), e o ganho de 133 tokens de saída não
  compensa inteiro. É relevante para o teto do ADR-0010 e some no dia em que o
  prompt caching for ligado (ADR-0021), porque o prompt é prefixo estável.
- **Os quatro campos legados são dívida com data mas sem prazo.** Eles ficam até
  o `/v2` ou até o app mínimo suportado ler `corrections[]`, e enquanto ficarem,
  toda mudança na regra de derivação muda o que um cliente antigo lê.
- **`severity` foi decidido sem eval.** A escala de três níveis é um palpite
  informado pela tela do CARD-016, não um resultado medido. **Gatilho para
  revisitar:** o eval da Fase 4 mostrar que o modelo usa um dos três níveis em
  menos de 10% das correções, ou que a UI precisa de uma distinção que a escala
  não faz.
- **`OTHER` é uma válvula de escape que pode virar lixeira.** Se ele passar a
  dominar a distribuição, a taxonomia está errada — e só o ErrorPattern
  (pós-MVP) vai medir isso.

**Equivalente mental .NET:** os quatro campos legados são um `[Obsolete]` que
não pode ser removido, implementado como propriedade calculada sobre a coleção
nova em vez de campo espelhado — a diferença entre uma *view* e uma coluna
desnormalizada, com a mesma consequência conhecida (a segunda desatualiza).
