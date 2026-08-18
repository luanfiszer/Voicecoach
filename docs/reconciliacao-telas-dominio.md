# Reconciliação: telas desenhadas × domínio do CARD-005

- **Data:** 2026-08-18 · **Sessão:** abertura do CARD-005
- **Fontes:** `docs/design/prompt-claude-design-mobile.md` (briefing das 7 telas),
  `docs/design/Design.pdf` (8 páginas, geradas a partir dele),
  `docs/visao-produto-e-arquitetura-alvo.md` §A/§D/§F, cards 005–017,
  ADRs 0003/0004/0008/0010/0012/0013.

## O princípio

**O domínio não se adapta ao front.** A tela é *evidência* de que uma regra
existe, não autoridade sobre a forma dela. Cada achado cai em exatamente uma
gaveta:

1. **Domínio** — regra que continuaria valendo se a tela sumisse amanhã.
2. **Contrato** — forma do payload, granularidade de status, o que vem em qual
   etapa. Aqui quem dita é o cliente (ADR-0008), e mora em `api/schemas`.
3. **Apresentação** — animação, microcopy, ordenação visual. Não encosta no
   backend.

## Premissas de escopo (LEARNING-0002)

| # | Premissa | Status |
|---|---|---|
| P1 | O `Design.pdf` é **exploração**, não decisão de produto congelada | **Confirmada pelo desenvolvedor (2026-08-18): "tudo ainda é exploração".** Consequência: **toda** regra derivada de tela abaixo é **premissa NÃO confirmada** até virar decisão explícita, e nenhuma delas altera escopo de card sem OK |
| P2 | Dentro do design, `Passo 1 de 3`, autoplay, `0.75×`, "reiniciar demo" e microcopy são andaime/apresentação; permanente é o loop conversa → correção → acúmulo | não confirmada |
| P3 | `Session` tem início e fim explícitos (visão §A), e encerrar é ação do usuário ("Encerrar", "Sessão encerrada") | não confirmada |
| P4 | Retenção de áudio já é decisão (CARD-017); o CARD-005 só precisa **não fechar a porta** | não confirmada |
| P5 | Quota é medida em **minutos falados**, não em turnos nem requests | não confirmada |
| P6 | Auth/convite é Fase 3; nesta fatia o `Student` vem de seed | confirmada (roadmap) |
| P7 | `audio_duration` no `Turn` entra **já no CARD-005** | **Confirmada pelo desenvolvedor (2026-08-18)** — única mudança de escopo autorizada do card por esta análise |

## A tabela

Legenda de "Já coberto?": ✅ previsto e suficiente · ⚠️ previsto mas incompleto
ou contraditório · ❌ não previsto por nenhum card.

### Tela 1 — Conversa (a tela principal)

| Tela / estado | Regra ou dado que ela revela | Gaveta | Onde mora | Card | Já coberto? |
|---|---|---|---|---|---|
| Header "Sessão de hoje · 4 turnos · 6 min" | `Session` agrega nº de turnos e **tempo falado** (soma das durações de áudio dos Turns) | domínio (o dado) + contrato (a agregação) | `domain/Session`, `Turn.audio_duration` | 005 (dado), 010 (payload) | ⚠️ o card não previa `audio_duration`; sem ele o "6 min" é incalculável (**P7** resolve) |
| Chip "12 min hoje" | Quota é **saldo de minutos falados no dia**, e é dado de leitura constante na tela principal | domínio | `domain`/`application` (quota) | 015 | ✅ o card **já** dizia "segundos de áudio" — outra leitura minha corrigida; o que faltava era o *reset*, ajustado nesta sessão |
| Bolha do aluno (transcrição) e do professor (texto + player) | `Turn` carrega transcript, texto da resposta e referência do áudio | domínio | `domain/Turn` | 005 | ✅ |
| Ação "traduzir" por resposta | Tradução é **sob demanda**, nunca pré-computada (visão §F corta tradução automática) | apresentação (o affordance) + contrato (o endpoint, se houver) | `api/` | 016 (decide lá) | ✅ como está |
| Estados a–d (idle, gravando, gravação concluída, enviando) | **Nada existe no servidor ainda** — o `Turn` nasce no upload, não na gravação | apresentação | cliente | 011/012 | ✅ |
| Estados e–h (`transcrevendo` → `pensando` → texto → áudio) | O `Turn` precisa expor **em que etapa está** e **payload parcial** | domínio (o estado) + contrato (a granularidade) | ver §"A tensão" | 005 + 010 | ⚠️ **incoerência interna do backlog** — ver abaixo |
| "Passo 1 de 3 / 2 de 3" com barra proporcional | O cliente **enumera** as etapas: são 3, ordenadas e nomeadas | contrato | `api/schemas` | 010 | ⚠️ mesmo ponto |
| "você pode guardar o telefone, avisamos com som" | Notificação local ao terminar o processamento (não é push de servidor) | apresentação | cliente | 012 | ✅ |
| "Áudio a caminho…" com texto já legível | Resultado parcial é estado **normal**, não degradado: o Turn é útil antes de completo | domínio | `domain/Turn` | 005 | ⚠️ mesmo ponto |

