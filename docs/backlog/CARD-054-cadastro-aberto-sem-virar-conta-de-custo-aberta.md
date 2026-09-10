# CARD-054 — Cadastro aberto sem virar conta de custo aberta

- **ID:** CARD-054
- **Épico:** Proteção de custo (bloqueante de V1.0 — N7 do corte)
- **Esforço:** M
- **Status:** backlog
- **Dependências:** CARD-049, CARD-015, ADR-0010 (**e o ADR que o substituir**)

## Contexto

Bloqueante do lançamento. Hoje a proteção de custo na raiz é **não ter cadastro
aberto**: o ADR-0010 item 5 trocou a verificação de e-mail por um código de
convite, com o argumento explícito de que *"a proteção mais barata contra abuso
é não ter cadastro aberto — o convite custa uma comparação de string"*.

**App Store pública apaga essa proteção inteira.** Qualquer pessoa baixa,
qualquer pessoa se cadastra, e cada conta criada é uma torneira de custo de IA
ligada ao seu cartão.

Isto é diferente do CARD-015: lá o teto é **por conta** (cota diária) e
**global** (kill switch). Aqui o problema é o **número de contas**, que é o
multiplicador que faz o teto por conta não bastar. Cem contas com cota de 10
minutos são mil minutos.

## Problema

Sem o convite, o caminho `baixar → cadastrar → falar` não tem nenhum atrito, e
o custo por turn é real (US$ 0,002678, CARD-014). Um script que cria contas em
laço, ou simplesmente um dia de divulgação bem-sucedida, transforma o teto
mensal do ADR-0010 numa parede que todo mundo bate junto — e o kill switch
derruba o produto para **os pagantes** também.

## Proposta técnica

Defesa em camadas, e nenhuma delas sozinha resolve.

1. **Verificação de e-mail antes do primeiro turn** (CARD-049) é a camada de
   base: ela não impede o abuso determinado, mas torna cada conta descartável um
   pouco mais cara.
2. **Rate limit por IP no cadastro**, e ele é diferente do limite por conta — a
   chave aqui é o IP porque a conta ainda não existe. Proposta declarada: **3
   cadastros/hora por IP**, estimativa a recalibrar. Camada de aplicação, porque
   o que se protege é a lógica de negócio.
3. **Uma cota de avaliação separada da cota do pagante.** É o item mais
   importante e o menos óbvio: o custo do abuso vem de quem **não paga**.
   Contas não pagantes precisam de um teto próprio, pequeno, distinto do
   `daily_audio_minutes_per_student` do CARD-015. Quanto vale um turn de graça é
   **decisão de produto** e não está tomada.
4. **O kill switch global não pode derrubar quem paga.** O ADR-0010 item 5
   descreve um `503` honesto quando o orçamento estoura. Com pagantes, isso
   passa a ser inaceitável: o corte tem de atingir **primeiro** o gratuito. Isso
   muda o desenho do kill switch do CARD-015, e o CARD-054 precisa correr junto
   ou depois dele, nunca antes.
5. **Instrumentar antes de apertar.** Os `usage_events` (ADR-0051) já dão custo
   por aluno; o que falta é a leitura "custo por conta criada nos primeiros N
   dias", que é o número que diz se o teto está no lugar certo.

**Nada aqui reabre o ADR-0010** — ele **já vai ser substituído** pelo ADR de
custo sob receita, que é pré-requisito do card de deploy. Este card é um dos
consumidores dessa decisão, e o número da cota gratuita provavelmente mora lá.

## Refinamento obrigatório — cache e limites

**Cache:** os contadores de limite. **TTL:** a janela do limite (hora, dia).
**Invalidação:** expiração natural da janela — nunca invalidação manual, que
seria uma porta para zerar o teto. O Redis já está no projeto (ADR-0038) e é o
lugar; o banco é a fonte da verdade do que foi **consumido** (`usage_events`),
o Redis é o lugar do que está sendo **contado agora**. Os dois papéis não se
confundem.

**Endpoint:** não cria nenhum; **endurece** os do CARD-049 e o `POST /v1/turns`.
Os tetos: 3 cadastros/h por IP; a cota de avaliação por conta não pagante; o
kill switch global com precedência para o pagante. Todos declarados como
estimativa e recalibrados por métrica.

**Dependência externa:** Redis, com o `redis_connect_timeout` já existente.
**Idempotente:** contar duas vezes o mesmo evento superestima o consumo — o que
erra para o lado seguro, e essa escolha precisa estar escrita. **Desfecho quando
o Redis está fora:** decidir explicitamente entre *fail-open* (deixa passar, e o
custo escapa) e *fail-closed* (barra todo mundo, e o produto cai). **Para o
limite de custo, fail-closed é a resposta**, e ela é o oposto do reflexo usual
de disponibilidade — por isso está escrita aqui.

## Escopo

- **In:** rate limit por IP no cadastro; a cota de avaliação separada; a
  precedência do pagante no kill switch; a leitura de custo por conta nova; os
  números declarados em configuração com o motivo.
- **Out:** captcha (atrito alto, dependência de terceiro, e provavelmente
  desnecessário nesta escala — gatilho: abuso automatizado **medido**).
  Verificação por telefone. Detecção de fraude. Banimento manual de conta, que
  vira card próprio se acontecer.

## Critérios de aceite

- **Dado** um IP que já criou 3 contas na última hora, **quando** tenta a
  quarta, **então** é barrado com Problem Details (ADR-0040), sem dizer se o
  e-mail existe.
- **Dado** uma conta não pagante que esgotou a cota de avaliação, **quando**
  posta um turn, **então** recebe o desfecho de cota — e a mensagem é um convite
  a assinar, não um erro.
- **Dado** o orçamento global estourado, **quando** um **pagante** posta um
  turn, **então** ele é atendido; **quando** um não pagante posta, **então** é
  barrado. É o critério que prova o item 4, e é o que separa este card do
  CARD-015.
- **Dado** o Redis fora, **quando** um turn é postado, **então** ele é **barrado**
  — e há teste que prova o *fail-closed*, porque o reflexo de quem escreve o
  código é o contrário.
- **Dado** um mês de uso, **quando** o custo por conta criada é consultado,
  **então** o número existe e é consultável sem dashboard novo.

## Riscos

- **Apertar o teto e estrangular o produto.** Um limite de avaliação pequeno
  demais faz o aluno desistir antes de ver valor — e o produto é uma conversa,
  que precisa de alguns turns para convencer. Este risco é maior que o do abuso,
  e o número certo só sai de uso real.
- **Fail-closed derruba o produto se o Redis oscilar.** É o preço aceito, e a
  mitigação é o Redis ser local ao servidor, não um serviço remoto.
- **Rate limit por IP pune NAT compartilhado** — uma faculdade, uma empresa, uma
  operadora móvel. Três cadastros por hora por IP pode barrar gente legítima, e
  esse é um caso real no Brasil. Vale medir antes de endurecer.

## Objetivo de aprendizado

Entender **por que um limitador de taxa é um problema de janela e não de
contador** — janela fixa, deslizante e *token bucket* dão resultados diferentes
na virada da janela, e a diferença é explorável. E entender por que o Redis é a
peça certa para isso e o Postgres não, mesmo o Postgres sendo a fonte da verdade
de tudo o mais neste projeto: a distinção entre o que precisa **durar** e o que
precisa ser **contado rápido e expirar sozinho**.
