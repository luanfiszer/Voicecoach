# ADR-0020 — Prompt caching no adapter do professor, com o prompt tratado como prefixo estável

- **Status:** **substituído por [ADR-0021](0021-prompt-caching-adiado-o-limiar-medido-nao-e-alcancado.md)**
  — a premissa central (prefixo mínimo cacheável de ~1.024 tokens) foi medida e
  é falsa para o `claude-haiku-4-5`: o limiar real é **4.096 tokens**, que uma
  conversa deste produto não alcança. O documento fica como registro do
  raciocínio; **a decisão em vigor é a do ADR-0021**.
- **Data:** 2026-08-19
- **Relacionado:** ADR-0009 (estratégia de modelos), ADR-0010 (política de custo),
  CARD-007 (adapter do professor)
- **Consome:** [`docs/analise-custo-e-precificacao.md`](../analise-custo-e-precificacao.md)

## Contexto

A sessão de medição de latência decompôs o custo de um turn e encontrou um
resultado que nenhum documento do projeto registrava: com STT e TTS locais
(ADR-0011), **100% do custo variável é o LLM**, dividido meio a meio entre
entrada e saída.

| Componente de um turn | Tokens | Custo | Fatia |
|---|---|---|---|
| Entrada — system prompt (~700) + histórico (~1.300) | ~2.000 | US$ 0,002 | 50% |
| Saída — JSON de correções + fala + tradução | ~400 | US$ 0,002 | 50% |
| STT e TTS locais | — | US$ 0 | 0% |

Metade do custo é, portanto, **reenvio de texto que não mudou**: o system prompt
é idêntico em toda chamada, e o histórico é o mesmo prefixo acrescido de um turn.
A API da Anthropic cobra leitura de cache a **0,1×** do preço de entrada.

Há uma segunda força, de arquitetura e não de custo: o caching **só funciona se
o prefixo for byte-idêntico**. Isso transforma "o prompt é um arquivo estável" de
boa prática em **requisito verificável** — e o CARD-007 já ia versionar o prompt
em `prompts/teacher/v1.md` por causa do eval. As duas exigências convergem.

Restrição real da API, que molda a decisão: o prefixo mínimo cacheável é de
**~1.024 tokens**. O system prompt sozinho (~700) fica **abaixo** disso.

## Decisão

**O adapter do professor trata system prompt + histórico como um prefixo estável
e marca o ponto de cache no fim do histórico, não no fim da mensagem.**

1. **Ordem de renderização fixa e estável**: `system` (arquivo versionado,
   carregado uma vez no boot) → histórico em ordem cronológica → a fala nova do
   aluno. O conteúdo volátil vem **sempre depois** do último ponto de cache.
2. **Nada de conteúdo volátil no prefixo.** É proibido injetar no system prompt
   ou no histórico: data/hora corrente, identificador de request, nome do aluno
   interpolado, contador de turn, ou qualquer valor que mude entre chamadas.
   Um único byte diferente invalida tudo depois dele.
3. **O cache não engata no primeiro turn de uma conversa**, e isso é aceito: com
   ~700 tokens de system, o prefixo só cruza o mínimo de ~1.024 quando o
   histórico entra. Não haverá padding artificial para forçar o cache —
   inflar o prompt para economizar é trocar custo por custo.
4. **O efeito é verificado, não presumido.** O adapter registra
   `usage.cache_read_input_tokens` e `usage.cache_creation_input_tokens` por
   chamada. `cache_read_input_tokens` igual a zero em turns subsequentes de uma
   mesma conversa é **defeito**, não variação — é o sinal de que alguém
   introduziu um invalidador silencioso no prefixo.
5. **O `UsageEvent` do CARD-014 passa a registrar as três contagens de entrada
   separadamente** (não-cacheada, escrita em cache, leitura de cache). Sem isso,
   o custo real fica indistinguível do custo bruto e a economia vira fé.

## Alternativas consideradas

### Alternativa A — Não fazer nada (status quo)

- **O que é:** reenviar system + histórico a preço cheio em toda chamada.
- **Por que foi rejeitada:** deixa ~30–35% do custo total na mesa em troca de
  nada. O trade-off que normalmente justificaria não otimizar — complexidade —
  aqui quase não existe: é um campo na requisição e uma regra sobre o que **não**
  colocar no prefixo. E a regra do §2 é boa higiene de prompt de qualquer forma.

