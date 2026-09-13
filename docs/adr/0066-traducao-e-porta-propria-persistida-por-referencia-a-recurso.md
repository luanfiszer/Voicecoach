# ADR-0066 — Tradução é porta própria, persistida, e endereçada por referência a recurso

- **Status:** aceito
- **Data:** 2026-09-13
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **1 — introduz uma
  dependência** (uma sexta porta, `Translator`, com adapter próprio sobre a
  Anthropic); **2 — define ou altera uma fronteira** (novo endpoint
  `POST /v1/turns/{id}/translations`, nova tabela `turn_translations`, novo
  enum persistido); **3 — afeta custo recorrente** (é a primeira funcionalidade
  que gasta LLM fora do loop de conversa).
- **Relacionado:** ADR-0009 (forte para pedagogia, barato para auxiliares),
  ADR-0010 (política de custo), ADR-0051 (custo congelado na escrita),
  ADR-0042 (a restrição do banco é a lei; a consulta é uma foto), ADR-0053
  (resiliência da fronteira externa), ADR-0063 (kill switch), CARD-036

## Contexto

O botão `traduzir` do artboard 06 está no design desde 2026-08-17 e não tinha
servidor. Traduzir é a **primeira funcionalidade do produto que gasta dinheiro
fora do loop de conversa** — e o loop é protegido por cota (ADR-0063) enquanto
o botão não era protegido por nada.

Três perguntas do card não tinham resposta escrita, e cada uma muda o desenho:
tradução é uma porta nova ou mais um papel da porta do professor? o "não pagar
duas vezes" é cache ou persistência? e como registrar o consumo, se a tabela
que o CARD-014 criou tem chave primária `turn_id` — já ocupada pelo turn da
conversa?

## Decisão

**1. Porta própria `Translator`, não um segundo método em `TeacherLlm`.** A
regra do projeto é *nome de porta é a capacidade* (visão §D), e as duas
capacidades divergem em quatro eixos: forma (fluxo de eventos × uma chamada,
um valor), latência (caminho crítico de 1,8 s × o aluno pediu e espera),
modelo (o forte × o barato do ADR-0009) e estado (histórico da conversa ×
nenhum). Um método a mais na porta do professor obrigaria **todo dublê de
`TeacherLlm`** a implementar tradução para continuar satisfazendo o `Protocol`,
e amarraria a troca do modelo forte à do barato. O adapter da Anthropic passa a
ter dois arquivos, não dois papéis.

**2. O endpoint traduz REFERÊNCIA A RECURSO, nunca texto do cliente.** O corpo
é `{target, index}` — `reply` (a resposta do professor) ou `correction` +
índice. Não existe campo `text`. É a decisão de segurança que o card nomeia
primeiro: um endpoint que traduz texto livre é um proxy de LLM aberto pago por
nós. O idioma de destino está no **nome do método da porta**
(`to_portuguese`), não em parâmetro, pela mesma razão — um parâmetro
convidaria a borda a repassar o que veio do cliente.

**3. Persistência, não cache** (RNF1, a espinha do card). O texto de origem é
imutável depois de gravado, então a tradução **nunca invalida**: não há TTL a
escolher nem gatilho de invalidação a escrever. Tabela `turn_translations` com
a identidade natural `(turn_id, target, index)` como chave primária composta —
a mesma disciplina do `TurnAudioChunk` (ADR-0023) e do `Correction`
(ADR-0049), sem id surrogate. É essa chave que implementa o "não pagar duas
vezes" (RF4) contra concorrência: duas requisições simultâneas passam as duas
pela consulta e só uma grava; a outra recebe `ConflictingWriteError`, relê e
devolve o texto da vencedora. **A janela em que as duas pagam ao provedor é
real e aceita** — é o mesmo tipo de desperdício raro que o ADR-0042 já aceitou
com o objeto órfão no storage, e fechá-la exigiria um lock distribuído para
economizar frações de centavo.

**Isto não é o dado derivado que o ADR-0016/0049 recusou.** Lá, o campo
espelhado podia ser recalculado por função pura, e por isso duplicava verdade.
Traduzir é uma chamada paga, externa e não-determinística: guardar o resultado
é memoização de trabalho caro, não segunda fonte de verdade.

**4. O custo é congelado na linha da tradução e somado ao `ServiceBudget` —
e NÃO num `UsageEvent`.** Aqui o card e o código colidem, e a colisão está
resolvida a favor do código existente: o RF3 pede "registrado como consumo
(`UsageEvent`)", mas a chave primária daquela tabela é o `turn_id` ("um turn,
um evento", invariante que o CARD-014 protege com teste). Um turn traduzido já
tem o evento da conversa, e o segundo INSERT é recusado pelo banco. O consumo é
então registrado onde ele **pode** ser registrado sem quebrar aquela
invariante: `turn_translations.estimated_cost_usd`, com a mesma precisão
(`NUMERIC(12,8)`), a mesma regra de nulo ("não sabemos precificar", nunca
"grátis") e o mesmo congelamento na escrita do ADR-0051. O RNF3 (contar no kill
switch) é cumprido literalmente, chamando `ServiceBudget.add_cost` — o mesmo
contador que o `ProcessTurn` alimenta e que o `POST /turns` consulta.

