# ADR-0031 — O que atravessa a porta do professor é um fluxo de eventos, não um objeto

- **Status:** aceito
- **Data:** 2026-08-21
- **Relacionado:** ADR-0023 (entrega em cascata), ADR-0026 (SSE), ADR-0029 (o
  análogo na porta de STT), ADR-0017 (erro), ADR-0030 (o mecanismo), CARD-007
- **Complementa:** a visão §D, que listava `TeacherLlm.respond(history,
  student_profile) -> TeacherFeedback`

## Contexto

A visão do backend descreveu a porta do professor como uma função que devolve um
objeto:

```
TeacherLlm — respond(history, student_profile) -> TeacherFeedback
```

O ADR-0023 depois decidiu que o áudio da resposta é **uma sequência de trechos**,
e o ADR-0026 que a entrega ao cliente é **progressiva**. Essas duas decisões
tornam a assinatura acima impossível de cumprir: um objeto só existe depois de
pronto, e o produto inteiro depende de agir **enquanto** a resposta está sendo
gerada.

A medição diz de quanto é a diferença: TTFT de 0,60–0,73 s contra resposta
inteira de 1,86–3,48 s (§5.1). **1,1 s a 2,9 s de espera que só existem porque
alguém decidiu esperar o objeto fechar.**

Esta é também a única decisão do CARD-007 que **não pode ser convertida depois**:
adapter batch e adapter em streaming têm forma diferente, e "streamar depois" é
reescrever o card inteiro.

## Decisão

**A porta `TeacherLlm` devolve um `AsyncIterator[TeacherEvent]`, e `TeacherEvent`
é uma união fechada de dataclasses imutáveis.**

```python
class TeacherLlm(Protocol):
    def respond_streaming(
        self, history: Sequence[Utterance]
    ) -> AsyncIterator[TeacherEvent]: ...

type TeacherEvent = SpokenSentence | FeedbackReady
```

1. **`SpokenSentence(text)` n vezes, depois `FeedbackReady(feedback, usage)`, e
   acaba.** O consumidor (CARD-009) reage a cada evento; quem só quer falar
   ignora o último, quem só quer persistir correção e custo só precisa dele.
2. **O método NÃO é `async def`.** Uma função `async def` com `yield` é um
   *gerador assíncrono*: chamá-la devolve o gerador na hora, sem `await`.
   Declarar a porta como `async def … -> AsyncIterator` significaria outra coisa
   — uma corrotina que, depois de aguardada, devolve um iterador — e **nenhum
   gerador assíncrono a satisfaria**. É um erro que o `mypy` pega e o `pytest`
   não.
3. **O que trafega é deliberadamente pobre**, como na porta de STT (ADR-0029):
   `Utterance(speaker, text)` entra, dataclasses saem. Nenhum tipo do SDK
   atravessa — nem `MessageParam`, nem `Message`, nem `Usage`.
4. **O histórico entra por parâmetro. O adapter não tem estado.** É o que mata
   os achados F5/F7 do diagnóstico (estado global de módulo no protótipo:
   `_history`, `_last_reply`, `_client`), e é inspecionável por teste.
5. **`LlmError` mora na porta, não no adapter** — e é aqui que ele difere do
   `SttProviderUnavailableError`, que vive em `adapters/stt/factory.py`. Aquele é
   erro de subida que ninguém captura; este o caso de uso **vai** capturar, e
   `application` não pode importar `adapters` (seta que sobe, `lint-imports`
   vermelho). **Onde o erro mora é consequência de quem precisa capturá-lo.**
   Herda de `RuntimeError` e não de `DomainError` pela mesma razão do ADR-0017:
   provedor fora do schema é falha de infraestrutura, não invariante de negócio.
6. **O cancelamento é o do protocolo do gerador.** Abandonar o `async for` faz o
   Python chamar `aclose()`, que levanta `GeneratorExit` no ponto do `yield`, que
   sai do `async with`, que fecha a conexão HTTP. Por isso o `async with` fica
   **dentro** do gerador: guardá-lo fora, ou engolir o `GeneratorExit`, deixaria
   a geração correndo e o produto pagando por tokens que ninguém vai ouvir.
