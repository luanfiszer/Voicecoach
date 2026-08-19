# Prompt — CARD-018: Turn com trechos de áudio (domínio, invariantes e migration)

- **Tipo:** prompt de sessão, complemento de `/executa-card 018`
- **Escrito em:** 2026-08-19, na sessão de reconstrução do backlog
- **Status:** não executado

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 018` e leia isto junto** —
> aqui está só o que é específico deste card e o que o texto do card não
> antecipa.

---

## 1. Por que este é o próximo card

O backlog foi reconstruído em torno de **primeiro áudio em ~1,8 s**
([`docs/reconstrucao-backlog-2026-08-19.md`](../reconstrucao-backlog-2026-08-19.md)).
O caminho crítico é `018 → 006 → 007 → 008 → 009 → 010 → 012`, e o 018 está na
frente por **dependência de dados, não por preferência**: sem `TurnAudioChunk`,
o CARD-008 não tem onde gravar a frase sintetizada e o CARD-009 não tem o que
emitir antes do fim do turn.

É também o momento **mais barato possível**: não existe nenhum turn em banco.
Toda migration aqui é sobre tabela vazia.

**Esforço P.** Se estiver ficando grande, algo saiu do escopo — ver §5.

---

## 2. A decisão já está tomada: leia o ADR antes do código

[**ADR-0023**](../adr/0023-ciclo-de-vida-do-turn-com-entrega-em-cascata.md)
substitui o ADR-0016 e é a fonte de verdade deste card. O ADR-0016 continua no
repositório como histórico, com o status atualizado — **leia os dois**, porque
o princípio que sobrevive está no antigo e a mudança está no novo:

> **Sobrevive:** não persista o que você consegue derivar.
> **Cai:** a premissa de que cada artefato é um objeto produzido inteiro.

Três coisas que o ADR decide e **não** se rediscutem nesta sessão:

1. **A enum `TurnStatus` não ganha valor nenhum.** `queued → processing →
   completed | failed`, como está. Acrescentar `streaming`/`speaking` ao estado
   persistido quebra o contrato aditivo do ADR-0008 e recria as duas fontes da
   mesma verdade que o ADR-0016 rejeitou.
2. **`delivered_partially` é derivado** (`failed` com trechos), não coluna.
3. **A tabela de derivação inverteu.** Com a cascata, o primeiro áudio existe
   **antes** de `reply_text` estar completo. A nova ordem de avaliação está no
   ADR-0023, item 4 — `reply_text` deixa de ser a condição de `speaking`.

---

## 3. O estado real do código — os arquivos que você vai tocar

Já verificado nesta sessão; não repita a arqueologia:

| Arquivo | O que já existe, e o que muda |
|---|---|
| `backend/src/voicecoach/domain/turn.py` | `Turn` como `@dataclass` com `TurnStatus`, os `attach_*`, `complete(now)` e `fail(reason, now)`. **`complete()` já exige `reply_audio_ref` não-nulo** — a invariante do áudio inteiro nasce pronta |
| `backend/src/voicecoach/adapters/persistence/models.py` | `TurnRow` já tem `reply_audio_ref` com o nome certo. **A tabela `turns` não muda** — o delta é só a tabela filha |
| `backend/src/voicecoach/adapters/persistence/mappers.py` | `turn_to_row`, `turn_from_row`, `apply_turn` — os três passam a lidar com a coleção |
| `backend/src/voicecoach/adapters/persistence/repositories.py` | `SqlAlchemyTurnRepository.get/add/update` |
| `backend/tests/domain/test_turn.py` | onde os testes de invariante moram |

**Atenção ao card:** ele foi escrito antes desta verificação e afirmava um
*rename* de `audio_ref` para `reply_audio_ref` que **não existe** — já corrigido
no arquivo do card. Se achar outra divergência entre card e código, o código
ganha, e a correção vai para o card na mesma sessão.

---

## 4. As armadilhas deste card — o que o texto não antecipa

### 4.1 A ordem da derivação é onde o bug vai nascer

A tabela do ADR-0023 é avaliada **de cima para baixo**, e a tentação é escrever
`if transcript: return "thinking"` antes de checar os trechos — o que produz
`thinking` com o professor já falando. Teste a tabela inteira, incluindo o caso
que só existe na cascata: **trecho presente com `reply_text` nulo**.

### 4.2 Índice denso é invariante, não detalhe

`append_audio_chunk` precisa recusar índice repetido e índice furado, **e a
mesma regra precisa existir no banco** (unique em `(turn_id, index)`). Duas
verificações porque protegem de coisas diferentes: a do domínio protege da lógica
errada, a do banco protege de duas escritas concorrentes.

### 4.3 `fail()` não pode apagar o que o aluno ouviu

É a invariante nova mais importante e a mais fácil de quebrar depois, porque
nenhum teste de status a pega: `fail()` continua funcionando, os trechos é que
somem. Escreva o teste que **conta os trechos depois do `fail()`**.

### 4.4 A coleção no SQLAlchemy async não carrega sozinha

Não existe lazy loading de graça no async: `turn_repository.get()` sem
`selectinload` devolve um `Turn` cuja coleção estoura ao ser tocada — e o erro
aparece longe do lugar onde a causa está. É decisão consciente de carregamento
por caso de uso, não default a herdar.

### 4.5 Não implemente o consumidor

Este card **não** grava trecho no storage (CARD-008), não emite evento
(CARD-010) e não orquestra nada (CARD-009). Se aparecer `boto3` ou `arq` no
diff, o escopo vazou.

---

## 5. Escopo — o que corta se estourar

A regra de desempate da reconstrução: **cede escopo, nunca latência**. Aqui não
há latência a ceder (é domínio puro), então o corte é por dependência:

- **Não corte:** a entidade, as invariantes, a migration, a derivação. É o que
  desbloqueia 008 e 009.
- **Pode virar card próprio:** o `selectinload` afinado por caso de uso, se a
  discussão de carregamento crescer.

---

## 6. Conflitos de governança que você vai encontrar — e como resolver

1. **O `CLAUDE.md` vigente vence.** A sessão de reconstrução propôs uma emenda
   (seção OBJETIVO, regra do explicador, campo do template) —
   [§5 do documento de reconstrução](../reconstrucao-backlog-2026-08-19.md).
   **Ela NÃO foi aceita.** Até que seja, valem: a regra do explicador com
   desfecho registrado no card, o item correspondente da DoD, e o campo
   "Objetivo de aprendizado". O CARD-018 traz **as duas** seções de propósito.
2. **A pergunta do explicador tem candidata natural aqui:** *o que quebra, e com
   que mensagem, se o `get()` do repositório não usar `selectinload`?* — é
   consequência observável, e a resposta se confere rodando o teste na hora. Se
   for usar, pergunte **antes** de escrever o mapeamento, não no fim.
3. **A skill `voicecoach-arquitetura` ainda não conhece os ADRs 0023–0027.**
   Se ela contradisser um deles, o ADR ganha — e a skill precisa ser atualizada
   (dívida registrada no CARD-004). Não afrouxe regra em silêncio nos dois
   sentidos.
4. **Item de ADR da DoD:** este card **não** gera ADR novo — ele implementa o
   ADR-0023. Registre isso por escrito citando o critério que **não** se
   aplicou, como o LEARNING-0003 exige; não deixe o item em branco.

---

## 7. Definition of Done específica deste card

Além da DoD do `CLAUDE.md`:

- [ ] A tabela de derivação do ADR-0023 tem teste para os **quatro** casos,
      incluindo trecho-sem-`reply_text`.
- [ ] `fail()` com 2 trechos preserva os 2 — testado contando, não inspecionando
      status.
- [ ] Índice repetido falha **no domínio e no banco** (dois testes).
- [ ] `uv run pytest --cov` verde com o núcleo (`domain` + `application`) ≥ 90%.
- [ ] `uv run lint-imports` verde — e, se a tabela nova não fizer os contratos
      morderem, prove que eles mordem injetando uma violação e revertendo.
- [ ] Card atualizado com status, evidência real (saída de comando colada) e
      dívidas.
- [ ] `docs/backlog/README.md` atualizado.

---

## 8. Restrições

- **Branch própria** (`card-018-turn-com-trechos-de-audio`); `main` é protegida.
- Commit **nunca** leva trailer `Co-Authored-By`
  ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
- **Não pushe nem abra PR sem perguntar.**
- **Não antecipe o V2** (realtime, VAD, barge-in, WebSocket): o gatilho do
  ADR-0003 continua escrito e nenhuma das três condições foi atingida.
- Responda em português. O desenvolvedor é sênior em C#/.NET e iniciante em
  Python — ao citar biblioteca, diga qual, por que ela e não a alternativa, e o
  equivalente mental em .NET. Sem aula de injeção de dependência, repositório ou
  camadas.
