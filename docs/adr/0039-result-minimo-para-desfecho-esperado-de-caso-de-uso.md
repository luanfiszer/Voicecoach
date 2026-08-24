# ADR-0039 — `Result` mínimo próprio para o desfecho esperado de um caso de uso

- **Status:** aceito
- **Data:** 2026-08-23
- **Fecha o TBD de:** [ADR-0017](0017-erro-de-dominio-e-excecao-result-fica-para-o-caso-de-uso.md)
  (item 3), que deixou a forma do `Result` em aberto **com gatilho escrito**
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **2 — define uma
  fronteira** (é a assinatura de retorno de todo caso de uso, presente e futuro),
  **5 — difícil de reverter** (mudar depois obriga a tocar todo handler e toda
  borda) e **6 — contraria/completa uma convenção estabelecida** (o ADR-0017
  registrou "TBD"; a skill `voicecoach-arquitetura` repete isso e passa a estar
  desatualizada a partir daqui).

## Contexto

O ADR-0017 decidiu metade do padrão de erro — *invariante de domínio violada
levanta exceção* — e adiou a outra metade **com gatilho objetivo**: *"a primeira
falha que é desfecho normal do negócio e não bug — quota diária estourada
(CARD-015), `Idempotency-Key` repetida (CARD-010) ou convite já usado (Fase 3)"*.

Ele também registrou o risco de adiar: *"se o gatilho demorar, a decisão de fato
do projeto vira 'exceção para tudo' por inércia"*.

O CARD-009 conferiu o gatilho e o **negou por evidência**: toda falha do pipeline
do worker era infraestrutura (motor de IA fora do ar, storage recusando `PUT`),
e nenhuma era desfecho de negócio. O CARD-010 é o primeiro caso de uso na borda,
e é aqui que a pergunta tem resposta.

**A conferência do gatilho neste card produziu uma surpresa que o ADR-0017 não
podia antecipar, e ela muda a forma da decisão.** Dos três exemplos escritos lá,
o que este card exercita é `Idempotency-Key` repetida — e ela **não é falha**:

> A resposta correta a uma chave repetida é `202` com o **mesmo** `turn_id`. O
> cliente reenviou porque a rede caiu. Nada deu errado; o desfecho é sucesso.

Ou seja: o exemplo canônico do gatilho, examinado de perto, é um **segundo
sucesso**, não uma falha. O que sobra como falha esperada de verdade neste card é
`SessionNotFound`: o cliente manda um `session_id` que não existe (id velho
guardado no aparelho, banco recriado em desenvolvimento). Não é bug de quem
chama — é entrada do mundo.

O gatilho **disparou**, portanto, mas por um caso diferente do previsto. E isso
importa para o desenho: o tipo precisa distinguir dois sucessos entre si tão bem
quanto distingue sucesso de falha.

## Decisão

**`Result[T, E]` é uma união fechada de duas dataclasses frozen, escrita neste
repositório em ~20 linhas (`application/result.py`), e é o tipo de retorno de
caso de uso cujo desfecho triste é normal do negócio.**

1. **A forma:**

   ```python
   @dataclass(frozen=True, slots=True)
   class Ok[T]:
       value: T

   @dataclass(frozen=True, slots=True)
   class Err[E]:
       error: E

   type Result[T, E] = Ok[T] | Err[E]
   ```

   Não existe classe base `Result` — é um **alias de tipo** (PEP 695). Quem
   consome faz `match` e termina em `assert_never`, o mesmo desenho já usado em
   `TeacherEvent` (ADR-0031) e `TurnEvent` (ADR-0035). É o `mypy` quem garante a
   exaustividade, no lugar do compilador de C#.

2. **`E` é um tipo por caso de uso, não um enum global.** `StartTurnHandler`
   devolve `Result[TurnAccepted, SessionNotFound]`, com `SessionNotFound` sendo
   uma dataclass frozen declarada junto do handler, carregando os dados que a
   borda precisa (o `session_id`) para montar o Problem Details. Um catálogo de
   erros do projeto inteiro obrigaria toda borda a tratar casos que aquele
   endpoint não pode produzir — e exaustividade só é útil quando o conjunto é
   pequeno e local.

3. **A regra que separa os dois mecanismos** — e ela é a decisão, não a sintaxe:

   | Situação | Exemplo real | Mecanismo |
   |---|---|---|
   | Invariante de agregado violada | `Session.start_turn()` numa sessão encerrada | **exceção** (ADR-0017) |
   | Infraestrutura não colaborou | fila fora do ar, storage recusou o `PUT` | **exceção** de porta |
   | Desfecho normal do negócio | sessão que o cliente não encontra; quota estourada (CARD-015) | **`Result`** |

   A pergunta que decide não é *"deu erro?"*, é **"quem chamou tem um bug?"**.
   Se tem, exceção — porque exceção ignorada explode e aparece, e Python não tem
   `[MustUseReturnValue]` nem `nodiscard` para obrigar alguém a olhar um retorno.

4. **Sucesso com nuance é `Ok`, não `Err`.** `Idempotency-Key` repetida devolve
   `Ok(TurnAccepted(turn_id, replayed=True))`. Transformá-la em `Err` seria
   mentir sobre o que aconteceu, e o cliente receberia um erro para uma operação
   que funcionou exatamente como projetada.