### Alternativa B — Encurtar o system prompt e o histórico

- **O que é:** atacar a mesma metade da conta reduzindo o que se envia — cortar
  instruções do prompt do professor, apertar a janela de histórico.
- **Por que foi rejeitada:** troca custo por **qualidade pedagógica**, que é
  exatamente o câmbio que este projeto não sabe fazer ainda por não ter eval com
  baseline (Fase 4). O caching entrega economia comparável **sem** tocar em uma
  palavra do prompt. A janela de histórico (alavanca C da análise de custo)
  continua disponível depois, e com caching ela fica menos urgente: prefixo longo
  deixa de ser caro.

### Alternativa C — Cache com TTL de 1 hora em vez do padrão de 5 minutos

- **O que é:** a API oferece TTL estendido, a um custo de escrita maior.
- **Por que foi rejeitada por ora:** o padrão de uso do produto é uma conversa
  contínua, com turns separados por dezenas de segundos — a janela de 5 minutos
  cobre isso com folga. O TTL de 1 h pagaria escrita mais cara para atender o
  aluno que volta ao app meia hora depois, e não há dado nenhum sobre a
  frequência desse caso. Reavaliar quando o `UsageEvent` (item 5) mostrar a
  distribuição real de intervalo entre turns — decisão medida, não estética.

### Alternativa D — Batch API (50% de desconto)

- **O que é:** enviar as chamadas ao LLM pela API de lotes.
- **Por que foi rejeitada:** é assíncrona com latência de horas. O produto é uma
  conversa; o orçamento de latência da visão §D é de segundos. Desconto que
  destrói o produto não é alternativa — está aqui só para ficar registrado que
  foi considerada e por quê.

## Consequências

**Positivas**

- ~30–35% do custo variável, sem tocar em uma palavra do prompt do professor e
  sem qualquer efeito sobre a resposta que o aluno recebe.
- Uma regra de higiene virou **contrato verificável**: "o prefixo é estável" deixa
  de ser intenção e passa a ter um número que denuncia a violação
  (`cache_read_input_tokens`).
- O item 5 dá ao CARD-014 a decomposição de custo real — pré-requisito para o
  kill switch do CARD-015 medir o que acha que está medindo.
- Converge com o que o CARD-007 já ia fazer por causa do eval (prompt em arquivo
  versionado), em vez de competir com isso.

**Negativas — o preço aceito**

- **Uma nova classe de bug silencioso.** Injetar um timestamp no prompt não
  quebra nada visível: as respostas continuam certas e o custo simplesmente sobe.
  É a pior forma de regressão — só o item 4 a torna detectável, e só se alguém
  olhar.
- **Uma restrição permanente sobre o prompt.** Personalizar o system prompt por
  aluno (nome, nível CEFR, erros recorrentes) passa a ter custo: ou o campo
  personalizado vai depois do ponto de cache, ou o cache morre. Isso amarra o
  desenho das features de personalização da Fase 6 — e é melhor amarrar agora,
  conscientemente, do que descobrir depois.
- **Nenhum ganho no primeiro turn** de cada conversa (item 3).
- O acoplamento a um detalhe de cobrança de um provedor específico entra no
  adapter. Aceitável porque é **exatamente ali** que ele deve morar: a porta
  `TeacherLlm` não muda, e um adapter de outro provedor simplesmente ignora o
  conceito.

**Equivalente mental .NET:** é um cache de saída com chave por prefixo, do lado
do provedor — parecido com `ETag`/`If-None-Match`, no sentido de que a economia
depende de a representação ser byte-idêntica. A analogia mais próxima no dia a
dia é um `MemoryCache` cuja chave é a concatenação de tudo que veio antes: mudou
um caractere no começo, a chave é outra e o cache inteiro é inútil — sem que
nada falhe.

## Como se verifica que esta decisão está viva

`usage.cache_read_input_tokens > 0` a partir do segundo turn de uma mesma
conversa. Zerou de forma persistente ⇒ há invalidador silencioso no prefixo,
e a lista de suspeitos é curta e está no item 2.
