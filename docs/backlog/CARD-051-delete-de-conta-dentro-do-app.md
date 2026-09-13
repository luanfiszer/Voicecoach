# CARD-051 — Delete de conta dentro do app: a exigência que reprova na revisão

- **ID:** CARD-051
- **Épico:** Lançamento na App Store (bloqueante de V1.0 — N4 do corte)
- **Esforço:** M
- **Status:** concluído (2026-09-13)
- **Dependências:** CARD-049, CARD-050, CARD-017, [ADR-0069](../adr/0069-delete-de-conta-conteudo-apaga-usageevent-sobrevive-anonimo.md)

## Contexto

**Guideline 5.1.1(v) da App Store: app que permite criar conta tem de permitir
excluí-la, dentro do próprio app.** Não vale mandar e-mail para o suporte, não
vale um link para a web. É motivo de rejeição direta, e é das mais fáceis de
esquecer porque nenhum usuário pede.

A visão já dizia, na Parte E, que a política de privacidade e o **direito de
exclusão** não adiam — *"processamos voz (dado pessoal) mesmo em beta próprio…
nascer certo é mais barato que retrofit"*. O prazo chegou.

Isto não é só conformidade de loja: é LGPD. E a decisão de produto de 2026-08-27
sobre o "Descartar" (CARD-032) — **o produto não apaga nada** — vale para turns,
**não** para a conta. São coisas diferentes e o card precisa dizer isso alto,
porque a regra escrita pode ser lida ao contrário.

## Problema

Não há conta (CARD-049 a cria) e não há exclusão. Quando houver conta, haverá
áudio do aluno no S3, transcrições, correções, sessões e eventos de uso — dado
pessoal espalhado por cinco lugares, cada um com retenção própria (ADR-0024).
Excluir de verdade é mais do que um `DELETE` numa linha.

## Proposta técnica

1. **Exclusão a partir da tela de conta**, com confirmação explícita e aviso do
   que se perde. Sem etapa fora do app.
2. **Decidir e escrever o que é apagado e o que é anonimizado.** Não é a mesma
   pergunta:
   - áudio, transcrições e correções são do aluno → **apagam**;
   - `UsageEvent` é registro de custo já incorrido (ADR-0051, custo congelado na
     escrita) → **provavelmente anonimiza**, porque apagá-lo reescreveria a
     contabilidade do passado;
   - registro fiscal de assinatura, se houver, tem retenção legal própria.
   **Esta decisão é ADR** — critério **4** do `adr/README.md` (afeta privacidade
   e retenção de dados de usuário). Ela não está tomada, e o card não fecha sem
   ela.
3. **O delete é assíncrono e tem prazo, não é instantâneo.** Apagar mídia no S3
   por aluno é trabalho proporcional ao histórico; fazê-lo no request deixaria a
   requisição pendurada. Job do `arq`, com a conta marcada como excluída
   **imediatamente** (o aluno não consegue mais entrar) e o expurgo em seguida.
4. **Idempotência é requisito, não detalhe:** o job vai rodar duas vezes (retry
   do `arq`, ADR-0052). Apagar o que já não existe é sucesso.
5. **Um turn em voo no momento da exclusão** precisa de resposta escrita — o
   caminho de cancelamento do CARD-043, se existir, é o mecanismo; se não, é
   deixar terminar e apagar depois.
6. **E o que acontece com a assinatura ativa?** Excluir a conta **não cancela a
   assinatura na Apple** — ela vive no Apple ID, não no seu banco. O app tem de
   dizer isso ao aluno, com clareza, ou ele continua pagando por um app que não
   usa mais. É a parte deste card que mais gera reclamação se ficar implícita.

## Refinamento obrigatório — cache e limites

**Cache:** invalidar a sessão na hora. Como o access token é stateless por 15
min (ADR-0007), **existe uma janela em que o token de uma conta excluída ainda é
aceito** — e aqui, ao contrário do caso comum, ela não é tolerável. A borda
precisa checar a existência da conta, ou o card documenta a janela como aceita.
Decidir, não deixar em aberto.

**Endpoint:** `DELETE /v1/students/me` (ou `POST /v1/students/me/delete`).
**Teto:** baixo, 3/h por conta — é ação única e irreversível. **Autorização:** só
a si mesmo, sempre a partir do token.

**Dependência externa:** o S3/MinIO, pelo adapter síncrono em executor
(ADR-0034). **Timeout e retry:** a política do CARD-026. **Idempotente:** sim,
por desenho (item 4). **Desfecho quando o storage está fora:** o job falha e
retenta; a conta **permanece marcada como excluída** e inacessível. O aluno
nunca vê essa falha — para ele, acabou.

## Escopo

- **In:** o ADR de retenção/anonimização; a tela com confirmação; o endpoint; a
  marcação imediata; o job de expurgo idempotente; o aviso sobre a assinatura; a
  decisão sobre a janela do token.
