"""A porta `SpeechToText` vista de `application`: um fake, e nada de STT real.

Este arquivo é a prova de que a fronteira do ADR-0027 funciona. Se ele
precisasse importar `faster_whisper` ou `mlx_whisper` para rodar, a porta não
estaria separando nada.

**O fake não declara herança nenhuma.** `Protocol` é tipagem *estrutural*: ele
satisfaz a porta por ter o método com a assinatura certa, e é o `mypy` — não o
runtime — quem confere isso, na linha anotada `stt: SpeechToText = ...`. Em C#
a classe precisaria dizer `: ISpeechToText` e o compilador cobraria ali; aqui
não há nada a declarar, e por isso o erro aparece no type checker em vez de
numa exceção de execução.
"""

from __future__ import annotations

from voicecoach.application.ports.speech_to_text import (
    AudioInput,
    SpeechToText,
    Transcript,
)


class FakeSpeechToText:
    """Devolve um texto combinado e registra o que recebeu.

    Nenhum framework de mock envolvido — é uma classe comum. Guardar as
    chamadas é o que permite asserção sobre o que o caso de uso mandou para a
    porta, quando o caso de uso existir (CARD-009).
    """

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[AudioInput] = []

    async def transcribe(self, audio: AudioInput) -> Transcript:
        self.calls.append(audio)
        return Transcript(
            text=self._text, language="en", duration_seconds=len(audio.data) / 32_000
        )


async def test_fake_satisfaz_a_porta_sem_declarar_heranca() -> None:
    # A anotação é a asserção: se `FakeSpeechToText` não tivesse a assinatura da
    # porta, o `mypy` reprovaria ESTA linha. O teste em si nunca chegaria a
    # falhar por causa disso.
    stt: SpeechToText = FakeSpeechToText("Wow, that sounds like an amazing project.")

    resultado = await stt.transcribe(AudioInput(data=b"\x00" * 32_000))

    assert resultado.text == "Wow, that sounds like an amazing project."
    assert resultado.language == "en"
    assert resultado.duration_seconds == 1.0


async def test_fake_registra_o_audio_recebido() -> None:
    fake = FakeSpeechToText("ok")
    stt: SpeechToText = fake

    await stt.transcribe(AudioInput(data=b"abc"))

    assert fake.calls == [AudioInput(data=b"abc")]


def test_audio_input_e_imutavel_e_compara_por_valor() -> None:
    # `frozen=True` gera `__eq__` por valor e `__hash__`; é o que faz a asserção
    # do teste acima funcionar sem escrever comparador nenhum.
    assert AudioInput(data=b"abc") == AudioInput(data=b"abc")
    assert AudioInput(data=b"abc") != AudioInput(data=b"xyz")
