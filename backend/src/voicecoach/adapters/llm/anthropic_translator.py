"""Adapter de tradução sobre a Anthropic (CARD-036, ADR-0009/ADR-0066).

**Uma chamada, um valor** — o contraste com o ``AnthropicTeacher`` é o ponto
inteiro da porta separada: lá é `messages.stream()` com tool use, ponto de
não-retorno e breaker em três pontos nomeados; aqui é `messages.create()`, sem
stream e sem tool, porque não há latência a esconder (RNF5) nem estrutura a
extrair — a resposta É o texto.

**Sem tool use, e a decisão é de custo.** Forçar um JSON com um campo só
gastaria tokens de schema em toda chamada para embrulhar aquilo que o modelo
já devolve como texto puro. O preço é não ter validação estrutural da resposta;
a compensação é que a única falha possível ("veio vazio") é verificável com um
``if``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from anthropic import (
    AnthropicError,
    APIConnectionError,
    APIStatusError,
)

from voicecoach.application.ports.teacher_llm import TokenUsage
from voicecoach.application.ports.translator import Translated, TranslatorError

if TYPE_CHECKING:
    from collections.abc import Sequence

# O mesmo conjunto do adapter do professor, e pela mesma razão — só que aqui
# ele não alimenta breaker nenhum: serve para a mensagem do log e para deixar
# escrito que 401/400 continuam sendo bug nosso, não "provedor fora".
_STATUS_DE_INDISPONIBILIDADE = frozenset({408, 409, 429, 529})

# **O prompt é constante de módulo, e curto de propósito.** Cada token dele é
# pago em toda tradução (RF5: o barato). A instrução de não responder à
# pergunta existe porque o texto de origem é a fala de um professor de inglês —
# um modelo prestativo tende a *responder* "Which beach did you go to?" em vez
# de traduzi-la.
_INSTRUCAO = (
    "Você traduz para português do Brasil. Devolva SOMENTE a tradução do texto "
    "recebido, sem aspas, sem comentários e sem responder ao conteúdo. "
    "Preserve o tom e mantenha em inglês os termos que o texto ensina."
)


def _e_indisponibilidade(exc: AnthropicError) -> bool:
    if isinstance(exc, APIConnectionError):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in _STATUS_DE_INDISPONIBILIDADE or exc.status_code >= 500
    return False


def _traduzir_erro(exc: AnthropicError) -> TranslatorError:
    """Erro do SDK vira erro **da porta**, na fronteira.

    Um só tipo para os dois casos (ver ``TranslatorError``): a tela é a mesma
    e não há breaker para alimentar. O texto da mensagem preserva a distinção
    para quem lê o log.
    """
    fora = "não atendeu" if _e_indisponibilidade(exc) else "recusou a requisição"
    message = f"o tradutor {fora}: {type(exc).__name__}: {exc}"
    return TranslatorError(message)


class _Usage(Protocol):
    @property
    def input_tokens(self) -> int: ...
    @property
    def output_tokens(self) -> int: ...


class _Message(Protocol):
    @property
    def usage(self) -> _Usage: ...
    @property
    def content(self) -> Sequence[object]: ...
    @property
    def model(self) -> str: ...


class _Messages(Protocol):
    async def create(self, **kwargs: object) -> _Message: ...


class _Client(Protocol):
    """O mínimo que este adapter consome do SDK — ver a nota na factory."""

    @property
    def messages(self) -> _Messages: ...


def _texto(mensagem: _Message) -> str:
    """Concatena os blocos de texto da resposta.

    Uma resposta sem tool tem normalmente **um** bloco, mas concatenar em vez
    de indexar `[0]` custa a mesma linha e não quebra no dia em que o provedor
    devolver dois.
    """
    partes = [
        texto
        for bloco in mensagem.content
        if getattr(bloco, "type", None) == "text"
        and isinstance(texto := getattr(bloco, "text", ""), str)
    ]
    return "".join(partes).strip()


class AnthropicTranslator:
    """Implementa ``Translator`` sobre um cliente assíncrono já construído."""

    def __init__(
        self,
        client: _Client,
        *,
        model: str,
        max_tokens: int,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout_seconds

    async def to_portuguese(self, text: str) -> Translated:
        try:
            mensagem = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=_INSTRUCAO,
                messages=[{"role": "user", "content": text}],
                timeout=self._timeout,
            )
        except AnthropicError as exc:
            raise _traduzir_erro(exc) from exc

        traduzido = _texto(mensagem)
        if not traduzido:
            message = "o tradutor devolveu uma resposta sem texto"
            raise TranslatorError(message)

        u = mensagem.usage
        return Translated(
            text=traduzido,
            usage=TokenUsage(
                # O modelo que RESPONDEU, não o alias pedido — a mesma nota do
                # `_uso` do professor: é o id datado que tem preço na tabela.
                model=mensagem.model,
                input_tokens=u.input_tokens,
                cache_creation_input_tokens=getattr(
                    u, "cache_creation_input_tokens", None
                )
                or 0,
                cache_read_input_tokens=getattr(u, "cache_read_input_tokens", None)
                or 0,
                output_tokens=u.output_tokens,
            ),
        )
