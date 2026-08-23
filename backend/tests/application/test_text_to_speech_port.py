"""A porta de TTS vista de `application`: fakes em memória, nenhum motor real.

Estes testes **não carregam Piper nem Kokoro**. É o ponto da porta: o caso de
uso do CARD-009 vai ser testado assim, em milissegundos, e o adapter de verdade
tem seus próprios testes marcados `slow`.
"""

from __future__ import annotations

import pytest

from voicecoach.application.ports.text_to_speech import (
    BYTES_PER_SAMPLE,
    SampleRateMismatchError,
    SynthesizedAudio,
    TextToSpeech,
    TtsError,
    concat,
)

TAXA = 22_050


def pcm_de(segundos: float, taxa: int = TAXA) -> bytes:
    """Silêncio com a duração pedida — o conteúdo não importa, o tamanho sim."""
    return b"\x00" * (int(segundos * taxa) * BYTES_PER_SAMPLE)


class FakeTts:
    """Um fake é uma classe comum: nenhum framework de mock, nenhuma herança.

    Ele satisfaz `TextToSpeech` por **ter o método com a assinatura certa** —
    tipagem estrutural. Não declara que implementa nada, e é por isso que a
    verificação de que ele de fato serve acontece no `mypy`, não em runtime:
    ver `test_o_fake_satisfaz_a_porta`.
    """

    def __init__(self, taxa: int = TAXA) -> None:
        self.taxa = taxa
        self.chamadas: list[str] = []

    async def synthesize(self, text: str) -> SynthesizedAudio:
        self.chamadas.append(text)
        # 0,05 s de áudio por caractere — nada realista, só determinístico.
        return SynthesizedAudio(
            pcm=pcm_de(0.05 * len(text), self.taxa), sample_rate=self.taxa
        )


def test_o_fake_satisfaz_a_porta() -> None:
    """A anotação é a asserção: quem verifica esta linha é o `mypy`, não o pytest.

    Se `FakeTts.synthesize` mudar de assinatura — outro nome de parâmetro, tipo
    de retorno diferente, deixar de ser `async` —, este arquivo passa a falhar
    no gate de tipos com o pytest ainda verde. Foi exatamente o que aconteceu
    três vezes no CARD-007.
    """
    porta: TextToSpeech = FakeTts()

    assert porta is not None


async def test_a_porta_e_chamada_uma_vez_por_sentenca() -> None:
    """A forma da porta: N chamadas curtas, não uma chamada longa (ADR-0023)."""
    tts = FakeTts()
    sentencas = ["That's a great point.", "How was your day?"]

    audios = [await tts.synthesize(s) for s in sentencas]

    assert tts.chamadas == sentencas
    assert len(audios) == 2


async def test_duracao_e_derivada_das_amostras() -> None:
    audio = SynthesizedAudio(pcm=pcm_de(1.5), sample_rate=TAXA)

    assert audio.duration_seconds == pytest.approx(1.5)


def test_duracao_acompanha_o_pcm_porque_nao_e_campo() -> None:
    """Se fosse campo, a concatenação deixaria a duração antiga para trás."""
    parte = SynthesizedAudio(pcm=pcm_de(2.0), sample_rate=TAXA)

    inteiro = concat([parte, parte])

    assert inteiro.duration_seconds == pytest.approx(4.0)


def test_full_dura_a_soma_das_partes() -> None:
    """Critério de aceite do card, com a tolerância que ele pede (±100 ms)."""
    partes = [
        SynthesizedAudio(pcm=pcm_de(d), sample_rate=TAXA) for d in (1.2, 0.8, 2.5, 0.4)
    ]

    inteiro = concat(partes)

    esperado = sum(p.duration_seconds for p in partes)
    assert inteiro.duration_seconds == pytest.approx(esperado, abs=0.1)


def test_concatenar_e_join_puro_sem_recodificar() -> None:
    """O ganho que a fronteira de PCM compra: os bytes saem intactos."""
    a = SynthesizedAudio(pcm=b"\x01\x02", sample_rate=TAXA)
    b = SynthesizedAudio(pcm=b"\x03\x04", sample_rate=TAXA)

    assert concat([a, b]).pcm == b"\x01\x02\x03\x04"


def test_taxas_diferentes_levantam_em_vez_de_produzir_audio_torto() -> None:
    """O único modo de falha desta fronteira que o tipo não pega."""
    a = SynthesizedAudio(pcm=pcm_de(1.0, 22_050), sample_rate=22_050)
    b = SynthesizedAudio(pcm=pcm_de(1.0, 24_000), sample_rate=24_000)

    with pytest.raises(SampleRateMismatchError, match="velocidade errada"):
        concat([a, b])


def test_concat_sem_partes_levanta() -> None:
    with pytest.raises(ValueError, match="nenhum trecho"):
        concat([])


def test_pcm_impar_nao_e_pcm16() -> None:
    """Buffer truncado é erro no ponto da construção, não áudio com estalo."""
    with pytest.raises(ValueError, match="truncado"):
        SynthesizedAudio(pcm=b"\x00\x00\x00", sample_rate=TAXA)


def test_taxa_invalida_levanta() -> None:
    with pytest.raises(ValueError, match="sample_rate"):
        SynthesizedAudio(pcm=b"", sample_rate=0)


def test_igualdade_e_por_valor_e_o_audio_e_hashavel() -> None:
    """`frozen=True` dá `__eq__` e `__hash__` por valor — Q9 em uma linha.

    É o que permite comparar coleções inteiras com um `==` só, e o que torna um
    `set` de trechos possível. Uma dataclass mutável não teria `__hash__`, e
    `{audio}` levantaria `TypeError`.
    """
    a = SynthesizedAudio(pcm=b"\x01\x02", sample_rate=TAXA)
    b = SynthesizedAudio(pcm=b"\x01\x02", sample_rate=TAXA)
    outro = SynthesizedAudio(pcm=b"\x01\x03", sample_rate=TAXA)

    assert a == b
    assert a != outro
    assert len({a, b, outro}) == 2


async def test_erro_da_porta_e_capturavel_por_quem_orquestra() -> None:
    """`TtsError` mora na porta porque é `application` que vai capturá-lo."""

    class TtsQueFalha:
        async def synthesize(self, text: str) -> SynthesizedAudio:
            message = "o motor não devolveu amostras"
            raise TtsError(message)

    porta: TextToSpeech = TtsQueFalha()

    with pytest.raises(TtsError):
        await porta.synthesize("qualquer coisa")