### Tela 2 — Card de correção

| Tela / estado | Regra ou dado que ela revela | Gaveta | Onde mora | Card | Já coberto? |
|---|---|---|---|---|---|
| "Sem erro no turno → nenhum card. O silêncio é o elogio." | **Zero correções é resultado válido**, não ausência de dado nem falha | domínio | `domain` (Turn 0..N Correction) | 013 | ✅ (card cita a regra) |
| Anatomia: original riscado → forma correta → explicação → badge de tipo | `Correction` = {type, original, corrected, explanation, severity} | domínio | `domain/Correction` | 013 | ✅ (visão §A) |
| Severidade em palavras: "pequeno ajuste" / "vale revisar" | Severidade é **escala fechada e pequena** (o design usa 2 níveis), atribuída pelo LLM — não é texto livre | domínio (a escala) + apresentação (o rótulo pt-BR) | `domain` enum | 013 | ⚠️ card diz "severity" sem definir a escala |
| "1 de 3 · 2 de 3" nas correções empilhadas | Ordem de leitura dentro do turno | apresentação | cliente | 016 | ✅ |
| Badges `grammar / vocabulary / preposition / word order / other` | Tipo é **enum fechado** — cinco valores, e `other` é a válvula | domínio | `domain` enum | 013 | ✅ |

### Tela 3 — Resumo pós-sessão

| Tela / estado | Regra ou dado que ela revela | Gaveta | Onde mora | Card | Já coberto? |
|---|---|---|---|---|---|
| "Você falou inglês por 8 minutos hoje" · 8:12 · 7 turnos · 5 correções | `Session` tem fim explícito, duração e agregações | domínio + contrato | `domain/Session` | 005 (entidade), 016 (tela) | ⚠️ depende de `audio_duration` (**P7**) |
| Barras "correções por tipo" | Agregação por enum de tipo dentro da sessão | contrato | `api/schemas` | 016 | ✅ |
| **"ACERTO DO DIA — hoje você usou o past perfect corretamente"** | **Reforço positivo é dado pedagógico**, não correção: o professor identifica um acerto notável e ele é guardado | domínio | `domain` (entidade nova ou campo em Turn) | **nenhum** | ❌ **achado #1** |
| Botão "Encerrar" | Encerrar sessão é **ação explícita do usuário**, com transição de estado | domínio | `domain/Session.end()` | 005 | ⚠️ card não menciona ciclo de vida de Session, só de Turn |

### Tela 4 — Histórico

| Tela / estado | Regra ou dado que ela revela | Gaveta | Onde mora | Card | Já coberto? |
|---|---|---|---|---|---|
| Lista com data, hora, duração, nº correções, nº turnos | `Session` precisa de `started_at`/`ended_at` consultáveis | domínio | `domain/Session` | 005 | ✅ |
| **"Áudio expirado — transcrição e correções permanecem"** | **Expiração do áudio não invalida o Turn**, e o app distingue "expirou" de "nunca teve" | domínio (a invariante) + contrato (o flag) | `domain/Turn` | 017 entrega, **005 não pode fechar a porta** | ✅ o CARD-017 **já** tem o critério (`reply_audio: unavailable`, não 500). Correção de uma leitura minha: eu havia marcado como buraco e não era |
| "Sessões anteriores a 30 dias vivem no app web" | Corte de janela no mobile é decisão de produto/paginação | contrato | `api/` | 016 / Fase 5 | ✅ |

### Tela 5 — Login / registro

| Tela / estado | Regra ou dado que ela revela | Gaveta | Onde mora | Card | Já coberto? |
|---|---|---|---|---|---|
| E-mail + senha + código de convite | Conta é **gated por convite** (visão §A, ADR-0010) | domínio | Fase 3 | Fase 3 | ✅ (a detalhar na fase) |
| **"Este convite já foi usado"** | Convite é de **uso único** e sabe quem o consumiu — é entidade, não string em env | domínio | Fase 3 | Fase 3 | ✅ (matéria da fase, não buraco) |
| Erros inline de credencial | Formato de erro (Problem Details) | contrato | `api/` | 010 | ✅ |