- **Out:** exportar os dados antes de excluir (direito de portabilidade — LGPD
  também o prevê, e ele **não** é exigência da loja; vira card próprio se
  entrar). Excluir turn isolado — o CARD-032 já decidiu que não apaga.

## Critérios de aceite

- **Dado** um aluno autenticado, **quando** exclui a conta pelo app, **então**
  não consegue mais entrar, imediatamente.
- **Dado** a exclusão pedida, **quando** o job termina, **então** não há áudio,
  transcrição, correção nem sessão daquele aluno — verificado consultando o
  storage e o banco, não confiando no código que apagou.
- **Dado** o job executado duas vezes, **quando** o segundo roda, **então**
  sucesso, sem erro.
- **Dado** o storage fora, **quando** o job roda, **então** ele retenta e a
  conta segue inacessível o tempo todo.
- **Dado** um aluno com assinatura ativa, **quando** vai excluir, **então** a
  tela diz, antes da confirmação, que a assinatura precisa ser cancelada
  separadamente, e mostra como.
- **Dado** um `UsageEvent` do aluno excluído, **quando** consultado, **então**
  ele existe na forma que o ADR decidir — e o teste reflete essa decisão.

## Riscos

- **Apagar demais.** Um `UsageEvent` apagado reescreve o custo do passado e
  quebra a única fonte de verdade de custo (ADR-0051). Por isso o ADR vem antes.
- **Apagar de menos.** Áudio esquecido num prefixo do S3 é dado pessoal
  retido sem base legal. O critério de aceite verifica **no storage**, de
  propósito.
- **A janela do token stateless.** É o tipo de detalhe que passa despercebido e
  aparece como "consegui usar o app depois de excluir a conta".
- **Testar exclusão é destrutivo por natureza.** Precisa de testcontainers
  (ADR-0018) e de dado semeado, nunca de uma conta de verdade.

## Objetivo de aprendizado

Entender a diferença entre **exclusão lógica imediata e expurgo físico
assíncrono**, e por que produtos sérios fazem os dois — o paralelo em .NET
seria um *soft delete* com um job de limpeza, com uma diferença que este caso
torna concreta: aqui o dado não está só no banco, está num object storage com
retenção própria, e "apagar" vira uma operação distribuída que precisa ser
idempotente porque **vai** rodar duas vezes.

## Execução (2026-09-13, loop autônomo)

### A decisão que o card pedia por escrito — [ADR-0069](../adr/0069-delete-de-conta-conteudo-apaga-usageevent-sobrevive-anonimo.md)

Ao ler o esquema real (não de memória, per LEARNING-0003), a tensão que o
card nomeia ("apagar demais" vs. "apagar de menos") já estava resolvida **do
jeito errado** no banco: `usage_events.turn_id` e `usage_events.student_id`
tinham `ON DELETE CASCADE`, herdados de uma época em que nenhum turn e
nenhuma conta jamais eram apagados (CARD-032 decidiu que "Descartar" não
apaga nada). Este é o primeiro card que de fato executa um `DELETE` sobre
`students`/`sessions`/`turns` — e o `CASCADE` existente apagaria a única
fonte de verdade de custo (ADR-0051) junto com a conta.

**Decidido (critério 4 do `adr/README.md` — privacidade e retenção; também
toca o critério 2, altera a fronteira de FK que o CARD-014 fixou):**
`UsageEvent` nunca é apagado por um delete de conta. `turn_id` perde a
restrição de FK (a coluna e a PK continuam existindo — só deixam de ser
*enforced* contra `turns`); `student_id` fica nulável com
`ON DELETE SET NULL`, para que o banco anonimize a linha no mesmo instante
em que apaga o `Student`, sem depender de um `UPDATE` que um job futuro
poderia esquecer. Detalhe completo, alternativas e consequências: ADR-0069.

### O que foi implementado

- **`Student.deleted_at`** (domínio + migration `f3a1c9e4b7d2`) — a exclusão
  lógica. `Student.is_active` deriva dele.
- **`DeleteAccountHandler`** (`application/use_cases/delete_account.py`):
  marca a conta e revoga TODAS as famílias de refresh
  (`revoke_all_for_student`, já existente desde o CARD-049) na mesma
  transação. `DELETE /v1/students/me` (204, rate limit 3/h por conta, próprio
  do card — "ação única e irreversível").
- **`requesting_student_id` deixou de ser 100% stateless** (ADR-0007 já
  previa a exceção, sem nomeá-la): a partir deste card ela também consulta o
  `Student` e recusa (401) se a conta não existir ou tiver `deleted_at`
  preenchido. É o ÚNICO ponto por onde toda rota autenticada passa — a
  checagem mora aqui, uma vez, para nenhuma rota (presente ou futura) poder
  esquecê-la. `LoginStudentHandler` ganhou a mesma checagem (a credencial
  sobrevive até o expurgo; sem ela, senha certa numa conta marcada ainda
  logaria).
