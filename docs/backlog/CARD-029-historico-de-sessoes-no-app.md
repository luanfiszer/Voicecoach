# CARD-029 — Histórico de sessões no app: consulta rápida no celular, análise completa na web

- **ID:** CARD-029
- **Épico:** Fase 3 — Domínio pedagógico
- **Plataforma:** backend/mobile · **Esforço:** M · **Status:** concluído (2026-09-13)
- **Dependências:** **CARD-030** (o backend desta tela), CARD-016; ADR-0008, ADR-0024

## Contexto

O artboard 10 desenha o histórico **no mobile**, com barra de abas
`Falar · Histórico · Perfil`. O CARD-016 o mandou para a web na Fase 5
(*"Out: histórico entre sessões"*).

**A divergência foi decidida em 2026-08-27 a favor do design** — e olhando o
artboard de perto, ela era menor do que parecia: a própria tela diz *"Consulta
rápida. A análise completa fica no app web"* e *"Sessões anteriores a 30 dias
vivem no app web"*. O design nunca pediu o histórico inteiro no celular; o "Out"
do CARD-016 é que foi absoluto demais.

Este card entrega a **consulta rápida**. A análise completa continua sendo web,
Fase 5.

## Problema

Três coisas faltam, em três camadas diferentes:

1. **Não existe `GET /v1/sessions`.** As rotas de sessão são só `POST`
   (`api/routes/sessions.py`), e o `SessionRepository` tem `add`/`get`/`update`
   — nenhum `list_by_student`. **Isto é o [CARD-030](CARD-030-consulta-de-sessoes-listagem-agregada.md)**,
   que roda antes; aqui a tela consome o endpoint pronto.
2. **Não existe navegação.** O `app/_layout.tsx` usa `Stack`, não `Tabs`; o app
   tem uma tela e uma rota de medição. A barra de abas do artboard 10 não existe,
   e ela é pré-requisito das três telas do design (`Falar`, `Histórico`,
   `Perfil`).
3. **"Áudio expirado ≠ turn inválido" nunca foi exercitado.** O CARD-017 tem o
   critério do lado servidor (`reply_audio: unavailable`, não 500). Nenhuma tela
   jamais o mostrou — e o artboard 10 é exatamente onde ele aparece, na terceira
   linha da lista.

## Proposta técnica

- **Endpoint de listagem** com as agregações que o card do artboard mostra: data
  e hora de início, duração falada, nº de turns, nº de correções. **Agregado no
  banco** (`func.count`/`func.sum`), como o `totals_for_student` do CARD-014 já
  faz — não carregando as sessões e contando em Python, que é o N+1 que o
  `lazy="raise_on_sql"` existe para tornar impossível.
- **Janela de 30 dias** no mobile, como a tela promete, com o resto explicitamente
  apontado para a web. É paginação de produto, não técnica — mas o parâmetro é
  do contrato e precisa nascer certo (ADR-0008: evolução aditiva).
- **`Tabs` do `expo-router`** substituindo o `Stack` no layout raiz. A rota
  `medicao` precisa continuar alcançável e **fora** das abas — ela é ferramenta
  de medição (ADR-0047), não tela de produto.
- **O flag de áudio expirado** vindo do servidor, não inferido no cliente por
  data. O cliente que calcula "faz mais de 30 dias, logo expirou" erra no dia em
  que a política de retenção mudar — e ela é configuração (CARD-017).

## Escopo

- **In:** as abas (`Tabs` do `expo-router`); a tela de histórico; o estado de
  áudio expirado renderizado; o estado vazio ("nenhuma sessão ainda"); o
  consumo tipado do endpoint pelo client de `packages/api-client`.
- **Movido para o CARD-030:** o endpoint, a query agregada, o índice e a
  derivação de disponibilidade de mídia.
- **Out:** abrir uma sessão do histórico e reproduzir a conversa inteira (é a
  análise completa, e é web); a tela de Perfil (artboard 12 — depende da auth da
  Fase 3); busca ou filtro; sessões além de 30 dias.

## Critérios de aceite

- **Dado** um aluno com 3 sessões, **quando** ele abre Histórico, **então** vê as
  três com data, hora, duração, nº de turns e nº de correções, mais recente
  primeiro.
- **Dado** uma sessão cujo áudio expirou, **então** a linha mostra *"áudio
  expirado — transcrição e correções permanecem"*, e a sessão **não** some nem
  aparece quebrada.
- **Dado** um aluno sem sessão nenhuma, **então** a tela mostra um estado vazio,
  não uma lista em branco.
- **Dado** a listagem de N sessões, **então** a tela renderiza sem trabalho por
  item além do necessário (a garantia de query é do CARD-030, RNF1).
- **Dado** o app, **então** as três abas existem e `medicao` continua alcançável
  fora delas.

## Riscos

- **Depende de um card de backend que pode escorregar.** Se o CARD-030 atrasar,
  a tentação é chamar `GET /v1/turns` em laço a partir do app — que é o N+1
  atravessando a rede. Se for para mockar, mocke o endpoint inteiro, não a forma.
- **Trocar `Stack` por `Tabs` mexe em toda navegação existente.** É uma mudança
  de layout raiz num app que hoje tem uma tela — barato agora, caro depois.
  Fazer junto com o card que precisa é o momento certo.
- **A janela de 30 dias vira promessa de produto.** Escrita na tela, ela obriga a
  web a existir para o resto. Está coerente com o ADR-0002, mas é dívida
  declarada até a Fase 5.

## Objetivo de aprendizado

