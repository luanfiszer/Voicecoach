# ADR-0069 — Delete de conta: conteúdo apaga, `UsageEvent` sobrevive anônimo

- **Status:** aceito
- **Data:** 2026-09-13
- **Relacionado:** ADR-0007 (auth), ADR-0024 (retenção assimétrica de mídia),
  ADR-0051 (`UsageEvent`, custo congelado na escrita), ADR-0063 (kill switch de
  custo), CARD-017, CARD-051
- **Critérios de obrigatoriedade:** **4 — afeta privacidade e retenção de dados
  de usuário** (é a exigência de LGPD/Guideline 5.1.1(v) que motiva o card) e
  **2 — altera uma fronteira** (o esquema de chaves estrangeiras de
  `usage_events`, que era enforced desde o CARD-014).

## Contexto

O CARD-051 (delete de conta dentro do app, exigência de loja e de LGPD) obriga
a decidir, por escrito, **o que apaga e o que anonimiza** quando um aluno
exclui a própria conta. O card já nomeia a tensão: áudio, transcrição e
correção são do aluno e apagam; `UsageEvent` é "provavelmente" anonimizado,
porque apagá-lo reescreveria a contabilidade do passado (ADR-0051, decisão 1:
"o custo é congelado na escrita, não recalculado na leitura").

O que o card **não** podia prever, porque exigiria ler o esquema, é que essa
tensão já está resolvida **do jeito errado** no banco: `usage_events.turn_id`
(chave primária) tem `ON DELETE CASCADE` para `turns.id`, e
`usage_events.student_id` tem `ON DELETE CASCADE` para `students.id`. Até
hoje isso nunca mordeu, porque **nenhum turn e nenhuma conta jamais foram
apagados** — o CARD-032 decidiu que "Descartar" não apaga nada, e não havia
delete de conta. O CARD-051 é o primeiro caminho de código que de fato
executa um `DELETE` sobre `students`/`sessions`/`turns`, e o `CASCADE`
existente apagaria a única fonte de verdade de custo do produto junto com a
conta — exatamente o risco que o próprio card lista em "Riscos: Apagar
demais".

## Decisão

**O conteúdo do aluno é apagado por linha (banco) e por objeto (S3);
`UsageEvent` nunca é apagado por um delete de conta, e fica anônimo pelo
efeito colateral de apagar o `Student`, não por um `UPDATE` que redige campo a
campo.**

1. **O que apaga, de verdade:** `TurnRow` do aluno (via `sessions`), o que já
   arrasta em cascata (`ON DELETE CASCADE` existente) `CorrectionRow`,
   `TurnAudioChunkRow` e `TranslationRow`; `SessionRow` do aluno; e todo objeto
   do S3 sob `student_prefix(student_id)` (`MediaStorage.delete_prefix`, já
   implementado e testado desde o CARD-017/ADR-0024 — este card só o liga ao
   fluxo de conta). `CredentialRow`, `RefreshTokenRow`,
   `EmailVerificationTokenRow` e `PasswordResetTokenRow` cascateiam da
   exclusão do próprio `StudentRow` (`ON DELETE CASCADE` já existente desde o
   CARD-049) — e-mail e hash de senha morrem com eles.
2. **O que nunca apaga:** `UsageEventRow`. É a linha que sustenta a soma de
   custo (ADR-0051) e o kill switch mensal (ADR-0063) — apagá-la subestimaria
   retroativamente um gasto que **já aconteceu**. Zero UsageEvent apagados é
   critério de aceite, não detalhe.
