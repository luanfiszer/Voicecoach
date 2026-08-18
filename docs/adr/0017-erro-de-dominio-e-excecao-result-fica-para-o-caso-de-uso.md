# ADR-0017 — Invariante de domínio violada é exceção; `Result` fica para o caso de uso

- **Status:** aceito
- **Data:** 2026-08-18

## Contexto

O padrão de erro estava marcado como **TBD** desde o CARD-001 — o `CLAUDE.md` e a
skill `voicecoach-arquitetura` registram que a visão §D menciona `Result` em
`application`, mas que a forma (exceção vs. tipo `Result`) nunca foi decidida, e
mandam **não inventar** até existir caso de uso real.

O CARD-005 é o primeiro código que esbarra no assunto: o domínio precisa recusar
transições impossíveis (`start_processing()` num `Turn` já `completed`; abrir um
`Turn` numa `Session` encerrada). Sem decisão, cada entidade inventaria a sua.

O desenvolvedor vem de **Result Pattern em .NET** e declarou a tentação de
trazê-lo inteiro. A restrição que evita a decisão prematura: **o CARD-005 não tem
nenhum caso de uso** — o escopo é domínio, portas e adapters. Falha *esperada*
(quota estourada, chave de idempotência repetida, convite já usado) só aparece a
partir do CARD-009/010/015.

Decidir agora o formato de retorno de casos de uso que ainda não existem seria
decidir sobre código imaginário — o erro que a Parte F da visão chama pelo nome.

## Decisão

**Separar as duas coisas que o `Result` mistura, e decidir só a que este card
exercita.**

1. **Violação de invariante de domínio é exceção.** Uma hierarquia mínima em
   `domain/errors.py`:

   - `DomainError(Exception)` — a raiz, para a borda capturar em um lugar só;
   - `InvalidStateTransition(DomainError)` — a transição pedida não existe a
     partir do estado atual.

   Justificativa: invariante violada significa que **o chamador tem um bug** —
   não é um desfecho previsto do fluxo. Exceção ignorada explode e aparece;
   `Result` ignorado passa batido (Python não tem `[MustUseReturnValue]` nem
   `nodiscard`). Em .NET a escolha seria a mesma: `InvalidOperationException`,
   não `Result.Failure`.

2. **A borda traduz, o núcleo não sabe de HTTP.** Um exception handler único em
   `api/` converte `DomainError` em **Problem Details (RFC 9457)** — já previsto
   no CARD-010. `domain` e `application` continuam sem conhecer o transporte.

3. **`Result` para falha esperada de caso de uso continua TBD**, agora **com
   gatilho escrito**: a primeira falha que é desfecho normal do negócio e não bug
   — quota diária estourada (CARD-015), `Idempotency-Key` repetida (CARD-010) ou
   convite já usado (Fase 3). Naquele card, e não antes, decide-se entre exceção
   de aplicação e tipo `Result` explícito, e a decisão vira ADR ali.

4. **Enquanto isso, nada de "erro genérico".** Nenhum `except Exception` sem
   `# noqa: BLE001` justificado (ADR-0015); nenhuma string de erro solta atravessando
   camada.

## Alternativas consideradas

### Alternativa A — Tipo `Result` explícito em tudo, desde já

- **O que é:** `Result[T, E]` como dataclass frozen + união, devolvido também
  pelos métodos de domínio; exaustividade garantida por `match` + `assert_never`
  sob `mypy --strict`.
- **A favor:** caminho triste visível na assinatura; familiar vindo de .NET;
  não usa exceção para fluxo previsto.
- **Por que foi rejeitada (agora):** (a) aplicá-lo a **invariante** é usar a
  ferramenta errada — invariante violada é bug, e transformar bug em valor de
  retorno faz o bug viajar silenciosamente; (b) Python não tem o açúcar que torna
  `Result` barato (não há `?`, e nada obriga o chamador a inspecionar o retorno);
  (c) decidir o formato de retorno dos casos de uso **antes de existir um caso de
  uso** é decidir sobre código imaginário. A alternativa não está rejeitada para
  sempre: está **adiada com gatilho**.

### Alternativa B — Exceção para tudo, fechando o TBD inteiro agora

- **O que é:** hierarquia de erros de domínio e de aplicação, handler único na
  borda, inclusive para falha esperada (quota, idempotência).
- **A favor:** é o idioma nativo do Python (EAFP); um mecanismo só; menos
  cerimônia.
- **Por que foi rejeitada:** transforma **fluxo esperado** em exceção — quota
  estourada é resposta normal do produto (a tela do design a trata como estado
  legítimo, com microcopy própria), não acidente. É exatamente o que o Result
  Pattern evita em .NET, e o desenvolvedor quer poder defender essa distinção em
  entrevista. Fechar o TBD inteiro aqui decidiria, de novo, sobre código que não
  existe.

### Alternativa C — Manter o TBD intocado

- **Por que foi rejeitada:** o CARD-005 **precisa** rejeitar transições hoje. Sem
  decisão, cada entidade inventa um mecanismo e a convenção nasce por acidente —
  que é o cenário que o TBD existia para evitar.

## Consequências

**Positivas**

- O card destrava com uma decisão pequena, sustentada por um argumento que
  sobrevive a entrevista: *invariante violada é bug do chamador; falha esperada é
  desfecho do negócio* — e cada uma merece um mecanismo diferente.
- `DomainError` como raiz dá à borda **um** ponto de tradução para Problem
  Details.
- O TBD que restou tem gatilho objetivo, em vez de prazo indefinido.

**Negativas — o preço aceito**

- O projeto conviverá com **dois mecanismos** de erro quando o `Result` entrar. A
  fronteira entre eles precisa ficar explícita na skill, ou vira decisão caso a
  caso — que é como convenção se dissolve.
- Exceção não aparece na assinatura: `mypy` não avisa quem esqueceu de tratar.
  Mitigação: invariante é para **não** ser tratada no caminho feliz; quem trata é
  a borda, num lugar só.
- Se o gatilho do `Result` demorar, a decisão de fato do projeto vira "exceção
  para tudo" por inércia. Mitigação: o gatilho está escrito acima, e o CARD-010
  é o próximo candidato.

**Equivalente mental .NET:** `InvalidOperationException` lançada pela entidade
quando alguém chama um método fora do estado válido, capturada por um
`IExceptionHandler`/middleware que devolve `ProblemDetails` — enquanto o
`Result<T>` fica reservado para o retorno dos handlers, onde a falha é parte do
contrato do caso de uso.
