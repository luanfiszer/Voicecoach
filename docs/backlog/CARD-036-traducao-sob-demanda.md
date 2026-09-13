# CARD-036 — Tradução sob demanda: o botão `traduzir` ganha um servidor

- **ID:** CARD-036
- **Épico:** Fase 3 — Domínio pedagógico (backend do `traduzir` do artboard 06)
- **Plataforma:** backend · **Esforço:** P · **Status:** concluído (2026-09-13)
- **Dependências:** CARD-013 (concluído), CARD-014 (concluído — é o instrumento de custo), CARD-026; ADR-0009, ADR-0010, ADR-0051

## Contexto

O botão `traduzir` está no artboard 06 desde 2026-08-17 e ficou confirmado em
2026-08-27. O CARD-016 sempre o tratou condicionalmente — *"chamando a tradução
on-demand (se o endpoint já existir; senão, entra no escopo aqui)"* — e o
endpoint **não existe**. Este card o tira do condicional.

A visão §F cortou tradução **automática**; a sob demanda sempre foi o desenho
aprovado. A diferença é exatamente o ponto: quem paga é quem pede.

## Problema

**Traduzir é a primeira funcionalidade do produto que gasta dinheiro fora do
loop principal — e o CARD-014 mediu que 100% do custo variável é LLM.**

Três consequências que nenhum card cobre hoje:

1. **não há endpoint**, e sem ele o botão é decorativo;
2. **não há teto.** O loop de conversa é limitado pela cota (CARD-015); traduzir
   não é limitado por nada. Um botão que chama o LLM e não conta é exatamente o
   buraco que o CARD-014 existiu para fechar do outro lado;
3. **não está decidido o que se traduz.** A resposta inteira do professor? Uma
   frase? A explicação de uma correção? São custos e UIs diferentes.

## Requisitos funcionais

- **RF1** — Existe um endpoint que traduz para português um texto **já
  produzido** pelo produto (resposta do professor ou explicação de correção),
  identificado por **referência ao recurso** — nunca por texto livre vindo do
  cliente.
- **RF2** — Traduzir **não** cria um `Turn` e não afeta o histórico pedagógico:
  não é uma interação com o professor, é uma leitura assistida.
- **RF3** — A tradução é **registrada como consumo** (`UsageEvent`, CARD-014),
  com o custo congelado na escrita como o ADR-0051 exige — senão o custo real
  por aluno volta a ser estimativa.
- **RF4** — Uma tradução já feita **não é paga duas vezes**: o mesmo texto
  traduzido de novo devolve o que já existe.
