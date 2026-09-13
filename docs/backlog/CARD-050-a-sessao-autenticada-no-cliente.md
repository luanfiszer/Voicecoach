# CARD-050 — A sessão autenticada no cliente: secure storage, refresh e expiração

- **ID:** CARD-050
- **Épico:** Contas e auth de verdade (bloqueante de V1.0 — N3 do corte)
- **Esforço:** M
- **Status:** concluído (2026-09-13)
- **Dependências:** CARD-049, ADR-0007, ADR-0046

## Contexto

A outra metade do N3. O CARD-049 entrega os endpoints; este entrega o que o app
faz com eles — e é a metade que costuma ser subestimada, porque "guardar um
token" parece trivial e não é.

O ADR-0007 já decidiu o que importa: **`expo-secure-store` (Keychain/Keystore),
nunca `AsyncStorage`**. O resto é máquina de estados.

## Problema

O app não tem noção de "quem está usado". Não há tela de entrada, não há token,
e o client de `packages/api-client` (ADR-0046) não manda credencial nenhuma.
Sem isso não há cota por aluno, não há assinatura e não há a tela de conta que o
delete (CARD-051) exige.

## Proposta técnica

1. **Tokens em `expo-secure-store`.** O `AsyncStorage` é texto puro no disco do
   app — num aparelho comprometido, é o refresh de 30 dias em claro.
2. **O refresh acontece no client, num lugar só.** Uma requisição que volta
   `401` dispara o refresh e **repete a original uma vez**. O ponto difícil é a
   concorrência: com o SSE do turn e uma chamada de perfil simultâneas, dois
   `401` não podem disparar dois refresh — o segundo rotacionaria o token que o
   primeiro acabou de emitir e **derrubaria a família inteira** (CARD-049, item
   3). Precisa de uma promessa compartilhada, e este é o pedaço que merece teste
   próprio.
3. **O SSE é o caso especial e não pode ser esquecido.** Ele é uma conexão
   longa: o token pode expirar **no meio** do stream. A retomada por
   `Last-Event-ID` (ADR-0041) já existe e é o mecanismo certo — reconectar com
   token novo, não derrubar o turn.
4. **Expiração é tela, não erro.** Refresh que falha leva à entrada, sem
   mensagem de pânico e **sem perder o turn em andamento** se houver um.
5. Telas: entrada, cadastro, "confirme seu e-mail", recuperação de senha, e a de
   conta (que o CARD-051 completa).

## Refinamento obrigatório — cache e limites

**Cache:** o access token em memória; o refresh em secure storage. TTL: o do
token (15 min). Invalidação: `401` do servidor, logout, e troca de senha. **O
relógio do aparelho não é fonte de verdade** — expirar por conta própria lendo
o `exp` é otimização válida, mas o `401` é quem manda; aparelho com relógio
errado é caso real.

**Endpoint:** consome os do CARD-049; não cria nenhum.

**Dependência externa:** a API. **Timeout, retry e desfecho** seguem a política
já estabelecida no cliente (ADR-0046 e o tratamento de rede do CARD-012, que já
nomeia o host inalcançável). **Idempotente:** login e refresh **não** são —
repetir um refresh é exatamente o que revoga a família. Isto proíbe retry
automático no refresh, e a proibição precisa estar no código com o motivo.

## Escopo

- **In:** secure storage; a máquina de sessão; o refresh único e concorrente no
  client; a reconexão do SSE com token renovado; as telas de entrada, cadastro,
  confirmação e recuperação; o logout.
- **Out:** delete de conta (CARD-051). Biometria. "Continuar conectado" como
  opção — a sessão é longa por desenho. Login social.

## Critérios de aceite

- **Dado** o app fechado e reaberto, **quando** havia sessão, **então** o aluno
  entra direto, sem redigitar senha.
- **Dado** um access expirado, **quando** duas requisições saem juntas e ambas
  recebem `401`, **então** **um único** refresh acontece e as duas seguem — e há
  teste que prova, porque é aqui que se derruba a família de tokens.
- **Dado** um refresh inválido, **quando** o app tenta renovar, **então** vai
  para a entrada com estado limpo, e nada do aluno anterior fica na tela.
- **Dado** um turn em andamento por SSE, **quando** o token expira no meio,
  **então** o stream reconecta com `Last-Event-ID` e **o turn não se perde**.
- **Dado** o aparelho com relógio adiantado em horas, **quando** o app faz
  requisições, **então** ele funciona — o `401` governa, não o relógio local.
- **Dado** logout, **quando** concluído, **então** o secure storage não guarda
  token nenhum.

## Riscos

- **A concorrência do refresh é o bug clássico**, e aqui ele tem consequência
  severa e não óbvia: derrubar a família desloga o aluno "sem motivo". Já está
  como critério de aceite justamente por isso.
- **O SSE com token expirado** é o caminho que ninguém exercita até acontecer em
  produção, com um turn longo.
- **`expo-secure-store` tem limite de tamanho por item** e comportamento próprio
  quando o aparelho não tem código de acesso configurado. Verificar cedo, não na
  véspera.

## Objetivo de aprendizado

Entender **como se serializa uma operação assíncrona compartilhada em
JavaScript** — a promessa única guardada num ref, que todos os chamadores
aguardam. Não há paralelo direto em C#: lá o reflexo seria `SemaphoreSlim` ou
`Lazy<Task<T>>`; aqui não há lock porque não há thread concorrente — o event
loop é um só, e o que existe é uma janela entre `await`s. Entender **por que a
corrida existe mesmo sem paralelismo** é o objetivo.

