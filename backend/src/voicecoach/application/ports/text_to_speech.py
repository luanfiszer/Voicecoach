"""Porta de síntese de voz (ADR-0011, ADR-0024, e o ADR de fronteira do CARD-008).

**Chamada uma vez por SENTENÇA, não por resposta.** Não é detalhe de uso: é a
forma da porta. Um ``synthesize(texto_inteiro)`` seria a versão batch que a
cascata (ADR-0023) existe para não construir — e converter batch em streaming
depois é reescrever o consumidor inteiro, como o ADR-0031 registrou para o
professor. O custo é linear no texto (RTF constante, medição §9.1), então cortar
em frases não desperdiça nada: a primeira frase sai em 0,09 s em vez de 0,35 s.

**O que atravessa a porta é PCM cru em ``bytes``, com a taxa junto.** Três
alternativas foram consideradas e a escolha está no ADR:

- ``numpy.ndarray`` é o que os dois motores realmente devolvem, e é exatamente o
  que não pode passar: ``NDArray[np.float32]`` é o tipo *natural* para áudio e
  amarraria ``application`` ao formato interno do adapter. O contrato do
  import-linter proíbe ``numpy`` aqui por isso (ADR-0029, item 2);
- **áudio já comprimido** (AAC/MP3) seria simétrico à porta de STT, mas
  comprimido não concatena: juntar os trechos no ``reply/full`` exigiria
  decodificar tudo de volta e comprimir outra vez — CPU no worker e uma segunda
  perda de qualidade;
- **PCM em ``bytes``** concatena com ``b"".join(...)``, não é tipo de
  biblioteca, e deixa a compressão para quem grava.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

# PCM16: cada amostra é um inteiro de 16 bits, logo 2 bytes. Mono, um canal.
# Este é o formato que atravessa a porta, e o adapter converte para ele — os
# dois motores medidos já o produzem nativamente (`audio_int16_bytes` no Piper).
BYTES_PER_SAMPLE = 2


class SampleRateMismatchError(ValueError):
    """Tentativa de juntar áudios de taxas diferentes.

    Existe para transformar num erro o único modo de falha desta fronteira que,
    sozinho, seria **inaudível para o código e audível para o aluno**: PCM de
    22.050 Hz concatenado com PCM de 24.000 Hz produz um arquivo perfeitamente
    válido, que toca com a velocidade errada em metade da resposta. Nenhuma
    verificação de tipo pega isso — só uma comparação explícita.

    Fica improvável na prática (a taxa vem do modelo, e o modelo é um só por
    processo), e é exatamente por isso que precisa ser barrada aqui: o dia em
    que dois adapters coexistirem, o erro seria descoberto pelo ouvido de um
    aluno.
    """


class TtsError(RuntimeError):
    """O sintetizador não produziu áudio utilizável.

    Mora **na porta** pela mesma razão do ``LlmError`` (ADR-0031, item 5): o
    caso de uso do CARD-009 **vai** capturá-lo para marcar o turn como falho, e
    ``application`` não pode importar ``adapters`` — seta que sobe,
    ``lint-imports`` vermelho. Onde o erro mora é consequência de quem precisa
    capturá-lo, não de quem o levanta.

    Herda de ``RuntimeError`` e não de ``DomainError`` (ADR-0017): motor que
    falha é infraestrutura, não invariante de negócio violada.
    """


@dataclass(frozen=True, slots=True)
class SynthesizedAudio:
    """Áudio sintetizado: amostras cruas mais a única informação que as decifra.

    ``sample_rate`` **não é metadado opcional**. PCM é uma lista de medidas sem
    cabeçalho; sem a taxa, nada nela diz a que velocidade tocar. Os mesmos bytes
    a 22.050 Hz em vez de 24.000 Hz saem 9% mais lentos e mais graves — e a
    falha é *audível*, nunca uma exceção. A taxa é propriedade do **modelo**
    (Kokoro 24.000, Piper 22.050), não da porta, e é por isso que ela viaja
    junto dos bytes em vez de ser uma constante em algum lugar.

    ``frozen=True`` + ``slots=True`` como o resto dos value objects do projeto.
    """

    pcm: bytes
    sample_rate: int

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            message = f"sample_rate precisa ser positivo, veio {self.sample_rate}"
            raise ValueError(message)
        if len(self.pcm) % BYTES_PER_SAMPLE:
            message = (
                f"PCM16 tem 2 bytes por amostra, mas vieram {len(self.pcm)} bytes "
                f"(ímpar): o buffer está truncado ou não é PCM16 mono"
            )
            raise ValueError(message)

    @property
    def duration_seconds(self) -> float:
        """A duração, **derivada** das amostras — nunca um campo à parte.

        É a mesma regra que mantém a etapa do ``Turn`` fora do banco
        (ADR-0023/0028): dado que se calcula não se guarda, porque guardado ele
        pode divergir. Aqui a divergência seria concreta — um campo
        ``duration_seconds`` sobreviveria a uma concatenação que muda o ``pcm``,
        e o cliente agendaria o playback do trecho com o tempo do trecho antigo.
        """
        return len(self.pcm) / BYTES_PER_SAMPLE / self.sample_rate


class TextToSpeech(Protocol):
    """Transforma uma sentença em fala.

    ``async`` porque quem chama é o worker, que é assíncrono. Como no STT, os
    motores locais são **CPU-bound** e empurram o trabalho para um executor — a
    porta não sabe e não se importa se a implementação é local, remota ou um
    fake.

    O V2 (ADR-0003) acrescenta streaming intra-frase **por extensão**; esta
    assinatura não muda.
    """

    async def synthesize(self, text: str) -> SynthesizedAudio: ...


def concat(parts: Sequence[SynthesizedAudio]) -> SynthesizedAudio:
    """Junta os trechos num áudio só — o insumo do ``reply/full`` (ADR-0024).

    **É por causa desta função que a porta trafega PCM.** Juntar amostras cruas
    é somar duas listas de números: ``b"".join(...)``, sem decodificar, sem
    recodificar e sem perda. Com áudio já comprimido, a mesma operação seria
    decodificar N arquivos, concatenar e comprimir de novo — CPU no worker e uma
    segunda passagem de perda em cima de conteúdo que já perdeu uma vez.

    Mora em ``application`` e não em ``adapters`` porque não faz IO nem conhece
    biblioteca nenhuma: é aritmética sobre ``bytes``. Quem a chama é o caso de
    uso do CARD-009, ao fechar o turn.
    """
    if not parts:
        message = "concat: nenhum trecho para juntar"
        raise ValueError(message)

    taxas = {p.sample_rate for p in parts}
    if len(taxas) > 1:
        message = (
            f"concat: trechos com taxas diferentes {sorted(taxas)}. Juntá-los "
            f"produziria áudio com a velocidade errada, sem levantar erro nenhum."
        )
        raise SampleRateMismatchError(message)

    return SynthesizedAudio(
        pcm=b"".join(p.pcm for p in parts),
        sample_rate=parts[0].sample_rate,
    )