3. **A anonimização é estrutural, não um `UPDATE` a mais para lembrar de
   escrever.** Dois ajustes de chave estrangeira, via migration:
   - `usage_events.student_id` passa a aceitar `NULL`, e seu `ON DELETE
     CASCADE` vira `ON DELETE SET NULL`. O banco desliga o vínculo no mesmo
     instante em que apaga o `Student` — sem essa etapa aparecer como uma
     linha de código que alguém poderia esquecer num caminho de exclusão
     futuro (script de operação, migração de dados, um segundo endpoint).
   - `usage_events.turn_id` **perde a restrição de chave estrangeira** com
     `turns.id` (a coluna continua existindo e continua sendo a chave
     primária da tabela; só deixa de ser *enforced* contra `turns`). É a
     única forma de permitir que um `Turn` seja apagado enquanto o
     `UsageEvent` que ele gerou sobrevive: `turn_id` é `NOT NULL` (é a PK),
     então `SET NULL` é impossível, e manter `CASCADE`/`RESTRICT` obrigaria a
     escolher entre apagar a linha de custo ou nunca poder apagar o turn.
     `UsageEvent` já não é lido por join com `turns` desde o ADR-0051 ("é lida
     em agregação, nunca junto de um turn") — soltar o *enforcement* apenas
     alinha o esquema ao que a própria porta já dizia sobre como a entidade é
     consumida.
4. **A exclusão é lógica e imediata; o expurgo é físico e assíncrono, por
   varredura periódica — o mesmo mecanismo de `sweep_stale_turns` e
   `sweep_inactive_sessions` (CARD-025/034), não uma fila de jobs por conta.**
   `Student` ganha `deleted_at`. O endpoint marca `deleted_at` e revoga todas
   as famílias de refresh (`revoke_all_for_student`, já existente desde o
   CARD-049) na mesma transação — a conta para de aceitar login e refresh na
   hora. Um `cron_job` do `arq`, rodando a cada poucos minutos, varre
   `students` com `deleted_at` preenchido, apaga o conteúdo (item 1) e só
   então apaga a própria linha de `Student` — o que, por causa do item 3,
   desliga o `usage_events.student_id` para `NULL` como consequência do
   próprio `DELETE`. **Reaproveitar o mecanismo de varredura, em vez de
   desenhar uma fila de expurgo nova, é decisão técnica deste ADR**: o
   problema (idempotência, coordenação entre réplicas via `job_id`
   determinístico, lote limitado) já estava resolvido e testado para os dois
   cron jobs anteriores, e nenhuma característica do expurgo de conta pede
   algo que eles não tinham.
5. **A janela do access token stateless não é tolerável aqui** (o próprio
   ADR-0007 já previa a exceção, sem nomeá-la). A partir deste ADR,
   `requesting_student_id` deixa de decodificar só o JWT: ele também busca o
   `Student` (uma consulta por chave primária, o mesmo custo de qualquer outra
   rota autenticada) e recusa com `401` se a conta não existir ou tiver
   `deleted_at` preenchido. O login também recusa contas com `deleted_at`
   preenchido, mesmo com senha correta — a credencial só é apagada no
   expurgo, então ela sobrevive à marcação e precisa ser checada à parte.

## Alternativas consideradas

### Alternativa A — Deixar o `ON DELETE CASCADE` como está, e `UsageEvent` apaga junto

- **O que é:** não tocar no esquema; a exclusão da conta apaga
  `students` → cascata até `usage_events` por `student_id` **e** por
  `turn_id`.
- **Por que foi rejeitada:** é exatamente o risco que o próprio CARD-051
  nomeia como "Apagar demais" — reescreveria retroativamente o custo já
  incorrido, e o kill switch mensal (ADR-0063) passaria a subestimar gasto
  real sempre que uma conta com uso fosse excluída. Contraria o ADR-0051 de
  forma direta.

### Alternativa B — Anonimizar por `UPDATE` explícito no job, sem tocar nas FKs

- **O que é:** manter os `ON DELETE CASCADE` como estão; o job de expurgo
  primeiro roda `UPDATE usage_events SET student_id = NULL WHERE student_id =
  :id`, e só depois apaga turns/sessions/student.
- **Por que foi rejeitada:** resolve `student_id`, mas não resolve `turn_id`
  — a PK continua com `ON DELETE CASCADE` para `turns.id`, então apagar os
  turns do aluno (etapa que o próprio card exige: "áudio, transcrição e
  correção apagam") continuaria arrastando o `UsageEvent` de cada um, com ou
  sem o `UPDATE`. Precisaria soltar a FK de `turn_id` de qualquer forma —
  ponto em que a anonimização de `student_id` por `UPDATE` explícito passa a
  ser um passo a mais que o banco já faz de graça com `SET NULL`, e que um
  caminho de exclusão futuro (fora deste job) poderia esquecer de repetir.

### Alternativa C — `UsageEvent` filha do agregado `Turn`, apagada e substituída por um resumo agregado por conta antes da exclusão

- **O que é:** antes de apagar as linhas do aluno, materializar um total
  (`StudentUsageTotals`) numa tabela de "custo histórico por período",
  desvinculada de `student_id` desde a origem.
- **Por que foi rejeitada:** perde granularidade que o produto pode precisar
  reconstituir (por modelo de LLM, por dia, para reprecificar histórico se a
  tabela de preços mudar de forma — ADR-0051 já trata isso como capacidade
  querida: "quem responde é a linha gravada"). Também introduz uma tabela e
  uma migração de dados só para este card, quando o efeito desejado
  (sobreviver ao `Student`, sem apontar para ninguém) já é alcançável soltando
  duas restrições de FK.

## Consequências

**Positivas**

- O custo histórico do produto (ADR-0051, ADR-0063) nunca é reescrito por um
  delete de conta — a soma mensal do kill switch continua verdadeira mesmo
  depois de contas excluídas.
- A anonimização de `student_id` é **atômica com o `DELETE` do `Student`**,
  garantida pelo banco (`ON DELETE SET NULL`) — não depende de nenhum
  caminho de código lembrar de rodar um `UPDATE` antes. É o mesmo espírito das
  lifecycle rules do S3 (ADR-0006/0024): "compliance que se cumpre sozinha",
  em vez de disciplina manual.
- Nenhum port novo, nenhuma fila nova: o expurgo reaproveita o `cron_jobs` do
  `arq` que o CARD-025/034 já validou (idempotência, `job_id` determinístico
  entre réplicas, lote limitado).

**Negativas — o preço aceito**

- `usage_events.turn_id` deixa de ter integridade referencial garantida pelo
  banco. Um bug em outro caminho de escrita poderia gravar um `turn_id` que
  nunca existiu, e nada avisaria no `INSERT`. Mitigado por escopo: um único
  ponto do código grava `UsageEvent`
  (`UsageEventRepository.add`, chamado uma vez por turn processado, sempre
  com o `turn_id` do próprio turn que acabou de ser criado).
- `requesting_student_id` deixa de ser puramente criptográfico: toda rota
  autenticada paga uma consulta extra por chave primária a cada request. É o
  preço explícito que o card exige pagar ("decidir, não deixar em aberto") —
  aceito porque a alternativa (não checar) reabriria a janela de até 15
  minutos de uso pós-exclusão que o próprio ADR-0007 já registrava como
  aceitável no caso comum e inaceitável neste.
- Um `UsageEvent` com `student_id = NULL` não entra mais em nenhuma agregação
  *por aluno* — o que é o comportamento correto, já que o aluno não existe
  mais —, mas continua contando em qualquer agregação **global** de custo. Se
  um dia existir uma tela de "gasto por aluno ainda ativo", ela precisa
  filtrar `student_id IS NOT NULL` explicitamente, e o teste que cobrir essa
  tela deve exercitar o caso.

**Equivalente mental .NET:** é o padrão comum de *soft delete + anonymize FK*
que aparece em sistemas de billing/audit quando uma entidade "Customer" sai
por LGPD/GDPR mas a linha de "InvoiceLineItem" (o equivalente de
`UsageEvent`) precisa sobreviver: no Fluent API do EF Core isso é
`.OnDelete(DeleteBehavior.SetNull)` na FK de auditoria — só que lá a FK
continua *enforced* porque o EF não tem um meio-termo direto para "aponta
para uma PK, mas sem restrição"; aqui o Postgres permite remover a
constraint e manter a coluna como um UUID histórico não verificado, que é
exatamente o que `turn_id` passa a ser.
