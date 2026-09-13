# CARD-058 — O botão `traduzir` ganha tela: o adendo que o CARD-016 prometeu

- **ID:** CARD-058
- **Épico:** Fase 3 — Domínio pedagógico (artboard 06)
- **Plataforma:** mobile · **Esforço:** P · **Status:** concluído (2026-09-13)
- **Dependências:** CARD-016 (concluído), CARD-036 (concluído — o endpoint já existe)

## Contexto

O artboard 06 desenha `traduzir` junto dos outros três controles da resposta
(play/pause, `0.75×`, `repetir`). O CARD-016 (UI de correções) tratou o botão
como condicional desde o início — "se o endpoint já existir; senão, decisão na
sessão" — e decidiu **deixar de fora**, registrando por quê:

> "o botão `traduzir` fica de fora. O endpoint (CARD-036) ainda não existe —
> está mais à frente na fila do loop. Implementar o botão sem o endpoint
> significaria ou um botão morto ou inventar a API fora de ordem. Registrado
> aqui para quando o CARD-036 for implementado: a UI do botão volta a este
> card ou vira um adendo pequeno nele."

O CARD-036 rodou depois e entregou o endpoint (`POST` de tradução sob demanda,
sem criar turn nem mexer na cota — RNF6 do próprio card: nada de tradução
preventiva). O adendo nunca aconteceu. Este card é ele.

## Problema

**O backend sabe traduzir; nenhuma tela pede.** O botão do artboard nunca foi
desenhado na UI, então hoje não há como o aluno acionar o endpoint que já
existe e já está testado.

## Proposta técnica

- **Um botão por resposta do professor**, ao lado (ou junto) dos controles que
  o CARD-035 for entregar — mas **não depende dele**: `traduzir` é uma chamada
  simples, sem fila de reprodução nem estado de velocidade/posição envolvidos.
  Pode e deve ser implementado independente da ordem entre os dois cards.
- **Estado local por turn**: `ocioso → traduzindo → traduzido | falhou`. A
  tradução, uma vez obtida, fica visível **até `limpar()`** (mesmo padrão de
  `correcoes`/`transcricao` em `useTurno`) — trocar de tela ou gravar de novo
  a descarta, pedir de novo busca de novo (RNF6 do CARD-036: sem cache do lado
  do servidor além do que ele já decidiu).
