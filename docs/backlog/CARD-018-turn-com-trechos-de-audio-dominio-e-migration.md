# CARD-018 — Turn com trechos de áudio: domínio, invariantes e migration

- **ID:** CARD-018 · **Épico:** Fase 1 — Fatia vertical em cascata
- **Plataforma:** backend · **Esforço:** P · **Status:** backlog
- **Dependências:** CARD-005 (concluído), ADR-0023

## Contexto

O CARD-005 modelou o `Turn` sob o ADR-0016: cada artefato é **um** objeto,
produzido inteiro. O [ADR-0023](../adr/0023-ciclo-de-vida-do-turn-com-entrega-em-cascata.md)
substituiu essa premissa — com a cascata, o áudio da resposta é uma sequência
ordenada de trechos, e o primeiro deles existe **antes** de `reply_text` estar
completo.

O CARD-005 está concluído e não se reabre. Este card é o delta.

## Por que agora

É o primeiro card do caminho crítico: sem a entidade de trecho, o CARD-008 não
tem onde gravar a frase sintetizada e o CARD-009 não tem como emitir nada antes
do fim. Todo o alvo de 1,8 s passa por aqui, e este é o momento mais barato de
pagar — **não existe nenhum turn em banco para migrar**.

## Problema

Hoje `Turn` tem `audio_ref` singular e a etapa derivada usa `reply_text` como
condição de `speaking`. Com a cascata, essa tabela de derivação passa a mentir:
haverá áudio tocando com `reply_text` ainda nulo.

## Proposta técnica

- Entidade `TurnAudioChunk` no domínio: `index` (0-based, denso),
  `storage_key`, `duration_seconds`, `text`, `created_at`. Relacionamento
  `Turn` 1-N, ordenado por `index`.
- `Turn.append_audio_chunk(...)` como único caminho de escrita, com as
  invariantes do ADR-0023: índice denso e crescente; proibido acrescentar em
  turn `completed` ou `failed`.
- `Turn.complete(now)` **já** exige `reply_audio_ref` não-nulo
  (`domain/turn.py`) — essa invariante nasce pronta e passa a significar "o
  áudio inteiro concatenado existe". Nada a mudar aqui.
- `Turn.fail(reason)` continua válido a partir de `processing` **com trechos
  presentes**, e **não apaga trecho nenhum** (o aluno ouviu; o registro tem de
  dizer isso).
- Propriedades derivadas, não colunas: `stage` (nova tabela do ADR-0023) e
  `delivered_partially`.
- Migration Alembic: tabela `turn_audio_chunks` com unique `(turn_id, index)`.
  **`turns` não muda** — `reply_audio_ref` já tem o nome certo e já significa o
  áudio inteiro. O delta é só a tabela filha.
- `TurnRow` ganha o `relationship` ordenado; `turn_from_row`/`turn_to_row`/
  `apply_turn` (`adapters/persistence/mappers.py`) passam a mapear a coleção, e
  `SqlAlchemyTurnRepository.get` carrega com `selectinload` — no async não
  existe lazy loading de graça.

## Escopo

- **In:** domínio, invariantes, migration, testes de domínio.
- **Out:** gravar de fato os trechos (CARD-008); emitir eventos (CARD-010);
  schema de API (CARD-010).

## Critérios de aceite

- **Dado** um `Turn` em `processing` sem artefato, **então** `stage` é
  `transcribing`; com `transcript`, `thinking`; com 1 trecho, `speaking`; com
  `reply_audio_ref`, `completed`.
- **Dado** um `Turn` com 2 trechos, **quando** `fail("tts timeout")`, **então**
  o status é `failed`, os 2 trechos permanecem e `delivered_partially` é `True`.
- **Dado** um `Turn` `completed`, **quando** se tenta acrescentar trecho,
  **então** levanta `DomainError` (ADR-0017).
- **Dado** um índice repetido ou furado, **então** a operação falha — no domínio
  e no banco (constraint testada).
- Cobertura de `domain` permanece ≥ 90% (ADR-0019).

## Riscos

Tentação de persistir `stage` como coluna "para facilitar a query operacional" —
é exatamente o que o ADR-0016 rejeitou e o ADR-0023 manteve rejeitado.

## Objetivo de aprendizado

*(campo do `CLAUDE.md` vigente; a emenda proposta o substitui por "Por que
agora")* — relacionamento 1-N no SQLAlchemy 2.0 async com coleção ordenada:
`relationship(order_by=...)`, `selectinload` e por que a coleção não carrega
sozinha no async (o contraste com o lazy loading do EF).
