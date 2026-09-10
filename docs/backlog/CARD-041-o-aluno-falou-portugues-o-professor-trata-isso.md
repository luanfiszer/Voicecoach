# CARD-041 — O aluno falou português, e o professor trata isso como professor

- **ID:** CARD-041
- **Épico:** Qualidade da conversa (briefing 2026-09-09, ponto 3 — decisão pedagógica)
- **Esforço:** M
- **Status:** backlog
- **Dependências:** CARD-039, ADR-0059, ADR-0055

## Contexto

Decisão de produto tomada em 2026-09-09, entre três alternativas apresentadas:
**o aluno que fala português deve ser entendido e tratado pedagogicamente** — o
professor ensina a dizer aquilo em inglês, em vez de fingir que ouviu inglês.

A alternativa mais barata (modelo multilíngue com `language="en"` fixo, custo
zero de latência) foi **recusada com o número na mesa**: ela apaga a informação
de que houve português, e o aluno receberia de volta a ilusão de ter falado
inglês. Está registrada no ADR-0055 como o recuo se os +0,17 s se mostrarem
caros.

Este card é também o **primeiro consumidor** do mecanismo do ADR-0059 — o bloco
de contexto do aluno no prompt. O CARD-045 (nível) usa o mesmo caminho depois.

## Problema

`prompts/teacher/v2.md` é um arquivo estático, enviado igual a cada turno. Ele
começa com *"a friendly English teacher chatting with a Brazilian student"* e
**não tem instrução nenhuma** sobre o que fazer quando o aluno não fala inglês.
A porta `TeacherLlm` não tem por onde receber essa informação, mesmo depois do
CARD-039 passar a detectá-la.

## Proposta técnica

Decisão em **ADR-0059** (aceito). Este card cria o mecanismo e o exercita com um
campo só.

1. `StudentContext` como value object de `application`, com **todos os campos
   opcionais**. Neste card só `spoken_language` é preenchido; o CARD-045
   acrescenta o nível sem tocar na assinatura da porta — que é a razão de ser
   de um objeto em vez de parâmetros soltos.
2. O bloco de contexto é montado em código e **anexado ao FINAL** do prompt de
   sistema, delimitado. `v2.md` não ganha interpolação (ADR-0059 item 2): o
   prefixo estável é propriedade medida (ADR-0020/0021) e montar no meio a
   destruiria para sempre.
3. A instrução pedagógica entra no prompt: quando a fala veio em português,
   reconhecer, dar a forma em inglês e convidar a repetir — **sem** transformar
   a conversa em aula de tradução, e **sem** anunciar o mecanismo.
4. **O idioma é dica, não comando** (ADR-0059 item 3). A detecção erra em fala
   curta (ADR-0055): o prompt trata a possibilidade, nunca o fato. A diferença é
   entre *"o aluno falou português"* e *"esta fala pode ter vindo em
   português"*, e ela é o que impede o professor de responder em modo tradução a
   um "yes" mal detectado.
5. A ordem dos campos da saída **não muda** (ADR-0022 é contrato de latência).

## Refinamento obrigatório — cache e limites

**Cache:** o prompt caching segue **adiado** (ADR-0021 — o limiar de 4.096
tokens não é alcançado; distância medida de 36%). Este card **muda a conta**: um
prefixo estável seguido de cauda variável é exatamente a forma que o caching
premia. TTL e invalidação continuam sem resposta e por isso **o cache não é
implementado aqui**; o que este card entrega é registrar o novo tamanho do
prefixo, para que a reabertura do ADR-0021 tenha número.

**Endpoint:** não se aplica.

**Dependência externa:** o Anthropic, já coberto pela política do CARD-026 e
pelo disjuntor do ADR-0053. Este card **não** muda timeout, retry nem desfecho —
o bloco de contexto entra dentro da mesma chamada. Idempotência: inalterada.

## Escopo

- **In:** `StudentContext`; a montagem do bloco no adapter do professor; a
  instrução pedagógica no `v2.md` (ou `v3.md`, se a mudança for grande o
  bastante para merecer versão); o idioma detectado viajando do STT ao professor
  através do caso de uso; o tamanho do prefixo registrado.
- **Out:** o nível do aluno (CARD-045, mesmo mecanismo). Ensinar de fato uma
  frase específica ("como se diz X") como feature dedicada. Traduzir a resposta
  — isso já é o CARD-036. Reabrir o ADR-0021.

## Critérios de aceite

- **Dado** um turn cuja transcrição veio com `language == "pt"`, **quando** o
  prompt é montado, **então** o bloco de contexto está presente, **no final** do
  prompt de sistema, e o `v2.md` é byte-a-byte o prefixo — verificado por teste
  de string, que é o que torna o item 2 do ADR-0059 executável e não retórico.
- **Dado** um turn com `language == "en"`, **quando** o prompt é montado,
  **então** o bloco de idioma **não** aparece (ausência é o caso normal).
- **Dado** um `StudentContext` totalmente vazio, **quando** o prompt é montado,
  **então** ele é idêntico ao de hoje. Nenhuma regressão para quem não tem
  contexto.
- **Dado** o bloco montado, **quando** lido, **então** ele fala em possibilidade
  ("may have spoken Portuguese"), não em fato — verificável por teste de
  conteúdo, e é a mitigação escrita do falso positivo.
- **Dado** a resposta do professor, **quando** transmitida, **então**
  `spoken_reply` continua sendo a primeira chave (ADR-0022 intacto).

## Riscos

- **Falso positivo da detecção** vira comportamento visível e estranho: o
  professor tratando inglês ruim como português. Mitigado pelo item 4; o plano B
  é `stt_language="en"` no `.env`, que desliga a detecção sem deploy.
- **Qualidade pedagógica não tem teste automatizado.** O eval harness é o P5 e
  não existe. A verificação real é conversa de verdade, e isso precisa estar
  escrito para não virar falso verde na DoD.
- **Tentação de resolver com um `if` na resposta** em vez de no prompt. O
  professor é quem ensina; o código que decide o que dizer ao aluno seria
  pedagogia em `application`.

## Objetivo de aprendizado

Entender por que um **value object com todos os campos opcionais** é a forma
certa de uma fronteira que vai crescer — e a diferença prática entre
`dataclass(frozen=True, slots=True)` com `| None` e o instinto C# de sobrecarga
de construtor ou parâmetro opcional: aqui a assinatura da porta **não muda mais
nunca**, e quem lê o `StudentContext` é obrigado pelo `mypy` a tratar a ausência
em vez de receber um default silencioso.