- **`PurgeDeletedAccountsHandler`** (`application/use_cases/purge_deleted_accounts.py`)
  — o expurgo físico, por **varredura periódica no worker** (`cron_jobs` do
  `arq`, a cada 5 min, no segundo 45 — mesmo mecanismo de
  `sweep_stale_turns`/`sweep_inactive_sessions`, CARD-025/034), não uma fila
  de jobs por conta: o problema (idempotência, coordenação entre réplicas via
  `job_id` determinístico, lote limitado) já estava resolvido e testado, e
  nenhuma característica do expurgo pedia mecanismo diferente. Ordem por
  conta: `turns` → `sessions` → storage (`MediaStorage.delete_prefix`, já
  implementado desde o CARD-017/ADR-0024) → `Student`. Se o storage falhar
  (`MediaStorageError`), a conta segue marcada e inacessível para a próxima
  rodada — turns/sessions já apagados não reaparecem, e reexecutá-los é
  `DELETE` de zero linhas (idempotente).
- **`StudentRepository`** ganhou `mark_deleted`/`list_pending_purge`/`delete`;
  `SessionRepository` e `TurnRepository` ganharam `delete_all_for_student`
  (a ordem entre os dois é a garantia central — `sessions` não tem
  `ON DELETE CASCADE` para `turns`, de propósito).
- **Cliente:** `Cliente.excluirConta()` em `packages/api-client`; a tela de
  Perfil (`apps/mobile/app/(tabs)/perfil.tsx`) ganhou o link "Excluir minha
  conta" → confirmação com o aviso sobre assinatura (item 6 do card) → botão
  destrutivo (`BotaoPrimario` ganhou `variante="destrutivo"`, cor `perigo`
  nova em `theme/tokens.ts` — sem artboard, registrada como convenção de
  plataforma, não invenção). Ao confirmar: `cliente.excluirConta()` seguido
  de `sessao.sair()` para a limpeza local (mesmo caminho do logout).

### Decisão autônoma registrada — aviso de assinatura é incondicional

O item 6 do card pede que a tela avise sobre assinatura ativa antes de
confirmar. Como a Fase 4 (pagamento/IAP) não existe ainda neste produto, o
app não tem como saber se há assinatura — o aviso é mostrado **sempre**,
texto genérico ("se você tem uma assinatura ativa..."), em vez de
condicionado a um estado que não existe. **Não é PENDENTE DE REVISÃO
HUMANA**: é a única leitura possível do requisito dado o que o sistema
consegue saber hoje; revisitar quando a Fase 4 chegar é natural, não
correção de bug.

### O que não foi verificado (dívida declarada)

- **Nada da tela de Perfil rodou em Simulador ou aparelho físico** — mesma
  limitação já registrada para o CARD-050 (o app inteiro, desde a auth,
  segue sem verificação visual real nesta sessão). Toda a lógica de sessão e
  o `excluirConta()` do client estão testados (`pnpm run gates` verde); o que
  só a tela renderizada prova (o link, o botão destrutivo, o texto de aviso)
  fica para a próxima sessão com Simulador/aparelho.
- **Lifecycle rules do S3 e o `delete_prefix`** (que este card liga ao fluxo
  de conta) já existiam prontos desde antes desta sessão — achado ao ler o
  código, não implementado aqui. O CARD-017 continua marcado "backlog" no
  índice do backlog por não ter sido a sessão que o executou formalmente;
  vale uma auditoria própria num card futuro, fora do escopo deste.

### Testes e gates

Backend: 6 testes novos de adapter contra Postgres real via testcontainers
(`tests/adapters/test_persistence.py`, incluindo os dois que provam o núcleo
do ADR-0069: apagar o turn preserva o `UsageEvent`, apagar a conta o
anonimiza via `SET NULL`), 2 de `DeleteAccountHandler`, 6 de
`PurgeDeletedAccountsHandler`, 2 de `LoginStudentHandler` (conta excluída),
4 de rota (`DELETE /v1/students/me`, incluindo um teste ponta a ponta com
JWT real que prova o critério de aceite central: o MESMO access token,
ainda dentro do TTL de 15 min, para de valer depois da exclusão). 623 testes
no total, `pytest --cov` 93,72% global, núcleo (`domain`+`application`)
99% — os dois gates de cobertura, `ruff format/check`, `mypy --strict` e
`lint-imports` verdes.

Cliente: 2 testes novos em `packages/api-client` (`excluirConta`); `pnpm run
gates` verde (lint + `tsc --strict` + vitest), 82 testes no monorepo
cliente.

### ADR

[ADR-0069](../adr/0069-delete-de-conta-conteudo-apaga-usageevent-sobrevive-anonimo.md)
— critério 4 (privacidade/retenção) e 2 (fronteira de FK). É o ADR que o
próprio card exige antes de fechar ("Esta decisão é ADR... e o card não
fecha sem ela").
