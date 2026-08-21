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

from voicecoach.adapters.llm.sentences import SentenceCutter
from voicecoach.application.ports.teacher_llm import (
    FeedbackReady,
    LlmError,
    Speaker,
    SpokenSentence,
    TeacherEvent,
    TeacherFeedback,
    TokenUsage,
    Utterance,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

TOOL_NAME = "teacher_feedback"

# A ordem aqui É o ADR-0022, e o teste `test_teacher_prompt.py` a assere. Não
# reordene por legibilidade: reordenar não quebra nada — só a latência sobe.
CAMPOS: dict[str, dict[str, str]] = {
    "spoken_reply": {"type": "string"},
    "has_mistakes": {"type": "boolean"},
    "original": {"type": "string"},
    "corrected": {"type": "string"},
    "tip": {"type": "string"},
    "translation_pt": {"type": "string"},
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


def _para_feedback(bruto: object) -> TeacherFeedback:
    """Converte o input da tool em `TeacherFeedback`, ou levanta.

    Validação à mão, e não com pydantic, por regra de camada: pydantic é
    contrato de API e vive na borda `api/` (ADR-0008). São seis campos de tipo
    conhecido — a "fronteira anti-corrupção" aqui cabe em vinte linhas, e o
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

    if not isinstance(bruto["has_mistakes"], bool):
        message = "has_mistakes não é booleano"
        raise LlmError(message)

    textos = {c: bruto[c] for c in CAMPOS if c != "has_mistakes"}
    errados = [c for c, v in textos.items() if not isinstance(v, str)]
    if errados:
        message = f"campos que deveriam ser texto não são: {errados}"
        raise LlmError(message)

    return TeacherFeedback(
        spoken_reply=textos["spoken_reply"],
        has_mistakes=bruto["has_mistakes"],
        original=textos["original"],
        corrected=textos["corrected"],
        tip=textos["tip"],
        translation_pt=textos["translation_pt"],
    )


def _uso(mensagem: _FinalMessage) -> TokenUsage:
    """As três contagens de entrada, separadas (ADR-0021, item 3).

    O caching está adiado, não esquecido: hoje `cache_creation` e `cache_read`
    são 0 em toda chamada, e é justamente por isso que precisam ser registrados
    — são o instrumento que detecta a mudança de regime.
    """
    u = mensagem.usage
    return TokenUsage(
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
    ) -> None:
        self._client = client
        self._model = model
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens
        self._timeout = timeout_seconds

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
        async with contexto as fluxo:
            async for evento in fluxo:
                pedaco = _delta_de_json(evento)
                if not pedaco:
                    continue
                buffer += pedaco.encode("utf-8")
                fala = _fala_parcial(buffer)
                for trecho in cortador.feed(fala):
                    yield SpokenSentence(text=trecho)

            mensagem = await fluxo.get_final_message()

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
