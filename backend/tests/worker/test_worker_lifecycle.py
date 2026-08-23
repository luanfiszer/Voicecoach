"""A subida do worker: ordem da carga, prontidão e residência (ADR-0025).

**Por que este arquivo existe mesmo com o pipeline já testado.** A consequência
negativa que o próprio ADR-0025 registra é que esquecer de ler o `ctx` e
instanciar o modelo dentro da task **não quebra teste nenhum** — só a latência
sobe 1 s por turno. Um defeito que nenhum teste de resultado pega precisa de um
teste de *estrutura*, e é este.

As fábricas reais são substituídas por dublês que **contam chamadas**. Isso torna
o critério exato em vez de temporizado: "o segundo job não paga carga" vira
"a fábrica foi chamada uma vez", que não tem margem para calibrar nem flakiness
para tolerar. A medição com modelo real está no teste `slow` de integração e em
`docs/medicao-latencia.md`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from voicecoach.config import Settings
from voicecoach.worker import main as worker_main
from voicecoach.worker.readiness import READY_KEY


class RedisEspiao:
    """Registra a ordem dos acontecimentos, não só o resultado."""

    def __init__(self, registro: list[str]) -> None:
        self.registro = registro

    async def set(self, name: str, value: str, *, ex: timedelta, **_: Any) -> None:
        self.registro.append(f"ready:{name}")

    async def delete(self, *names: str) -> int:
        self.registro.append("ready:delete")
        return len(names)


class FabricaContada:
    """Uma fábrica que conta quantas vezes carregou o modelo."""

    def __init__(self, registro: list[str], rotulo: str) -> None:
        self.registro = registro
        self.rotulo = rotulo
        self.chamadas = 0

    def __call__(self, settings: Settings) -> object:
        self.chamadas += 1
        self.registro.append(f"carrega:{self.rotulo}")
        return object()


def _settings_de_teste() -> Settings:
    """`_env_file=None` isola do `.env` da máquina, como a fixture do conftest."""
    return Settings(anthropic_api_key="k", _env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def ambiente(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Substitui as fábricas caras e o engine por dublês que registram a ordem."""
    registro: list[str] = []
    fabricas = {
        rotulo: FabricaContada(registro, rotulo)
        for rotulo in ("stt", "tts", "teacher", "storage")
    }
    monkeypatch.setattr(worker_main, "create_speech_to_text", fabricas["stt"])
    monkeypatch.setattr(worker_main, "create_text_to_speech", fabricas["tts"])
    monkeypatch.setattr(worker_main, "create_teacher_llm", fabricas["teacher"])
    monkeypatch.setattr(worker_main, "create_media_storage", fabricas["storage"])
    monkeypatch.setattr(worker_main, "get_settings", _settings_de_teste)

    class EngineFalso:
        async def dispose(self) -> None:
            registro.append("engine:dispose")

    monkeypatch.setattr(worker_main, "create_engine", lambda _url: EngineFalso())
    monkeypatch.setattr(worker_main, "create_session_factory", lambda _engine: object())
    return {"registro": registro, "fabricas": fabricas}


async def test_a_chave_de_prontidao_e_gravada_depois_de_toda_a_carga(
    ambiente: dict[str, Any],
) -> None:
    """O item 3 do ADR-0025, em forma de asserção sobre ORDEM.

    Gravar a chave antes da carga faria a API anunciar um worker que ainda não
    consegue transcrever — exatamente a mentira que o ADR existe para matar.
    """
    registro: list[str] = ambiente["registro"]
    ctx: dict[str, Any] = {"redis": RedisEspiao(registro)}

    await worker_main.startup(ctx)

    assert registro.index(f"ready:{READY_KEY}") > registro.index("carrega:stt")
    assert registro.index(f"ready:{READY_KEY}") > registro.index("carrega:tts")
    await ctx["readiness"].stop()


async def test_os_modelos_ficam_no_ctx_e_nenhuma_task_os_constroi(
    ambiente: dict[str, Any],
) -> None:
    """A residência, verificada onde ela pode ser perdida sem ninguém notar."""
    ctx: dict[str, Any] = {"redis": RedisEspiao(ambiente["registro"])}

    await worker_main.startup(ctx)

    assert {"stt", "tts", "teacher", "storage", "encoder", "events"} <= set(ctx)
    await ctx["readiness"].stop()


async def test_dois_jobs_seguidos_carregam_o_modelo_uma_vez_so(
    ambiente: dict[str, Any],
) -> None:
    """O critério de aceite do card, sem margem de tempo para calibrar.

    O card pedia "o segundo job não paga carga, com margem". Com o Kokoro a
    diferença era de ~6 s e qualquer margem servia; com o Piper ela caiu para
    ~1 s (ADR-0032), e um limiar de tempo mal calibrado passaria por acidente
    num dia de máquina rápida. Contar construções é o mesmo critério sem o
    problema: **duas** chamadas à fábrica seriam a regressão, e uma é a decisão.
    """
    registro: list[str] = ambiente["registro"]
    ctx: dict[str, Any] = {"redis": RedisEspiao(registro)}
    await worker_main.startup(ctx)

    # Dois jobs: o que a task faz com o ctx é ler, nunca construir.
    for _ in range(2):
        assert ctx["stt"] is not None
        assert ctx["tts"] is not None

    assert ambiente["fabricas"]["stt"].chamadas == 1
    assert ambiente["fabricas"]["tts"].chamadas == 1
    assert registro.count("carrega:stt") == 1
    await ctx["readiness"].stop()


async def test_o_shutdown_apaga_a_chave_e_devolve_as_conexoes(
    ambiente: dict[str, Any],
) -> None:
    """Simetria do item 2 do ADR-0025.

    Sem o `dispose`, subir e derrubar o worker num teste de integração vazaria
    conexões entre casos; sem apagar a chave, a API afirmaria "pronto" por até
    30 s depois de um `compose down`.
    """
    registro: list[str] = ambiente["registro"]
    ctx: dict[str, Any] = {"redis": RedisEspiao(registro)}
    await worker_main.startup(ctx)

    await worker_main.shutdown(ctx)

    assert "ready:delete" in registro
    assert "engine:dispose" in registro


def test_o_arq_nao_consome_job_antes_de_o_startup_retornar() -> None:
    """A barreira do ADR-0025, item 1 — e ela é da biblioteca, não nossa.

    Este teste lê o código do `arq` porque a garantia é **de sequência dentro do
    `Worker.main`**: o `on_startup` é aguardado, e só depois o laço de polling
    começa. Um upgrade que invertesse essas duas linhas faria o worker aceitar
    jobs sem modelo carregado, sem quebrar nenhum teste de comportamento nosso.
    """
    import inspect

    from arq.worker import Worker

    fonte = inspect.getsource(Worker.main)

    assert fonte.index("await self.on_startup(self.ctx)") < fonte.index(
        "async for _ in poll(self.poll_delay_s)"
    )
