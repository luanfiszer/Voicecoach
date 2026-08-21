"""STT local em CPU com ``faster-whisper`` (CTranslate2).

Default fora do Apple Silicon e único caminho que o CI exercita (ADR-0027).
Os parâmetros aqui NÃO são os que os tutoriais mostram — são os medidos:

- ``float32``, não ``int8``. Contraintuitivo e medido: abandonar a quantização
  fez o ``small.en`` cair de 1,48 s para 1,18 s. "int8 porque é mais leve" é
  otimização por hábito que a medição desmentiu;
- ``beam_size=1``, não 5. Corta ~30%;
- língua forçada ``en``. Não é autodetecção — o aluno fala inglês por
  definição, e detectar custa uma janela a mais.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

from voicecoach.adapters.stt.audio import decode, duration_seconds
from voicecoach.application.ports.speech_to_text import AudioInput, Transcript

if TYPE_CHECKING:
    from collections.abc import Iterable

    import numpy as np
    from numpy.typing import NDArray

# Medidos em `docs/medicao-latencia.md` §3.2. Constantes de módulo, não campos
# de configuração: são conclusões de medição, e mexer neles sem remedir é
# desfazer a medição. O que É configurável é o modelo (ADR-0027, item 7).
COMPUTE_TYPE = "float32"
DEVICE = "cpu"
BEAM_SIZE = 1
LANGUAGE = "en"

# O VAD (detecção de atividade de voz) segue LIGADO como no protótipo, e segue
# NÃO AVALIADO (ADR-0027, item 8): o insumo sintético da medição não tinha
# silêncio nem hesitação para ele ter o que fazer. A avaliação vai junto com a
# escolha de modelo, quando houver voz de aprendiz real.
VAD_FILTER = True


class _Segment(Protocol):
    """O que este adapter usa de um segmento — nada além do texto.

    Declarar o mínimo que se consome (em vez de importar o tipo real da
    biblioteca) mantém o teste unitário honesto: o stub do teste precisa ter
    exatamente isto, e não um objeto inteiro do `faster-whisper`.
    """

    text: str


class _Info(Protocol):
    """O segundo elemento da tupla — só a língua nos interessa."""

    language: str


class _Engine(Protocol):
    """O pedaço do ``WhisperModel`` que este adapter consome.

    Escrito com os parâmetros nomeados explicitamente em vez de ``**kwargs:
    Any``: o ruff proíbe ``Any`` em assinatura (``ANN401``), e a proibição
    ajuda — declarar o contrato exato faz o type checker conferir a chamada
    abaixo, que de outro modo aceitaria qualquer nome de parâmetro errado.
    """

    def transcribe(
        self,
        audio: NDArray[np.float32],
        /,
        *,
        language: str,
        beam_size: int,
        vad_filter: bool,
    ) -> tuple[Iterable[_Segment], _Info]: ...


class FasterWhisperSpeechToText:
    """Implementa ``SpeechToText`` sobre um ``WhisperModel`` já construído.

    Recebe o motor pronto em vez de construí-lo: carregar o modelo leva ~0,4 s
    e ele fica **residente** no worker (ADR-0025), então quem decide o momento
    da carga é a composition root, não o adapter. É também o que torna este
    adapter testável sem baixar 500 MB de pesos.
    """

    def __init__(self, engine: _Engine) -> None:
        self._engine = engine

    async def transcribe(self, audio: AudioInput) -> Transcript:
        """Transcreve sem travar o event loop.

        ``run_in_executor`` joga a função síncrona numa thread do pool — é o
        paralelo de ``Task.Run``, com uma diferença que muda o resultado: em
        .NET o pool paraleliza de verdade; em Python o GIL serializa bytecode,
        e o ganho só existe porque o CTranslate2 **solta o GIL** enquanto roda
        código nativo. Sem isso, o worker inteiro congelaria por 1,2 s a cada
        turno, e nenhuma outra corrotina avançaria.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio)

    def _transcribe_sync(self, audio: AudioInput) -> Transcript:
        samples = decode(audio)
        segments, info = self._engine.transcribe(
            samples,
            language=LANGUAGE,
            beam_size=BEAM_SIZE,
            vad_filter=VAD_FILTER,
        )
        # ARMADILHA, e é por isso que esta linha está DENTRO do executor:
        # `segments` é um *generator*, não uma lista. A chamada acima devolve
        # em microssegundos sem transcrever nada; o trabalho de CPU só acontece
        # quando alguém consome o iterador. Consumi-lo fora daqui (na corrotina)
        # jogaria 1,2 s de CPU de volta no event loop — exatamente o que o
        # `run_in_executor` existe para evitar.
        #
        # O parente mais próximo em C# é `IEnumerable` com `yield return`. A
        # diferença que importa não é a preguiça em si: é ONDE o trabalho roda.
        text = " ".join(segment.text.strip() for segment in segments)
        return Transcript(
            text=text.strip(),
            language=info.language,
            duration_seconds=duration_seconds(samples),
        )


def load_faster_whisper(model_size: str) -> FasterWhisperSpeechToText:
    """Carrega os pesos e devolve o adapter pronto — a operação cara.

    Separada do construtor porque é ela que baixa o modelo na primeira execução
    (36-99 s medidos, uma vez) e que o CARD-009 vai chamar no startup do worker
    para manter o modelo residente.
    """
    from faster_whisper import WhisperModel

    engine: _Engine = WhisperModel(model_size, device=DEVICE, compute_type=COMPUTE_TYPE)
    return FasterWhisperSpeechToText(engine)