### Tela 6 — Perfil / configurações

| Tela / estado | Regra ou dado que ela revela | Gaveta | Onde mora | Card | Já coberto? |
|---|---|---|---|---|---|
| "A2–B1" sobre régua A1…C2 | CEFR é **faixa (min, max)**, nunca valor único | domínio | `domain/CefrAssessment` | Fase 6 | ✅ (visão §A já diz faixa) |
| "É uma estimativa, não certificação" | Honestidade epistêmica do produto | apresentação | cliente | Fase 6 | ✅ |
| **"Quota de hoje 12/20 min · Renova às 00:00 (horário de Brasília)"** | Reset é **dia-calendário em fuso fixo**, não janela deslizante de 24h | domínio | `application` (quota) | 015 | ❌ **achado #3** — contradiz a visão §D ("janela deslizante") |
| "Tocar áudio automaticamente", "Tema: Sistema" | Preferências de UI | apresentação | **device**, não servidor | — | ✅ recomendação: não persistir no backend (§F) |
| "Sair" | Sessão de auth | domínio | Fase 3 | Fase 3 | ✅ |

### Tela 7 — Estados de sistema

| Tela / estado | Regra ou dado que ela revela | Gaveta | Onde mora | Card | Já coberto? |
|---|---|---|---|---|---|
| Microfone negado | Permissão do device | apresentação | cliente | 011 | ✅ |
| **Offline: "Sua fala está guardada aqui… vai sozinho quando a conexão voltar" · "Gravação de 0:14 — pendente"** | Áudio pode ser enviado **muito depois de gravado** ⇒ pode chegar para uma `Session` **já encerrada** | domínio (a invariante) | `domain/Session` + `application` | 005 (invariante), 012 (fila local) | ❌ **achado #4** |
| Quota atingida: "revisar as correções de hoje continua liberado" | Quota bloqueia **criação de Turn**, nunca leitura do que já existe | domínio | `application` | 015 | ⚠️ → **ajustado no card** nesta sessão |
| "As aulas estão pausadas — atingimos o limite de custo do dia" | Kill switch por orçamento, com mensagem honesta | domínio | `application` | 015 (ADR-0010) | ✅ |
| "Avisar quando voltar" | Push de reengajamento | produto | — | — | ❌ **achado #5** — §F cortou push do MVP (gatilho: revisão espaçada) |
| **"Demorou mais que o normal — resposta não chegou em 30s" · [Tentar de novo] [Descartar]** | Um Turn pode **travar**; alguém precisa declará-lo falho, e "descartar" é ação do usuário sobre um Turn em andamento | domínio (estado) + contrato (a ação) | `domain/Turn` + `application` | **nenhum** | ❌ **achado #6** |

---

## As três perguntas obrigatórias

### 1. Que regra de negócio a tela revela que o backlog não previa?

1. **Reforço positivo persistido ("acerto do dia").** Não é `Correction` — é o
   oposto dela. Nenhum card, nenhuma linha da visão §A. É a única regra
   *pedagógica* nova que o design produziu.
2. **Turn não nasce em Session encerrada.** A tela de offline torna concreto o
   que era hipotético: com fila local, a fala gravada às 21h pode subir às 23h,
   depois de a sessão ter sido encerrada. Sem a invariante, o Turn entra numa
   sessão morta e some da UI.
3. **Reset de quota em dia-calendário e fuso fixo** (`America/São_Paulo`),
   contra "janela deslizante" da visão §D. Duas regras diferentes com a mesma
   palavra ("quota diária"); a tela escolheu uma.
4. **Timeout e descarte de Turn.** Quem marca `failed` depois de N segundos — o
   worker que morreu não marca nada — e o que "Descartar" significa no servidor.
5. **Quota bloqueia escrita, não leitura.**
6. **Severidade é escala fechada** com rótulo humano, não campo livre.

> **Correção honesta desta análise:** dois itens que eu havia listado como
> buraco já estavam cobertos — o CARD-017 tem o critério do áudio expirado
> (`reply_audio: unavailable`, não 500) e o CARD-015 já media quota em segundos
> de áudio. Ficam como achado apenas o **reset por dia-calendário** e a
> distinção **escrita vs. leitura**, ambos ajustados no CARD-015.

