"""O adapter do professor: cascata, cancelamento, ausência de estado e erro tipado.

Nenhum teste aqui toca a API. O que chama a rede vive em
`test_teacher_llm_integration.py`, atrás do marker `slow` — e **gasta dinheiro**.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from fakes_llm import (
    FEEDBACK_COMPLETO,
    FakeClient,
    FakeMessage,
    FakeToolUse,
    FakeUsage,
    em_pedacos,
)

from voicecoach.adapters.llm.anthropic_teacher import AnthropicTeacher
from voicecoach.application.ports.teacher_llm import (
    FeedbackReady,
    LlmError,
    Speaker,
    SpokenSentence,
    TeacherEvent,
    TeacherLlm,
    Utterance,
)
from voicecoach.domain.correction import CorrectionType, Severity

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

HISTORICO = [
    Utterance(speaker=Speaker.STUDENT, text="I work in a hospital as a nurse"),
    Utterance(speaker=Speaker.TEACHER, text="That sounds meaningful."),
    Utterance(
        speaker=Speaker.STUDENT, text="I think my job is very stressful sometimes"
    ),
]


def adapter(cliente: FakeClient) -> AnthropicTeacher:
    return AnthropicTeacher(
        cliente,
        model="claude-haiku-4-5",
        system_prompt="prompt de teste",
        max_tokens=700,
        timeout_seconds=30.0,
    )


def cliente_completo() -> FakeClient:
    bruto = json.dumps(FEEDBACK_COMPLETO)
    final = FakeMessage(content=[FakeToolUse(FEEDBACK_COMPLETO)])
    return FakeClient(em_pedacos(bruto), final)


async def coleta(porta: TeacherLlm) -> list[TeacherEvent]:
    return [evento async for evento in porta.respond_streaming(HISTORICO)]


# --- o critério que define o card -------------------------------------------


async def test_primeira_sentenca_sai_antes_de_o_json_fechar() -> None:
    """Stream que NUNCA fecha o objeto: se o adapter esperasse, não sairia nada.

    O buffer termina no meio de uma palavra e sem `}`. `json.loads` levantaria
    aqui; é o `partial_mode="trailing-strings"` do `jiter` que faz a fala
    incompleta ser legível.
    """
    truncado = '{"spoken_reply": "Hi there, how are you today? I am so gl'
    cliente = FakeClient(em_pedacos(truncado), FakeMessage(content=[]))
    porta: TeacherLlm = adapter(cliente)

    # A porta promete `AsyncIterator` — o consumidor só precisa de `async for`.
    # `aclose()` é do GERADOR, e é ele que este teste quer exercitar; daí o cast.
    gerador = cast(
        "AsyncGenerator[TeacherEvent, None]", porta.respond_streaming(HISTORICO)
    )
    primeiro = await anext(gerador)
    await gerador.aclose()

    assert primeiro == SpokenSentence(text="Hi there, how are you today?")


async def test_gerador_nao_executa_nada_ate_alguem_iterar() -> None:
    """Chamar não é executar — e é por isso que um teste que só chama passa verde.

    `async def` + `yield` devolve o gerador na hora, sem `await`. O corpo (aqui:
    a validação do histórico vazio) só roda no primeiro `__anext__`.
    """
    cliente = cliente_completo()
    porta: TeacherLlm = adapter(cliente)

    gerador = porta.respond_streaming([])  # histórico vazio: deveria falhar

    assert cliente.messages.chamadas == []  # nem a chamada foi montada

    with pytest.raises(LlmError, match="histórico vazio"):
        await anext(gerador)


# --- cancelamento ------------------------------------------------------------


async def test_abandonar_a_iteracao_fecha_o_stream() -> None:
    """`aclose()` levanta `GeneratorExit` no `yield`, que sai do `async with`.

    Sem isso o produto pagaria por tokens que ninguém vai ouvir: a geração
    continuaria correndo do outro lado da conexão.
    """
    cliente = cliente_completo()
    porta: TeacherLlm = adapter(cliente)

    gerador = cast(
        "AsyncGenerator[TeacherEvent, None]", porta.respond_streaming(HISTORICO)
    )
    await anext(gerador)
    registro = cliente.messages.registros[0]
    assert registro == {"aberto": True, "fechado": False}

    await gerador.aclose()

    assert registro == {"aberto": True, "fechado": True}


async def test_stream_fecha_tambem_no_caminho_feliz() -> None:
    cliente = cliente_completo()
    porta: TeacherLlm = adapter(cliente)

    await coleta(porta)

    assert cliente.messages.registros[0]["fechado"] is True


# --- ausência de estado ------------------------------------------------------


async def test_adapter_nao_guarda_estado_entre_duas_chamadas() -> None:
    cliente = cliente_completo()
    porta: TeacherLlm = adapter(cliente)

    primeira = await coleta(porta)
    segunda = await coleta(porta)

    assert primeira == segunda  # mesma entrada, mesma saída — nada acumulou
    assert len(cliente.messages.chamadas) == 2
    # Cada chamada levou o histórico INTEIRO que recebeu, e só ele: se o adapter
    # guardasse conversa, a segunda chamada teria o dobro de mensagens.
    for chamada in cliente.messages.chamadas:
        assert len(chamada["messages"]) == len(HISTORICO)


def test_adapter_so_guarda_configuracao() -> None:
    """Inspeção direta: os atributos são os do construtor, e nada mais."""
    instancia = adapter(cliente_completo())

    guardado = {
        nome: valor for nome, valor in vars(instancia).items() if nome != "_client"
    }
    assert guardado == {
        "_model": "claude-haiku-4-5",
        "_system_prompt": "prompt de teste",
        "_max_tokens": 700,
        "_timeout": 30.0,
    }


# --- o fluxo completo, e a igualdade de dataclass que o torna asserível -------


async def test_fluxo_termina_com_feedback_ready_e_as_tres_contagens() -> None:
    cliente = cliente_completo()
    porta: TeacherLlm = adapter(cliente)

    eventos = await coleta(porta)

    assert all(isinstance(e, SpokenSentence) for e in eventos[:-1])
    ultimo = eventos[-1]
    assert isinstance(ultimo, FeedbackReady)
    assert ultimo.feedback.spoken_reply == FEEDBACK_COMPLETO["spoken_reply"]
    # As duas correções chegaram tipadas, com o índice atribuído pela POSIÇÃO no
    # array — o modelo não manda índice (ver `_para_correcao`).
    assert [c.index for c in ultimo.feedback.corrections] == [0, 1]
    assert ultimo.feedback.corrections[0].type is CorrectionType.VOCABULARY
    assert ultimo.feedback.corrections[1].severity is Severity.MODERATE
    # As três contagens de entrada, separadas (ADR-0021, item 3). Hoje as de
    # cache são 0 em toda chamada — e é exatamente por isso que existem.
    assert ultimo.usage.input_tokens == 1084
    assert ultimo.usage.cache_creation_input_tokens == 0
    assert ultimo.usage.cache_read_input_tokens == 0


async def test_a_fala_emitida_reconstroi_o_spoken_reply() -> None:
    """Nenhum pedaço se perde e nenhum se repete entre os trechos emitidos."""
    cliente = cliente_completo()
    porta: TeacherLlm = adapter(cliente)

    eventos = await coleta(porta)
    falado = " ".join(e.text for e in eventos if isinstance(e, SpokenSentence))

    assert falado == FEEDBACK_COMPLETO["spoken_reply"]


async def test_usage_sem_campos_de_cache_vira_zero() -> None:
    """Provedor que não reporta cache não pode derrubar o adapter."""

    class UsageMagro:
        input_tokens = 10
        output_tokens = 20

    final = FakeMessage(content=[FakeToolUse(FEEDBACK_COMPLETO)])
    final.usage = UsageMagro()  # type: ignore[assignment] # dublê deliberadamente incompleto
    cliente = FakeClient(em_pedacos(json.dumps(FEEDBACK_COMPLETO)), final)

    eventos = await coleta(adapter(cliente))

    ultimo = eventos[-1]
    assert isinstance(ultimo, FeedbackReady)
    assert ultimo.usage.cache_read_input_tokens == 0


# --- caminho triste: LlmError, nunca texto cru adiante -----------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        pytest.param({"spoken_reply": "oi"}, "sem os campos", id="campos-faltando"),
        pytest.param(
            {**FEEDBACK_COMPLETO, "corrections": "nem é lista"},
            "corrections não é um array",
            id="corrections-nao-e-array",
        ),
        pytest.param(
            {**FEEDBACK_COMPLETO, "translation_pt": 42},
            "deveriam ser texto",
            id="tipo-errado-no-texto",
        ),
        pytest.param(
            {**FEEDBACK_COMPLETO, "corrections": [{"type": "grammar"}]},
            "correção 0 sem os campos",
            id="correcao-incompleta",
        ),
        pytest.param(
            # O provedor impõe o `enum` do schema, então isto não deveria
            # acontecer — o teste existe porque "não deveria" não é garantia, e
            # um valor fora da escala viraria uma linha que o banco recusa lá no
            # fim do pipeline, longe da causa.
            {
                "spoken_reply": "oi",
                "translation_pt": "oi",
                "corrections": [
                    {
                        "type": "grammar",
                        "original_excerpt": "a",
                        "corrected_form": "b",
                        "explanation": "c",
                        "severity": "catastrophic",
                    }
                ],
            },
            "fora da escala combinada",
            id="severidade-inventada",
        ),
        pytest.param(
            {**FEEDBACK_COMPLETO, "corrections": ["nem é objeto"]},
            "correção 0 não é um objeto",
            id="item-de-correcao-nao-e-objeto",
        ),
        pytest.param(["nem é objeto"], "não é um objeto", id="nao-e-objeto"),
    ],
)
async def test_resposta_fora_do_schema_vira_llm_error(
    entrada: object, esperado: str
) -> None:
    final = FakeMessage(content=[FakeToolUse(entrada)])
    cliente = FakeClient(em_pedacos(json.dumps(FEEDBACK_COMPLETO)), final)

    with pytest.raises(LlmError, match=esperado):
        await coleta(adapter(cliente))


async def test_resposta_sem_tool_use_vira_llm_error() -> None:
    from fakes_llm import FakeTexto

    final = FakeMessage(content=[FakeTexto()], usage=FakeUsage())
    cliente = FakeClient(em_pedacos(json.dumps(FEEDBACK_COMPLETO)), final)

    with pytest.raises(LlmError, match="não chamou a tool"):
        await coleta(adapter(cliente))


async def test_sentencas_ja_emitidas_nao_sao_desditas_pelo_erro() -> None:
    """O contrato do caminho triste é do CARD-009; aqui só se prova o que sai.

    A fala já emitida saiu. O erro vem DEPOIS dela, e é o consumidor que decide
    o que fazer com um turno que falou metade.
    """
    final = FakeMessage(content=[FakeToolUse({"spoken_reply": "só isso"})])
    cliente = FakeClient(em_pedacos(json.dumps(FEEDBACK_COMPLETO)), final)
    porta: TeacherLlm = adapter(cliente)

    emitidos: list[TeacherEvent] = []

    async def consome() -> None:
        async for evento in porta.respond_streaming(HISTORICO):
            emitidos.append(evento)

    with pytest.raises(LlmError):
        await consome()

    assert emitidos
    assert all(isinstance(e, SpokenSentence) for e in emitidos)


# --- a requisição montada ----------------------------------------------------


async def test_requisicao_usa_tool_use_com_streaming_granular() -> None:
    """Sem `eager_input_streaming` a cascata deixa de existir — sem erro nenhum."""
    cliente = cliente_completo()

    await coleta(adapter(cliente))

    chamada = cliente.messages.chamadas[0]
    tool = chamada["tools"][0]
    assert tool["eager_input_streaming"] is True
    assert chamada["tool_choice"] == {"type": "tool", "name": tool["name"]}
    assert chamada["timeout"] == 30.0
    assert chamada["model"] == "claude-haiku-4-5"


async def test_papeis_do_historico_viram_user_e_assistant() -> None:
    cliente = cliente_completo()

    await coleta(adapter(cliente))

    assert [m["role"] for m in cliente.messages.chamadas[0]["messages"]] == [
        "user",
        "assistant",
        "user",
    ]
