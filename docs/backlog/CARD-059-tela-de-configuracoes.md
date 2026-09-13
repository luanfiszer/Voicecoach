# CARD-059 — Configurações: uma quarta aba para o que é preferência de aparelho, não de conta

- **ID:** CARD-059
- **Épico:** Fase 3 — Domínio pedagógico / experiência do app
- **Plataforma:** mobile · **Esforço:** P · **Status:** concluído com escopo reduzido (2026-09-13) — seção 1 adiada
- **Dependências:** CARD-029 (as abas já existem — `expo-router` `Tabs`). O item
  "preferências de reprodução" do escopo depende também do **CARD-035**
  (velocidade não existe antes dele); os outros dois itens não dependem de
  nenhum card em aberto.

## Contexto

O app tem três abas desde o CARD-029: Falar, Histórico, Perfil. **Perfil** é
hoje um placeholder ("Em breve — depende de login") porque o artboard 12
(saldo de cota, conta) precisa de autenticação, que só chega na Fase 3
(CARD-049+).

Decidido em sessão com o desenvolvedor (2026-09-13): **Configurações é aba
própria**, separada de Perfil — não uma seção dentro dele. A distinção que
justifica isso: Perfil é sobre a **conta** (quem sou, quanto já usei — precisa
de auth); Configurações é sobre o **aparelho** (como o app se comporta para
mim — não precisa de conta nenhuma, e por isso pode existir e ser útil hoje,
antes da Fase 3 chegar).

## Problema

**Não existe lugar nenhum no app para uma preferência que não é da conversa em
si.** Cada vez que uma feature quiser um comportamento configurável (velocidade
padrão de reprodução, autoplay, o que for), ela não tem onde morar — e a
alternativa (esconder a opção dentro da tela de conversa) polui a tela que
existe para uma coisa só: falar.

## Proposta técnica

- **Quarta aba, `Tabs` do `expo-router`** — mesmo padrão do CARD-029
  (`app/(tabs)/configuracoes.tsx`, entrada em `app/(tabs)/_layout.tsx`).
  `tabBarIcon: () => null`, pelo mesmo motivo do CARD-029: nenhum artboard
  desenhou um glifo para esta aba (ela não existe em nenhum artboard ainda),
  e o projeto não tem biblioteca de ícones — inventar um agora seria
  dependência nova sem ADR (critério 1 de `docs/adr/README.md`).
- **Sem nenhum artboard de referência.** Diferente de toda tela implementada
  até aqui, esta nasce de uma conversa entre desenvolvedor e agente, não de um
  design pronto. Seguir o style guide (`docs/design/README.md`: paleta,
  tipografia, alvo de toque 48px) é obrigatório; o layout exato (lista de
  seções vs. lista simples) é decisão de implementação, não de design a
  reconciliar.
- **Cada preferência é uma leitura+escrita local**, não uma chamada ao
  servidor — RNF4 do próprio CARD-035 já registrou o princípio para
  velocidade ("preferência é do aparelho, não do servidor"); este card estende
  a mesma regra às demais. `AsyncStorage` é suficiente (chave-valor simples,
  sem necessidade de arquivo — diferente do caso de `expo-file-system` que o
  CARD-027 recusou para áudio).

## Escopo (2026-09-13, decidido com o desenvolvedor)

- **In — três seções, nesta ordem de prioridade:**
  1. **Preferências de reprodução** — velocidade padrão da resposta do
     professor (o mesmo `0.75×`/`1×` do CARD-035, mas como *default* aplicado
     a toda resposta nova, não só à atual) e, se o CARD-035 tiver decidido um
     alternador de autoplay, ele mora aqui. **Esta seção só entra quando o
     CARD-035 existir** — construir o toggle antes do valor que ele controla
     é o botão morto que o CARD-016 já evitou uma vez para `traduzir`.
  2. **Limite de gravação, como informação, não como controle** — mostra o
     valor de `config.limiteGravacaoSegundos` (hoje 90s). **Somente leitura**:
     o valor é decidido pelo produto (ele é menor que o limite do servidor de
     propósito — ver `apps/mobile/README.md`), e deixar o aluno editá-lo abre
     a possibilidade de configurar um valor que o servidor rejeita. Existe
     aqui só para o aluno entender por que a gravação parou sozinha, sem
     precisar adivinhar.
  3. **Sobre** — versão do app (`app.json > expo.version`), e um espaço
     reservado (sem link ainda) para a política de privacidade do CARD-052,
     quando ela existir.
