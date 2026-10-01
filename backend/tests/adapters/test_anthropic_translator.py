"""``AnthropicTranslator`` com um cliente fake — sem rede (CARD-063).

O adapter chegou ao CARD-036 sem teste próprio; o CARD-063 achou, por QA na
stack real, que ele às vezes RESPONDIA ao texto em vez de traduzi-lo. Se o
modelo obedece ou não é medição (`benchmarks/llm_traducao_responde.py`), não
teste unitário. O que se testa aqui é o que é do adapter: o texto vai
delimitado como material, as marcas não voltam para a tela, e erro do SDK vira
erro da porta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

import httpx2
import pytest
from anthropic import APIConnectionError, APIStatusError

from voicecoach.adapters.llm.anthropic_translator import AnthropicTranslator
from voicecoach.application.ports.translator import TranslatorError


@dataclass
class _Bloco:
    text: str
    type: str = "text"


@dataclass
class _Uso:
    input_tokens: int = 40
    output_tokens: int = 12


@dataclass
class _Mensagem:
    content: list[_Bloco]
    model: str = "claude-haiku-4-5-20251001"
    usage: _Uso = field(default_factory=_Uso)


class _Mensagens:
    def __init__(self, resposta: _Mensagem | BaseException) -> None:
        self._resposta = resposta
        self.pedidos: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _Mensagem:
        self.pedidos.append(kwargs)
        if isinstance(self._resposta, BaseException):
            raise self._resposta
        return self._resposta


class _Cliente:
    def __init__(self, resposta: _Mensagem | BaseException) -> None:
        self.messages = _Mensagens(resposta)


def _tradutor(
    resposta: _Mensagem | BaseException,
) -> tuple[AnthropicTranslator, _Cliente]:
    cliente = _Cliente(resposta)
    tradutor = AnthropicTranslator(
        cast("Any", cliente),
        model="claude-haiku-4-5",
        max_tokens=500,
        timeout_seconds=15.0,
    )
    return tradutor, cliente


def _pedido() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


async def test_o_texto_vai_delimitado_como_material_nao_como_conversa() -> None:
    """O defeito do CARD-063: a pergunta do professor ia crua e era respondida."""
    tradutor, cliente = _tradutor(_Mensagem([_Bloco("Que tipo de projeto?")]))

    await tradutor.to_portuguese("What kind of project are you working on?")

    (pedido,) = cliente.messages.pedidos
    assert pedido["messages"] == [
        {
            "role": "user",
            "content": "<texto>\nWhat kind of project are you working on?\n</texto>",
        }
    ]
    assert "<texto>" in pedido["system"]


async def test_as_marcas_ecoadas_pelo_modelo_nao_chegam_a_tela() -> None:
    tradutor, _ = _tradutor(_Mensagem([_Bloco("<texto>\nQue legal!\n</texto>")]))

    traduzido = await tradutor.to_portuguese("How cool!")

    assert traduzido.text == "Que legal!"


async def test_devolve_o_uso_do_modelo_que_respondeu() -> None:
    tradutor, _ = _tradutor(_Mensagem([_Bloco("Oi")]))

    traduzido = await tradutor.to_portuguese("Hi")

    assert traduzido.usage.model == "claude-haiku-4-5-20251001"
    assert traduzido.usage.input_tokens == 40
    assert traduzido.usage.output_tokens == 12


async def test_resposta_sem_texto_e_erro_da_porta() -> None:
    tradutor, _ = _tradutor(_Mensagem([_Bloco("<texto></texto>")]))

    with pytest.raises(TranslatorError, match="sem texto"):
        await tradutor.to_portuguese("Hi")


@pytest.mark.parametrize(
    ("erro", "trecho"),
    [
        (APIConnectionError(request=_pedido()), "não atendeu"),
        (
            APIStatusError(
                "HTTP 529",
                response=httpx2.Response(529, request=_pedido()),
                body=None,
            ),
            "não atendeu",
        ),
        (
            APIStatusError(
                "HTTP 400",
                response=httpx2.Response(400, request=_pedido()),
                body=None,
            ),
            "recusou a requisição",
        ),
    ],
)
async def test_erro_do_sdk_vira_erro_da_porta(erro: BaseException, trecho: str) -> None:
    tradutor, _ = _tradutor(erro)

    with pytest.raises(TranslatorError, match=trecho):
        await tradutor.to_portuguese("Hi")
