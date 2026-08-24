# ADR-0042 — A idempotência do `POST` mora numa coluna do Postgres, não no Redis

- **Status:** aceito
- **Data:** 2026-08-23
- **Relacionado:** [ADR-0035](0035-canal-worker-api-por-pubsub-com-o-banco-como-fonte-da-verdade.md)
  (o banco é a fonte da verdade), [ADR-0005](0005-fila-e-worker-arq-sobre-redis.md)
  (o `_job_id` do arq), CARD-025 (varredura de turns travados)
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **2 — altera uma
  fronteira** (coluna nova em `turns`, e um cabeçalho que passa a ser
  obrigatório no contrato), **4 — afeta privacidade** (a chave é dado gerado
  pelo cliente e precisa de política de retenção) e **5 — difícil de reverter**
  (migration com índice único).

## Contexto

O CARD-010 especificou *"Redis `SETNX` + TTL"* e nomeou o risco sem resolvê-lo:
*"janela entre 'criei o Turn' e 'enfileirei'"*. O caso de uso é concreto e não
teórico: rede móvel cai no meio do upload, o app reenvia a mesma fala, e o aluno
não pode acabar com dois turnos processados — cada um custa dinheiro (ADR-0010) e
minutos de quota (CARD-015).

Há **três** estados de crash entre receber o áudio e responder:

1. crash antes de o Turn existir;
2. crash **depois** de o Turn existir e **antes** de o job ser publicado;
3. crash depois de publicar e antes de responder.

O que separa as duas soluções é o estado 1. Com `SETNX`, a chave é gravada
**antes** do Turn (é o que a torna uma reserva) — e um crash ali deixa uma chave
existindo e apontando para nada. O retry do cliente encontra a chave, não
encontra o turn, e não há resposta certa: recusar é errado (nada foi criado),
criar é errado (a chave já existe). A saída seria uma máquina de estados na
chave (`reservada` → `confirmada`), o que é precisamente uma segunda fonte de
verdade sobre o mesmo fato.

## Decisão

**A `Idempotency-Key` é uma coluna de `turns`, com índice único parcial. A chave
e o Turn nascem no mesmo commit.**

1. **`turns.idempotency_key`**, `VARCHAR(255)` nulo, com
   `CREATE UNIQUE INDEX ... WHERE idempotency_key IS NOT NULL`. Parcial porque o
   worker, os testes e um eventual backfill criam `Turn` sem passar pela borda
   HTTP — e "nasceu antes da idempotência" é exatamente o que o nulo significa.
2. **Os três estados de crash deixam de ter buraco:**

   | Crash | O que sobra | Como se resolve |
   |---|---|---|
   | antes do commit | **nada** — nem chave, nem Turn | o retry cria normalmente |
   | entre commit e enfileiramento | Turn `queued` sem job | o retry com a mesma chave **enfileira de novo**; o CARD-025 varre os que ninguém reenviar |
   | depois de enfileirar | tudo certo | o retry recebe o mesmo `turn_id` e o mesmo job |

3. **O caminho repetido também enfileira**, e é isso que cura o estado 2 sozinho.
   É seguro porque o `ArqTurnQueue` publica com `_job_id=turn:{id}`: o segundo
   pedido do mesmo turn não vira segundo job, e um turn já concluído é no-op no
   handler do worker (ADR-0037).
4. **Chave repetida é `202` com o mesmo `turn_id` e `replayed: true`** — um
   **sucesso**, não uma falha (ADR-0039 item 4).
5. **A corrida é resolvida pelo índice, não pela consulta.** A leitura "esta
   chave já existe?" é uma foto; entre ela e o `INSERT`, outra requisição pode
   comitar. O `IntegrityError` é traduzido na porta como `ConflictingWriteError`
   (`adapters/persistence/unit_of_work.py`), e o caso de uso reconsulta e devolve
   o `turn_id` de quem chegou primeiro. Sem isso, um duplo toque no botão — o
   caso mais banal que a idempotência existe para tratar — seria 500.
6. **O cabeçalho é obrigatório.** Gerar uma chave quando o cliente esquece faria
   o esquecimento virar um turno extra processado e pago, em silêncio.
7. **Retenção:** a chave morre com o Turn, sem ciclo de vida próprio. É dado do
   cliente, cai no `DELETE` de conta do CARD-017 junto com o resto do Turn, e não
   carrega nada além de um identificador opaco gerado pelo app.

## Alternativas consideradas

### Alternativa A — Redis `SETNX` + TTL (o que o card especificava)

- **O que é:** `SETNX idem:{chave} <turn_id>` com expiração de 24 h; se a chave
  já existe, devolve o `turn_id` guardado.