- **Out:** qualquer preferência que precise de conta (notificações, plano,
  dados pessoais — tudo isso é Perfil, Fase 3 em diante); edição do limite de
  gravação; tema claro/escuro manual (o app já segue o sistema via
  `theme/tokens.ts`, e nenhum artboard pediu um seletor manual); qualquer
  configuração de desenvolvimento/debug (isso é `app.json > extra`, nunca uma
  tela visível ao aluno).

## Critérios de aceite

- **Dado** o app, **então** existe uma quarta aba "Configurações", visível e
  alcançável como as outras três.
- **Dado** o CARD-035 já implementado, **quando** mudo a velocidade padrão em
  Configurações, **então** a próxima resposta nova do professor já nasce
  naquela velocidade — sem precisar mudar por resposta.
- **Dado** a tela de Configurações, **então** ela mostra o limite de gravação
  atual como texto, sem nenhum controle de edição.
- **Dado** a tela de Configurações, **então** ela mostra a versão instalada do
  app.
- **Dado** o app reaberto depois de fechado, **então** a preferência de
  velocidade escolhida **persiste** (sobrevive ao restart — `AsyncStorage`,
  não `useState`).

## Riscos

- **Nasce sem artboard.** O risco é inventar excesso — a régua é a Parte F da
  visão (anti-overengineering) e o próprio escopo acima, que já foi reduzido
  a três itens concretos. Qualquer quarta seção que aparecer durante a
  implementação e não estiver nesta lista **não entra sem confirmar antes**.
- **A seção de reprodução fica vazia até o CARD-035 existir.** Se este card
  rodar primeiro, a seção 1 do escopo é adiada dentro dele mesmo (a tela
  nasce só com as seções 2 e 3) — não é motivo para bloquear o card inteiro.

## Objetivo de aprendizado

Persistência local simples no Expo (`AsyncStorage`) para preferência de
usuário — o primeiro uso dela no projeto (a outra candidata a persistência
local, offline de gravação no CARD-027, foi cortada de escopo). Diferença que
importa: aqui o dado é pequeno, não crítico (perder uma preferência é
recuperável, o aluno só escolhe de novo) — o oposto do padrão de cautela que o
CARD-027 aplicou ao áudio de uma gravação perdida.

## Execução (2026-09-13, loop autônomo)

**Escopo reduzido de propósito, pela regra que o próprio card escreve em
"Riscos":** o CARD-035 não rodou nesta sessão (aparelho físico indisponível —
ver `docs/loop-autonomo-2026-09-13-resumo.md`), então a seção 1
(preferências de reprodução) não tem o que controlar ainda — implementá-la
seria o botão morto que o card já recusa para si mesmo. **Implementadas as
seções 2 e 3.**

- **Rota:** `app/(tabs)/configuracoes.tsx`, quarta `Tabs.Screen` em
  `_layout.tsx` (mesmo padrão do CARD-029: rota fina delegando para
  `TelaConfiguracoes`, `tabBarIcon: () => null` pelo mesmo motivo — nenhum
  artboard desenhou glifo, sem biblioteca de ícones no projeto).
- **Seção "Limite de gravação"**: lê `config.limiteGravacaoSegundos`
  (a mesma fonte que `useGravacao.ts` já usa para parar a gravação sozinha),
  formatado por extenso (`rotuloDoLimiteDeGravacao`, extraído e testado —
  ADR-0061). **Sem controle de edição**, como o escopo exige.
- **Seção "Sobre"**: `Constants.expoConfig?.version` (hoje `0.0.0`,
  `app.json > expo.version`) — não passa por `config.ts` porque não é
  `expo.extra` (o arquivo é só para isso, por design, ver seu próprio
  docstring); é uma leitura direta, de baixo risco.
- **Nenhuma dependência nova**: com a seção 1 fora, não há preferência para
  persistir ainda — `AsyncStorage` não entrou nesta sessão. O objetivo de
  aprendizado do card (persistência local) fica para quando o CARD-035
  entregar o valor a persistir.
- **Gates** (`pnpm run gates`): verdes, 52 testes.
- **ADR:** nenhum critério de `docs/adr/README.md` se aplica.
- **Regra do explicador (modo autônomo):** nenhuma decisão de produto nova —
  o corte de escopo já estava escrito no próprio card ("esta seção só entra
  quando o CARD-035 existir").

**Pendência para quem fechar a seção 1:** ela entra quando o CARD-035
existir, com `AsyncStorage` para persistir a velocidade padrão — é aí que o
objetivo de aprendizado deste card se cumpre de fato.
