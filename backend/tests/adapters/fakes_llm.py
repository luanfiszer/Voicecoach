"""Dublês do stream do `anthropic`, para exercitar o adapter sem tocar a API.

Cada classe aqui declara **só** o que o adapter consome — os mesmos `Protocol`
mínimos de `anthropic_teacher.py`, vistos do outro lado. É isso que torna o
teste honesto: se o adapter passar a ler um campo novo do SDK, este arquivo
para de satisfazê-lo e o `mypy` acusa.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence


class FakeDelta:
    def __init__(self, partial_json: str) -> None:
        self.partial_json = partial_json


class FakeEvent:
    """Um `content_block_delta` com um pedaço de JSON parcial."""

    type = "content_block_delta"

    def __init__(self, partial_json: str) -> None:
        self.delta = FakeDelta(partial_json)


class FakeRuido:
    """Um evento que não carrega JSON — o adapter tem de ignorá-lo."""

    type = "content_block_start"


class FakeToolUse:
    type = "tool_use"

    def __init__(self, entrada: object) -> None:
        self.input = entrada


class FakeTexto:
    """Um bloco de texto no meio do conteúdo, para provar que o adapter procura."""

    type = "text"


class FakeUsage:
    def __init__(
        self,
        entrada: int = 1084,
        saida: int = 180,
        cache_creation: int = 0,
        cache_read: int = 0,
    ) -> None:
        self.input_tokens = entrada
        self.output_tokens = saida
        self.cache_creation_input_tokens = cache_creation
        self.cache_read_input_tokens = cache_read


class FakeMessage:
    def __init__(
        self,
        content: Sequence[object],
        usage: FakeUsage | None = None,
        model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        self.content = content
        self.usage = usage or FakeUsage()
        # O id DATADO, como a API o devolve — não o alias `claude-haiku-4-5` que
        # a config pede. É a diferença que faz a busca de preço do CARD-014 ser
        # por prefixo em vez de por igualdade, e um fake que devolvesse o alias
        # esconderia exatamente esse detalhe.
        self.model = model


class FakeStream:
    def __init__(self, pedacos: Sequence[str], final: FakeMessage) -> None:
        self._pedacos = pedacos
        self._final = final
        self.consumidos: list[str] = []

    def __aiter__(self) -> AsyncIterator[object]:
        return self._eventos()

    async def _eventos(self) -> AsyncIterator[object]:
        yield FakeRuido()
        for pedaco in self._pedacos:
            self.consumidos.append(pedaco)
            yield FakeEvent(pedaco)

    async def get_final_message(self) -> FakeMessage:
        return self._final


class FakeContext:
    """Registra abertura e fechamento — é como se prova que o stream fechou."""

    def __init__(self, stream: FakeStream, registro: dict[str, bool]) -> None:
        self._stream = stream
        self._registro = registro

    async def __aenter__(self) -> FakeStream:
        self._registro["aberto"] = True
        return self._stream

    async def __aexit__(self, *exc: object) -> None:
        self._registro["fechado"] = True


class FakeMessages:
    def __init__(self, pedacos: Sequence[str], final: FakeMessage) -> None:
        self._pedacos = pedacos
        self._final = final
        self.chamadas: list[dict[str, Any]] = []
        self.registros: list[dict[str, bool]] = []
        self.streams: list[FakeStream] = []

    def stream(self, **kwargs: object) -> FakeContext:
        self.chamadas.append(dict(kwargs))
        registro = {"aberto": False, "fechado": False}
        self.registros.append(registro)
        stream = FakeStream(self._pedacos, self._final)
        self.streams.append(stream)
        return FakeContext(stream, registro)


class FakeClient:
    def __init__(self, pedacos: Sequence[str], final: FakeMessage) -> None:
        self.messages = FakeMessages(pedacos, final)


FEEDBACK_COMPLETO: dict[str, object] = {
    "spoken_reply": (
        "That sounds really stressful. Have you tried talking to your manager "
        "about the deadline? It might help a lot."
    ),
    "translation_pt": "Isso parece bem estressante.",
    # Duas correções, porque é o caso que separa o contrato novo do velho: os
    # campos legados do `/v1` saem da PRIMEIRA (CARD-013), e um fake com uma só
    # não provaria nada sobre essa escolha.
    "corrections": [
        {
            "type": "vocabulary",
            "original_excerpt": "very stressful",
            "corrected_form": "quite stressful",
            "explanation": "Both work, but 'quite' sounds more natural here.",
            "severity": "minor",
        },
        {
            "type": "word_order",
            "original_excerpt": "stressful sometimes",
            "corrected_form": "sometimes stressful",
            "explanation": "'sometimes' usually comes before the adjective.",
            "severity": "moderate",
        },
    ],
}


def em_pedacos(texto: str, tamanho: int = 7) -> list[str]:
    """Fatia o JSON como o provedor faria — em pedaços que cortam no meio de tudo."""
    return [texto[i : i + tamanho] for i in range(0, len(texto), tamanho)]
