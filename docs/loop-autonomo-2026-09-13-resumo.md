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

## 13. Quarta leva — CARD-050, a pedido explícito de continuar

O desenvolvedor autorizou continuar ("Continue, se necessario me pergunte as
pendencias") depois de revisar o CARD-049. Esta leva mergeou o CARD-050
sozinho.

### O que foi mergeado

| Card | PR | O que entregou |
|---|---|---|
| CARD-050 | [#57](https://github.com/luanfiszer/Voicecoach/pull/57) | A sessão autenticada no cliente mobile: `expo-secure-store` para o refresh token; `sessaoAutenticada.ts` (núcleo puro, sem React/nativo) com a promessa de renovação compartilhada — o objetivo de aprendizado do card; `fetchAutenticado` injetando `Authorization` e renovando uma única vez em `401`; cinco telas (entrada, cadastro, confirme-seu-e-mail, esqueci-minha-senha, redefinir-senha) roteadas por `useState` local, fora do `expo-router`; `useTurno`/`useHistorico` migrados para `fetchAutenticado`, herdando renovação automática sem código próprio; oito métodos novos em `packages/api-client` (`registrar`, `login`, `renovarTokens`, `sair`, `confirmarEmail`, `reenviarConfirmacao`, `pedirRedefinicaoDeSenha`, `redefinirSenha`) |

Nenhum outro card foi tocado nesta leva. `pnpm run gates` verde (80 testes,
24 novos) antes do merge; nenhum `--no-verify`, nenhum gate contornado.

### O teste que prova o critério de aceite mais caro do card

Duas chamadas de `fetchAutenticado` disparadas com `Promise.all`, ambas
recebendo `401` de um `fetch` fake, contra um `renovarTokens` fake com atraso
artificial de 5ms — a asserção é `chamadasDeRenovacao === 1`. Sem a promessa
compartilhada guardada em variável de closure, seriam duas chamadas e a
segunda revogaria a família de tokens que a primeira acabou de emitir
(CARD-049, item 3). Ver `apps/mobile/src/features/auth/sessaoAutenticada.test.ts`.

### Decisão autônoma registrada — pendente de revisão humana

**Recuperação de senha sem deep link**: o aluno cola o código do e-mail à
mão em `TelaRedefinirSenha`, em vez de um link que abre o app direto. Motivo
registrado no próprio card: o e-mail do CARD-049 aponta para um `POST` no
servidor — um clique comum não coleta a senha nova nem dispara o `POST` de
qualquer forma, então o mecanismo funciona ponta a ponta sem deep link, só
sem o toque único. Configurar `expo-linking` com associação de domínio é
infraestrutura que nenhum critério de aceite pede. **PENDENTE DE REVISÃO
HUMANA**: se a fricção de colar o código for grande na prática, virar deep
link é o próximo passo natural. Detalhe completo em
`docs/backlog/CARD-050-a-sessao-autenticada-no-cliente.md`.

### O que não foi verificado (dívida declarada)

- **Nada rodou em aparelho físico ou Simulador.** `expo-secure-store` é
  módulo nativo novo e exige `expo prebuild`/`expo run:ios`; nenhum aparelho
  estava pareado nesta leva (mesma limitação do CARD-035 em §10). Toda a
  lógica está testada em Node (ADR-0061); o que só o aparelho prova (Keychain
  de verdade, app reaberto depois de fechado) fica para a próxima sessão com
  aparelho.
- **SSE reconectando com token renovado no meio do stream**: coberto por
  composição (o `useTurno` já usa `fetchAutenticado`), mas sem teste
  dedicado — `useTurno.ts` já não tinha teste próprio antes deste card.

### ADR

Nenhum novo. `expo-secure-store` já estava decidido no ADR-0007; a forma do
client (sem estado, sem dedup) já estava decidida no ADR-0046.

### Como retomar

Sem pausa pedida pelo desenvolvedor desta vez. Candidatos seguintes, ambos
dependentes do CARD-049/050 (concluídos):

- **CARD-051** (delete de conta) — bloqueante de V1.0, N4 do corte, exige um
  ADR próprio (retenção vs. anonimização de `UsageEvent`) antes de fechar,
  por critério 4 do `adr/README.md`.
- **CARD-060** (login social Google+Apple) — tem ADR pendente, revisando o
  ADR-0007.

## 14. Quinta leva — CARD-051, o último bloqueante de V1.0 que dependia só de código

Continuação direta da leva anterior. Mergeou o CARD-051 sozinho — o maior
card desta sessão depois do CARD-049, e o único que exigiu um ADR novo.

### O que foi mergeado

| Card | PR | O que entregou |
|---|---|---|
| CARD-051 | [#59](https://github.com/luanfiszer/Voicecoach/pull/59) | Delete de conta dentro do app (Guideline 5.1.1(v), LGPD). Exclusão lógica imediata (`Student.deleted_at`, revoga refresh tokens, `requesting_student_id` passa a checar a conta a cada request) + expurgo físico assíncrono e idempotente por varredura periódica do worker (`turns` → `sessions` → storage → `Student`). [ADR-0069](adr/0069-delete-de-conta-conteudo-apaga-usageevent-sobrevive-anonimo.md): `UsageEvent` nunca é apagado — `turn_id` perde a FK, `student_id` vira `ON DELETE SET NULL`. `DELETE /v1/students/me`, tela de Perfil com confirmação e aviso de assinatura, `Cliente.excluirConta()` |

Nenhum outro card foi tocado nesta leva. 623 testes de backend (14 novos),
cobertura 93,72% global / 99% no núcleo; 82 testes de cliente. Todos os
gates locais verdes + CI verde antes do merge; nenhum `--no-verify`.

### A decisão técnica central, e por que ela não foi uma pergunta ao vivo

Ler o esquema real (não de memória — LEARNING-0003) revelou que
`usage_events.turn_id`/`student_id` tinham `ON DELETE CASCADE` desde o
CARD-014, herdado de uma época em que nenhum turn e nenhuma conta eram
apagados. O CARD-051 é o primeiro código que de fato apaga os dois, e o
`CASCADE` existente apagaria a única fonte de verdade de custo
(ADR-0051) junto com a conta — exatamente o "Apagar demais" que o próprio
card lista como risco.

Não foi tratada como pergunta ao vivo porque a resposta já estava escrita
no próprio card ("UsageEvent... provavelmente anonimiza, porque apagá-lo
reescreveria a contabilidade do passado") e nos ADRs que o produto já tinha
(ADR-0051): é a aplicação de uma decisão de arquitetura já tomada a um
esquema que ainda não a refletia, não uma escolha de produto nova. Registrada
como [ADR-0069](adr/0069-delete-de-conta-conteudo-apaga-usageevent-sobrevive-anonimo.md),
citando o critério 4 (privacidade/retenção) do `adr/README.md`.

### Outras decisões técnicas, todas decididas e registradas (não perguntas)

- **`requesting_student_id` deixa de ser 100% stateless.** Passa a consultar
  o `Student` a cada request autenticado — um `SELECT` por PK a mais em toda
  rota do produto. Aceito porque o próprio ADR-0007 já registrava esta
  exceção por escrito ("aqui a janela não é tolerável"); o card só pedia para
  não deixá-la em aberto.
- **Expurgo por varredura periódica no worker, não fila de job por conta.**
  Reaproveita o mecanismo já testado do CARD-025/034 (`cron_jobs`, `job_id`
  determinístico entre réplicas) em vez de desenhar um port de fila novo —
  nenhuma característica do expurgo pedia algo diferente.
- **Aviso de assinatura incondicional na tela de Perfil.** A Fase 4
  (pagamento) não existe ainda; o app não tem como saber se há assinatura
  ativa, então o aviso aparece sempre, texto genérico. Não é produto
  inventado — é a única leitura possível do requisito dado o que o sistema
  sabe hoje.

### O que não foi verificado (dívida declarada)

A tela de Perfil (link "Excluir minha conta", confirmação, botão
destrutivo) não rodou em Simulador nem aparelho físico nesta leva — mesma
lacuna já registrada para o CARD-050. Toda a lógica está testada (gates
verdes); o que só a tela renderizada prova fica para a próxima sessão com
Simulador/aparelho.

### Achado que não é deste card, registrado para não se perder

`CARD-017` (lifecycle rules + `delete_prefix`) já estava implementado antes
desta sessão — achado ao ler o código para escrever o ADR-0069, não algo que
este card fez. O índice do backlog continua marcando `017` como "backlog"
porque nenhuma sessão o executou formalmente como card próprio; vale uma
auditoria dedicada num card futuro, fora do escopo do CARD-051.

### Como retomar

Sem pausa pedida pelo desenvolvedor. Com o CARD-051 mergeado, os
bloqueantes de V1.0 que só dependiam de código (049, 050, 051) estão
fechados. O que resta na faixa de auth/conta é:

- **CARD-060** (login social Google+Apple) — tem ADR pendente, revisando o
  ADR-0007. Não depende de nada além do CARD-049 (concluído).
- **CARD-052** (delete de turn/sessão pelo aluno, se existir no backlog com
  esse número) ou o próximo item da fila de bloqueantes de V1.0 — vale
  reler `docs/backlog/README.md` inteiro antes de escolher, porque esta
  sessão já mudou o estado de várias linhas dele.

## 15. Sexta leva — CARD-060, avisado que bateria numa parede de credenciais

O desenvolvedor foi perguntado explicitamente ("CARD-051 está fechado. Como
devo seguir?") e escolheu seguir para o CARD-060 mesmo depois do aviso de
que a sessão provavelmente bateria numa parede de credenciais externas
(mesma classe de bloqueio do Resend no CARD-049). Mergeou o backend inteiro
do card — o único desta leva.

### O que foi mergeado

| Card | PR | O que entregou |
|---|---|---|
| CARD-060 (parcial — ver "bloqueado") | [#61](https://github.com/luanfiszer/Voicecoach/pull/61) | Verificação de `id_token`/`identityToken` via `PyJWT`+`PyJWKClient` (RS256) contra o JWKS público de cada provedor, sem SDK completo. `SocialIdentity` (entidade própria, `(provider, external_id)` único) vinculada por e-mail verificado a uma `Credential` existente, em vez de duplicar conta. Conta puramente social recebe uma `Credential` sem senha usável, herdando toda a máquina de verificação de e-mail do CARD-049 sem mudar uma linha dela. [ADR-0070](adr/0070-login-social-google-e-apple-juntos-vinculo-por-email.md) (revisa o ADR-0007). `POST /v1/auth/google`, `POST /v1/auth/apple`, `Cliente.loginGoogle`/`loginApple` |

30 testes novos (653 no total do backend), incluindo verificação
criptográfica real com um par de chaves RSA gerado na hora — token válido,
chave errada, audiência errada, emissor errado, expirado, sem e-mail, JWKS
fora do ar, e o quirk documentado da Apple (`email_verified` chega como
STRING `"true"`/`"false"`, não booleano). Gates locais e CI verdes antes do
merge.

### O bloqueio, exatamente como avisado

`GOOGLE_CLIENT_ID` e `APPLE_CLIENT_ID` (o Services ID da Apple) não existem
— os dois exigem uma conta Google Cloud e um Apple Developer Program
(matrícula paga em nome do desenvolvedor), fora do alcance de uma sessão de
agente. Sem eles: nenhuma verificação rodou contra o Google/Apple de
verdade (só contra chaves de teste), e nenhuma tela ou SDK nativo foi
construído no `apps/mobile` — um botão de sign-in sem as credenciais reais
para configurá-lo produziria código não testável e não funcional. O card
ficou **bloqueado**, não **concluído**, com os três passos de retomada
escritos no próprio card.

### Decisão técnica que vale destacar: por que a rota não falha no boot

`GOOGLE_CLIENT_ID`/`APPLE_CLIENT_ID` são valores **públicos** do provedor
(vão no `app.json` do cliente, para o SDK nativo) — ao contrário de
`jwt_secret`/`resend_api_key`, não são segredo, então não recebem
fail-fast no boot. O processo sobe normalmente sem eles; a rota responde
`503` ("provedor não configurado") se alguém a chamar antes de as
credenciais existirem. É a mesma disciplina de "nunca 500, nunca silêncio"
do resto do produto, aplicada a uma ausência que é esperada nesta fase, não
uma falha de infraestrutura.

### Achado da Apple que valia verificar no protocolo, não supor

O `identityToken` da Apple **nunca** carrega o nome do usuário em claim
nenhuma — a Apple entrega o nome separado do JWT, no objeto de credencial
do lado do cliente, e só na primeira autorização. Isso já era um risco
nomeado pelo próprio card; o que a implementação teve de decidir foi ONDE
capturar isso (`display_name_hint` no comando do caso de uso, usado só
quando a conta ainda não existe) — decisão técnica direta, não pergunta ao
desenvolvedor.

### Como retomar

Com CARD-049/050/051 concluídos e CARD-060 bloqueado (mas com todo o
trabalho de código feito), não sobra nenhum card "seguro" e pronto na fila
de auth/conta que não dependa de credencial externa, aparelho físico, ou
julgamento de produto que só o desenvolvedor tem. Vale reler
`docs/backlog/README.md` inteiro para escolher o próximo card — o estado
mudou bastante ao longo desta noite.
