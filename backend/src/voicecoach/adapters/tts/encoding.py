"""Compressão do PCM antes de gravar no storage (ADR-0024).

**Por que isto existe.** A porta de TTS trafega PCM cru porque é o que
concatena barato (o `reply/full` é um `b"".join`). Mas PCM é grande: 17 s de
resposta são **816 KB** contra ~136 KB em AAC 64 kbps, e quem baixa é o celular
do aluno em rede móvel. A compressão acontece no último momento possível — ao
gravar —, e não antes, para que a concatenação continue barata.

**Por que PyAV e não uma dependência nova.** O PyAV já está no projeto: veio com
o `faster-whisper` e é quem decodifica o áudio do aluno (ADR-0029). Ele traz os
encoders de AAC, Opus e MP3 embutidos — verificado, não suposto. Usar outra
biblioteca seria pagar por algo que já está instalado.

**Por que AAC.** É o mesmo formato que o app grava (ADR-0029, item 5), toca
nativamente nos dois SOs e no navegador, e não exige licença como o MP3. Opus
comprime melhor, mas o Safari só o toca dentro de contêiner específico — e o
cliente aqui é um `<audio>` de app, não um player que a gente controla.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import av

if TYPE_CHECKING:
    from voicecoach.application.ports.text_to_speech import SynthesizedAudio

# 64 kbps mono é o ponto medido no ADR-0029 para a voz: 151 KB para 20 s, com
# decodificação de 6 ms. Voz não precisa de mais — o conteúdo é banda estreita.
BITRATE = 64_000
CONTENT_TYPE = "audio/aac"
EXTENSION = "aac"


def to_aac(audio: SynthesizedAudio) -> bytes:
    """Comprime PCM16 mono em AAC dentro de um contêiner ADTS.

    ADTS (`format="adts"`) e não MP4: é um fluxo AAC com cabeçalho por quadro,
    que não precisa de índice no fim do arquivo. Um MP4 exigiria reposicionar o
    ponteiro para escrever o `moov` — impossível num buffer que se quer entregar
    em streaming, e é o tipo de detalhe que só aparece quando o arquivo já está
    no bucket e não toca.
    """
    saida = io.BytesIO()
    with av.open(saida, mode="w", format="adts") as container:
        stream = container.add_stream("aac", rate=audio.sample_rate)
        stream.bit_rate = BITRATE

        frame = av.AudioFrame(format="s16", layout="mono", samples=len(audio.pcm) // 2)
        frame.sample_rate = audio.sample_rate
        frame.planes[0].update(audio.pcm)

        for packet in stream.encode(frame):
            container.mux(packet)
        # `encode(None)` esvazia o buffer interno do encoder. Sem isso, o fim do
        # áudio some — e some em silêncio, que é o pior modo de falha possível.
        for packet in stream.encode(None):
            container.mux(packet)

    return saida.getvalue()
