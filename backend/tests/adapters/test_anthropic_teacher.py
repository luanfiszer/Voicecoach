"""O adapter do professor: cascata, cancelamento, ausência de estado e erro tipado.

Nenhum teste aqui toca a API. O que chama a rede vive em
`test_teacher_llm_integration.py`, atrás do marker `slow` — e **gasta dinheiro**.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import httpx2
import pytest
from anthropic import APIConnectionError, APIStatusError, APITimeoutError
from fakes_llm import (
    FEEDBACK_COMPLETO,
    FakeClient,
    FakeMessage,
    FakeToolUse,
    FakeUsage,
    em_pedacos,
)

from voicecoach.adapters.llm.anthropic_teacher import AnthropicTeacher
from voicecoach.adapters.resilience import CircuitBreaker
from voicecoach.application.ports.teacher_llm import (
    FeedbackReady,
    LlmError,
    Speaker,
    SpokenSentence,
    TeacherEvent,
    TeacherLlm,
    TeacherUnavailableError,
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


def adapter(
    cliente: FakeClient,
    breaker: CircuitBreaker | None = None,
) -> AnthropicTeacher:
    return AnthropicTeacher(
        cliente,
        model="claude-haiku-4-5",
        system_prompt="prompt de teste",
        max_tokens=700,
        timeout_seconds=30.0,
        # Um breaker que nunca abre é o default dos testes que não são sobre
        # ele: `failure_threshold` alto o basta para nenhum caso existente
        # esbarrar nele. Quem testa o breaker passa o seu.
        breaker=breaker
        or CircuitBreaker(
            failure_threshold=1_000_000,
            recovery=timedelta(seconds=30),
            clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
            name="fake",
        ),
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


def test_adapter_so_guarda_configuracao_e_o_breaker() -> None:
    """Inspeção direta: os atributos são os do construtor, e nada mais.

    **O `_breaker` é a primeira exceção à regra "nada de estado entre
    chamadas", e ela é deliberada** (CARD-026). O que o teste original proibia
    era estado de CONVERSA — `_history` e `_last_reply` do protótipo, que faziam
    a segunda chamada depender da primeira e travaram a evolução daquele código.
    O breaker guarda estado sobre o **provedor**, não sobre o aluno: nenhuma
    resposta muda por causa dele, e duas chamadas com o mesmo histórico
    continuam dando a mesma saída (é o que o teste acima afirma).

    A distinção vale escrita porque a próxima pessoa a acrescentar um atributo
    aqui vai encontrar este teste e precisa saber qual dos dois casos é o seu.
    """
    instancia = adapter(cliente_completo())

    guardado = {
        nome: valor
        for nome, valor in vars(instancia).items()
        if nome not in ("_client", "_breaker")
    }
    assert guardado == {
        "_model": "claude-haiku-4-5",
        "_system_prompt": "prompt de teste",
        "_max_tokens": 700,
        "_timeout": 30.0,
    }
    assert isinstance(instancia._breaker, CircuitBreaker)


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


# --- CARD-026: a fronteira externa deixa de ser uma requisição crua ----------
#
# Os três cenários da §4.7 do prompt do card são cenários DIFERENTES, e é fácil
# escrever só o terceiro:
#
#   morto    — a conexão nem abre
#   lento    — responde, mas depois do prazo
#   com erro — responde rápido, com falha de conteúdo. NÃO abre o circuito
#
# O terceiro é o que separa um breaker útil de um que abre sozinho em produção.


class ClienteQueFalha:
    """Cliente do SDK que levanta onde o teste mandar.

    `chamadas` é o que prova o critério "falha **sem abrir conexão**": com o
    circuito aberto, `stream()` não é sequer invocado.
    """

    def __init__(self, erro: BaseException, *, no_aenter: bool = True) -> None:
        self._erro = erro
        self._no_aenter = no_aenter
        self.chamadas = 0
        self.messages = self

    def stream(self, **kwargs: object) -> ClienteQueFalha:
        self.chamadas += 1
        return self

    async def __aenter__(self) -> ClienteQueFalha:
        if self._no_aenter:
            raise self._erro
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def __aiter__(self) -> ClienteQueFalha:
        return self

    async def __anext__(self) -> object:
        # Falha DEPOIS de o stream ter aberto: o provedor demonstrou estar vivo.
        raise self._erro


class Relogio:
    """Relógio controlado pelo teste — a janela de recuperação sem esperar 30 s."""

    def __init__(self) -> None:
        self.agora = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.agora

    def avanca(self, delta: timedelta) -> None:
        self.agora += delta


def breaker_de_teste(relogio: Relogio, *, limite: int = 3) -> CircuitBreaker:
    return CircuitBreaker(
        failure_threshold=limite,
        recovery=timedelta(seconds=30),
        clock=relogio,
        name="professor (teste)",
    )


def _pedido() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def morto() -> APIConnectionError:
    return APIConnectionError(request=_pedido())


def lento() -> APITimeoutError:
    return APITimeoutError(request=_pedido())


def status(codigo: int) -> APIStatusError:
    return APIStatusError(
        f"HTTP {codigo}", response=httpx2.Response(codigo, request=_pedido()), body=None
    )


def _adapter_que_falha(
    erro: BaseException, disjuntor: CircuitBreaker, *, no_aenter: bool = True
) -> tuple[AnthropicTeacher, ClienteQueFalha]:
    cliente = ClienteQueFalha(erro, no_aenter=no_aenter)
    porta = AnthropicTeacher(
        cast("Any", cliente),
        model="claude-haiku-4-5",
        system_prompt="prompt de teste",
        max_tokens=700,
        timeout_seconds=30.0,
        breaker=disjuntor,
    )
    return porta, cliente


@pytest.mark.parametrize(
    ("rotulo", "erro"),
    [
        ("morto", morto()),
        ("lento", lento()),
        ("sobrecarregado (529)", status(529)),
        ("rate limited (429)", status(429)),
        ("erro do provedor (503)", status(503)),
    ],
)
async def test_provedor_que_nao_atende_vira_erro_DA_PORTA(  # noqa: N802 — o nome É a asserção
    rotulo: str, erro: BaseException
) -> None:
    """**O buraco que este card encontrou, e o maior deles.**

    O adapter não capturava nada, e a hierarquia do SDK é
    `AnthropicError -> Exception` — não `RuntimeError`. Nenhuma delas casava com
    o `FALHAS_DE_INFRAESTRUTURA` do `ProcessTurn`, então o provedor fora do ar
    atravessava o caso de uso INTEIRO sem ser capturado: o turn não era marcado
    `failed`, o retry do CARD-025 não era pedido, e o aluno ficava na tela de
    espera até a varredura o encerrar 5 minutos depois.

    Se este teste um dia falhar porque o `anthropic` passou a herdar de
    `RuntimeError`, a tradução continua certa — o que ela garante é o tipo da
    PORTA, e é dele que o caso de uso depende.
    """
    relogio = Relogio()
    porta, _ = _adapter_que_falha(erro, breaker_de_teste(relogio))

    with pytest.raises(TeacherUnavailableError):
        await coleta(porta)


@pytest.mark.parametrize("codigo", [400, 401, 403, 404])
async def test_erro_que_e_culpa_NOSSA_nao_vira_indisponibilidade(  # noqa: N802 — o nome É a asserção
    codigo: int,
) -> None:
    """Chave errada não é "o provedor caiu", e a diferença tem consequência.

    Um 401 tratado como indisponibilidade abriria o circuito e esconderia o
    defeito atrás de uma tela de "serviço indisponível" que nunca se resolveria
    sozinha — o produto ficaria fora do ar esperando um provedor que está bem.
    """
    relogio = Relogio()
    disjuntor = breaker_de_teste(relogio)
    porta, _ = _adapter_que_falha(status(codigo), disjuntor)

    with pytest.raises(LlmError) as capturado:
        await coleta(porta)

    assert not isinstance(capturado.value, TeacherUnavailableError)
    assert not disjuntor.aberto


async def test_falha_de_CONTEUDO_nao_abre_o_circuito() -> None:  # noqa: N802 — o nome É a asserção
    """**O terceiro cenário da §4.7, e o mais fácil de esquecer.**

    O provedor responde rápido e bem; o que veio dentro é que está fora do
    schema. Isso é o professor FUNCIONANDO e respondendo mal — tipicamente um
    bug de prompt nosso. Um breaker que contasse isto abriria o circuito num dia
    de deploy de prompt e derrubaria o produto inteiro, com a tela dizendo ao
    aluno que o serviço está indisponível quando o serviço está ótimo.
    """
    relogio = Relogio()
    disjuntor = breaker_de_teste(relogio, limite=2)
    # Stream que fecha sem chamar a tool: `_entrada_da_tool` levanta `LlmError`.
    cliente = FakeClient(em_pedacos('{"spoken_reply": "oi"}'), FakeMessage(content=[]))
    porta: TeacherLlm = adapter(cliente, disjuntor)

    for _ in range(10):
        with pytest.raises(LlmError):
            await coleta(porta)

    assert not disjuntor.aberto


async def test_falha_DEPOIS_de_o_stream_abrir_nao_conta_para_o_breaker() -> None:  # noqa: N802 — o nome É a asserção
    """A janela do breaker termina no `__aenter__`, e é por isso que ele é nosso.

    Se o stream abriu, o provedor está vivo — ele atendeu. Uma queda no meio
    derruba o turn (vira `TeacherUnavailableError`, o aluno é avisado), mas não
    é evidência de que o provedor esteja fora do ar, e contá-la faria o breaker
    abrir por uma conexão instável de um aluno só.

    **É esta linha que nenhuma biblioteca de breaker daria de graça:** todas
    embrulham corrotina, cujo desfecho é um só no fim. Aqui há dois desfechos
    distintos no meio de um gerador.
    """
    relogio = Relogio()
    disjuntor = breaker_de_teste(relogio, limite=1)
    porta, _ = _adapter_que_falha(morto(), disjuntor, no_aenter=False)

    with pytest.raises(TeacherUnavailableError):
        await coleta(porta)

    assert not disjuntor.aberto


async def test_com_o_circuito_aberto_a_falha_e_imediata_e_SEM_ABRIR_CONEXAO() -> None:  # noqa: N802 — o nome É a asserção
    """Critério de aceite: o turn N+1 falha sem abrir conexão e em tempo desprezível.

    `chamadas` conta invocações de `stream()` — o momento em que a requisição
    seria montada. Depois de aberto o circuito, ele **para de crescer**: é isso
    que transforma 60 s de espera por aluno em microssegundos, e é o que o card
    quer dizer com "a falha é barata".
    """
    relogio = Relogio()
    disjuntor = breaker_de_teste(relogio, limite=3)
    porta, cliente = _adapter_que_falha(morto(), disjuntor)

    for _ in range(3):
        with pytest.raises(TeacherUnavailableError):
            await coleta(porta)
    assert cliente.chamadas == 3
    assert disjuntor.aberto

    for _ in range(20):
        with pytest.raises(TeacherUnavailableError, match="circuito aberto"):
            await coleta(porta)

    assert cliente.chamadas == 3  # nenhuma conexão nova foi sequer montada


async def test_vencida_a_janela_a_chamada_seguinte_tenta_de_novo() -> None:
    """Critério de aceite: o circuito não fica aberto para sempre."""
    relogio = Relogio()
    disjuntor = breaker_de_teste(relogio, limite=1)
    porta, cliente = _adapter_que_falha(morto(), disjuntor)

    with pytest.raises(TeacherUnavailableError):
        await coleta(porta)
    with pytest.raises(TeacherUnavailableError, match="circuito aberto"):
        await coleta(porta)
    assert cliente.chamadas == 1

    relogio.avanca(timedelta(seconds=31))

    with pytest.raises(TeacherUnavailableError):
        await coleta(porta)
    assert cliente.chamadas == 2  # a sonda de fato tentou


async def test_provedor_que_volta_fecha_o_circuito_e_o_produto_volta() -> None:
    """O caminho de volta inteiro, que é o que justifica o breaker existir."""
    relogio = Relogio()
    disjuntor = breaker_de_teste(relogio, limite=1)
    quebrado = ClienteQueFalha(morto())
    saudavel = cliente_completo()
    porta = AnthropicTeacher(
        cast("Any", quebrado),
        model="claude-haiku-4-5",
        system_prompt="prompt de teste",
        max_tokens=700,
        timeout_seconds=30.0,
        breaker=disjuntor,
    )

    with pytest.raises(TeacherUnavailableError):
        await coleta(porta)
    assert disjuntor.aberto

    # O provedor volta: troca-se o cliente por um que responde, como se a rede
    # tivesse se restabelecido entre um turn e outro.
    porta._client = cast("Any", saudavel)
    relogio.avanca(timedelta(seconds=31))

    eventos = await coleta(porta)

    assert not disjuntor.aberto
    assert isinstance(eventos[-1], FeedbackReady)
