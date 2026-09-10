# CARD-046 — `CefrAssessment`: o nível estimado pelo que o aluno de fato faz

- **ID:** CARD-046
- **Épico:** Qualidade da conversa (briefing 2026-09-09, ponto 5 — feature 2 de 3)
- **Esforço:** G — **quebrar antes de começar**
- **Status:** backlog
- **Dependências:** CARD-045, ADR-0049, ADR-0059, **ADR novo obrigatório**

## Contexto

Segunda das três features do ponto 5, e a que a visão de produto nomeia como
conceito de domínio: *"estimativa de nível (A1–C2) com confiança, reavaliada por
janela de sessões, apresentada **como faixa** ('A2–B1'), nunca como veredito
psicométrico"* (`visao-produto-e-arquitetura-alvo.md:35`).

Ela existe para corrigir o que o CARD-045 não consegue: **autoavaliação é
notoriamente ruim**, e um nível declarado errado piora a conversa em silêncio.
A estimativa é a correção, não o enfeite.

O insumo já existe e é tipado: as `Correction` são entidades persistidas desde o
**ADR-0049**, com tipo do erro, trecho, forma correta, explicação e severidade.
Este card é o primeiro consumidor real desse acúmulo.

## Problema

Não há `CefrAssessment` — nem entidade, nem tabela, nem cálculo, nem
apresentação. E, diferente do CARD-045, **não é claro a partir de quê estimar**:

- as `Correction` dizem o que o aluno **erra**, não o que ele **consegue**. Um
  aluno C1 falando de assunto difícil pode acumular mais correções que um A2
  falando do café da manhã;
- a densidade de correções depende do quanto ele falou, e o `Turn` tem a
  duração;
- a visão pede **confiança** junto, e confiança de quê é uma decisão.

**Este é o card com mais decisão não tomada de todos os nove.** Por isso ele é
**G** e a primeira coisa que ele exige é ser quebrado.

## Proposta técnica

**Um ADR é obrigatório antes da implementação** — critério **2** do
`docs/adr/README.md` (define uma fronteira: conceito de domínio persistido, com
forma de dado e apresentação próprias). Ele **não foi escrito na investigação de
2026-09-09**, e isso é deliberado: não há evidência para decidir a janela, o
algoritmo nem a forma da confiança, e ADR escrito sem evidência é ficção com
número de série.

O que o ADR terá de fechar, listado aqui para que a sessão que o escrever não
comece do zero:

1. **A partir de quê.** As `Correction` por si só são insuficientes (ver
   Problema). Candidatos: densidade de correções por minuto falado, distribuição
   de `severity`, distribuição de `type`, riqueza da fala do próprio aluno.
2. **Quem calcula.** A visão diz *"estimativa por LLM com confiança, recalculada
   a cada N turns"* — o que faz da estimativa uma chamada de IA a mais, com
   custo (ADR-0010) e latência **fora** do caminho crítico (job do `arq`, nunca
   no turn).
3. **A janela.** "A cada N turns" precisa de N, e de o que fazer com o histórico
   antigo.
4. **Faixa, não escalar** — e o tipo tem de impedir a apresentação de mentir
   sobre a origem: `CefrLevel` declarado é escalar (CARD-045), `CefrAssessment`
   é faixa com confiança. São tipos diferentes de propósito.
5. **O que o professor recebe.** O `StudentContext` (ADR-0059) já acomoda os
   dois; a regra de precedência entre declarado e estimado é decisão de produto.

**Quebra sugerida, se o ADR confirmar o desenho:** (a) entidade + migration +
apresentação como faixa; (b) o job de recálculo; (c) o estimado chegando ao
professor e à tela.

## Refinamento obrigatório — cache e limites

**Cache:** a estimativa **é** um dado derivado guardado — e o CLAUDE.md manda
não persistir o que se consegue derivar (ADR-0016). A defesa é que aqui derivar
custa **uma chamada de LLM**, o que a torna um caso de cache legítimo e não de
duplicação. **TTL:** a janela de N turns. **Invalidação:** o N-ésimo turn novo.
As duas respostas existem — e sem elas o cache não seria implementado.

**Endpoint:** leitura do nível estimado, junto do perfil do CARD-045. **Teto:**
o mesmo do perfil. **Nunca** um endpoint que dispare o recálculo sob demanda:
seria uma chamada de LLM à disposição de quem apertar o botão.

**Dependência externa:** o Anthropic, num job do `arq`. **Timeout e retry:** a
política do CARD-026 e o disjuntor do ADR-0053; retry explícito do ADR-0052.
**Idempotente:** recalcular duas vezes produz duas estimativas — a segunda
substitui a primeira, e isso precisa ser escrito, porque "rodou duas vezes" é o
caso normal de um job com retry. **Desfecho quando o provedor está fora:** a
estimativa anterior permanece e o recálculo tenta de novo depois. Nunca apagar a
estimativa boa por não ter conseguido fazer a nova.

## Escopo

- **In:** o ADR; a entidade e a migration; o cálculo; o job; a apresentação como
  faixa; o estimado no `StudentContext`.
- **Out:** `ErrorPattern` e revisão espaçada — **cortados do MVP pela visão**,
  com gatilho escrito (~50+ `Correction` reais de um usuário). Gráficos de
  evolução (web companion). Mini-teste (CARD-047).

## Critérios de aceite

> Provisórios: o ADR pode mudá-los, e isso é esperado num card cuja primeira
> entrega é uma decisão.

- **Dado** um aluno com correções acumuladas, **quando** o job roda, **então**
  existe um `CefrAssessment` com faixa e confiança, e ele **não** substitui o
  nível declarado — os dois coexistem.
- **Dado** um aluno sem correções suficientes, **quando** o job roda, **então**
  nenhuma estimativa é produzida. **Estimar com pouco dado é pior que não
  estimar**, e é o que a confiança existe para expressar.
- **Dado** o job executado duas vezes para o mesmo aluno, **quando** as
  estimativas são lidas, **então** o resultado é o mesmo que uma execução — o
  retry não duplica.
- **Dado** uma estimativa, **quando** apresentada, **então** é faixa com
  confiança, nunca um único nível — teste sobre a apresentação, porque é aí que
  a regra da visão pode ser violada sem ninguém notar.
- **Dado** o provedor de LLM fora, **quando** o job roda, **então** a estimativa
  anterior permanece intacta.

## Riscos

- **Estimativa errada apresentada com confiança alta** é pior que não ter
  estimativa: vira rótulo. A visão já antecipou isso, e é a razão da faixa.
- **Custo recorrente novo** fora do caminho do turn, mas dentro do teto do
  ADR-0010. O ADR precisa da conta.
- **O card é G e vai tentar ser feito inteiro.** O maior risco é de processo, e
  a mitigação está escrita: o ADR primeiro, a quebra depois.
- **Massa de dados insuficiente.** Com um único usuário (o autor), pode não
  haver `Correction` suficiente para o card ter o que estimar. Gatilho honesto
  para adiar: se o uso real não produziu volume, este card **espera**, e o
  CARD-045 sozinho já entrega valor.

## Objetivo de aprendizado

Entender como um **conceito de domínio derivado e caro** difere de um campo
comum — quando "não persistir o que se consegue derivar" (ADR-0016) deixa de
valer, e por quê. Em .NET o reflexo seria uma *materialized view* ou uma tabela
de projeção; aqui a fonte não é uma consulta, é uma chamada de IA não
determinística, e isso muda o que "recalcular" significa: duas execuções sobre
o mesmo dado **não dão o mesmo resultado**, e o desenho tem de sobreviver a isso.
