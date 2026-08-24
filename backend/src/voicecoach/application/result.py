"""``Result`` — o desfecho *esperado* de um caso de uso (ADR-0017, fechado aqui).

O ADR-0017 decidiu metade do padrão de erro e deixou a outra metade TBD **com
gatilho escrito**: *"o primeiro desfecho que é normal do negócio e não bug"*.
O CARD-009 conferiu o gatilho e registrou que não era ali — toda falha do
pipeline era infraestrutura. O CARD-010 é onde ele dispara.

**A regra que separa os dois mecanismos, e ela é a decisão inteira:**

======================  =========================================  ==============
Situação                Exemplo                                    Mecanismo
======================  =========================================  ==============
Invariante violada      ``Turn.complete()`` sem áudio da resposta   **exceção**
Infraestrutura caiu     Redis fora, S3 recusou o ``PUT``            **exceção**
Desfecho normal do      sessão que o cliente não encontra, quota    **``Result``**
negócio que não é bug   estourada (CARD-015), convite já usado
======================  =========================================  ==============

A pergunta que decide não é *"deu erro?"*, é **"quem chamou tem um bug?"**.
Se tem, exceção — porque exceção ignorada explode e aparece, e Python não tem
``[MustUseReturnValue]`` nem ``nodiscard`` para obrigar alguém a olhar um valor
de retorno. Se não tem, ``Result`` — porque o desfecho é parte do contrato do
caso de uso e a tela do produto o trata como estado legítimo, com microcopy
própria, não como acidente.

**Por que 20 linhas próprias e não a biblioteca ``returns``.** Ela existe, é
madura e traz plugin de mypy. Ela também traz o vocabulário funcional inteiro
— ``bind``, ``map``, ``flow``, ``@safe``, contêineres ``Maybe``/``IO`` — para
substituir o que cabe aqui embaixo, num projeto cuja Parte F corta peça sem
pergunta a responder e cujo ADR-0010 cobra cada dependência. O que se perde é
o encadeamento monádico; o que se ganha é que qualquer leitor entende o tipo
sem aprender uma biblioteca. **Gatilho para reavaliar:** o dia em que
encadear três casos de uso que podem falhar virar boilerplate repetido.

**Dois idiomas de Python que não têm paralelo em C#:**

1. ``class Ok[T]`` é a sintaxe de genérico do PEP 695 (3.12+) — o parâmetro de
   tipo é declarado no colchete, sem ``TypeVar`` global. É o mais perto que
   Python chega de ``record Ok<T>(T Value)``.
2. ``type Result[T, E] = Ok[T] | Err[E]`` é um **alias de tipo**, não uma
   classe: não existe classe base ``Result``, e ``isinstance(x, Result)`` não
   funciona. A união é fechada por convenção e verificada pelo ``mypy`` — quem
   consome faz ``match`` e termina em ``assert_never``, e é *isso* que faz
   acrescentar um caso novo quebrar na verificação em vez de sumir em runtime.
   Em C# você usaria ``OneOf``/``ErrorOr`` e o compilador cobraria a
   exaustividade do ``switch``; aqui quem cobra é o type checker.

**Equivalente mental .NET:** ``ErrorOr<T>`` / ``OneOf<TOk, TErr>`` devolvido
pelo handler, com ``InvalidOperationException`` continuando a ser levantada
pela entidade quando alguém a chama fora do estado válido.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Ok[T]:
    """O caso de uso concluiu. ``value`` é o que ele produziu."""

    value: T


@dataclass(frozen=True, slots=True)
class Err[E]:
    """O caso de uso não concluiu, e isso era previsto.

    ``error`` é um **valor**, não uma exceção: normalmente uma dataclass frozen
    declarada junto do caso de uso que a devolve, carregando os dados que a
    borda precisa para montar a resposta (qual sessão não existe, quantos
    minutos faltavam). Uma união fechada de erros por caso de uso, e não um tipo
    de erro global, porque exaustividade só é útil quando o conjunto é pequeno e
    local — um enum de erros do projeto inteiro obrigaria toda borda a tratar
    casos que aquele endpoint não pode produzir.
    """

    error: E


# União FECHADA — o mesmo desenho do `TeacherEvent` (ADR-0031) e do `TurnEvent`
# (ADR-0035). Não há classe base: `Result` é um alias, e a exaustividade quem
# garante é o `match` com `assert_never` do lado de quem consome.
type Result[T, E] = Ok[T] | Err[E]
