"""Validação do áudio que chega no POST — content type, bytes e duração.

**Por que a borda decodifica o áudio.** A entidade ``Turn`` exige
``audio_duration > 0`` desde o instante zero (``__post_init__``), e a duração é
insumo da quota em minutos falados (CARD-015). Havia duas formas de obtê-la:

1. **o cliente manda num campo do formulário** — barato, e mentiroso por
   construção. Um app com bug (ou alguém com ``curl``) declara 1 s para uma fala
   de 3 minutos, e a quota do CARD-015 passa a medir uma ficção;
2. **o servidor mede** — custa uma decodificação (6 ms em AAC, 24 ms em Opus,
   medidos em `medicao-latencia.md` §3.5) e entrega de brinde a validação
   "isto é mesmo áudio", porque um arquivo corrompido não decodifica.

Escolhida a 2. O custo é conhecido e o benefício é dobrado.

**Reusa o ``decode`` do STT de propósito.** É a única implementação de
decodificação do projeto (``adapters/stt/audio.py``), e ela não depende do
binário ``ffmpeg`` no PATH — é PyAV, que já é dependência base. Uma segunda
implementação aqui poderia aceitar um arquivo que o worker depois recusaria, e
o aluno descobriria isso 1,6 s depois em vez de na hora do upload.

**E ela roda em executor.** ``decode`` é síncrono e CPU-bound; chamado direto de
uma corrotina, ele congela o event loop da API inteira enquanto dura — o mesmo
modo de falha que o ADR-0034 mediu no ``boto3`` (122 ms sem nenhuma outra
corrotina rodando). Numa API que atende N alunos, isso é latência que aparece em
todo mundo por causa de um upload.
"""

from __future__ import annotations

import asyncio
import functools
from datetime import timedelta

from fastapi import status

from voicecoach.adapters.stt.audio import decode, duration_seconds
from voicecoach.api.errors import ProblemError
from voicecoach.api.schemas.problem import BASE, TYPE_VALIDATION
from voicecoach.application.ports.speech_to_text import AudioInput

TYPE_UNSUPPORTED_MEDIA = f"{BASE}:unsupported-audio-type"
TYPE_AUDIO_TOO_LONG = f"{BASE}:audio-too-long"

# Content type → extensão da chave de storage (ADR-0024). A extensão sai daqui e
# **não** dos bytes: o decodificador identifica o contêiner sozinho (ADR-0029),
# mas a CHAVE precisa de um nome antes de o objeto existir. Um content type
# mentiroso produz uma chave com extensão errada — e não um erro —, o que é
# aceitável porque a chave é identificador, não formato declarado ao player;
# quem serve o objeto é o `content_type` gravado junto dele.
EXTENSAO_POR_TIPO = {
    "audio/aac": "aac",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/mpeg": "mp3",
    "audio/ogg": "ogg",
    "audio/opus": "opus",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/webm": "webm",
}


def extensao_para(content_type: str | None) -> str:
    """A extensão da chave, ou 415 se o tipo não é um dos aceitos.

    415 e não 422: o corpo pode estar perfeito — o que a API recusa é o
    **formato**, que é exatamente a semântica de *Unsupported Media Type*.
    """
    tipo = (content_type or "").split(";")[0].strip().lower()
    extensao = EXTENSAO_POR_TIPO.get(tipo)
    if extensao is None:
        raise ProblemError(
            type_=TYPE_UNSUPPORTED_MEDIA,
            title="Formato de áudio não suportado",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Content-Type {tipo!r} não é aceito neste endpoint.",
            accepted=sorted(EXTENSAO_POR_TIPO),
        )
    return extensao


async def medir(audio: bytes, *, maximo: timedelta) -> timedelta:
    """Decodifica para medir — e recusa o que não é áudio ou é longo demais.

    ``run_in_executor`` empurra a decodificação para uma thread do pool padrão,
    devolvendo o controle ao event loop enquanto ela corre. ``functools.partial``
    é o jeito de passar argumentos, já que ``run_in_executor`` não os aceita —
    é o ``Task.Run(() => ...)`` do C#, com a diferença de que aqui a thread vem
    de um pool que também serve a todo o resto do processo.
    """
    if not audio:
        raise _invalido("o arquivo enviado está vazio.")

    loop = asyncio.get_running_loop()
    try:
        amostras = await loop.run_in_executor(
            None, functools.partial(decode, AudioInput(data=audio))
        )
    except Exception as exc:
        raise _invalido(f"não foi possível decodificar o áudio: {exc}") from exc

    duracao = timedelta(seconds=duration_seconds(amostras))
    if duracao <= timedelta(0):
        raise _invalido("o áudio enviado tem duração zero.")
    if duracao > maximo:
        raise ProblemError(
            type_=TYPE_AUDIO_TOO_LONG,
            title="Áudio longo demais",
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"a fala tem {duracao.total_seconds():.1f} s e o limite é "
                f"{maximo.total_seconds():.0f} s."
            ),
            max_duration_seconds=maximo.total_seconds(),
        )
    return duracao


def _invalido(detalhe: str) -> ProblemError:
    return ProblemError(
        type_=TYPE_VALIDATION,
        title="Áudio inválido",
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=detalhe,
    )
