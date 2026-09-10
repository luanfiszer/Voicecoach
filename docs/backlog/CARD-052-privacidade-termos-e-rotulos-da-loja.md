# CARD-052 — Política de privacidade, termos e os rótulos de privacidade da loja

- **ID:** CARD-052
- **Épico:** Lançamento na App Store (bloqueante de V1.0 — N5 do corte)
- **Esforço:** M — **e boa parte não é engenharia**
- **Status:** backlog
- **Dependências:** CARD-051, CARD-017, ADR-0024

## Contexto

Bloqueante do lançamento, e o mais fácil de deixar para a véspera — o que é
exatamente quando ele custa caro, porque **descreve o que o sistema faz**, e
descobrir na hora que o sistema faz outra coisa significa mudar código com o
build pronto.

A visão, na Parte E, já classificava isto como **"não adia"**: *"processamos voz
(dado pessoal) mesmo em beta próprio: definir no MVP a retenção de áudio,
transcrições, direito de exclusão e o texto da política. Nascer certo é mais
barato que retrofit."*

O App Store Connect exige, para publicar: **URL de política de privacidade**,
**URL de suporte** e os **rótulos de privacidade** ("App Privacy") preenchidos —
a declaração item a item do que é coletado, para quê, e se está ligado à
identidade do usuário.

## Problema

Não existe política, não existem termos, não existe página de suporte, e os
rótulos nunca foram preenchidos. Pior: **os rótulos precisam ser verdadeiros**,
e a verdade sobre este produto tem itens que exigem atenção — áudio de voz
enviado a um servidor, transcrições guardadas, e **conteúdo do aluno indo para
um terceiro (Anthropic)**, que é o item que mais gente declara errado.

## Proposta técnica

**Boa parte deste card é redigir, não programar** — e o valor de engenharia está
em fazer o texto corresponder ao sistema.

1. **Inventário do que o sistema faz com dado pessoal**, derivado do código e
   não da memória: o que é coletado (e-mail, senha em hash, áudio, transcrição,
   correções, uso), onde mora, por quanto tempo (as retenções assimétricas do
   ADR-0024 — 1 dia / 90 dias / 7 dias), e para quem vai (Anthropic, provedor de
   e-mail, Apple). **Este inventário é o card**; a política é a redação dele.
2. **Política de privacidade e termos de uso**, publicados numa URL estável — o
   que implica um lugar onde hospedar. A web companion não existe ainda, então
   isto pode ser páginas estáticas simples, e essa decisão é do card.
3. **Rótulos de App Privacy** preenchidos a partir do inventário. Declarar a
   mais é seguro; declarar a menos é falsidade perante a Apple.
4. **URL de suporte** — exigência da loja, e um endereço de contato que exista.
5. **Verificar a coerência com o produto real**, e é aqui que o card pode
   estourar: se a política diz "áudio retido por 7 dias" e o CARD-017 ainda não
   implementou o lifecycle, **a política está mentindo**. Por isso a dependência
   do 017 é dura, não de conveniência.
6. **Consentimento e permissão de microfone**: a *purpose string* do iOS
   (`NSMicrophoneUsageDescription`) tem de dizer a verdade sobre o que acontece
   com a gravação, e ela é lida pelo revisor.

## Refinamento obrigatório — cache e limites

**Cache:** não se aplica.

**Endpoint:** nenhum no produto. As páginas são estáticas; se forem servidas
pela API, ficam **fora** de `/v1` e sem autenticação — política que só o usuário
logado lê não serve para nada, e a loja precisa alcançá-la sem conta.

**Dependência externa:** onde as páginas ficam hospedadas. Se for o mesmo
servidor da API, elas **caem junto com ela** — e uma política inacessível é uma
não-conformidade. Hospedagem estática independente é o desfecho provável, e é
decisão a registrar.

## Escopo

- **In:** o inventário de dados derivado do código; política e termos redigidos
  e publicados; rótulos de App Privacy; URL de suporte; revisão da purpose
  string do microfone; a conferência da política contra o que o sistema de fato
  faz.
- **Out:** consultoria jurídica de verdade — o card produz um texto honesto e
  específico, não um parecer. Portabilidade de dados. Consentimento granular por
  finalidade. DPO e demais formalidades que a LGPD prevê para tratamento em
  escala.

## Critérios de aceite

- **Dado** o inventário, **quando** conferido contra o código, **então** cada
  item nomeia **arquivo e retenção reais** — nada declarado de memória.
- **Dado** a política publicada, **quando** a API está fora do ar, **então** ela
  continua acessível.
- **Dado** os rótulos preenchidos, **quando** comparados ao inventário, **então**
  não há item coletado que não esteja declarado — inclusive o envio de conteúdo
  do aluno a um terceiro.
- **Dado** a purpose string do microfone, **quando** lida por alguém de fora,
  **então** ela diz para onde a gravação vai, não só que "o app precisa do
  microfone".
- **Dado** a política, **quando** ela cita um prazo de retenção, **então** existe
  código que o cumpre (CARD-017) — e o card **não fecha** com prazo declarado e
  não implementado.

## Riscos

- **O risco central é o inverso do usual:** aqui o texto é fácil e o **sistema**
  é que pode não corresponder. Descobrir isso na véspera do envio significa
  mudar código, não parágrafo.
- **Declarar rótulo errado** é problema com a Apple depois de aprovado, que é
  pior que reprovar antes.
- **Este card é chato e não tem recompensa visível**, o que o torna o candidato
  natural a ser empurrado. Ele bloqueia o envio de qualquer forma.

## Objetivo de aprendizado

Não é de Python nem de React, e vale declarar em vez de inventar um: é aprender
a **derivar um inventário de dados pessoais a partir do código**, e ver como a
retenção assimétrica que o ADR-0024 escolheu por custo e latência vira, do outro
lado, uma afirmação legal que alguém pode cobrar. É a primeira vez neste projeto
em que uma decisão de arquitetura precisa ser dita em português para um leigo —
e descobrir que ela não é dizível costuma significar que ela não estava clara.
