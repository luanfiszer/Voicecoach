# Resumo do loop autônomo — 2026-09-13

> Consolida o que o loop autônomo (autorizado nesta data, sem pausa para
> aprovação humana por card) fez desde a última revisão do desenvolvedor.
> Ponto de parada: **imediatamente após o merge do CARD-027**, a pedido
> explícito do desenvolvedor ("quando finalizar o próximo card pare para eu
> analisar"). O prompt atualizado para retomar está em
> [`docs/prompt-loop-autonomo-backlog.md`](prompt-loop-autonomo-backlog.md).
>
> **Retomada na mesma noite (§10):** o desenvolvedor autorizou explicitamente
> continuar o loop a partir do prompt de `docs/prompt-loop-autonomo-backlog.md`.
> Essa segunda leva mergeou CARD-058 e CARD-059 e parou de novo, agora no
> ponto que o próprio prompt já previa: a recomendação de confirmação
> explícita antes do CARD-049.

## 1. Cards mergeados nesta sessão de loop, em ordem

| Card | PR | O que entregou |
|---|---|---|
| CARD-057 | #30, #34 | Imagem do MinIO migrada de `docker.io` para `quay.io` (saiu do Docker Hub e quebrava todo CI). [ADR-0062](adr/0062-a-imagem-do-minio-migra-do-docker-hub-para-o-quay-io.md) |
| CARD-039 | #31 | STT multilíngue: modelo trocado, `stt_language` configurável, `Transcript`/`Segment` param de parar de descartar confiança/segmentos |
| CARD-040 | #32, #33 | `Turn.reject()` — "não entendi, pode repetir?" vira desfecho tipado; `RejectionReason.NOT_ENGLISH` |
| CARD-042 | #29 | `remove()` do `expo-audio` não pausa nada (medido: 1,98–2,0s de áudio sobrevivendo); "regravar" também não calava. [ADR-0061](adr/0061-o-primeiro-teste-do-cliente-vitest-sobre-logica-extraida.md), [LEARNING-0006](learnings/0006-remove-nao-e-dispose-e-o-gate-que-faltava-era-o-teste.md), [LEARNING-0007](learnings/0007-o-relato-dizia-recomecar-e-a-investigacao-mapeou-um-gesto-so.md) |
| CARD-015 | #39 | Cota diária (minutos+turns) + kill switch global por custo + rate limit por sessão+IP, sem migration. [ADR-0063](adr/0063-cota-diaria-em-minutos-e-turns-e-kill-switch-global-por-custo.md) |
| CARD-028 | #41 | Registro de decisão dos artboards 03–06 contra a cascata; extraído `subtitulo`/`rotulo` de `rotulos.ts`, testado |
| CARD-016 | #42 | UI de correções tipadas (`corrections[]`) + resumo mínimo de sessão; corrigida bolha "SEM ERROS" que contrariava a regra "sem correção ⇒ sem card" |
| CARD-031 | #43 | `end` na borda; sessão encerrada vira desfecho `Err` tipado |
| CARD-033 | #44 | Saldo de cota e estado do serviço como leitura (`GET /v1/students/me/quota`). [ADR-0064](adr/0064-leitura-de-cota-e-estado-do-servico-get-students-me-quota.md) |
| CARD-032 | #45 | "Descartar" turn travado — **decidido que não apaga nada**, só marca. [ADR-0065](adr/0065-descartar-turn-marca-sem-apagar-e-sobrevive-a-conclusao-concorrente.md) |
| CARD-036 | #46 | Tradução sob demanda: porta própria, tabela, endpoint. [ADR-0066](adr/0066-traducao-e-porta-propria-persistida-por-referencia-a-recurso.md) |
| CARD-030 | #47 | `GET /v1/sessions` agregado no banco + mídia expirada como contrato. [ADR-0067](adr/0067-listagem-de-sessoes-e-o-significado-de-midia-expirada.md) |
| CARD-034 | #48 | Encerramento automático de sessão por inatividade (job periódico do `arq`) |
| CARD-029 | #49 | Histórico de sessões no app: abas Falar/Histórico/Perfil (`expo-router` `Tabs`), tela de histórico, rótulos de data/duração testados |
| **CARD-027** | **#50** | **Telas de exceção do app**: um `OverlayDeExcecao`, quatro conteúdos (offline/cota/pausado/travado), discriminados pela URN do Problem Details — ver §3 |

Todos com quality gates locais verdes + CI verde antes do merge; nenhum
`--no-verify`, nenhum gate contornado.

## 2. Bloqueados / adiados nesta janela, com o motivo

| Card | Situação | Por quê |
|---|---|---|
| CARD-041 | bloqueado | Contradiz o ADR-0057 revisado pelo CARD-040 (português agora é `NOT_ENGLISH`, recusado antes do professor). **Precisa de decisão do desenvolvedor**: revogar o card ou reabrir o ADR |
| CARD-044 | bloqueado | Falta escuta comparada entre vozes `high` (custam 6,5× a mais que `medium`) — preferência subjetiva, fora do que o loop decide sozinho |
| CARD-043 | adiado | Recuo do próprio ADR-0058: >12 arquivos em toda camada, risco concreto em `aclose()` do gerador do professor, e falta de autenticação para "só o dono cancela" |
| CARD-045 | bloqueado | Duas causas independentes: o mecanismo do CARD-041 (bloqueado) e `/v1/students/me`, que pressupõe autenticação inexistente |
| CARD-019 | bloqueado | Spike de STT/TTS no aparelho exige aparelho físico, fala real de aprendiz e escuta comparada — sem parte segura para o loop autônomo |
| CARD-035 | bloqueado | Controles do player (scrub, 0.75×, repetir) — todos os critérios de aceite são audíveis; Simulador não tem microfone nem áudio real (ADR-0054 item 3) |
| CARD-046 | não iniciado | O próprio card pede para não escrever o ADR sem evidência (janela/algoritmo do CEFR) — regra do card, não do loop |

## 3. O que o CARD-027 entregou e por que é o ponto de parada natural

Fecha as últimas três telas "órfãs" desde 2026-08-17 (offline, cota, pausado+
timeout). Destaques:

- **Achado no caminho, não introduzido pelo card**: `ErroDaApi` (em
  `packages/api-client`) descartava o campo `type` do Problem Details desde
  sempre — sem ele, "cota" (429) e "kill switch" (503) não teriam como se
  distinguir por código no dia em que dividirem o mesmo status HTTP. Corrigido.
- **Corte de escopo pré-autorizado pelo próprio card**: a fila local de envio
  offline (persistência entre reaberturas do app) foi cortada — exigiria
  `expo-file-system` como dependência nova, e o card já previa esse corte
  como o candidato natural se o esforço estourasse. Fica o retry manual na
  mesma sessão do app.
- **Verificação real, não só typecheck**, usando o mesmo mecanismo de
  deep-link sem toque que os cards de medição já usavam:
  - **offline** — modo avião real no Simulador (sessão anterior);
  - **cota** — backend local com `DAILY_QUOTA_TURNS_PER_STUDENT=1`, segunda
    execução voltou 429, overlay "Por hoje é isso" renderizado;
  - **travado** — sem worker isolado para pausar, o processo do backend
    inteiro foi congelado com `kill -STOP` logo após o upload ser aceito e
    descongelado 33s depois; o watchdog do cliente (um `setTimeout`
    independente de rede) disparou sozinho, confirmando inclusive que o texto
    "30s" vem de configuração, não está fixo;
  - **pausado (kill switch)** — **não verificado ponta a ponta**: forçar
    `ServiceBudget.is_exceeded()` exigiria gasto real de LLM ou manipular o
    Redis. Coberto só por teste unitário (URN distinta de cota). Dívida
    declarada no card, não escondida.
- **Nenhum ADR novo** — avaliado contra os 6 critérios de `docs/adr/README.md`
  e nenhum se aplica (o fix do `ErroDaApi` implementa uma decisão já tomada
  pelo ADR-0040, não decide nada novo).

Detalhe completo, com a seção "Execução" inteira: `docs/backlog/CARD-027-telas-de-excecao-do-app.md`.

## 4. Achados técnicos que valem lembrar (não específicos de um card)

- **Não existe autenticação em nenhuma rota do backend** (CARD-049+). Vários
  cards desta janela (043, 045) esbarraram nisso.
- **`dict[X, int](...)` subscreve um genérico e AVALIA o nome do tipo** — um
  import feito só sob `TYPE_CHECKING` vira `NameError` em runtime se usado
  assim. Mordeu duas vezes em `repositories.py`.
- **O Simulador não tem microfone, nem prova latência real, nem "negado
  permanentemente"** (ADR-0054 item 3) — mas **prova mais do que a sessão
  anterior a este loop assumia**: screenshots (`xcrun simctl io booted
  screenshot`) e deep links (`xcrun simctl openurl booted "scheme://path"`)
  dão navegação e verificação visual reais. O que falta de fato é **gesto de
  toque automatizado** (`idb`/Maestro/Detox não instalados) e **áudio**
  (entrada e a percepção subjetiva de saída).
- **Truque novo desta sessão**: congelar o processo do backend com
  `kill -STOP`/`kill -CONT` simula timeout de rede de forma determinística,
  sem precisar de um worker isolado para pausar nem de sabotar código.

## 5. Estado do backlog logo após o CARD-027 (ver §8 para o que mudou depois)

Com o CARD-027 mergeado, **todo o backlog de Fase 1–3 que o loop autônomo podia
tocar sem aparelho físico, escuta subjetiva ou autenticação estava esgotado**:
concluído, bloqueado (com nota) ou adiado. Não sobrava nenhum card "seguro" e
"pronto" na fila **até o teste em aparelho físico da mesma noite mudar isso —
ver §8**.

O que restava:

- **Cards bloqueados** (041, 044, 019, 035, 045, 046) — todos esperando
  decisão do desenvolvedor ou insumo que só ele tem (aparelho físico, escuta,
  julgamento de produto/UX).
- **CARD-049 em diante** — a fundação de autenticação (JWT, cadastro,
  login). É o próximo passo natural, mas cruza um limiar: dados de conta
  real, segredo de assinatura de token, provedor de e-mail ainda sem ADR. O
  prompt atualizado (`docs/prompt-loop-autonomo-backlog.md`) recomenda
  **pedir confirmação explícita antes de abrir este card**, mesmo em modo
  autônomo — não é regra nova, é a "cautela redobrada" que o prompt original
  já previa para esta faixa, agora que ela deixou de ser hipotética.
- **Fase 4 (020/022/023)** — pagamento/entitlements, mesma cautela, mesma
  dependência de auth.

## 6. Decisões autônomas tomadas nesta janela que merecem revisão prioritária

- **CARD-015**: rate limit usa `session_id` no lugar de "conta" (não existe
  auth ainda) — **PENDENTE DE REVISÃO HUMANA** (registrado no próprio card).
- **CARD-027**: corte da fila local offline (persistência entre reaberturas
  do app) — decisão conservadora pré-autorizada pelo risco do próprio card,
  não uma pergunta nova, mas vale conferir se a leitura fez sentido.
- **CARD-041/044/045**: bloqueios que dependem de uma escolha do
  desenvolvedor (revogar card vs. reabrir ADR; ouvir e escolher voz).

## 8. Teste em aparelho físico (2026-09-13, mesma noite) — o que mudou depois do ponto de parada

Depois do CARD-027, o desenvolvedor testou o app pela primeira vez num
iPhone físico (dev build via `pnpm run ios:device`, ADR-0054), com microfone
e alto-falante reais — não mais o Simulador. Isso mudou o estado do backlog:

- **Um bug real de uso apareceu e foi corrigido**: a partir da segunda
  gravação de cada sessão do app, o microfone era cortado ~100ms depois de
  começar a gravar, produzindo áudio vazio. Causa raiz: `pause()` do
  `expo-audio` agenda uma desativação de **toda a `AVAudioSession`** 100ms
  depois — mesmo num player que já tinha terminado de tocar sozinho, e a fila
  de playback só libera seus players no próximo `limpar()`, então toda
  gravação nova calava de novo os players (já mudos) do turn anterior,
  disparando a desativação tardia bem em cima da gravação nova. Investigado
  baixando o `.m4a` real do MinIO (`boto3`) e inspecionando com `afinfo`
  (confirmou ~90ms de áudio real contra os 15–20s falados), e lendo o Swift
  da dependência (`node_modules/expo-audio/ios/AudioModule.swift`) — mesmo
  método do [LEARNING-0006]. Corrigido em `silencio.ts`
  (`silenciarELiberar` só pausa quem `playing` ainda é `true`) e documentado
  em [LEARNING-0008](learnings/0008-pause-tambem-nao-e-inofensivo-desativa-a-sessao-100ms-depois.md).
  Mergeado no PR #51, junto com o resto deste item.
- **CARD-035 (repetir, `0.75×`, scrub) foi desbloqueado.** O motivo do
  bloqueio original — falta de aparelho físico com áudio real — deixou de
  existir. O card em si não foi implementado nesta sessão, só reaberto.
- **Dois cards novos nasceram do uso real do app**, a pedido do
  desenvolvedor: **CARD-058** (a UI do botão `traduzir` — o endpoint do
  CARD-036 já existe, só faltava a tela) e **CARD-059** (uma quarta aba de
  Configurações, para preferência de aparelho, sem depender da autenticação
  que a aba Perfil espera).
- **Um problema de ambiente foi resolvido e vale saber para a próxima vez**:
  o dev-client (Simulador **e** aparelho físico) não repropaga
  `app.json > extra` sozinho — ele é embutido no binário nativo em tempo de
  build. Editar `app.json` e só reiniciar o Metro **não basta**; é preciso
  `expo run:ios` (ou `--device`) de novo para o valor novo aparecer. O
  sintoma é um `RedBox`/crash "extra.<campo> inválido: undefined" mesmo com o
  Metro servindo o manifesto certo.

**Estado do backlog agora**: já não é verdade que "nada sobrou" — 058 e 059
são cards seguros para o loop autônomo pegar (sem áudio, sem aparelho, sem
ambiguidade de produto), e 035 pode ser tentado se um aparelho físico estiver
pareado e conectado na sessão (verificável com `xcrun devicectl list
devices`), com o caminho de verificação sem-ouvido descrito no prompt
atualizado.

## 9. Como retomar

O prompt de loop (`docs/prompt-loop-autonomo-backlog.md`) foi atualizado
depois do §8 para refletir este estado — a seção "Como escolher o próximo
card" agora começa por **CARD-058 → CARD-059 → CARD-035 (condicional a
aparelho disponível)**, antes de chegar ao CARD-049. Colar o arquivo inteiro
(a partir de "## Papel") numa sessão nova é suficiente para retomar sem
re-derivar nada disto.