Roteamento por sistema de arquivos no `expo-router`: como `Tabs` e `Stack` se
aninham, e como se mantém uma rota fora da navegação principal — o oposto do
roteamento por configuração do React web e sem paralelo em .NET, onde a rota é
atributo ou registro explícito, nunca o nome do arquivo.

## Execução (2026-09-13, loop autônomo)

**Verificado antes de codar: este card é testável sem simulador de áudio.**
Ao contrário do CARD-035 (bloqueado na mesma sessão), nenhum critério de
aceite aqui depende de ouvido — é navegação, agregação e texto. A lógica
(rótulos de data/duração) foi extraída e testada com Vitest (ADR-0061); a
estrutura (abas, integração com o backend real) foi verificada com o
Simulador iOS **e** screenshot, algo que a sessão anterior (CARD-035) havia
subestimado como completamente inacessível — não é: falta ouvido e gesto de
toque automatizado, não falta a possibilidade de ver a tela.

**`GET /v1/sessions` (o item 1 do Problema) já veio pronto do CARD-030**, que
rodou antes na ordem de dependência. Este card só consome.

**Abas (`expo-router`, o item 2).** `Stack` → grupo `(tabs)` com `Tabs`. As
rotas de ferramenta (`medicao`, `diagnostico-silencio`) ficam **irmãs** de
`(tabs)` dentro de `app/`, não dentro dele — é o parêntese do expo-router que
tira o segmento da URL sem tirar a rota da árvore. Verificado no Simulador via
deep link (`voicecoach://medicao`): a rota abre **sem** barra de abas, exatamente
o critério de aceite.

**Perfil é uma aba real com tela placeholder**, não uma aba ausente. O
critério de aceite pede as TRÊS abas presentes; a tela de Perfil de verdade
(artboard 12, saldo de cota, conta) depende da auth da Fase 3 (CARD-049/050),
que está fora do escopo deste card e do produto hoje. Isto não é
implementação pela metade — é a aba certa, com o conteúdo certo para o que
existe: "Em breve — depende de login (Fase 3)".

**Ícone das abas: nenhum, e é decisão, não omissão.** O artboard 10 desenha um
círculo vazio sobre cada rótulo — nenhum glifo específico (casa/relógio/pessoa)
foi desenhado, o que indica placeholder de design, não requisito. O projeto
não tem biblioteca de ícones (nenhuma dependência nova sem ADR — critério 1 de
`docs/adr/README.md`). A escolha foi `tabBarIcon: () => null` — texto puro —
em vez do triângulo de fallback do React Navigation, que pareceria um ícone
quebrado. Verificado visualmente: sem o `null`, o simulador mostrava um
triângulo cinza sob cada rótulo.

**O item 3 do Problema ("áudio expirado ≠ turn inválido nunca foi
exercitado")** agora tem tela: `reply_media_available: false` renderiza
"Áudio expirado — transcrição e correções permanecem", sem esconder a sessão
nem quebrar o card. Não pôde ser fotografado com dado real nesta sessão (a
única sessão existente no banco de testes é de hoje, `reply_media_available:
true`) — coberto pelo teste unitário do componente/rótulos e pela leitura do
código; ver Riscos.

**Verificação end-to-end real, não só typecheck.** Subida a infra local
(Postgres/Redis/MinIO via `docker-compose.yml`, migrations, `uvicorn` com o
código atual — havia um servidor de desenvolvimento **desatualizado** rodando
há 7h, de antes do CARD-030, que respondia `405` para `GET /v1/sessions`;
substituído), o app rodado de verdade no Simulador (`expo run:ios`) e
navegado por deep link (`voicecoach://historico`, `voicecoach://perfil`,
`voicecoach://medicao` — o mesmo mecanismo que `app/medicao.tsx` já usa,
necessário porque não há automação de toque disponível nesta máquina, CARD-011).
A tela de Histórico renderizou uma sessão real (13 turnos, 2 correções, 1:47
falados) batendo campo a campo com o artboard. Screenshots capturados com
`xcrun simctl io booted screenshot`.

**Nenhum ADR novo.** Nenhum critério de `docs/adr/README.md` se aplica:
nenhuma dependência nova (Tabs já vem do `expo-router` já instalado); a
mudança de navegação é estrutura de cliente, não contrato de API nem formato
de dado persistido; não afeta custo nem segurança; é trivialmente reversível
(voltar a `Stack` é uma troca de arquivo). Os dois tokens de cor novos
(`acentoSuave`, `chip`) são derivação visual pequena, documentada como tal no
próprio `tokens.ts` — não uma decisão de arquitetura.

**Testes:** `apps/mobile/src/features/historico/rotulosDoHistorico.test.ts`
(10, cada um mapeado a um pedaço do artboard 10 — inclusive o caso "23h50 de
ontem vista logo após a meia-noite" continuar sendo 'Ontem'),
`packages/api-client/src/cliente.test.ts` (5, novo — o primeiro teste deste
pacote, usando a mesma costura de `fetch` injetável do ADR-0046 para provar
URL/query, envelope tipado, `ErroDaApi` e `ErroDeRede`).

**Dívida declarada (ADR-0048/skill do cliente):** o Simulador não prova
microfone nem latência real — irrelevante aqui, este card não toca áudio. O
que o Simulador **não** provou e fica em aberto: o aviso de áudio expirado
com dado de verdade (não havia sessão antiga no banco de teste) e o
comportamento de toque real no `RefreshControl` (puxar-para-atualizar) —
verificado por leitura de código e pela mesma API que `useHistorico` já usa,
não por gesto.

**Regra do explicador:** nenhuma pergunta de previsão coube — a única decisão
de produto em aberto (ícone das abas) tinha uma direção conservadora óbvia
(nenhuma dependência nova) e foi tomada e registrada, não perguntada.
