"""Adapter do professor sobre o SDK `anthropic` 1.x, em streaming (ADR-0030).

O mecanismo é **tool use com `eager_input_streaming`**, escolhido por medição e
não por gosto: no spike do CARD-007 ele foi o único que preservou a ordem das
chaves nas três execuções **e** entregou `spoken_reply` legível em 0,88 s. O
texto livre reordenou as chaves em 1 de 3 — exatamente o risco que o ADR-0022
deixou registrado em aberto.

Três quebras do SDK 1.x que mordem aqui, e por isso estão escritas:

- `temperature`, `top_p` e `top_k` **foram removidos** das assinaturas (passar um
  é `TypeError`), então não há o que "ajustar" na geração;
- o HTTP migrou para `httpx2` — daí ele estar na lista `forbidden` junto do
  `anthropic`;
- `isinstance(x, anthropic.Stream)` **não casa** com o objeto de
  `messages.stream()`; o tipo é `anthropic.lib.streaming.AsyncMessageStream`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

import jiter
from anthropic import AnthropicError, APIConnectionError, APIStatusError

from voicecoach.adapters.llm.sentences import SentenceCutter
from voicecoach.adapters.resilience import CircuitBreaker, CircuitOpenError
from voicecoach.application.ports.teacher_llm import (
    FeedbackReady,
    LlmError,
    Speaker,
    SpokenSentence,
    TeacherEvent,
    TeacherFeedback,
    TeacherUnavailableError,
    TokenUsage,
    Utterance,
)
from voicecoach.domain.correction import Correction, CorrectionType, Severity

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

# Códigos HTTP em que o provedor está **indisponível**, não em que nós erramos.
# 408/504 prazo, 409 conflito de concorrência do provedor, 429 excesso de
# chamadas, 529 sobrecarga (código próprio da Anthropic), 5xx em geral.
#
# O complemento importa tanto quanto a lista: 400, 401, 403 e 404 ficam de fora
# de propósito. Um 401 é chave errada e um 400 é requisição malformada — os dois
# são bug NOSSO, e abrir o circuito por causa deles esconderia o defeito atrás
# de uma tela de "serviço indisponível" que nunca se resolveria sozinha.
_STATUS_DE_INDISPONIBILIDADE = frozenset({408, 409, 429, 529})


def _e_indisponibilidade(exc: AnthropicError) -> bool:
    """O provedor não atendeu, ou atendeu e recusou por nossa culpa?

    É a pergunta que decide se o breaker conta a falha, e é a diferença entre um
    breaker útil e um que abre sozinho em produção (§4.7 do prompt do CARD-026).
    """
    if isinstance(exc, APIConnectionError):
        # Cobre `APITimeoutError`, que herda dela: prazo estourado é o provedor
        # não tendo atendido a tempo.
        return True
    if isinstance(exc, APIStatusError):
        status = exc.status_code
        return status in _STATUS_DE_INDISPONIBILIDADE or status >= 500
    return False


def _traduzir(exc: AnthropicError) -> LlmError:
    """Erro do SDK vira erro **da porta** — o ADL do guia, na fronteira.

    Sem isto o `anthropic` vaza para `application` pelo caminho que o
    `lint-imports` não vê: não por um `import`, mas por uma **exceção**
    atravessando. E o efeito medido era pior que o acoplamento — a hierarquia do
    SDK é `AnthropicError -> Exception`, e não `RuntimeError`, então nenhuma
    delas casava com o `FALHAS_DE_INFRAESTRUTURA` do `ProcessTurn`. O provedor
    fora do ar atravessava o caso de uso inteiro sem ser capturado: o turn não
    era marcado `failed`, o retry do CARD-025 não era pedido, e o aluno ficava
    na tela de espera até a varredura o encerrar 5 minutos depois.
    """
    if _e_indisponibilidade(exc):
        message = f"o professor não atendeu: {type(exc).__name__}: {exc}"
        return TeacherUnavailableError(message)
    message = f"o professor recusou a requisição: {type(exc).__name__}: {exc}"
    return LlmError(message)


TOOL_NAME = "teacher_feedback"

# O schema de UMA correção. `enum` no JSON Schema é o que faz o provedor recusar
# um valor fora da escala antes de nós — a validação em `_para_correcao` existe
# para o caso de ele não cumprir, não no lugar dele.
CAMPOS_DA_CORRECAO: dict[str, Any] = {
    "type": {"type": "string", "enum": [m.value for m in CorrectionType]},
    "original_excerpt": {"type": "string"},
    "corrected_form": {"type": "string"},
    "explanation": {"type": "string"},
    "severity": {"type": "string", "enum": [m.value for m in Severity]},
}

# A ordem aqui É o ADR-0022, e o teste `test_teacher_prompt.py` a assere. Não
# reordene por legibilidade: reordenar não quebra nada — só a latência sobe.
#
# **`corrections` é o último de propósito** (CARD-013). É o campo mais longo do
# objeto, e o parse é incremental (ADR-0030): cada byte gerado antes de
# `spoken_reply` fechar é atraso no primeiro áudio que o aluno ouve. Pelo mesmo
# motivo os quatro campos texto do protótipo SAÍRAM daqui — eles continuam no
# contrato `/v1`, derivados de `corrections` por `legacy_summary`, e parar de
# pedi-los ao modelo devolve parte dos tokens que o array custa.
CAMPOS: dict[str, dict[str, Any]] = {
    "spoken_reply": {"type": "string"},
    "translation_pt": {"type": "string"},
    "corrections": {
        "type": "array",
        # O teto está no prompt E aqui: o prompt pede no máximo 2 por pedagogia,
        # o schema impede que o descumprimento vire uma tela com sete correções.
        "maxItems": 2,
        "items": {
            "type": "object",
            "properties": CAMPOS_DA_CORRECAO,
            "required": list(CAMPOS_DA_CORRECAO),
            "additionalProperties": False,
        },
    },
}

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": CAMPOS,
    "required": list(CAMPOS),
    "additionalProperties": False,
}

_PAPEL = {Speaker.STUDENT: "user", Speaker.TEACHER: "assistant"}


class _Usage(Protocol):
    """As contagens que o `usage` da resposta sempre traz."""

    input_tokens: int
    output_tokens: int


class _FinalMessage(Protocol):
    """O mínimo que este adapter lê da mensagem final.

    Declarar o que se consome — em vez de importar o tipo real do SDK — é o que
    mantém o teste unitário honesto: o fake precisa ter exatamente isto, e não
    um objeto inteiro do `anthropic`. Mesmo padrão do `_Segment` do STT.
    """

    # `@property` e não atributo, pela mesma razão do `_Client.messages`: membro
    # de Protocol declarado como atributo é INVARIANTE, e um dublê que exponha
    # `usage: FakeUsage` deixaria de satisfazê-lo mesmo tendo tudo o que se lê.
    @property
    def usage(self) -> _Usage: ...
    @property
    def content(self) -> Sequence[object]: ...
    # O modelo que de fato respondeu (CARD-014). A API resolve o alias pedido
    # (`claude-haiku-4-5`) para um id datado e o devolve aqui — é ele que tem
    # preço, e é ele que vai para a linha de custo.
    @property
    def model(self) -> str: ...


class _Stream(Protocol):
    """O pedaço do `AsyncMessageStream` que este adapter consome."""

    def __aiter__(self) -> AsyncIterator[object]: ...
    async def get_final_message(self) -> _FinalMessage: ...


class _StreamContext(Protocol):
    """O gerenciador de contexto devolvido por `messages.stream(...)`.

    É um *async context manager*: o `async with` abre a conexão HTTP na entrada
    e a fecha na saída. Não existe paralelo direto em C# — o mais próximo é um
    `await using` sobre um `IAsyncDisposable`.
    """

    async def __aenter__(self) -> _Stream: ...
    async def __aexit__(self, *exc: object) -> None: ...


class _Messages(Protocol):
    # `**kwargs: object` e não `Any`: a assinatura real do SDK é uma pilha de
    # overloads, e declarar o mínimo mantém o fake do teste honesto.
    def stream(self, **kwargs: object) -> _StreamContext: ...


class _Client(Protocol):
    # `@property` e não atributo: no SDK real `messages` é somente-leitura, e um
    # atributo no Protocol exigiria que fosse atribuível. O mypy reprova a
    # diferença — foi ele quem apontou, não o runtime.
    @property
    def messages(self) -> _Messages: ...


def _mensagens(history: Sequence[Utterance]) -> list[dict[str, str]]:
    return [{"role": _PAPEL[u.speaker], "content": u.text} for u in history]


def _fala_parcial(buffer: bytes) -> str:
    """`spoken_reply` já legível no JSON truncado — string aberta incluída.

    `partial_mode="trailing-strings"` é a peça toda. Com `partial_mode=True` o
    `jiter` devolveria `{}` enquanto a aspa de fechamento não chegasse, ou seja,
    a fala só apareceria quando estivesse inteira — que é literalmente esperar o
    objeto fechar, e é o que este card existe para não fazer.
    """
    try:
        dados = jiter.from_json(buffer, partial_mode="trailing-strings")
    except ValueError:
        return ""  # ainda não há sequer um objeto — normal nos primeiros bytes
    if not isinstance(dados, dict):
        return ""
    valor = dados.get("spoken_reply")
    return valor if isinstance(valor, str) else ""


def _para_correcao(bruto: object, index: int) -> Correction:
    """Converte um item de `corrections[]` em `Correction`, ou levanta.

    **O `index` é atribuído aqui, pela posição no array**, e não vem do modelo.
    É a mesma escolha do `TurnAudioChunk` (ADR-0023) por uma razão diferente:
    ali o índice precisa ser conhecido antes, para montar a chave de storage;
    aqui, pedir o índice ao modelo seria dar a ele a chance de repetir ou furar
    a sequência — e o furo só apareceria como violação de chave primária, no
    fundo do pipeline. A ordem do array já é a ordem pedagógica que o prompt
    pede, então a posição É a informação.

    Os dois `StrEnum` levantam `ValueError` para valor fora da escala, e ele
    vira `LlmError` como qualquer outro desvio de schema: é o provedor devolvendo
    algo que não combinamos, não invariante de domínio violada (ADR-0017).
    """
    if not isinstance(bruto, dict):
        message = f"correção {index} não é um objeto: {type(bruto).__name__}"
        raise LlmError(message)

    faltando = [c for c in CAMPOS_DA_CORRECAO if c not in bruto]
    if faltando:
        message = f"correção {index} sem os campos {faltando}"
        raise LlmError(message)

    errados = [c for c in CAMPOS_DA_CORRECAO if not isinstance(bruto[c], str)]
    if errados:
        message = f"correção {index}: campos que deveriam ser texto não são: {errados}"
        raise LlmError(message)

    try:
        tipo = CorrectionType(bruto["type"])
        severidade = Severity(bruto["severity"])
    except ValueError as exc:
        message = f"correção {index} fora da escala combinada: {exc}"
        raise LlmError(message) from exc

    return Correction(
        index=index,
        type=tipo,
        original_excerpt=bruto["original_excerpt"],
        corrected_form=bruto["corrected_form"],
        explanation=bruto["explanation"],
        severity=severidade,
    )


def _para_feedback(bruto: object) -> TeacherFeedback:
    """Converte o input da tool em `TeacherFeedback`, ou levanta.

    Validação à mão, e não com pydantic, por regra de camada: pydantic é
    contrato de API e vive na borda `api/` (ADR-0008). São três campos de tipo
    conhecido — a "fronteira anti-corrupção" aqui cabe em trinta linhas, e o
    schema já foi imposto pelo provedor no modo estrito.

    Fora do schema é `LlmError`, **nunca** texto cru adiante: o fallback do
    protótipo (tratar o texto inválido como `spoken_reply`) mandava a mensagem
    de erro do modelo direto para o TTS.
    """
    if not isinstance(bruto, dict):
        message = f"resposta do professor não é um objeto: {type(bruto).__name__}"
        raise LlmError(message)

    faltando = [c for c in CAMPOS if c not in bruto]
    if faltando:
        message = f"resposta do professor sem os campos {faltando}"
        raise LlmError(message)

    textos = {c: bruto[c] for c in ("spoken_reply", "translation_pt")}
    errados = [c for c, v in textos.items() if not isinstance(v, str)]
    if errados:
        message = f"campos que deveriam ser texto não são: {errados}"
        raise LlmError(message)

    correcoes = bruto["corrections"]
    if not isinstance(correcoes, list):
        message = f"corrections não é um array: {type(correcoes).__name__}"
        raise LlmError(message)

    return TeacherFeedback(
        spoken_reply=textos["spoken_reply"],
        translation_pt=textos["translation_pt"],
        corrections=tuple(_para_correcao(item, i) for i, item in enumerate(correcoes)),
    )


def _uso(mensagem: _FinalMessage) -> TokenUsage:
    """As três contagens de entrada, separadas (ADR-0021, item 3).

    O caching está adiado, não esquecido: hoje `cache_creation` e `cache_read`
    são 0 em toda chamada, e é justamente por isso que precisam ser registrados
    — são o instrumento que detecta a mudança de regime.

    O `model` vem da **mensagem**, não da `Settings` (CARD-014): a API resolve o
    alias configurado para um id datado, e é o datado que tem preço na tabela.
    Este adapter, aliás, sequer conhece a `Settings` — quem a lê é a factory.
    """
    u = mensagem.usage
    return TokenUsage(
        model=mensagem.model,
        input_tokens=u.input_tokens,
        cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", None)
        or 0,
        cache_read_input_tokens=getattr(u, "cache_read_input_tokens", None) or 0,
        output_tokens=u.output_tokens,
    )


def _entrada_da_tool(mensagem: _FinalMessage) -> object:
    for bloco in mensagem.content:
        if getattr(bloco, "type", None) == "tool_use":
            return getattr(bloco, "input", None)
    message = "o professor não chamou a tool de resposta"
    raise LlmError(message)


class AnthropicTeacher:
    """Implementa `TeacherLlm` sobre um cliente assíncrono já construído.

    Recebe o cliente pronto pelo mesmo motivo que o adapter de STT recebe o
    motor: quem decide o momento da construção é a composition root. E, como lá,
    **não há estado nenhum entre chamadas** — o histórico entra por parâmetro.
    """

    def __init__(
        self,
        client: _Client,
        *,
        model: str,
        system_prompt: str,
        max_tokens: int,
        timeout_seconds: float,
        breaker: CircuitBreaker,
    ) -> None:
        self._client = client
        self._model = model
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens
        self._timeout = timeout_seconds
        # Recebido pronto, como o cliente: quem decide a política é a
        # composition root. Obrigatório e não `None` por default — um breaker
        # opcional é um breaker que alguém esquece de ligar em produção, e a
        # falha disso é silenciosa (tudo funciona, só fica caro).
        self._breaker = breaker

    async def respond_streaming(
        self, history: Sequence[Utterance]
    ) -> AsyncIterator[TeacherEvent]:
        """Emite as sentenças conforme saem, e o feedback inteiro no fim.

        `async def` + `yield` faz disto um **gerador assíncrono**: chamar este
        método devolve o gerador na hora, sem `await`, e nada aqui dentro roda
        até alguém fazer `async for`. Um teste que chama e não itera não
        exercita nada — e passa verde.

        O `async with` fica **dentro** do gerador de propósito. Quando o
        consumidor abandona o laço, o Python chama `aclose()`, que levanta
        `GeneratorExit` exatamente no `yield`, que sai do `async with`, que fecha
        a conexão HTTP. Guardar o stream fora do `async with` — ou engolir essa
        exceção — deixaria a geração correndo e faria o produto pagar por tokens
        que ninguém vai ouvir.
        """
        if not history:
            message = "histórico vazio: não há fala do aluno para responder"
            raise LlmError(message)

        # **Antes de montar qualquer coisa.** Com o circuito aberto a falha tem
        # de ser barata: nenhuma conexão, nenhum token, nenhum objeto de stream.
        # É o critério de aceite do card — "falha sem abrir conexão e em tempo
        # desprezível".
        try:
            self._breaker.antes_de_chamar()
        except CircuitOpenError as exc:
            raise TeacherUnavailableError(str(exc)) from exc

        cortador = SentenceCutter()
        buffer = b""
        fala = ""

        contexto = self._client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            system=self._system_prompt,
            messages=_mensagens(history),
            tools=[
                {
                    "name": TOOL_NAME,
                    "description": "Devolve a resposta do professor ao aluno.",
                    "input_schema": TOOL_SCHEMA,
                    # Sem isto os deltas de JSON não chegam na granularidade que
                    # a cascata precisa — e a cascata deixa de existir, sem erro
                    # nenhum. Não é beta e não é header (SDK 1.x).
                    "eager_input_streaming": True,
                }
            ],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            timeout=self._timeout,
        )

        # Tudo o que pode dar errado ANTES da primeira sentença acontece aqui
        # dentro, onde o retry do SDK ainda é legítimo: a conexão só abre no
        # `__aenter__`. Depois do primeiro `yield` não existe retry possível —
        # a resposta já começou a ser falada, e recomeçar faria o aluno ouvir
        # tudo de novo. As duas zonas do ADR-0030 caem de graça do desenho.
        #
        # **`conectado` é a janela do breaker, e é por isso que ele não é uma
        # biblioteca.** O que conta como "provedor fora" é falhar ANTES de o
        # `__aenter__` voltar; depois disso o provedor demonstrou estar vivo — ele
        # abriu o stream — e um erro posterior é outra coisa, que derruba o turn
        # sem derrubar o produto.
        conectado = False
        try:
            async with contexto as fluxo:
                conectado = True
                self._breaker.sucesso()

                async for evento in fluxo:
                    pedaco = _delta_de_json(evento)
                    if not pedaco:
                        continue
                    buffer += pedaco.encode("utf-8")
                    fala = _fala_parcial(buffer)
                    for trecho in cortador.feed(fala):
                        yield SpokenSentence(text=trecho)

                mensagem = await fluxo.get_final_message()
        except AnthropicError as exc:
            # `AnthropicError` e não `Exception`: o `GeneratorExit` do consumidor
            # que abandona o laço herda de `BaseException` e **não** é capturado
            # aqui — se fosse, o cancelamento do ADR-0031 item 6 viraria "falha
            # do provedor" e o breaker abriria por um aluno ter desistido.
            if not conectado:
                self._breaker.falha()
            raise _traduzir(exc) from exc

        feedback = _para_feedback(_entrada_da_tool(mensagem))

        # A última sentença só pode sair agora: até a geração fechar, ela é
        # indistinguível de uma que ainda ia crescer. E sai do texto VALIDADO,
        # não do buffer parcial, para o aluno nunca ouvir um pedaço que o
        # provedor acabou reescrevendo.
        for trecho in cortador.flush(feedback.spoken_reply):
            yield SpokenSentence(text=trecho)

        yield FeedbackReady(feedback=feedback, usage=_uso(mensagem))


def _delta_de_json(evento: object) -> str:
    """O pedaço de JSON deste evento, ou string vazia se ele não trouxer nenhum."""
    if getattr(evento, "type", None) != "content_block_delta":
        return ""
    delta = getattr(evento, "delta", None)
    return getattr(delta, "partial_json", "") or ""