**A ordem das operações é sobre dinheiro:** a consulta ao que já foi traduzido
vem **antes** do kill switch. Uma tradução já paga é resposta pronta; recusá-la
porque o orçamento do dia estourou cobraria o aluno pelo estado do caixa sem
que nenhuma chamada nova acontecesse. É o mesmo raciocínio do reenvio
idempotente do ADR-0063 (F11 do CARD-015).

**5. Resiliência: timeout curto e retry do SDK, sem breaker.** O breaker do
ADR-0053 protege contra **repetição em série** num worker com `MAX_JOBS = 1` —
um aluno depois do outro pagando 30 s para descobrir a mesma coisa. Traduzir é
iniciado pelo aluno, tem rate limit próprio (RNF2: 10/min por aluno, mais o
teto por IP) e falha em 15 s num 503 que a tela explica (RF6). **Gatilho para
acrescentar o breaker:** a tradução passar a ser chamada de dentro do worker,
ou o log mostrar rajadas de `TranslatorError` em série.

## Alternativas consideradas

### Alternativa A — mais um método em `TeacherLlm`

Menos arquivos, e o adapter da Anthropic já tem cliente construído. Rejeitada
pelo custo em teste, que é onde ele aparece: todo dublê da porta do professor
(há vários, em quatro arquivos de teste) passaria a precisar de um
`to_portuguese` que aqueles testes nunca chamam — e o `mypy` cobraria cada um
deles, em silêncio sobre o motivo.

### Alternativa B — coluna `translated_*` em `turns` e em `turn_corrections`

Nenhuma tabela nova, nenhum repositório novo. Rejeitada por duas razões
independentes: `Correction` é `frozen=True` e **write-once** por decisão do
ADR-0049 (um segundo `attach_corrections` levanta), e uma coluna mutável ao
lado dela contradiria essa invariante; e uma coluna em `turns` resolveria
apenas metade dos alvos, deixando o outro sem lugar.

### Alternativa C — Redis com TTL, como o `ServiceBudget`

O reflexo natural de "não repetir trabalho caro". Rejeitada porque o problema
não tem a forma de cache: nada invalida, então qualquer TTL é uma data
arbitrária em que o produto **volta a pagar** pela mesma tradução. E o Redis
deste projeto é infraestrutura efêmera (fila e contadores); um `FLUSHALL` num
incidente apagaria dado pelo qual o aluno já pagou.

### Alternativa D — traduzir preventivamente, junto da resposta do professor

Zero latência para o aluno. Rejeitada — é o corte da visão §F, reafirmado no
RNF6 do card: pagaria tradução para toda resposta para servir a fração que
alguém pede. **Gatilho para reabrir:** medir que quase todo aluno traduz quase
toda resposta.

## Consequências

- **Positivas:** o botão do artboard 06 sai do condicional em que o CARD-016 o
  deixou; o gasto com tradução é medido por linha e entra no mesmo teto global
  do resto (RNF3), então a pergunta "quantas traduções por sessão?" passa a ter
  resposta; e o `assistant_model`, que existia em `config.py` sem nenhum
  consumidor desde o ADR-0009, ganha o primeiro.
- **Negativas:** é a **sexta porta** do sistema, e cada porta é mais um dublê a
  manter. A janela de corrida em que duas requisições simultâneas pagam pela
  mesma tradução existe e está aceita. E o custo da tradução **não** aparece no
  `totals_for_student` do CARD-014 — quem quiser o gasto total de um aluno
  precisa somar duas tabelas. **Gatilho para unificar num livro-razão só:** a
  primeira pergunta de negócio que precise do custo total por aluno (a tela de
  perfil do CARD-033 hoje mostra minutos, não dinheiro).
- **Pendente de revisão humana:** a decisão 4 contraria a letra do RF3, que
  nomeia `UsageEvent`. O desenvolvedor pode preferir o caminho mais caro —
  quebrar a PK de `usage_events` para admitir mais de um evento por turn, com
  um discriminador de tipo — e nesse dia a linha da tradução vira uma
  migration de consolidação. Está escrito aqui para ser decidido com
  informação, não descoberto depois.
- **Equivalente mental .NET:** a porta nova é mais uma interface no contêiner
  com sua própria `HttpClient` nomeada (política de retry própria, e não a do
  cliente do professor); a tabela de traduções é uma tabela de memoização
  persistente com chave composta — o análogo de um `[MemoryCache]` que virou
  `DbSet` porque o item nunca expira e recomputá-lo custa dinheiro.
