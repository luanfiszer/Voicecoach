# ADR-0040 — O formato de erro da API é Problem Details (RFC 9457), num handler só

- **Status:** aceito
- **Data:** 2026-08-23
- **Implementa:** [ADR-0008](0008-contrato-api-versionamento-e-tipos-gerados.md)
  item 5 e [ADR-0017](0017-erro-de-dominio-e-excecao-result-fica-para-o-caso-de-uso.md)
  item 2, que **prometeram** este formato e nunca o especificaram
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **2 — define uma
  fronteira** (o corpo do erro é contrato de API tanto quanto o corpo do sucesso,
  e sob o ADR-0008 ele só evolui aditivamente).

## Contexto

O ADR-0008 item 5 diz uma frase — *"erros no formato Problem Details (RFC 9457)
via exception handlers"* — e o ADR-0017 item 2 repete a promessa. **Nenhum dos
dois foi implementado:** até o CARD-010 o `create_app()` não registrava
`exception_handler` nenhum, e o único erro que a API produzia era o
`{"detail": ...}` default do FastAPI.

Três forças tornaram isso insuficiente agora:

1. **Passaram a existir erros com significado.** Sessão encerrada, sessão
   inexistente, `Last-Event-ID` inválido, fila fora do ar, formato de áudio
   recusado. Um cliente precisa distinguir "tente de novo" de "não adianta
   tentar", e sem formato ele faria `if` sobre string de mensagem.
2. **Dois clientes TypeScript** (ADR-0002) consomem a mesma API, e os tipos vêm
   do OpenAPI (ADR-0008). Um formato só significa **um** tipo de erro gerado.
3. **A tradução tem de acontecer num lugar só.** O ADR-0017 escolheu exceção
   para invariante justamente para que a borda capturasse `DomainError` em um
   ponto; sem os handlers, essa escolha estava pela metade.

## Decisão

**Todo erro da API responde `application/problem+json` no formato da RFC 9457,
produzido por `exception_handler`s registrados em `api/errors.py` — e nunca por
`JSONResponse` montada dentro de uma rota.**

1. **O corpo** tem os campos da RFC (`type`, `title`, `status`, `detail`) e
   aceita **extension members** por tipo de problema (`session_id` no
   `session-not-found`, `accepted` no `unsupported-audio-type`, `errors` na
   validação).
2. **`type` é a chave semântica**, no formato `urn:voicecoach:problem:<slug>`.
   URN e não URL porque a RFC exige um URI **estável**, não um que resolva — e
   um `https://` apontando para um domínio que o projeto não possui seria
   promessa falsa de documentação. `title` e `detail` são para humano e podem
   mudar; `type` é o que o cliente compara.
3. **O código HTTP responde "de quem é o problema?"**:

   | Exceção | HTTP | Por quê |
   |---|---|---|
   | `RequestValidationError`, áudio indecodificável | 422 | o cliente mandou algo inaceitável |
   | content type recusado | 415 | o corpo pode estar certo; o **formato** não é aceito |
   | áudio acima do teto | 413 | idem, sobre tamanho |
   | `TurnNotFoundError`, `SessionNotFound` | 404 | o recurso não existe |
   | `MalformedEventIdError` | 400 | o `Last-Event-ID` não é do esquema |
   | `DomainError` | **409** | a requisição está bem formada; o **estado** é que não permite |
   | erros de porta (fila, storage, canal, unicidade) | 503 | não é culpa do cliente e **pode passar** |

4. **`DomainError` é 409 e não 400.** O caso concreto que fixa isso: a fala
   gravada offline às 21h que chega às 23h, depois de a sessão ter sido
   encerrada. Nada na requisição está errado — o estado do recurso mudou.
5. **Falha de infraestrutura nunca repassa `str(exc)` ao cliente**, e é logada
   com stack. A mensagem de uma falha de conexão costuma carregar host, porta e,
   no pior caso, credencial embutida na URL — é a mesma precaução do `_describe`
   do readiness (ADR-0014).
