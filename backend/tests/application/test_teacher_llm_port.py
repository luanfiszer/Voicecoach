"""A porta `TeacherLlm` vista de `application`: um fake, e nada de SDK.

Este arquivo é a prova de que a fronteira do ADR-0031 funciona. Se ele
precisasse importar `anthropic` ou `jiter` para rodar, a porta não estaria
separando nada.

**O fake não declara herança nenhuma.** `Protocol` é tipagem *estrutural*: ele
satisfaz a porta por ter o método com a assinatura certa, e quem confere isso é
o `mypy`, na linha anotada `professor: TeacherLlm = ...` — não o runtime. Em C#
a classe diria `: ITeacherLlm` e o compilador cobraria ali; aqui não há nada a
declarar, e por isso o erro aparece no type checker em vez de numa exceção.

E há uma armadilha específica desta porta: o método **não** é `async def`. Um
fake escrito como `async def respond_streaming(...)` devolveria uma corrotina, e
não um gerador — o `pytest` só quebraria no `async for`, mas o `mypy` reprova a
atribuição antes disso.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from voicecoach.application.ports.teacher_llm import (
    FeedbackReady,
    LlmError,
    Speaker,
    SpokenSentence,
    TeacherEvent,
    TeacherFeedback,
    TeacherLlm,
    TokenUsage,
    Utterance,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

FEEDBACK = TeacherFeedback(
    spoken_reply="Nice. Tell me more about it.",
    translation_pt="Legal. Me conte mais sobre isso.",
    # Lista vazia é o desfecho ESPERADO na maior parte dos turns: o prompt v2
    # manda o professor ser conservador, e "não houve erro" tem de ser
    # representável sem campo sentinela.
    corrections=(),
)
USO = TokenUsage(
    model="claude-haiku-4-5-20251001",
    input_tokens=1084,
    cache_creation_input_tokens=0,
    cache_read_input_tokens=0,
    output_tokens=42,
)


class FakeTeacherLlm:
    """Emite as sentenças combinadas e registra o histórico que recebeu.

    Nenhum framework de mock envolvido — é uma classe comum. Guardar as chamadas
    é o que vai permitir asserção sobre o que o caso de uso mandou para a porta,
    quando o caso de uso existir (CARD-009).
    """

    def __init__(self, sentencas: Sequence[str], *, falha: bool = False) -> None:
        self._sentencas = sentencas
        self._falha = falha
        self.calls: list[Sequence[Utterance]] = []
        self.cancelado = False

    async def respond_streaming(
        self, history: Sequence[Utterance]
    ) -> AsyncIterator[TeacherEvent]:
        self.calls.append(history)
        try:
            for texto in self._sentencas:
                yield SpokenSentence(text=texto)
            if self._falha:
                message = "resposta do professor sem os campos ['tip']"
                raise LlmError(message)
            yield FeedbackReady(feedback=FEEDBACK, usage=USO)
        except GeneratorExit:
            # É aqui que o cancelamento chega quando o consumidor abandona o
            # laço. Registrar e deixar propagar: engolir um `GeneratorExit` é o
            # que faria a geração real continuar correndo.
            self.cancelado = True
            raise


HISTORICO = [Utterance(speaker=Speaker.STUDENT, text="I work in a hospital")]


async def test_fake_satisfaz_a_porta_sem_declarar_heranca() -> None:
    # A anotação é a asserção: se `FakeTeacherLlm` não tivesse a assinatura da
    # porta, o `mypy` reprovaria ESTA linha. O teste em si nunca chegaria a
    # falhar por causa disso.
    professor: TeacherLlm = FakeTeacherLlm(["Nice.", "Tell me more about it."])

    eventos = [e async for e in professor.respond_streaming(HISTORICO)]

    # Comparação de LISTA INTEIRA de eventos, com um `==` só. É a igualdade
    # estrutural que `@dataclass` gera que torna isto possível: dois
    # `SpokenSentence` com o mesmo texto são iguais, sem comparador escrito.
    assert eventos == [
        SpokenSentence(text="Nice."),
        SpokenSentence(text="Tell me more about it."),
        FeedbackReady(feedback=FEEDBACK, usage=USO),
    ]


async def test_fake_registra_o_historico_recebido() -> None:
    fake = FakeTeacherLlm(["ok"])
    professor: TeacherLlm = fake

    async for _ in professor.respond_streaming(HISTORICO):
        pass

    assert fake.calls == [HISTORICO]


async def test_chamar_sem_iterar_nao_executa_nada() -> None:
    """O gerador é preguiçoso: nem o registro da chamada aconteceu ainda."""
    fake = FakeTeacherLlm(["ok"])
    professor: TeacherLlm = fake

    professor.respond_streaming(HISTORICO)

    assert fake.calls == []


async def test_abandonar_a_iteracao_cancela_a_geracao() -> None:
    fake = FakeTeacherLlm(["Primeira.", "Segunda.", "Terceira."])
    professor: TeacherLlm = fake

    vistos: list[TeacherEvent] = []
    async for evento in professor.respond_streaming(HISTORICO):
        vistos.append(evento)
        break

    # O `async for` com `break` deixa o gerador suspenso; quem o fecha é o
    # coletor de lixo. Fechar à mão é o que torna o teste determinístico —
    # e é o mesmo `aclose()` que o runtime acabaria chamando.
    await professor.respond_streaming(HISTORICO).aclose()  # type: ignore[attr-defined] # a porta promete AsyncIterator; aclose é do gerador

    assert len(vistos) == 1


async def test_llm_error_atravessa_a_porta() -> None:
    """O erro é da porta, não do adapter — é `application` quem vai capturá-lo."""
    professor: TeacherLlm = FakeTeacherLlm(["Uma frase."], falha=True)

    async def consome() -> list[TeacherEvent]:
        return [e async for e in professor.respond_streaming(HISTORICO)]

    with pytest.raises(LlmError, match="sem os campos"):
        await consome()


def test_eventos_iguais_por_valor_e_hashaveis() -> None:
    """`frozen=True` gera `__eq__` por valor E `__hash__`; sem ele, só identidade.

    É por isso que dois eventos com o mesmo texto são iguais e podem ir para um
    `set` — uma dataclass mutável seria comparada por valor mas **proibida** como
    chave, porque um objeto que muda invalidaria o hash já calculado.
    """
    assert SpokenSentence(text="oi") == SpokenSentence(text="oi")
    assert SpokenSentence(text="oi") != SpokenSentence(text="tchau")
    assert len({SpokenSentence(text="oi"), SpokenSentence(text="oi")}) == 1


def test_utterance_e_imutavel() -> None:
    fala = Utterance(speaker=Speaker.STUDENT, text="hi")

    with pytest.raises(AttributeError):
        fala.text = "outro"  # type: ignore[misc] # frozen: a atribuição é o teste
