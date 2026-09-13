# ADR-0065 — "Descartar" marca um campo aditivo e sobrevive à conclusão concorrente do worker

- **Status:** aceito
- **Data:** 2026-09-13
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **2 — define ou
  altera uma fronteira** (novo endpoint público `POST /v1/turns/{id}/discard`,
  novo campo aditivo `discarded_at` no contrato e nova coluna persistida) e
  **5 — seria difícil de reverter** (o RF1 do CARD-032, já decidido com o
  desenvolvedor em 2026-08-27, fixou "aditivo, nunca apaga" como a semântica
  permanente de "Descartar" — mudar isso depois exigiria migrar dado real).
- **Relacionado:** ADR-0016/ADR-0023 (não persistir o que se deriva — este
  campo é a exceção deliberada: "descartado" não é derivável de mais nada),
  ADR-0017/ADR-0039 (`Err` vs. exceção), ADR-0031 (o mesmo princípio de
  `UPDATE` atômico do `SessionRepository.try_end`, aqui aplicado a `Turn`),
  CARD-032

## Contexto

O artboard 16 ("demorou mais que o normal") tem um botão "Descartar" sem dono
no backend. O RF1 do card já decidiu, por escrito, a semântica de produto:
**nada é apagado** — o turn continua no histórico e nas agregações, e
"descartar" só tira o turn da tela ativa. O que faltava eram três decisões de
implementação com superfície real:

1. **Como representar "descartado" sem violar o ADR-0023** (não persistir o
   que se deriva) — já que aqui, ao contrário de `stage`, não há nada de que
   "descartado" possa ser derivado: é um fato que só existe porque o aluno
   agiu;
2. **como recusar atomicamente um turn `completed`** (RF2) sem a corrida
   clássica "ler o status, decidir, escrever" morder sob concorrência (RNF6);
3. **como impedir que a conclusão do worker, que pode ter carregado o turn
   ANTES do descarte, apague o descarte ao gravar seu próprio resultado** —
   o risco mais sutil do card, e o motivo de ele pedir teste de corrida real
   (`asyncio.gather`, não sequencial disfarçado).

## Decisão

**1. `discarded_at: datetime | None`, campo aditivo no domínio, na tabela e no
contrato.** É a única exceção consciente ao ADR-0023 nesta área do sistema:
todo outro campo de `Turn` é ou entrada do aluno ou artefato do pipeline,
e "descartado" é o primeiro fato que nasce de uma ação do aluno SOBRE um turn
já existente, sem mudar seu `status`. Ele convive com qualquer status exceto
`completed` — inclusive `failed`, que é o caso comum do artboard 16.

**2. `TurnRepository.try_discard` é um único `UPDATE` com `CASE`** (não um
par leitura+escrita):

```sql
UPDATE turns
SET discarded_at = CASE
    WHEN status != 'completed' THEN COALESCE(discarded_at, :now)
    ELSE discarded_at
END
WHERE id = :id
RETURNING discarded_at
```

Devolve o `discarded_at` final: não-nulo é sucesso (novo ou repetido —
RNF1), nulo é recusa (RF2, turn completo e nunca descartado antes). As duas
condições do RF2 avaliadas dentro do MESMO `UPDATE` são o que torna a
checagem atômica — mesmo princípio do `COALESCE` de
`SessionRepository.try_end` (ADR-0031), agora com um `CASE` porque aqui a
condição de elegibilidade depende de OUTRA coluna (`status`), não só da
própria.

