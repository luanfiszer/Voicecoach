# CARD-029 — Histórico de sessões no app: consulta rápida no celular, análise completa na web

- **ID:** CARD-029
- **Épico:** Fase 3 — Domínio pedagógico
- **Plataforma:** backend/mobile · **Esforço:** M · **Status:** backlog
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