- **A favor:** nenhuma migration, escrita mais barata, e expiração automática —
  a chave não fica no banco para sempre.
- **Por que foi rejeitada:** o estado de crash 1 não tem saída honesta (chave
  apontando para nada), e resolvê-lo exige uma máquina de estados na chave, que é
  uma segunda fonte de verdade sobre "este turn existe?" — o oposto do que o
  ADR-0035 decidiu. Some-se que o Redis deste projeto **não é durável por
  configuração** e é usado como caminho rápido, não como registro: perder o
  arquivo de dump significaria perder a idempotência de todos os turnos em voo.
  O TTL, que é a vantagem real da alternativa, resolve um problema que aqui não
  existe: a chave não precisa expirar sozinha porque ela some junto do Turn.

### Alternativa B — Tabela própria de chaves (`idempotency_keys`)

- **O que é:** uma tabela com `(key, turn_id, created_at)`, no mesmo banco.
- **A favor:** mantém `turns` livre de vocabulário de transporte, e permitiria
  reusar o mecanismo para outros endpoints (o `POST /v1/sessions`, um dia).
- **Por que foi rejeitada agora:** duas escritas e uma decisão de expiração para
  a mesma garantia que uma coluna e um índice entregam. E o que ela protegeria —
  "a entidade não deve carregar vocabulário de transporte" — já é uma concessão
  aceita no `Turn`, que guarda `input_audio_ref`, uma chave de storage.
  **Gatilho para entrar:** o segundo endpoint que precisar de idempotência.

### Alternativa C — Nenhuma idempotência; o cliente que evite reenviar

- **O que é:** confiar no app para não repetir.
- **Por que foi rejeitada:** o reenvio **é** a estratégia correta do cliente
  quando a resposta não chega — ele não tem como distinguir "o servidor não
  recebeu" de "o servidor recebeu e a resposta se perdeu". Sem idempotência, a
  única forma de o app ser correto seria nunca reenviar, o que transforma toda
  falha de rede em fala perdida. Num produto cujo caminho triste é rede móvel,
  isso não é uma economia — é o defeito.

## Consequências

**Positivas**

- Os três estados de crash têm desfecho escrito, e dois deles se curam com o
  retry natural do cliente.
- Uma fonte de verdade só. "Este turn existe?" e "esta chave foi usada?" são a
  mesma linha, e não podem divergir.
- A corrida real (duas requisições simultâneas) é resolvida pelo banco, que é
  quem de fato sabe — em vez de por uma consulta que sempre estará desatualizada
  no instante seguinte.

**Negativas — o preço aceito**

- **Uma migration e uma coluna a mais**, com vocabulário de transporte dentro do
  agregado. É a tensão honesta: `idempotency_key` não é palavra de pedagogia. Ela
  está lá porque a unicidade que a torna útil é do banco, e o que o banco grava é
  a entidade.
- **A chave nunca expira sozinha.** Ela vive o que o Turn viver, o que significa
  que a tabela guarda para sempre um identificador que só teve utilidade por
  alguns segundos. Custo de bytes desprezível; custo conceitual real (é dado de
  cliente sem propósito depois do primeiro minuto).
- **`ConflictingWriteError` é um erro de porta que existe por causa de UMA
  restrição.** Se outra violação de unicidade aparecer em `turns`, o caso de uso
  vai interpretá-la como colisão de idempotência e reconsultar — e não achar
  nada. O código levanta explicitamente nesse caso em vez de mentir, mas a
  tradução é grossa demais para ser elegante. **Gatilho para refinar:** a segunda
  restrição de unicidade em `turns`.
- **Um objeto órfão fica no storage** quando a corrida é perdida: o áudio já
  subiu (storage antes do banco) e o Turn não foi criado. A retenção de 7 dias do
  ADR-0024 o recolhe, mas é lixo previsível, não acidente.
- **`SqlAlchemyUnitOfWork` passa a existir só na API.** O worker continua usando
  a `AsyncSession` crua como `UnitOfWork` (ela satisfaz o `Protocol`), então há
  duas implementações da mesma porta com comportamentos diferentes em erro. É
  deliberado — o worker não tem restrição de unicidade a traduzir — e é o tipo de
  assimetria que confunde quem chega.

**Equivalente mental .NET:** um índice único + `DbUpdateException` capturada e
traduzida no `SaveChangesAsync`, em vez de um lock distribuído no Redis. É a
mesma escolha entre "o banco é quem sabe" e "eu coordeno por fora" — e a primeira
ganha sempre que o banco já está no caminho da escrita.
