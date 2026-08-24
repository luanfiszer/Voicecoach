"""Dublês e fixtures da borda HTTP.

**Por que não é um `conftest.py` em `tests/api/`.** Dois arquivos com esse nome
(um em `tests/`, outro em `tests/api/`) colidem no `mypy`: sem pacotes, os dois
viram o módulo `conftest` e a checagem para com *"Duplicate module named
conftest"*. As saídas seriam `explicit_package_bases` (que muda como o `mypy`
resolve `voicecoach` e quebrou 288 outras checagens ao ser tentada) ou excluir um
dos dois da checagem — ou seja, abrir mão de tipar justamente os dublês, que é
onde o `Protocol` é verificado.

As fixtures ficam no `conftest.py` da raiz de `tests/`, que é o único; os dublês
e utilitários ficam aqui.

E o arquivo mora em `tests/` e não em `tests/api/` pela mesma razão que o
`fakes_pipeline.py`: o pytest insere no `sys.path` o diretório de cada
`conftest.py`, então `tests/` é alcançável de qualquer subpasta — e o
`conftest.py` da raiz, que é quem importa daqui, é carregado **antes** de
`tests/api/` existir no caminho.
"""

from __future__ import annotations

import io
import struct
import wave
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes_pipeline import (
    FakeMediaStorage,
    FakeSessionRepository,
    FakeTurnEvents,
    FakeTurnRepository,
    FakeUnitOfWork,
)
from voicecoach.domain.session import Session
from voicecoach.domain.turn import Turn

ALUNO = UUID("00000000-0000-0000-0000-000000000001")
TURN_ID = UUID("22222222-2222-2222-2222-222222222222")
AGORA = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def wav_de(segundos: float, *, taxa: int = 16_000) -> bytes:
    """Um WAV PCM16 mono válido, feito só com a stdlib.

    **Áudio de verdade, e não `b"fake"`**, porque a rota decodifica o upload para
    medir a duração (ver `api/audio_intake.py`). Um teste com bytes falsos
    exercitaria só o caminho de erro — e o caminho feliz nunca seria tocado.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as arquivo:
        arquivo.setnchannels(1)
        arquivo.setsampwidth(2)
        arquivo.setframerate(taxa)
        arquivo.writeframes(struct.pack("<h", 0) * int(segundos * taxa))
    return buffer.getvalue()


class Fakes:
    """O saco de dublês que cada teste inspeciona depois de chamar a rota."""

    def __init__(self) -> None:
        self.sessao = Session(id=uuid4(), student_id=ALUNO, started_at=AGORA)
        self.sessions = FakeSessionRepository(self.sessao)
        self.turns = FakeTurnRepository()
        self.storage = FakeMediaStorage()
        self.canal = FakeTurnEvents()
        self.uow = FakeUnitOfWork()
        self.enfileirados: list[UUID] = []

    async def enqueue(self, turn_id: UUID) -> None:
        self.enfileirados.append(turn_id)


def turn_pronto(
    fakes: Fakes, *, trechos: int = 0, transcript: str | None = None
) -> Turn:
    """Um Turn já em ``processing``, gravado no repositório fake."""
    turn = Turn(
        id=TURN_ID,
        session_id=fakes.sessao.id,
        input_audio_ref="in.wav",
        audio_duration=timedelta(seconds=2),
        created_at=AGORA,
    )
    turn.start_processing(AGORA)
    if transcript is not None:
        turn.attach_transcript(transcript, AGORA)
    for i in range(trechos):
        turn.append_audio_chunk(
            index=i,
            storage_key=f"{ALUNO}/{turn.session_id}/{turn.id}/reply/{i:03d}.aac",
            duration_seconds=1.5,
            text=f"frase {i}",
            now=AGORA,
        )
    fakes.turns.turns[turn.id] = turn
    return turn