## 10. Segunda leva desta noite — CARD-058, CARD-059, e por que parou de novo

Retomada a partir do prompt do §9, na mesma noite.

### Cards mergeados nesta leva

| Card | PR | O que entregou |
|---|---|---|
| CARD-058 | [#52](https://github.com/luanfiszer/Voicecoach/pull/52) | Botão `traduzir`: `traduzirTexto` ganhou corpo em `packages/api-client` (a assinatura já estava declarada, sem implementação — achado no início da sessão, provavelmente resíduo de uma sessão anterior); estado local por turn em `useTurno.ts`; botão na bolha da resposta em `ListaDoTurno.tsx`. Alvo sempre `reply` |
| CARD-059 | [#53](https://github.com/luanfiszer/Voicecoach/pull/53) | Quarta aba Configurações, sem artboard. Só as seções 2 (limite de gravação, leitura) e 3 (sobre/versão) — a seção 1 (velocidade padrão) adiada de propósito até o CARD-035 existir |

Os dois com quality gates locais verdes (`pnpm run gates` na raiz do monorepo
cliente) + CI verde antes do merge; nenhum `--no-verify`, nenhum gate
contornado.

### CARD-035: verificado no início, e não reaberto

`xcrun devicectl list devices --timeout 10 -v` mostrou o iPhone **pareado**
mas com `tunnelState: disconnected` — não é o mesmo estado de
`tunnelState: connected` que a sessão do teste físico (§8) tinha. Pela regra
que o próprio prompt de retomada registra ("não reabri-lo às cegas"), o card
**não foi tocado**. Ele volta a ser candidato quando o aparelho estiver
pareado **e** conectado no início de uma sessão futura.

### Onde a sessão parou, e por quê

Esgotados 058 e 059, e 035 indisponível, o próximo item da fila é o bloco de
bloqueantes de V1.0 a partir do **CARD-049** (cadastro/login/JWT). O próprio
prompt de retomada (§9) já carregava uma recomendação forte para este ponto
exato: **parar e pedir confirmação explícita do desenvolvedor antes de abrir
o CARD-049**, porque ele introduz autenticação real num backend que hoje não
tem nenhuma, toca segredo (chave de assinatura de token) e depende de um ADR
de provedor de e-mail que ainda não existe — e é fundação de que 050/051/054
dependem em cadeia. Errar aqui é retrabalho em quatro cards, não um card
isolado.

A sessão parou aqui e perguntou ao desenvolvedor antes de abrir o CARD-049,
em vez de decidir por conta própria — é exatamente a situação que a
recomendação do prompt descreve, não uma pausa nova inventada pelo agente.

### Decisões autônomas desta leva que valem revisão

- **CARD-058**: alvo da tradução sempre `reply` (nunca `correction`) — leitura
  literal dos critérios de aceite do próprio card, não ambiguidade nova.
- **CARD-058**: botão dentro da bolha da resposta, não numa barra de
  controles — decisão local e reversível, o CARD-035 ainda não existe para
  ditar o layout.
- **CARD-059**: nenhuma — o corte de escopo (só seções 2 e 3) já estava
  escrito no próprio card como o caminho certo se o CARD-035 não tivesse
  rodado antes.

Nenhuma das três está marcada **PENDENTE DE REVISÃO HUMANA** no sentido do
§6 — são leituras diretas do texto dos cards, não decisões de produto
inventadas pelo agente.

## 11. Terceira leva desta noite — CARD-049, e por que parou aqui

O desenvolvedor confirmou abrir o CARD-049 depois da pergunta do §10. Esta
leva mergeou um card grande e parou **a pedido explícito dele**, para
revisão, antes de tocar no CARD-050.

### O que foi mergeado

| Card | PR | O que entregou |
|---|---|---|
| CARD-049 | [#55](https://github.com/luanfiszer/Voicecoach/pull/55) | Cadastro/login/tokens completo (ADR-0007): argon2id, JWT+refresh rotativo com detecção de reuso, verificação de e-mail, **recuperação de senha** (adicionada nesta sessão — o próprio card a nomeava como "o furo clássico"). 8 endpoints em `/v1/auth`. `requesting_student_id()` deixou de ser `DEV_STUDENT_ID` fixo em TODAS as rotas. [ADR-0068](adr/0068-provedor-de-email-transacional-resend-com-console-como-default.md) (Resend + console). Um segundo commit na mesma branch, antes do merge, corrigiu o CI (faltava `JWT_SECRET` no passo que gera o schema OpenAPI e os tipos TS) |

Nenhum outro card foi tocado nesta leva — CARD-049 sozinho já era do
tamanho de vários cards anteriores somados (58 arquivos, ~6300 linhas).

### Duas perguntas de produto, feitas ao vivo ao desenvolvedor e respondidas
(registro completo em `docs/perguntas-em-aberto.md`)

1. **"Ativar JWT real em TODAS as rotas já existentes agora, sabendo que
   isso quebra o app até o CARD-050 existir?"** — **sim, ativar tudo.** Não
   foi decisão do agente: o app mobile fica sem falar com o backend até o
   próximo card.
2. **"Login social (Google) entra junto deste card, ou é card separado?"**
   — **card separado.** "Só Google" viola a Guideline 4.8 da Apple (exige
   Sign in with Apple também); virou o **CARD-060**, com ADR próprio
   pendente para revisar o ADR-0007.

### Três bugs achados pelos próprios testes, corrigidos antes do merge

1. `Argon2PasswordHasher.verify` não cobria `InvalidHashError` — hierarquia
   de exceção separada de `VerificationError` no argon2-cffi (verificado com
   `.__mro__`: uma desce de `ValueError`, a outra de `Argon2Error`). Sem o
   segundo `except`, um hash malformado faria login **crashar** (500) em vez
   de recusar.
2. `mark_email_verified` pedia `credential_id`, mas todo chamador só tem
   `student_id` — `KeyError` no primeiro teste de roundtrip. A porta foi
   corrigida para filtrar por `student_id` (único em `credentials`).
3. A rota `confirm-email` reusava `TYPE_INVALID_REFRESH_TOKEN` por engano,
   copiado do endpoint de refresh vizinho — corrigido com um tipo próprio
   (`TYPE_INVALID_EMAIL_CONFIRMATION_TOKEN`).

### Decisões — o que é PENDENTE DE REVISÃO HUMANA de verdade

- **`RESEND_API_KEY` não existe no `.env`** — `EMAIL_PROVIDER` fica em
  `console` (escreve o link no log) até o desenvolvedor criar a conta
  Resend e decidir sobre domínio verificado. O e-mail de confirmação nunca
  foi testado contra a API real, só com `httpx.MockTransport`.
- **CARD-060** (login social) está criado e sem ADR ainda — o ADR que
  revisa o ADR-0007 fica para quando aquele card rodar.
- Recuperação de senha não tem UI: o e-mail carrega o token como texto,
  sem formulário — trabalho de cliente (CARD-050/052).

As duas perguntas de produto (acima) **não** são pendências — foram
respondidas ao vivo, não são decisão autônoma do agente.

### Achado técnico que vale lembrar

O padrão "adicionar um import antes de qualquer uso" faz o hook de
pre-edição (`ruff check --fix`) **remover o import como não usado** — só
sobrevive quando import e primeiro uso entram no mesmo `Edit`. Mordeu
umas 15 vezes nesta sessão (sempre com o mesmo sintoma: `F821 Undefined
name` no próximo edit). Não é bug do processo, é uma característica do
autofix que vale saber de antemão na próxima sessão longa de edição.

## 12. Como retomar

**Parou a pedido explícito do desenvolvedor**, não por falta de card seguro
— ao contrário das paradas anteriores (§1, §10), aqui havia um próximo card
claro (CARD-050) e a decisão de não seguir foi dele, para revisar o volume
grande que o CARD-049 trouxe antes de continuar.

Próximo candidato natural: **CARD-050** (a sessão autenticada no cliente
mobile — secure storage, refresh automático, expiração). É outro card
grande, do lado mobile, e o app **já está quebrado** sem ele (efeito
colateral aceito do CARD-049). O próprio card nomeia o bug do refresh
concorrente como risco central — vale reler o card inteiro antes de
começar, não só o resumo daqui.

Depois dele (ou em paralelo, se o desenvolvedor preferir), **CARD-060**
(login social) tem o ADR pendente e depende do CARD-049 (concluído) — pode
ser o próximo card de backend caso o CARD-050 fique para uma sessão de
cliente específica.