- **RF5** — O modelo é o **barato** da estratégia do ADR-0009 ("forte para
  pedagogia, barato para auxiliares"). Traduzir não é pedagogia.
- **RF6** — Tradução indisponível é desfecho esperado, não erro do aluno: o
  texto original continua lá, e a UI diz que não deu.

## Requisitos não funcionais

- **RNF1 — Refinamento de cache, e aqui ele é a espinha do card** (template,
  §"Refinamento obrigatório"). A tradução de um texto imutável **nunca**
  invalida: o texto de origem não muda depois de gravado. Isso torna o RF4 um
  problema de **persistência**, não de cache com TTL — e é a decisão de desenho
  do card: coluna ao lado do texto, tabela própria, ou chave no Redis com TTL.
  A resposta muda o custo de tudo.
- **RNF2 — Rate limit próprio.** É endpoint autenticado que gasta dinheiro, e o
  guia arquitetural §05 é explícito: endpoint autenticado também abusa. O
  limite entra no refinamento, não depois.
- **RNF3 — Conta no budget global** (kill switch do CARD-015). Com o orçamento
  do dia estourado, traduzir para junto do resto — é gasto de IA como qualquer
  outro.
- **RNF4 — Resiliência pela política do CARD-026.** É a segunda chamada externa
  do produto; nasce com timeout, retry e o desfecho de indisponibilidade já
  definidos, não com uma requisição crua.
- **RNF5 — Latência não é crítica.** O aluno pediu e espera; não há orçamento de
  1,8 s aqui. Isto **libera** o desenho: pode ser síncrono, pode ser mais lento,
  não precisa de streaming nem de cascata.
- **RNF6 — Sem tradução preventiva.** Nada de traduzir "por via das dúvidas" ao
  gerar a resposta. É o corte da visão §F e ele continua valendo: o gatilho para
  reabrir seria medir que quase todo aluno traduz quase toda resposta.

## Escopo

- **In:** o endpoint; a decisão de persistência do RF4; o registro de consumo; o
  rate limit; o adapter de tradução atrás de porta própria (o núcleo não conhece
  provedor); testes com fake.
- **Out:** a UI do botão (CARD-016) e sua posição no player (CARD-035);
  tradução da fala **do aluno** (ele sabe o que disse); escolha de idioma de
  destino — é pt-BR, e um seletor é card futuro com gatilho.

## Critérios de aceite

- **Dado** uma resposta do professor, **quando** peço a tradução, **então**
  recebo o texto em português e um `UsageEvent` é gravado com o custo.
- **Dado** a mesma resposta, **quando** peço de novo, **então** recebo o mesmo
  texto e **nenhum** `UsageEvent` novo é gravado.
- **Dado** o kill switch de orçamento ativo, **então** a tradução é recusada com
  Problem Details, e o texto original continua legível.
- **Dado** um pedido de tradução, **então** nenhum `Turn` é criado e a cota de
  minutos do aluno não muda.
- **Dado** o provedor de tradução fora do ar, **então** a resposta é o desfecho
  de dependência indisponível do CARD-026 — não um 500.
- **Dado** um cliente pedindo tradução de texto arbitrário, **então** o endpoint
  recusa: ele traduz recursos, não payload.

## Riscos

- **O RF1 é uma decisão de segurança disfarçada de contrato.** Um endpoint que
  traduz texto livre é um proxy de LLM aberto pago por você. Referência a
  recurso é o que impede isso, e é por isso que está no RF1 e não numa nota.
- **O RF4 pode inflar o card.** Se a decisão for tabela própria, entram
  migration e mais um repositório. Se for coluna, o texto traduzido passa a
  viver dentro do agregado de correção/turn — e o ADR-0049 já teve essa
  discussão sobre campos derivados. Vale olhar como ele decidiu antes de repetir
  o debate.
- **Custo pequeno que ninguém mede vira custo grande.** O CARD-014 mediu US$
  0,002678/turn de conversa. Traduzir é barato **por chamada**; a pergunta é
  quantas chamadas por sessão, e a única forma de saber é o RF3.

## Objetivo de aprendizado

Como uma porta nova entra num sistema que já tem cinco (`SpeechToText`,
`TeacherLlm`, `TextToSpeech`, `MediaStorage`, `TurnEvents`) — em particular, se
tradução é uma **porta própria** ou mais um uso da porta do LLM. A pergunta é a
mesma do ADR-0036 ("o primeiro consumidor revela o que faltava nas portas") e a
resposta define se o adapter da Anthropic passa a ter dois papéis.

## Execução (2026-09-13, loop autônomo)

**A pergunta do objetivo de aprendizado, respondida: porta própria.**
`Translator` (`application/ports/translator.py`) com adapter próprio
(`adapters/llm/anthropic_translator.py`). O critério foi o do projeto — *nome
de porta é a capacidade* — e as duas divergem em quatro eixos (forma, latência,
modelo, estado), tabelados no docstring da porta. O argumento decisivo é de
teste: um método a mais em `TeacherLlm` obrigaria **todo dublê** daquela porta
a implementar tradução para continuar satisfazendo o `Protocol`. O adapter da
Anthropic passa a ter dois **arquivos**, não dois papéis.

**RF1 (referência a recurso, nunca texto)** — o corpo do POST é
`{target, index}`; não existe campo `text` no schema. O idioma de destino está
no nome do método da porta (`to_portuguese`), não em parâmetro, pela mesma
razão. Testado por `test_o_endpoint_recusa_texto_arbitrario_do_cliente`, cuja
asserção que importa é a última: o provedor nunca viu o texto do cliente.

**RF2** — nenhum `Turn` criado, nenhum `UsageEvent` escrito, cota de minutos
intocada (`test_traduzir_nao_cria_turn_nem_mexe_na_cota`).

**RF3 + RNF1 (as duas decisões caras)** — tabela `turn_translations`
(migration `842710677a72`) com PK composta `(turn_id, target, index)`, custo
congelado na escrita em `NUMERIC(12,8)` e nulo com o mesmo significado do
`UsageEvent` ("não sabemos precificar", nunca "grátis"). **Persistência e não
cache** porque nada invalida: o texto de origem é imutável, então qualquer TTL
seria uma data arbitrária para o produto voltar a pagar pela mesma tradução.

**Decisão autônoma (loop sem desenvolvedor, 2026-09-13):** o RF3 nomeia
`UsageEvent`, mas a PK daquela tabela é o `turn_id` — "um turn, um evento",
invariante que o CARD-014 protege com teste — e um turn traduzido já tem o
evento da conversa. → **O custo foi congelado na própria linha da tradução e
somado ao `ServiceBudget`** (que é o mecanismo que faz o RNF3 valer de fato).
→ **Porquê:** é a alternativa que registra o consumo sem quebrar uma
invariante existente, e é reversível — uma migration de consolidação folda as
linhas num livro-razão único no dia em que houver um. A alternativa cara
(quebrar a PK de `usage_events` com um discriminador de tipo) é decisão de
modelagem financeira, não de implementação. → **PENDENTE DE REVISÃO HUMANA**
(registrada também no ADR-0066, consequências).

**RF4** — a consulta vem antes de tudo; a chave composta é quem garante sob
concorrência (`ConflictingWriteError` → relê → devolve a vencedora, mesmo
desenho do ADR-0042). A prova nos testes é a **contagem de chamadas ao
provedor**, não o texto: `test_a_mesma_traducao_nao_e_paga_duas_vezes` afirma
uma chamada, uma linha, um lançamento no orçamento.

**RF5** — `assistant_model` (o barato do ADR-0009). Este card é o **primeiro
consumidor** daquele campo, que existia em `config.py` sem ninguém que o lesse.

**RF6** — `TranslatorError` entrou em `FALHAS_DE_INFRAESTRUTURA`: provedor fora
do ar vira `503 dependency-unavailable`, nunca 500
(`test_provedor_fora_do_ar_e_503_de_dependencia_e_nao_500`).

**RNF2** — rate limit próprio: 10/min por aluno (mais apertado que os 20 de
turns, porque traduzir é gesto de leitura) mais o teto por IP. Hoje o
`student_id` é constante, então é a chave por IP que separa clientes — anotado
na dependência.

**RNF3** — `ServiceBudget.add_cost` depois do commit: somar ao teto um gasto
cuja linha não foi gravada faria o orçamento morder por um custo que ninguém
consegue auditar.

**RNF4 — sem breaker, e é decisão registrada.** O breaker do ADR-0053 protege
contra repetição **em série** num worker `MAX_JOBS = 1`; traduzir é iniciado
pelo aluno, tem rate limit próprio e falha em 15 s. **Gatilho para
acrescentá-lo:** tradução chamada de dentro do worker, ou rajadas de
`TranslatorError` no log.

**RNF5/RNF6** — síncrono, sem stream e sem tool use (economiza os tokens de
schema em toda chamada); nenhuma tradução preventiva.

**Testes:** `tests/application/test_translate_text.py` (14, incluindo a corrida
e o modelo sem preço), `tests/api/test_turns.py` (10 novos, pela rota),
`tests/adapters/test_persistence.py` (6 novos contra Postgres real — roundtrip
do `Decimal`, enum pelo valor, a PK composta recusando a segunda, e o
`CASCADE`), `tests/domain/test_translation.py` (5, as invariantes).

**Contrato:** `openapi.json` e `packages/api-client/src/schema.d.ts`
regenerados.

**ADR novo:** [0066](../adr/0066-traducao-e-porta-propria-persistida-por-referencia-a-recurso.md)
— critérios 1 (dependência/porta nova), 2 (endpoint, tabela e enum novos) e 3
(afeta custo recorrente).

**Regra do explicador:** nenhuma pergunta de previsão coube nesta sessão — o
card já trazia as três decisões caras enunciadas (porta, persistência,
registro de consumo), e as duas primeiras se resolveram com regras já escritas
do projeto. A terceira virou a decisão autônoma acima, marcada para revisão em
vez de fechada em silêncio.
