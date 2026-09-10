# CARD-047 — Mini-teste inicial de nível *(mapeado, sem data)*

- **ID:** CARD-047
- **Épico:** Qualidade da conversa (briefing 2026-09-09, ponto 5 — feature 3 de 3)
- **Esforço:** G — **não estimável ainda**
- **Status:** backlog — **implementação futura sem data prevista**
- **Dependências:** CARD-045, CARD-046

## Contexto

Terceira das três features do ponto 5. **Decisão do desenvolvedor em
2026-09-09: fica mapeada, mas é implementação futura sem data prevista.**

O card existe para que a ideia não se perca e para que o **gatilho** de entrada
esteja escrito — não para ser executado agora. O briefing já a classificava
como *"o mais caro dos três e o mais fácil de adiar"*, e a razão é que ela é
**produto e conteúdo, não só engenharia**: um mini-teste exige perguntas
calibradas, uma escala defensável e uma noção do que cada resposta significa —
nada disso emerge da conversa nem do código.

## Problema

O nível declarado (CARD-045) depende de autoavaliação, que é ruim. O estimado
(CARD-046) depende de acúmulo, e por isso **não existe no primeiro dia** — que é
justamente quando a calibragem mais importa, porque é quando o aluno decide se o
produto serve para ele.

O mini-teste é a única das três features que dá nível **antes** da primeira
conversa. É esse o buraco que ele preenche, e é por isso que ele não é
redundante com as outras duas.

## Proposta técnica

Nada decidido, e é honesto dizê-lo. O que uma sessão futura terá de responder,
registrado para não recomeçar do zero:

1. **Que forma tem o teste** — conversa guiada com o próprio professor (reusa
   todo o pipeline, custa turns), ou instrumento à parte (perguntas fixas,
   barato, mas é conteúdo curado, que a visão corta do MVP na Parte F).
2. **Quantos minutos** o aluno aceita gastar antes de conversar de verdade. Um
   teste longo antes da primeira conversa é a forma mais eficiente de perder o
   usuário no primeiro dia.
3. **O que acontece com o resultado** — vira `cefr_level` declarado (CARD-045)?
   Vira um `CefrAssessment` de confiança alta (CARD-046)? São tipos diferentes
   com origens diferentes, e escolher errado faria a apresentação mentir.
4. **Se é pulável.** Quase certamente sim.

**Um ADR será obrigatório** se o desenho envolver conteúdo curado ou um fluxo de
onboarding bloqueante — critério 2, e possivelmente 3 (custo por conta criada,
que é uma superfície de abuso que o ADR-0010 e o CARD-038 tratam).

## Refinamento obrigatório — cache e limites

**Não se aplica ainda** — não há endpoint, cache nem dependência definidos,
porque não há desenho. Registrar "não se aplica" aqui seria falso; o correto é
que **estas perguntas fazem parte da sessão que desbloquear o card**, e o card
não fecha sem elas.

## Escopo

- **In:** nada. O card é registro.
- **Out:** tudo, até o gatilho disparar.

## Critérios de aceite

Não se aplica enquanto o card estiver mapeado. **O critério de saída deste
estado** é o gatilho abaixo ter disparado e uma sessão ter respondido as quatro
perguntas da proposta técnica.

## Gatilho para entrar no roadmap

Qualquer um dos três, **e o primeiro é o mais provável**:

1. **CARD-045 e CARD-046 em produção, e a calibragem do primeiro dia ainda
   incomodando** — ou seja, evidência de uso de que o nível declarado erra o
   bastante para justificar o custo.
2. **Um segundo usuário real além do autor.** Autoavaliação do próprio
   desenvolvedor sobre o próprio inglês é um caso especial: ele sabe o que está
   fazendo. O problema é de quem não sabe.
3. **Curadoria de conteúdo entrando no produto por outro motivo** (trilhas,
   objetivos de estudo) — aí o custo marginal do teste cai muito, porque a
   máquina de conteúdo já existiria.

## Riscos

O risco deste card é **ser executado antes do gatilho**. É a feature mais fácil
de justificar por entusiasmo ("todo app de idioma tem um teste inicial") e a que
mais exige o que o projeto não tem: conteúdo curado. A Parte F da visão corta
"trilha/objetivos de estudo" por exatamente esse motivo, e o argumento transfere
inteiro.

## Objetivo de aprendizado

A definir quando o card for desbloqueado. Registrar um objetivo agora seria
inventar aprendizado para trabalho que não foi desenhado — e o objetivo de
aprendizado é obrigatório justamente por ser específico.