- **Sem re-tradução automática.** Se o aluno já traduziu esta resposta e toca
  de novo, decidir: reusar o resultado em memória (não gasta IA de novo) ou
  pedir de novo — a leitura mais alinhada ao RNF6 do CARD-036 ("sem tradução
  preventiva", ou seja, tradução É gasto real) é **reusar em memória**, nunca
  pedir duas vezes pela mesma resposta sem o aluno limpar a tela.
- **Erro de tradução não é erro do turn.** Falhar em traduzir não pode
  degradar a exibição da resposta original — mesma filosofia do ADR-0024 item
  5 ("áudio expirado ≠ turn inválido"), aqui: "tradução indisponível ≠
  resposta inválida".

## Escopo

- **In:** o botão `traduzir`; o estado local por turn; a chamada ao endpoint
  do CARD-036 via `packages/api-client`; o texto traduzido exibido junto da
  resposta original (não substituindo — o artboard mostra os dois).
- **Out:** tradução de turns do histórico (o CARD-029 mostra resumo agregado,
  não o texto turn a turno — se um dia precisar, é outro card); tradução
  automática/preventiva (RNF6 do CARD-036, herdado aqui); qualquer UI de cota
  específica de tradução (a cota geral já existe, CARD-015/033).

## Critérios de aceite

- **Dado** uma resposta do professor já concluída, **quando** toco `traduzir`,
  **então** vejo a tradução aparecer junto do texto original, sem substituí-lo.
- **Dado** uma tradução já obtida para esta resposta, **quando** toco
  `traduzir` de novo, **então** não é feita uma segunda chamada ao servidor.
- **Dado** o endpoint de tradução falhar, **então** a resposta original
  continua visível e legível — só a tradução mostra um estado de erro local.
- **Dado** eu grave uma fala nova (ou limpe a tela), **então** a tradução
  anterior some junto com o resto do turn.

## Riscos

- **Onde o botão mora na tela** depende um pouco de como o CARD-035 organizar
  os controles — se ele rodar primeiro, `traduzir` deve conviver com o layout
  que ele criar; se rodar depois, o CARD-035 é quem deve encaixar o que este
  card já tiver desenhado. Nenhuma ordem quebra o outro card, mas o layout
  final é responsabilidade de quem fechar por último.

## Objetivo de aprendizado

Nenhum novo — este card reusa o padrão de estado local por turn que
`useTurno`/`useFilaDePlayback` já estabeleceram (ADR-0061: extrair a lógica,
testar sem mock nativo). O ganho aqui é de disciplina de escopo: fechar uma
dívida registrada há duas sessões, sem inflar o card com nada que o artboard
não pede.

## Execução (2026-09-13, loop autônomo)

**Premissa de escopo, confirmada pelo próprio texto do card:** o alvo da
tradução é sempre `reply` (a resposta do professor) — o card e os critérios
de aceite falam o tempo todo de "resposta do professor", nunca de correção
individual. Traduzir uma `Correction` específica (o outro valor de
`AlvoDeTraducao`) não está nos critérios de aceite nem no "In"; fica de fora
por leitura literal do card, não por suposição nova.

- **`packages/api-client`**: implementado `traduzirTexto` em `cliente.ts`
  (a assinatura já estava declarada no tipo `Cliente`, sem corpo — achado ao
  abrir a sessão, provavelmente início de uma sessão anterior). `POST
  /v1/turns/{turn_id}/translations` com `{ target, index }` no corpo,
  seguindo o contrato do `schema.d.ts` gerado a partir do `openapi.json` do
  CARD-036. Três testes novos em `cliente.test.ts` (corpo montado
  corretamente para `reply` e para `correction` com índice explícito; 404
  vira `ErroDaApi` com `detail`).
- **`apps/mobile`**: estado `EstadoDeTraducao` (`fase` + `texto`) adicionado a
  `useTurno.ts`, no mesmo padrão de `correcoes`/`transcricao` — zerado por
  `limpar()`. Função `traduzir()` chama o endpoint só quando `fase` é
  `ocioso` ou `falhou`; `traduzido`/`traduzindo` são no-op, o que implementa
  o critério de aceite "não é feita uma segunda chamada ao servidor" sem
  cache próprio (RNF6 do CARD-036 — quem cacheia é o servidor, o cliente só
  não insiste).
- **UI**: botão dentro da bolha "PROFESSOR" de `ListaDoTurno.tsx`, abaixo do
  texto dos trechos e antes das correções — visível só com `estado ===
  'concluido'`. Ao traduzir, o texto aparece junto (nunca substitui o
  original, critério de aceite). Rótulo do botão extraído para
  `rotuloDaTraducao.ts` (testável sem `Pressable`/`Text` nativos, mesmo
  padrão de `rotulosDeCorrecao.ts` — ADR-0061), com teste próprio.
- **Decisão técnica (posição do botão), registrada porque o "Riscos" do card
  pedia isso explicitamente:** o CARD-035 ainda não rodou nesta sessão (ver
  `docs/loop-autonomo-2026-09-13-resumo.md`), então não havia layout de
  controles (`0.75×`/`repetir`) para encaixar. O botão foi colocado dentro da
  própria bolha da resposta, não numa barra de controles separada — decisão
  local e reversível, não uma escolha de produto. Quem rodar o CARD-035 é
  quem decide se migra para uma barra única.
- **Gates** (`pnpm run gates`, raiz do monorepo cliente): `biome check .`,
  `tsc --noEmit` (api-client e mobile) e `vitest run` — todos verdes, 49
  testes.
- **ADR:** nenhum critério de `docs/adr/README.md` § "Quando um ADR é
  OBRIGATÓRIO" se aplica — não há dependência nova, a fronteira (contrato do
  endpoint) já existia do CARD-036, não há mudança de custo recorrente nem de
  segurança, a decisão é trivial de reverter, e nada contraria convenção
  estabelecida.
- **Regra do explicador (modo autônomo):** nenhuma pergunta de previsão coube
  aqui — as duas decisões não-óbvias (alvo `reply`-only e posição do botão)
  já estavam resolvidas pelo próprio texto do card, não são decisão de
  produto nova.
