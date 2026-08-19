"""Resolução do adapter de STT no boot (ADR-0027, itens 2 e 3).

Estes testes NÃO carregam modelo: exercitam `resolve_stt_provider`, que é a
parte que decide. A construção de verdade (que baixa pesos) fica no teste
marcado `slow`.

A plataforma é forjada com `monkeypatch` sobre `sys.platform` e
`platform.machine` — é o que permite testar o caminho x86 numa máquina ARM, e
sem isso o critério "falha no boot em plataforma incompatível" só seria
verificável comprando outro computador.
"""

from __future__ import annotations

import logging
import platform
import sys
from typing import TYPE_CHECKING

import pytest

from voicecoach.adapters.stt import faster_whisper_adapter, mlx_whisper_adapter
from voicecoach.adapters.stt.factory import (
    SttProviderUnavailableError,
    create_speech_to_text,
    is_apple_silicon,
    resolve_stt_provider,
)
from voicecoach.config import Settings, SttProvider

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def plataforma(monkeypatch: pytest.MonkeyPatch) -> Callable[[str, str], None]:
    """Forja a plataforma vista pelo módulo da fábrica."""

    def _forja(so: str, maquina: str) -> None:
        monkeypatch.setattr(sys, "platform", so)
        monkeypatch.setattr(platform, "machine", lambda: maquina)

    return _forja


def test_auto_em_apple_silicon_escolhe_mlx(
    plataforma: Callable[[str, str], None],
) -> None:
    plataforma("darwin", "arm64")

    assert resolve_stt_provider(SttProvider.AUTO) is SttProvider.MLX


def test_auto_fora_de_apple_silicon_escolhe_faster_whisper(
    plataforma: Callable[[str, str], None],
) -> None:
    plataforma("linux", "x86_64")

    assert resolve_stt_provider(SttProvider.AUTO) is SttProvider.FASTER_WHISPER


def test_auto_em_mac_intel_escolhe_faster_whisper(
    plataforma: Callable[[str, str], None],
) -> None:
    # macOS não basta: o que decide é o processador. Um Mac Intel cai no
    # caminho de CPU como qualquer x86.
    plataforma("darwin", "x86_64")

    assert resolve_stt_provider(SttProvider.AUTO) is SttProvider.FASTER_WHISPER


def test_auto_e_logado_na_subida(
    plataforma: Callable[[str, str], None], caplog: pytest.LogCaptureFixture
) -> None:
    # Critério de aceite do card: latência que não é explicável depois é
    # latência que não se otimiza.
    plataforma("linux", "x86_64")

    with caplog.at_level(logging.INFO, logger="voicecoach.adapters.stt.factory"):
        resolve_stt_provider(SttProvider.AUTO)

    assert "faster_whisper" in caplog.text
    assert "linux" in caplog.text
    assert "x86_64" in caplog.text


def test_mlx_explicito_em_x86_falha_no_boot_nomeando_a_plataforma(
    plataforma: Callable[[str, str], None],
) -> None:
    # O item 3 do ADR-0027: NUNCA cair para o outro adapter. O fallback
    # silencioso esconderia uma regressão de 2x atrás de um log.
    plataforma("linux", "x86_64")

    with pytest.raises(SttProviderUnavailableError) as erro:
        resolve_stt_provider(SttProvider.MLX)

    mensagem = str(erro.value)
    assert "linux" in mensagem
    assert "x86_64" in mensagem
    assert "faster_whisper" in mensagem  # diz o que fazer, não só o que quebrou


def test_mlx_explicito_em_apple_silicon_passa(
    plataforma: Callable[[str, str], None],
) -> None:
    plataforma("darwin", "arm64")

    assert resolve_stt_provider(SttProvider.MLX) is SttProvider.MLX


def test_faster_whisper_explicito_e_respeitado_mesmo_em_apple_silicon(
    plataforma: Callable[[str, str], None],
) -> None:
    # Escolha explícita não é "sugestão": serve para comparar os dois adapters
    # na mesma máquina.
    plataforma("darwin", "arm64")

    assert resolve_stt_provider(SttProvider.FASTER_WHISPER) is (
        SttProvider.FASTER_WHISPER
    )


def test_openai_ainda_nao_tem_adapter() -> None:
    with pytest.raises(NotImplementedError, match="ADR-0010"):
        resolve_stt_provider(SttProvider.OPENAI)


def test_is_apple_silicon_reflete_a_maquina_real() -> None:
    esperado = sys.platform == "darwin" and platform.machine() == "arm64"

    assert is_apple_silicon() is esperado


# --- create_speech_to_text: a composição, sem pagar a carga do modelo --------
#
# Os loaders são importados DENTRO de `create_speech_to_text`, então trocá-los
# no módulo de origem funciona: o import só acontece na chamada. Se o import
# estivesse no topo do arquivo, o nome já estaria resolvido e este monkeypatch
# não teria efeito — é a mesma mecânica que faz o import tardio do `mlx`
# funcionar.


def _settings(provider: SttProvider) -> Settings:
    return Settings(  # type: ignore[call-arg]  # o pydantic preenche do ambiente
        anthropic_api_key="test-key", stt_provider=provider, _env_file=None
    )


def test_create_usa_o_modelo_do_faster_whisper(
    plataforma: Callable[[str, str], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    recebido: list[str] = []
    monkeypatch.setattr(
        faster_whisper_adapter,
        "load_faster_whisper",
        lambda modelo: recebido.append(modelo),
    )
    plataforma("linux", "x86_64")

    create_speech_to_text(_settings(SttProvider.AUTO))

    # Cada adapter tem a SUA string de modelo (nome CTranslate2 aqui,
    # repositório do Hugging Face no mlx): trocá-las é um erro silencioso que
    # só apareceria como "modelo não encontrado" na primeira transcrição.
    assert recebido == ["small.en"]


def test_create_usa_o_repositorio_do_mlx(
    plataforma: Callable[[str, str], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    recebido: list[str] = []
    monkeypatch.setattr(
        mlx_whisper_adapter,
        "load_mlx_whisper",
        lambda repo: recebido.append(repo),
    )
    plataforma("darwin", "arm64")

    create_speech_to_text(_settings(SttProvider.AUTO))

    assert recebido == ["mlx-community/whisper-small.en-mlx"]


def test_create_propaga_a_falha_de_boot_sem_carregar_nada(
    plataforma: Callable[[str, str], None],
) -> None:
    plataforma("linux", "x86_64")

    with pytest.raises(SttProviderUnavailableError):
        create_speech_to_text(_settings(SttProvider.MLX))