## Execução (2026-09-13, loop autônomo)

### O que foi implementado

- **`packages/api-client`**: os oito métodos de `/v1/auth` (`registrar`,
  `login`, `renovarTokens`, `sair`, `confirmarEmail`, `reenviarConfirmacao`,
  `pedirRedefinicaoDeSenha`, `redefinirSenha`) no mesmo `criarCliente` — sem
  mudar a forma do factory (ADR-0046 continua valendo: nenhum estado, nenhuma
  dedup, nenhuma decisão de retry mora aqui). 12 testes novos.
- **`apps/mobile/src/features/auth/sessaoAutenticada.ts`** — o núcleo puro
  (zero import de React, zero import nativo) que implementa a máquina de
  estados: `carregando → autenticado | nao_autenticado`, a renovação com
  promessa compartilhada (o objetivo de aprendizado do card), e
  `fetchAutenticado` — um substituto de `fetch` que injeta o `Authorization`
  e, num `401`, renova e repete a chamada original **uma única vez**. 12
  testes, incluindo o critério de aceite mais caro do card (duas chamadas
  concorrentes que recebem `401` disparam um único `renovarTokens`).
- **`armazenamentoDeToken.ts`** — o refresh token em `expo-secure-store`
  (ADR-0007, dependência já decidida ali; nenhum ADR novo). Sem teste
  próprio, de propósito: é a fronteira nativa que o núcleo existe para não
  precisar mockar (ADR-0061).
- **`useSessao.tsx`** — o contexto React sobre o núcleo; `ProvedorDeSessao`
  envolve o app inteiro em `app/_layout.tsx`, que agora decide entre a tela
  de carregamento, o fluxo de auth (não autenticado) ou o `Stack` do produto
  (autenticado) — a guarda de sessão mora **fora** do `expo-router`, como
  `useState` local, não como grupo de rotas.
- **Cinco telas** (`TelaEntrada`, `TelaCadastro`, `TelaConfirmeSeuEmail`,
  `TelaEsqueciMinhaSenha`, `TelaRedefinirSenha`), roteadas por
  `FluxoDeAuth.tsx` com `useState` local — nenhuma precisa de URL própria.
  Estilo do artboard 11 (campo com rótulo, botão cheio acento, link em
  negrito), sem o código de convite (morto pelo ADR-0010/CARD-049).
  Componentes extraídos e reusados: `CampoDeTexto`, `BotaoPrimario`,
  `LinkDeTexto`.
- **`useTurno.ts`/`useHistorico.ts`** passaram a construir o client com
  `fetch: fetchAutenticado` — é o que faz TODO o produto (turn, histórico,
  cota, tradução) herdar a renovação automática sem nenhum código
  específico por feature.
- **`perfil.tsx`**: mínimo funcional (botão "Sair") — o resto da tela de
  conta é do CARD-051, como o próprio card já previa ("a tela de conta que o
  CARD-051 completa").

### Decisão autônoma registrada — link de redefinição de senha sem deep link

**A pergunta que se faria:** o link de "esqueci minha senha" deveria abrir o
app direto (deep link `voicecoach://...` + página web de fallback), ou o
aluno cola o código à mão?

**Decisão:** colar à mão (campo de texto na `TelaRedefinirSenha`), sem deep
link. **Por quê:** o e-mail que o CARD-049 já manda aponta para um endpoint
que é `POST` no servidor — um clique comum, em qualquer cliente de e-mail,
não tem como coletar a senha nova nem disparar um `POST`; a ação sempre
precisaria do app ou de uma página web (que não existe) de qualquer forma.
Configurar deep link (`expo-linking`, já presente, mas sem associação de
domínio/universal link configurada) e um fallback web é infraestrutura nova
que nenhum critério de aceite deste card pede — o mecanismo funciona ponta a
ponta (testado) sem isso, só sem o toque único. **PENDENTE DE REVISÃO
HUMANA**: se a fricção de colar o código for grande demais na prática, virar
deep link é o próximo passo natural, e não uma correção de bug.

### O que não foi verificado (dívida declarada, não escondida)

- **Nada disto rodou em aparelho físico ou Simulador.** `expo-secure-store`
  é módulo nativo novo — exige `expo prebuild`/`expo run:ios` para existir de
  verdade, e nenhum aparelho estava pareado nesta sessão (mesma limitação
  registrada para o CARD-035). Toda a lógica está testada em Node
  (ADR-0061); o que só o aparelho prova (Keychain de verdade, o app
  reaberto depois de fechado) fica para a próxima sessão com aparelho.
- **SSE reconectando com token renovado no meio do stream**: coberto **por
  composição** (o client do `useTurno` usa `fetchAutenticado`, então
  qualquer reconexão — inclusive a de `Last-Event-ID` já existente desde o
  ADR-0041 — herda a renovação), mas não tem teste dedicado: `useTurno.ts`
  já não tinha teste próprio antes deste card (é o hook mais amarrado a
  `AppState`/`expo-audio` do projeto), e não é este card que muda essa
  convenção.

### Gates

`pnpm run gates` (lint + `tsc --strict` + vitest) verde — 80 testes no
monorepo cliente, dos quais 24 novos nesta sessão.

### ADR

Nenhum novo. `expo-secure-store` já estava decidido no ADR-0007; a forma do
client (sem estado, sem dedup) já estava decidida no ADR-0046. Nenhuma
fronteira nova, nenhuma dependência que não estivesse já escolhida.
