"""O pipeline com os modelos REAIS — a primeira medição de COMPOSIÇÃO do projeto.

**Marcado `slow`, e o custo é de dois tipos ao mesmo tempo** — é a primeira vez
que isso acontece no repositório, e por isso está dito aqui:

- **dinheiro**, como no CARD-007: o professor real é uma chamada paga à
  Anthropic (~US$ 0,02 por execução no `claude-haiku-4-5`);
- **CPU e download**, como no CARD-006/008: STT e TTS locais carregam pesos
  (36-99 s na primeira execução de uma máquina limpa) e são gratuitos
  (ADR-0010/0011/0032).

Quem roda `-m slow` precisa saber qual dos dois está aceitando.

**Por que este teste existe além dos 21 com fakes.** Todos os números do projeto
até aqui são de **componente isolado** — 0,59 s de STT, 1,86 s de LLM, 0,09 s da
primeira frase no TTS. A §1 da medição avisa há semanas que o custo de
*composição* (contenção de CPU entre STT e TTS, GIL, cópia de áudio entre
etapas) é desconhecido. Este é o teste que o mede, e o número vai para
`docs/medicao-latencia.md`.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from voicecoach.adapters.llm.factory import create_teacher_llm
from voicecoach.adapters.stt.factory import create_speech_to_text, is_apple_silicon
from voicecoach.adapters.tts.encoding import AacAudioEncoder
from voicecoach.adapters.tts.factory import create_text_to_speech
from voicecoach.application.use_cases.process_turn import (
    ProcessTurn,
    ProcessTurnHandler,
)
from voicecoach.config import Settings, SttProvider
from voicecoach.domain.session import Session
from voicecoach.domain.turn import Turn, TurnStatus

if TYPE_CHECKING:
    from voicecoach.application.ports.speech_to_text import SpeechToText

from fakes_pipeline import (
    FakeMediaStorage,
    FakeSessionRepository,
    FakeTurnEvents,
    FakeTurnRepository,
    FakeUnitOfWork,
)

pytestmark = pytest.mark.slow

FIXTURE = Path(__file__).parent.parent / "fixtures" / "stt" / "amazing-project.wav"
VOICES_DIR = Path(__file__).resolve().parents[2] / "voices"
VOZ = "en_US-lessac-medium"

sem_voz = pytest.mark.skipif(
    not (VOICES_DIR / f"{VOZ}.onnx").exists(),
    reason=f"voz {VOZ} não baixada em {VOICES_DIR}",
)
sem_chave = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY ausente: o teste ponta a ponta gasta dinheiro real",
)


def _settings(provider: SttProvider) -> Settings:
    return Settings(  # type: ignore[call-arg]
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "test-key"),
        stt_provider=provider,
        tts_voices_dir=VOICES_DIR,
        _env_file=None,
    )


@pytest.mark.skipif(not is_apple_silicon(), reason="mlx só existe em Apple Silicon")
def test_carga_do_mlx_whisper_medida_em_separado() -> None:
    """A dívida do ADR-0025, item 7 — nunca cronometrada até aqui.

    Ela deixou de ser a parcela pequena: com o Piper baixando o TTS de 5,63 s
    para 0,43 s (ADR-0032), a carga do STT passou a ser a **maior** parte da
    subida do worker. O número medido vai para `docs/medicao-latencia.md`.

    Sem asserção de limiar: um teste que reprovasse acima de X seria flaky numa
    máquina ocupada, e a pergunta aqui é "quanto custa?", não "está rápido?".
    """
    inicio = time.perf_counter()
    create_speech_to_text(_settings(SttProvider.MLX))
    decorrido = time.perf_counter() - inicio

    print(f"\n[medição] carga do mlx-whisper: {decorrido:.2f} s")
    assert decorrido > 0


@sem_voz
@sem_chave
async def test_pipeline_real_entrega_o_primeiro_trecho_antes_de_replied_at() -> None:
    """O turn inteiro com STT, professor e TTS reais. **Gasta dinheiro.**

    A asserção é a mesma dos testes com fake — a cascata existe — mas aqui ela
    passa por três bibliotecas, dois modelos residentes e uma chamada de rede.
    O que este teste acrescenta é o **tempo**, impresso para ir ao documento de
    medição.
    """
    settings = _settings(SttProvider.AUTO)

    carga = time.perf_counter()
    stt: SpeechToText = create_speech_to_text(settings)
    tts = create_text_to_speech(settings)
    teacher = create_teacher_llm(settings)
    tempo_de_carga = time.perf_counter() - carga

    student_id, session_id = uuid4(), uuid4()
    turn = Turn(
        id=uuid4(),
        session_id=session_id,
        input_audio_ref=f"{student_id}/{session_id}/input.wav",
        audio_duration=timedelta(seconds=3),
        created_at=datetime.now(UTC),
    )
    storage = FakeMediaStorage()
    storage.objetos[turn.input_audio_ref] = (FIXTURE.read_bytes(), "audio/wav")
    eventos = FakeTurnEvents()

    handler = ProcessTurnHandler(
        turns=FakeTurnRepository(turn),
        sessions=FakeSessionRepository(
            Session(id=session_id, student_id=student_id, started_at=datetime.now(UTC))
        ),
        unit_of_work=FakeUnitOfWork(),
        storage=storage,
        speech_to_text=stt,
        teacher=teacher,
        text_to_speech=tts,
        encoder=AacAudioEncoder(),
        events=eventos,
        clock=lambda: datetime.now(UTC),
        history_turns=6,
    )

    inicio = time.perf_counter()
    await handler.handle(ProcessTurn(turn.id, final_attempt=True))
    total = time.perf_counter() - inicio

    assert turn.status is TurnStatus.COMPLETED, turn.failure_reason
    assert turn.audio_chunks, "a cascata não produziu trecho nenhum"
    assert turn.replied_at is not None
    assert turn.audio_chunks[0].created_at < turn.replied_at

    primeiro = turn.audio_chunks[0].created_at - turn.created_at
    print(
        f"\n[medição] carga dos modelos: {tempo_de_carga:.2f} s"
        f"\n[medição] turn completo: {total:.2f} s"
        f"\n[medição] trechos: {len(turn.audio_chunks)}"
        f"\n[medição] até o 1º trecho gravado: {primeiro.total_seconds():.2f} s"
    )