**3. `apply_turn` (o mapeador que o `update()` do worker usa) nunca copia
`discarded_at` de volta**, meio deliberado e documentado no próprio código.
Um Turn carregado pelo worker antes de um descarte concorrente tem
`discarded_at=None` em memória; se `apply_turn` o copiasse de volta, o
`UPDATE` do worker apagaria silenciosamente um descarte que aconteceu
depois da leitura — a mesma classe de bug do "get-then-set" em qualquer
outro lugar do sistema. A correção não é lock nem retry: é a exclusão do
campo da lista do mapeador, que faz os dois escritores (worker e descarte)
tocarem **colunas SQL disjuntas**. Sob concorrência real, o Postgres
serializa as duas `UPDATE` na mesma linha pelo lock de linha padrão — a
ordem de chegada decide só quem vê o status "completed" primeiro (RF2), nunca
se um apaga o campo do outro.

**4. Posse mascarada como 404 (RNF2), já sem autenticação real.** O aluno da
requisição (hoje sempre `DEV_STUDENT_ID`, `api/dependencies.py:requesting_student_id`)
é comparado contra o `student_id` da sessão dona do turn; um turn de outro
aluno devolve o MESMO `TurnNotFound` de um id inexistente — nunca um 403
distinto, que daria a quem tenta adivinhar ids uma forma de confirmar que um
id existe sem ser dono dele. Este é o primeiro endpoint do projeto a fazer
essa checagem; o padrão (não o código) é o que outros endpoints "de posse"
devem repetir quando a autenticação real (CARD-049) chegar.

## Alternativas consideradas

### Alternativa A — soft delete genérico (`deleted_at` reaproveitado de algo futuro)

Rejeitada: nomear o campo por uma operação genérica de exclusão sugeriria
que uma consulta futura deveria filtrar `WHERE deleted_at IS NULL`
universalmente — e um turn descartado **continua** contando em toda
agregação (RNF4/RNF5). Um nome específico (`discarded_at`) impede esse
acoplamento acidental.

### Alternativa B — tabela própria de descartes (`turn_discards`, um registro por descarte)

Mais "normalizado", mas rejeitada: descartar é um fato **do turn**, não uma
entidade com ciclo de vida própria — não há histórico de múltiplos descartes
a guardar (RNF1 já torna a segunda chamada um no-op), e uma tabela nova só
para um timestamp opcional seria complexidade sem benefício, pelo mesmo
raciocínio que rejeitou uma tabela de idempotência separada no CARD-010
(ADR-0042).

### Alternativa C — `SELECT ... FOR UPDATE` explícito para serializar descarte × conclusão

Tecnicamente resolveria a corrida também, mas foi rejeitada em favor da
exclusão em `apply_turn`: um lock explícito exigiria que TODO caminho de
escrita do Turn soubesse do lock (inclusive `update()` do worker, que não
tem relação nenhuma com descarte), enquanto a exclusão de coluna resolve o
problema estruturalmente — o worker nem precisa saber que "descartar"
existe.

## Consequências

- **Positivas:** nenhuma migration de dado (a coluna nasce nula); o RF6 do
  card ("o desfecho é definido, não acidental") vira uma garantia mecânica —
  provada em `tests/adapters/test_persistence.py::test_descarte_concorrente_com_a_conclusao_nunca_perde_nenhum_dos_dois`
  contra Postgres real, com duas conexões distintas; o padrão de posse
  mascarada fica registrado para o próximo endpoint que precisar dele.
- **Negativas:** `apply_turn` ganhou uma exclusão que só faz sentido lendo o
  docstring — um mapeador novo no futuro que precise copiar "tudo que mudou"
  tem de lembrar de excluir `discarded_at` também, ou reabre o bug. Não há
  teste de tipo que force isso (é campo opcional num dataclass mutável, não
  união fechada); a defesa é o docstring e este ADR.
- **Equivalente mental .NET:** o `CASE` dentro do `UPDATE` é o mesmo truque de
  um `UPDATE ... SET x = CASE WHEN ... END` que se escreveria contra
  qualquer banco relacional para evitar round-trip de leitura+escrita: em EF
  Core seria `ExecuteUpdateAsync` com uma expressão condicional, em vez de
  `Attach` + mudar propriedade + `SaveChanges` (que é exatamente o
  "get-then-set" que este ADR evita).
