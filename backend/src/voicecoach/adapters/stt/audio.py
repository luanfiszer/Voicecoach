"""Decodificação do áudio recebido — de bytes codificados para PCM.

Os dois adapters precisam da mesma coisa: um vetor de amostras float32 a
16 kHz, mono. Esta é a única implementação disso no projeto, e ela existe como
módulo separado para que trocar de adapter não troque de decodificador — se
cada um decodificasse do seu jeito, comparar a latência dos dois compararia
duas coisas diferentes.
"""

from __future__ import annotations

import io

import numpy as np
from faster_whisper.audio import decode_audio
from numpy.typing import NDArray

from voicecoach.application.ports.speech_to_text import AudioInput

# 16 kHz mono é o que o Whisper consome em qualquer implementação: o modelo foi
# treinado nessa taxa e o próprio pré-processamento reamostra para ela. Mandar
# 44,1 kHz não melhora a transcrição, só gasta reamostragem.
SAMPLE_RATE = 16_000


def decode(audio: AudioInput) -> NDArray[np.float32]:
    """Converte os bytes recebidos em amostras, sem tocar o disco.

    Usa o ``decode_audio`` do ``faster-whisper``, que é um wrapper fino sobre o
    **PyAV** (binding da libav*). Duas razões para reusá-lo em vez de escrever
    o laço de reamostragem à mão:

    1. ele já resolve container, canal e taxa numa chamada, e é código que a
       biblioteca mantém e testa;
    2. ele **não** depende do binário ``ffmpeg`` no PATH — que é a armadilha
       que derruba o caminho de arquivo do ``mlx_whisper`` (ADR-0029).

    O ``faster-whisper`` é dependência base nas duas plataformas, então usá-lo
    aqui não cria dependência nova para o caminho ``mlx``.

    ``io.BytesIO`` embrulha os bytes num objeto que se comporta como arquivo —
    o equivalente de passar um ``MemoryStream`` onde se esperava um
    ``FileStream``. É o que evita gravar um temporário só para reler.

    Custo medido: 6 ms num turno de 20 s em AAC; 24 ms se for Opus
    (``medicao-latencia.md`` §3.5).
    """
    samples: NDArray[np.float32] = decode_audio(
        io.BytesIO(audio.data), sampling_rate=SAMPLE_RATE
    )
    return samples


def duration_seconds(samples: NDArray[np.float32]) -> float:
    """Duração real do áudio, derivada das amostras.

    Deliberadamente calculada aqui, e não lida do que cada biblioteca reporta:
    o ``faster-whisper`` devolve um ``info.duration`` e o ``mlx-whisper`` não
    devolve nada equivalente. Derivando das amostras, ``Transcript
    .duration_seconds`` significa exatamente a mesma coisa nos dois adapters —
    o que importa, porque esse número vai virar cota do aluno.
    """
    return len(samples) / SAMPLE_RATE