### 2. Que entidade ou campo o CARD-005 ia criar que nenhuma tela usa?

Excesso é erro tão caro quanto falta (visão §F). O que **não** deve entrar:

| Tentação | Por que cortar |
|---|---|
| `Student.email` / `password_hash` / convite | Auth é Fase 3. Nesta fatia o Student é **seed**; campo de credencial criado agora nasce sem regra e sem uso |
| `Student.cefr_level` | CEFR é Fase 6 e é **faixa**, não escalar — criar o campo agora é criar o **formato errado** |
| `Student.daily_quota_minutes` | Quota é CARD-015, e a tela mostra saldo *calculado*, não configuração por aluno |
| `Session.title` / tópico | Nenhuma tela mostra título: o histórico identifica sessão por **data e hora** |
| `Turn.cost` / tokens | É `UsageEvent` (CARD-014), Out explícito do card |
| `Turn.updated_at` genérico | Não responde nenhuma pergunta da tela. Timestamps **por artefato** respondem várias (progresso, latência, timeout) |
| Estado `pending` **visível no contrato** | Nenhuma tela distingue "na fila" de "transcrevendo". O estado interno pode existir; **exibi-lo** é vazamento de mecânica |

### 3. Onde a tela pede algo que o domínio não consegue responder hoje?

| A tela pergunta | O domínio proposto responde? |
|---|---|
| "em que passo dos 3 estou?" | ❌ — `processing` cobre STT+LLM+TTS inteiros |
| "quantos minutos falei hoje / nesta sessão?" | ❌ sem `audio_duration` (**P7** corrige) |
| "já passou de 30s sem resposta?" | ❌ sem timestamp de início de processamento |
| "esse áudio expirou ou nunca existiu?" | ❌ — precisa distinguir os dois casos |
| "qual foi o acerto do dia?" | ❌ — não existe o conceito |
| "esta sessão ainda aceita turnos?" | ❌ — `Session` não tem ciclo de vida no card |

---

## A tensão dos estados — a leitura procede, e é pior do que parecia

**Procede.** O `Design.pdf` (pág. 3) é mais explícito que o briefing: as telas
`1c`/`1d` escrevem **"Passo 1 de 3"** e **"Passo 2 de 3"** com barra de progresso
proporcional, e a `1e` mostra texto legível com "Áudio a caminho…". Com
`pending → processing → completed | failed`, `processing` cobre as três etapas: o
cliente só poderia distinguir "transcrevendo" de "pensando" com um temporizador —
mentira de UI, e o próprio briefing proíbe ("nunca spinner genérico parado").

**Mas o achado real não é "o backlog não previu".** É **incoerência interna do
backlog**:

- **visão §D**: *"O status do Turn é por etapa com payload parcial"*;
- **CARD-010**: já especifica `GET /v1/turns/{id}` com
  `transcribing → thinking → speaking → completed` e payload parcial progressivo;
- **CARD-005**: modela `pending → processing → completed | failed`.

Ou seja: **o CARD-010 promete uma granularidade que o modelo do CARD-005 não
consegue produzir**, e quem está fora de linha com a visão é o CARD-005. A tela
não trouxe requisito novo — ela expôs uma contradição que já estava escrita.

### É ADR? Sim — critério 2, e também o 5

Conferido contra a lista "Quando um ADR é OBRIGATÓRIO" de `docs/adr/README.md`
(LEARNING-0003):

- **Critério 2 — "Define ou altera uma fronteira: … contrato de API, formato de
  dados persistidos"**: a máquina de estados do Turn é as duas coisas ao mesmo
  tempo — coluna persistida (mudar exige migration) e campo do contrato `/v1`
  (ADR-0008 restringe evolução a aditiva; acrescentar valor a um enum de status
  quebra cliente que faz tratamento exaustivo).
- **Critério 5 — "Seria difícil de reverter"**: trocar a granularidade depois
  custa migration + backfill + versão de contrato, mais que uma sessão.

Logo: **ADR obrigatório antes de codar o domínio.**

### As alternativas (a decisão é sua)

#### A — Mais estados na máquina do Turn
`queued → transcribing → thinking → synthesizing → completed | failed`

- **A favor:** um campo só; o contrato do CARD-010 vira projeção direta; consulta
  operacional trivial ("quantos travaram no TTS?"); ordem total explícita.
- **Contra:** o status precisa ser mantido **em sincronia** com o payload — dá
  para existir `status=speaking` com `reply_text` nulo se um passo falhar no meio
  da escrita. Classe de bug que só existe porque há duas fontes da mesma verdade.
