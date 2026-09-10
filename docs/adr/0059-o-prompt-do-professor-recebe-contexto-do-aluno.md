# ADR-0059 — O prompt do professor deixa de ser estático: ele recebe um bloco de contexto do aluno

- **Status:** aceito
- **Data:** 2026-09-09
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **2 — define ou altera
  uma fronteira** (a porta `TeacherLlm` passa a receber um insumo novo) e **3 —
  afeta custo recorrente** (o prompt deixa de ser prefixo estável, o que muda a
  conta do ADR-0021 sobre prompt caching).
- **Relacionado:** ADR-0020/0021 (caching), ADR-0022 (ordem dos campos),
  ADR-0031 (a porta é um fluxo de eventos), ADR-0055 (idioma detectado)

## Contexto

Dois dos cinco apontamentos do primeiro uso real terminam no mesmo lugar:

- **ponto 5** — *"o nível do aluno não entra na conversa"*. `Student` não tem
  campo de nível (a docstring de `domain/student.py:9` diz "Fase 6"), enquanto a
  visão de produto diz que a estimativa CEFR **entra no MVP na forma barata**
  (`visao-produto-e-arquitetura-alvo.md:40`). Visão diz MVP, backlog diz Fase 7,
  e não havia card — é um buraco de planejamento que o uso real cobrou;
- **ponto 3, segunda metade** — decidido em 2026-09-09 que o aluno que fala
  português deve ser **entendido e tratado pedagogicamente** (ADR-0055), o que
  só é possível se o professor souber que houve português.

Hoje `prompts/teacher/v2.md` é um arquivo **estático**, lido uma vez e enviado
igual a cada turno. Nada do aluno chega até ele além da transcrição e do
histórico. Não há mecanismo para "este aluno é A2" nem para "esta fala veio em
português" — e inventar dois mecanismos diferentes para duas informações sobre o
mesmo aluno seria construir o mesmo caminho duas vezes.

## Decisão

**A porta do professor passa a receber um bloco de contexto do aluno, e o prompt
passa a ter uma seção montada em tempo de execução a partir dele.**

1. **Um objeto, não parâmetros soltos.** `StudentContext`, value object de
   `application`, com os campos que existirem: nível declarado, nível estimado
   (quando o CARD-046 o produzir), idioma detectado da fala do turno. Parâmetros
   soltos obrigariam a mexer na assinatura da porta a cada informação nova —
   e este ADR existe porque já há duas.
2. **O prompt estático continua estático, e o contexto vai DEPOIS dele.** O
   arquivo `v2.md` não ganha interpolação. O contexto é um bloco anexado ao
   final do prompt de sistema, delimitado. Isso não é estilo: é o que preserva
   o **prefixo estável** de que o ADR-0020 falava — se o caching voltar (o
   ADR-0021 o adiou por não alcançar 4.096 tokens, com a distância medida em
   36%), o pedaço grande e imutável continua na frente, e só a cauda varia.
   Montar o contexto no meio do arquivo destruiria essa propriedade para sempre.
3. **O contexto é dica, nunca comando.** O prompt instrui o professor a *usar* o
   nível para calibrar vocabulário, velocidade e tolerância a erro — e a **não**
   anunciá-lo ao aluno. A visão é explícita: nível é faixa apresentada com
   confiança, nunca veredito, e um professor que diz "como você é A2, vou falar
   devagar" transforma uma estimativa em rótulo. O mesmo vale para o idioma
   detectado: `pt` é uma dica de que o aluno pode ter falado português, e a
   detecção erra em fala curta (ADR-0055) — o professor trata a possibilidade,
   não o fato.
4. **A ordem dos campos da resposta não muda.** O ADR-0022 é contrato de
   latência: `spoken_reply` continua sendo a primeira chave, e nada neste ADR
   toca a saída. O contexto muda o que entra, não o que sai.
5. **Ausência é o caso normal.** Aluno sem nível declarado, turn sem idioma
   detectado: o bloco simplesmente não aparece, e o professor se comporta como
   hoje. Nenhum campo do contexto é obrigatório, e nenhum ganha default
   inventado — "supor B1 quando não sei" seria pior que não saber.

## Alternativas consideradas

### Alternativa A — um prompt por nível (seis arquivos)

`teacher/v2-a1.md` … `teacher/v2-c2.md`, escolhidos por chave. Cada um seria um
prefixo perfeitamente estável, ótimo para caching. Rejeitada por dois motivos:
multiplica por seis o custo de toda mudança pedagógica futura (uma regra nova de
correção vira seis edições e seis chances de divergir), e **não acomoda a
segunda dimensão** — idioma detectado multiplicaria de novo. O caching, que era
a única vantagem real, está adiado por medição própria (ADR-0021).

### Alternativa B — interpolar variáveis dentro do `v2.md`

`Você está conversando com um aluno {nivel}.` no meio do texto. É o que qualquer
template engine faria. Rejeitada pelo item 2: mataria o prefixo estável, que é
uma propriedade que este projeto **mediu** e sobre a qual escreveu dois ADRs.
Também espalha a lógica de montagem por um arquivo de conteúdo, onde nenhum
teste a alcança.

### Alternativa C — mandar o contexto como primeira mensagem do usuário

Em vez de anexar ao sistema, injetar um turn sintético. Rejeitada porque
confunde contexto com fala: o histórico da conversa é dado pedagógico e vai
inteiro para o `Turn`; um turn falso poluiria histórico, contagem e qualquer
leitura futura das `Correction`.

## Consequências

- **Positivas:** um mecanismo serve às duas necessidades e às próximas
  (`ErrorPattern`, objetivos de estudo) sem novo ADR. O nível finalmente muda a
  conversa, que é o pedido do ponto 5. O professor pode reagir ao português em
  vez de fingir que não aconteceu.
- **Negativas:** o prompt deixa de ser reproduzível a partir de um arquivo só —
  para saber o que o modelo recebeu num turn é preciso reconstruir o contexto
  daquele momento, o que é dívida de observabilidade que aparece na primeira
  depuração de resposta estranha (mitigação: registrar o bloco montado no span
  do turn, não o prompt inteiro). A conta do ADR-0021 muda: um prefixo estável
  seguido de cauda variável é justamente o formato que o caching premia, e
  reabrir a medição vira consequência deste ADR, não item independente. E há
  **risco pedagógico real**: um nível errado no contexto piora a conversa de
  forma silenciosa — o professor fala fácil demais para quem podia mais, e
  ninguém percebe pelo log.
- **Equivalente mental .NET:** é a diferença entre uma constante `const string
  SystemPrompt` e um `SystemPrompt + BuildContextBlock(student)` — trivial em
  qualquer linguagem, e o que custa não é a concatenação: é ter decidido, por
  escrito, que ela vai no fim e não no meio.