## Alternativas consideradas

### Alternativa A — A biblioteca `returns`

- **O que é:** contêineres `Result`/`Maybe`/`IO` prontos, com plugin de `mypy`,
  encadeamento monádico (`bind`, `map`, `flow`) e decoradores (`@safe`).
- **A favor:** madura, testada, e resolveria de graça o encadeamento de vários
  casos de uso que podem falhar. É a resposta "não reinvente a roda".
- **Por que foi rejeitada:** ela troca 20 linhas legíveis por um **vocabulário
  inteiro** que todo leitor do projeto passaria a precisar aprender — num
  repositório cujo produto declarado é o conhecimento do desenvolvedor, e cujo
  desenvolvedor está aprendendo Python. É também uma dependência a mais sob o
  ADR-0010 e a Parte F da visão, para um problema que ainda não tem a forma que
  ela resolve: **não há, hoje, nenhum encadeamento de casos de uso falíveis**;
  há um handler devolvendo um desfecho para uma rota. **Gatilho para reavaliar:**
  o dia em que encadear três casos de uso que podem falhar virar boilerplate
  repetido — que é exatamente o problema do `bind`.

### Alternativa B — Nenhum `Result`: dataclass de saída, e exceção para o resto

- **O que é:** `StartTurnHandler` devolve `TurnAccepted(turn_id, replayed)` e
  `SessionNotFound` vira uma exceção de aplicação, traduzida na borda como todas
  as outras.
- **A favor:** é o idioma nativo do Python (EAFP), um mecanismo só, menos
  cerimônia. E tem um argumento honesto: a leitura estrita do gatilho do
  ADR-0017 aponta para `Idempotency-Key` repetida, que este ADR acaba de mostrar
  **não ser** falha — logo, dá para sustentar que o gatilho não disparou de novo.
- **Por que foi rejeitada:** porque o gatilho disparou, só que por outro caso. E
  porque o ADR-0017 nomeou o risco de continuar adiando: *"a decisão de fato do
  projeto vira 'exceção para tudo' por inércia"*. A quota do CARD-015 é a falha
  esperada mais óbvia do produto (a tela a trata como estado legítimo, com
  microcopy própria) e está a dois cards de distância; decidir a forma agora,
  com um caso pequeno e reversível, custa menos do que decidir depois com um
  caso caro. Fica registrado que esta alternativa é defensável.

### Alternativa C — `Result` também para invariante de domínio

- **O que é:** aplicar o tipo a tudo, inclusive a `Session.start_turn()` numa
  sessão encerrada.
- **Por que foi rejeitada:** já rejeitada no ADR-0017 (Alternativa A) e a razão
  não mudou: invariante violada é bug do chamador, e transformar bug em valor de
  retorno faz o bug viajar em silêncio. Listada aqui para deixar explícito que
  fechar o TBD **não** reabre a metade que o ADR-0017 já decidiu.

## Consequências

**Positivas**

- O TBD mais antigo do projeto fecha, com uma regra de duas linhas que sobrevive
  a entrevista: *invariante violada é bug do chamador; falha esperada é desfecho
  do negócio*.
- A assinatura de todo caso de uso futuro está decidida antes de existirem dez
  deles — a quota do CARD-015 e o convite da Fase 3 herdam a forma pronta.
- A exaustividade é verificada: acrescentar um desfecho ao caso de uso sem
  tratá-lo na borda quebra no `mypy`, não em produção.
- Zero dependência nova.

**Negativas — o preço aceito**

- **O projeto passa a conviver com dois mecanismos de erro**, exatamente como o
  ADR-0017 previu. A fronteira está na tabela do item 3 e no docstring de
  `application/result.py`, mas ela é uma regra que alguém precisa **ler** — não
  há gate que a imponha. É o elo fraco desta decisão, e é honesto dizer que a
  primeira violação provável é alguém devolver `Err` para uma falha de
  infraestrutura porque "também não é bug do chamador".
- **`Result` não atravessa um gerador.** Descoberto ao escrever
  `StreamTurnEventsHandler`: um gerador assíncrono não tem valor de retorno que
  o consumidor leia, então "o turn não existe" continua sendo exceção
  (`TurnNotFoundError`) mesmo sendo, conceitualmente, o mesmo tipo de desfecho
  que `SessionNotFound`. A alternativa seria um item-sentinela na união de
  eventos, o que faria todo consumidor tratar um caso que não é evento. **É uma
  inconsistência real do desenho, registrada em vez de escondida.**
- **Não há nada que obrigue o chamador a inspecionar o retorno.** Em C#, um
  `Result` ignorado também compila; a diferença é que lá existem analisadores
  para isso. Aqui a mitigação é o `match` com `assert_never` ser a forma idiomática
  de consumir — mas quem quiser ignorar, ignora.
- **Um caso de uso com muitos desfechos vai inflar o `match` da borda.** Hoje são
  dois. **Gatilho para reavaliar o formato:** um handler com mais de quatro
  variantes de `Err`.

**Equivalente mental .NET:** `ErrorOr<T>` / `OneOf<TOk, TErr>` devolvido pelo
handler, com `InvalidOperationException` continuando a ser levantada pela
entidade quando alguém a chama fora do estado válido — e o `switch` exaustivo
sendo cobrado pelo `mypy` no lugar do compilador.