- **Custo no V2 (ADR-0003):** o pior dos três. No realtime as etapas **deixam de
  ser sequenciais** (STT incremental e TTS em stream se sobrepõem); uma enum
  linear passa a mentir. O ADR-0003 aceita reescrever a orquestração, mas promete
  que **a entidade sobrevive** — esta alternativa é a que mais arrisca essa
  promessa.

#### B — Estado grosso + artefatos com timestamp, `stage` derivado no servidor
`queued → processing → completed | failed`, mais `transcript`, `reply_text`,
`audio_ref` com seus respectivos `*_at`. O `stage` do contrato é **calculado**,
não coluna.

- **A favor:** a etapa vira **função dos dados** ("tem transcript ⇒ STT acabou"),
  então o status **não tem como mentir** sobre o payload; os timestamps por
  artefato entregam de graça a medição de latência ponta a ponta que o CARD-012
  exige e o "passou de 30s" do achado #6; o CARD-010 entrega o que já prometeu
  sem mudar de escopo.
- **Contra:** a derivação é lógica a mais em algum lugar — se ficar no cliente,
  duplica em mobile e web. Mitigação: derivar **no servidor** (`api/schemas`),
  um lugar só. Consulta operacional fica mais verbosa.
- **Custo no V2:** o menor. Timestamp por artefato continua verdadeiro com
  pipeline sobreposto; só o cálculo do `stage` muda, e ele mora na borda —
  exatamente a camada que o ADR-0003 já assume descartável.

#### C — Etapas como entidade própria (`TurnStep`)
`{turn_id, kind, status, started_at, ended_at, error}`.

- **A favor:** histórico completo por etapa; **retry por etapa** (refazer só o TTS
  sem repagar o LLM — economia real, ADR-0010); observabilidade rica; acomoda
  etapas concorrentes do V2 sem mudança de forma.
- **Contra:** uma tabela, um agregado e um join a mais para um pipeline de **três
  passos fixos**. É um workflow engine em miniatura — o padrão que a Parte F
  corta por antecipação.
- **Gatilho honesto para entrar depois:** a primeira vez que precisarmos
  reprocessar **uma** etapa sem refazer as outras.

### Minha recomendação (não decisão)

**B**, com `stage` derivado no servidor e **C anotada com gatilho escrito**. É a
única das três em que o estado não pode divergir do payload, é a mais barata no
V2, e não muda o escopo do CARD-010. **Aguardando seu OK antes de escrever o
ADR.**

---

## Proposta de ajuste do backlog (proposta — nada alterado ainda)

| # | Card | Mudança proposta | Por quê |
|---|---|---|---|
| 1 | **005** | `audio_duration` no `Turn` (**já aprovado**) + timestamps por artefato + ciclo de vida da `Session` (abrir/encerrar) + invariante "Turn não nasce em Session encerrada" | Sem duração, "6 min"/"12 de 20 min" são incalculáveis e o CARD-015 precisaria de migration + backfill. A invariante é regra de domínio pura, o lugar mais barato para ela |
| 2 | **010** | Precisar que `stage` é **derivado no servidor**, não coluna (se você escolher B) | O card já promete status por etapa; falta dizer de onde ele vem |
| 3 | **013** | Fixar `severity` como enum fechado, com os níveis do design | Hoje diz "severidade" sem escala — vira campo livre por omissão |
| 4 | **015** | Fixar unidade (minutos falados), reset (dia-calendário, fuso fixo) e que quota bloqueia **escrita**, não leitura | Contradiz "janela deslizante" da visão §D — precisa de decisão explícita, possivelmente ADR |
| 5 | **017** | Acrescentar critério "áudio expirado ≠ Turn inválido: transcrição e correções permanecem" | O card cobre lifecycle e delete, não o comportamento de **leitura** depois da expiração |
| 6 | **009 ou 010** | Dar dono ao timeout/`failed` e ao "descartar" | Hoje ninguém marca um Turn travado; sem isso o achado #6 fica órfão |
| 7 | — | **Não** criar card para o "acerto do dia" agora | É Fase 6 (resumo pós-sessão completo). Registrado aqui como achado; criar card agora seria domínio inchado por antecipação (§F) |
| 8 | — | **Manter push cortado** ("avisar quando voltar") | §F já decidiu, com gatilho: revisão espaçada implementada |

**Nada em `docs/backlog/` foi alterado.** A tabela de `docs/backlog/README.md` só
muda depois do OK.
