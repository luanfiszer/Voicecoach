"""O adapter contra a API de verdade. **GASTA DINHEIRO.**

Marcado `slow` e deselecionado por padrão (`addopts = -m 'not slow'`). Diferente
do `slow` do CARD-006, que só custava tempo de CPU: aqui cada execução consome
tokens pagos, dentro do teto do ADR-0010. Rodar à mão:

    uv run pytest -m slow tests/adapters/test_teacher_llm_integration.py

É este teste que exercita a costura que o `# type: ignore[arg-type]` da fábrica
suprime — o `AsyncAnthropic` real satisfazendo, ou não, o que o adapter consome.
"""

from __future__ import annotations

import os

import pytest

from voicecoach.adapters.llm.factory import create_teacher_llm, load_teacher_prompt
from voicecoach.application.ports.teacher_llm import (
    FeedbackReady,
    Speaker,
    SpokenSentence,
    TeacherEvent,
    Utterance,
)
from voicecoach.config import Settings

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="sem ANTHROPIC_API_KEY: o teste chamaria a API paga",
    ),
]

HISTORICO = [
    Utterance(speaker=Speaker.STUDENT, text="I work in a hospital as a nurse"),
    Utterance(
        speaker=Speaker.TEACHER,
        text="That sounds meaningful. What do you like most about it?",
    ),
    Utterance(
        speaker=Speaker.STUDENT, text="I think my job is very stressful sometimes"
    ),
]


@pytest.fixture
def settings() -> Settings:
    return Settings(anthropic_api_key=os.environ["ANTHROPIC_API_KEY"])


async def test_professor_real_responde_em_cascata(settings: Settings) -> None:
    professor = create_teacher_llm(settings)

    eventos: list[TeacherEvent] = [
        e async for e in professor.respond_streaming(HISTORICO)
    ]

    falas = [e for e in eventos if isinstance(e, SpokenSentence)]
    assert falas, "nenhuma sentença foi emitida"
    assert isinstance(eventos[-1], FeedbackReady)

    feedback = eventos[-1].feedback
    assert feedback.spoken_reply.strip()
    # A fala emitida em cascata reconstrói exatamente o que foi validado no fim.
    assert " ".join(f.text for f in falas) == feedback.spoken_reply.strip()
    # Sem prompt caching (ADR-0021): as duas contagens são 0 e é isso que se
    # espera hoje. No dia em que deixarem de ser, o regime mudou.
    assert eventos[-1].usage.cache_read_input_tokens == 0
    assert eventos[-1].usage.input_tokens > 0


async def test_prompt_real_e_o_que_vai_para_a_api(settings: Settings) -> None:
    """O prompt do arquivo é o mesmo que a fábrica injeta — sem cópia paralela."""
    assert load_teacher_prompt().startswith("You are a friendly English teacher")
    assert settings.teacher_model == "claude-haiku-4-5"
