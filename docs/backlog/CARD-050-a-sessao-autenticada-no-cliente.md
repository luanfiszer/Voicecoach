# CARD-050 — A sessão autenticada no cliente: secure storage, refresh e expiração

- **ID:** CARD-050
- **Épico:** Contas e auth de verdade (bloqueante de V1.0 — N3 do corte)
- **Esforço:** M
- **Status:** backlog
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