7. **A última sentença sai do texto validado, não do buffer parcial.** Até a
   geração fechar, o fim do buffer é indistinguível de uma sentença que ainda ia
   crescer — o aluno nunca ouve um pedaço que o provedor acabou reescrevendo.

## Alternativas consideradas

### Alternativa A — Manter `respond(history) -> TeacherFeedback` e streamar depois

- **O que é:** a assinatura da visão §D, com o streaming adicionado quando o
  CARD-009 precisar.
- **Por que foi rejeitada:** não é acréscimo, é reescrita. Todo o consumidor, o
  contrato de SSE do ADR-0026 e o ciclo de vida do `Turn` do ADR-0023 mudam de
  forma junto. E o custo de adiar está medido: 1,1 s a 2,9 s por turno, num alvo
  de 1,8 s.

### Alternativa B — Devolver um `AsyncIterator[str]` de trechos de fala

- **O que é:** a porta emite só as sentenças; o feedback estruturado sai por um
  segundo método ou por uma segunda chamada.
- **Por que foi rejeitada:** obrigaria a segunda passagem sobre a mesma geração
  (ou uma segunda chamada paga, que é a alternativa C do ADR-0030), e jogaria
  fora o `usage`, que já vem de graça no fim do stream e que o CARD-014 precisa.
  Uma união fechada custa duas dataclasses e resolve os dois casos.

### Alternativa C — Callback (`on_sentence=…`) em vez de iterador

- **O que é:** o adapter recebe uma função e a chama a cada sentença.
- **Por que foi rejeitada:** inverte o controle sem ganho — quem chama perde a
  capacidade de parar, de aplicar backpressure e de compor com outro `async for`.
  E o cancelamento, que com gerador é de graça, viraria um sinalizador manual.
  Em .NET é a diferença entre `IObservable<T>` e `IAsyncEnumerable<T>`, e pela
  mesma razão: aqui quem consome é um pipeline sequencial, não um observador.

## Consequências

**Positivas**

- Desbloqueia a cascata: primeira sentença em **0,68–0,76 s** medidos, contra
  2,05–3,74 s da resposta inteira.
- O ciclo de vida do `Turn` (ADR-0023) e o SSE (ADR-0026) recebem exatamente a
  forma de que precisam, sem adaptação intermediária.
- O adapter sem estado é testável sem SDK e sem rede: os testes de `application`
  usam um fake em memória que é uma classe comum, sem framework de mock.
- União fechada com dataclasses imutáveis dá igualdade por valor, e é isso que
  permite asserir uma **lista inteira de eventos** com um `==` só.

**Negativas — o preço aceito**

- **Um idioma que engana quem vem de C#.** Chamar `respond_streaming(...)` e não
  iterar **não executa nada** — um teste escrito assim passa verde sem exercitar
  linha nenhuma. Há teste específico para isso, porque a armadilha é silenciosa.
- **A porta promete `AsyncIterator`, mas o cancelamento é do `AsyncGenerator`.**
  `aclose()` não está no tipo declarado; o teste que o exercita precisa de um
  `cast`. Manter `AsyncIterator` foi decisão consciente: é o contrato mínimo que
  o consumidor precisa, e exigir `AsyncGenerator` obrigaria todo fake a ser
  gerador.
- **Exaustividade da união depende de disciplina do consumidor.** `match` sem
  `assert_never` no `case _` aceita um evento novo em silêncio e explode em
  runtime. Não há como impor isso da porta.
- **Acrescentar um evento novo é mudança de contrato**, não refatoração — o
  CARD-009 e o emissor de SSE reagem a cada caso.
- **Erro no meio do fluxo deixa fala já emitida "no ar".** O contrato do caminho
  triste é do CARD-009: o que já foi falado, foi falado, e nenhuma sentença é
  desdita.

**Equivalente mental .NET:** `IAsyncEnumerable<TeacherEvent>` com `yield return`,
onde `TeacherEvent` é uma hierarquia selada consumida por *pattern matching*
exaustivo. A diferença que muda o desenho é o cancelamento: lá é um
`CancellationToken` que alguém tem de passar adiante; aqui vem do protocolo do
gerador, desde que ninguém o desligue sem querer.