6. **Não existe handler para `Exception`.** Um handler genérico transformaria
   todo bug num 500 bem formatado e, pior, faria o `httpx` dos testes **parar de
   propagar** a exceção — escondendo em verde o que deveria falhar em vermelho.
   500 não é contrato; é bug, e bug tem de doer.
7. **O que pode virar 4xx é decidido ANTES de a resposta começar.** Numa
   resposta em streaming, o código HTTP já foi enviado quando o primeiro byte
   sai, e um handler que dispare depois não tem o que fazer — o Starlette recusa
   explicitamente (*"Caught handled exception, but response already started"*).
   Logo, a validação do `Last-Event-ID` acontece na rota, não dentro do gerador.

## Alternativas consideradas

### Alternativa A — Manter o `{"detail": ...}` default do FastAPI

- **O que é:** não fazer nada; usar `HTTPException` e o corpo que o framework
  já produz.
- **A favor:** zero código, e é o que 90% dos projetos FastAPI fazem.
- **Por que foi rejeitada:** `detail` é uma string ou uma lista, sem
  discriminador estável — o cliente não tem como distinguir "quota estourada" de
  "sessão encerrada" sem comparar texto, que muda quando alguém melhora a
  microcopy. E o ADR-0008 já havia decidido o contrário; contrariá-lo em
  silêncio seria afrouxar uma decisão sem ADR, que é o que o ADR-0012 proíbe.

### Alternativa B — Envelope próprio (`{"error": {"code": ..., "message": ...}}`)

- **O que é:** inventar o formato, mais curto e mais familiar que a RFC.
- **A favor:** menos campos, e `code` é mais direto que uma URN.
- **Por que foi rejeitada:** é reinventar um padrão publicado para economizar
  dois campos. A RFC 9457 traz de graça o content type `application/problem+json`
  (que permite a um interceptador do cliente reconhecer um erro sem inspecionar
  o corpo) e os *extension members*, que é justamente o que um envelope caseiro
  precisaria improvisar no primeiro erro que carregasse dado estruturado. Formato
  próprio também não aparece em nenhuma ferramenta de terceiros.

### Alternativa C — Um handler por rota, montando `JSONResponse`

- **O que é:** cada endpoint trata os seus erros e devolve a resposta.
- **Por que foi rejeitada:** garante divergência. O ADR-0017 escolheu exceção
  para invariante **para que existisse um ponto de tradução**; espalhar a
  tradução desfaz a escolha e faz o formato depender de quem escreveu a rota
  mais recente.

## Consequências

**Positivas**

- Duas promessas antigas (ADR-0008 item 5, ADR-0017 item 2) saem do papel.
- O cliente ganha um discriminador estável (`type`) e um content type
  reconhecível, e os tipos TS do erro saem do mesmo OpenAPI que os do sucesso.
- A tradução mora num arquivo, e acrescentar um erro novo é uma entrada na
  tabela — não uma decisão por rota.

**Negativas — o preço aceito**

- **A tabela de códigos é uma convenção que alguém precisa ler.** Não há gate
  que impeça uma rota nova de levantar `HTTPException` e fugir do formato. A
  mitigação é o checklist de PR, não a ferramenta.
- **`type` como URN é uma decisão que fica visível no contrato para sempre.**
  Se um dia o projeto tiver domínio e quiser URLs que documentem cada problema,
  a mudança é breaking sob o ADR-0008 e exige `/v2` ou um campo novo.
- **500 continua fora do formato**, por escolha. Um cliente que trate erros
  genericamente precisa lidar com dois formatos: Problem Details e o que o
  servidor ASGI produzir num crash.
- **Extension members são invisíveis para o `mypy`.** `extra="allow"` é regra de
  runtime do pydantic; construir `ProblemDetails(errors=...)` é reprovado
  estaticamente, e por isso a construção passa por `model_validate` sobre um
  dicionário. É cerimônia real, com o motivo escrito no código.

**Equivalente mental .NET:** `ProblemDetails` + `IExceptionHandler` /
`AddProblemDetails()` do ASP.NET Core, que implementa a mesma RFC — com a
diferença de que lá o formato vem ligado por default e aqui ele é uma decisão
que precisou ser escrita duas vezes antes de existir.
