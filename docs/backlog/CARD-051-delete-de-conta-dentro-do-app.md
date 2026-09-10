# CARD-051 — Delete de conta dentro do app: a exigência que reprova na revisão

- **ID:** CARD-051
- **Épico:** Lançamento na App Store (bloqueante de V1.0 — N4 do corte)
- **Esforço:** M
- **Status:** backlog
- **Dependências:** CARD-049, CARD-050, CARD-017, ADR-0024

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
