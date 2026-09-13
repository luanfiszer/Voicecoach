"""Remedição do CARD-039/ADR-0055: modelo multilíngue e o custo da detecção.

A investigação de 2026-09-09 que motivou o ADR-0055 mediu isto com scripts
ad-hoc, não commitados — a tabela do ADR existe, mas não como instrumento
reexecutável. Este script fecha essa lacuna: mesmo protocolo de
`stt_mlx.py`/`stt_faster_whisper.py`, comparando três configurações no motor
`mlx` (o `auto` desta máquina):

1. `small.en` com `language="en"` fixo — o comportamento ANTIGO;
2. `small` multilíngue com `language="en"` fixo — o recuo barato do ADR-0055;
3. `small` multilíngue com `language=None` — o comportamento NOVO (default).

O insumo `pt-br-curto.wav` é fala sintética em português (`say -v Luciana`,
mesma voz da investigação original) — mistura de idioma no meio de uma
conversa em inglês, o caso que motivou o card.
"""

from __future__ import annotations

from typing import Any

import mlx_whisper
import soundfile as sf
from _common import INPUT_DIR, SAMPLE_RATE, cronometra, grava, resume

REPETICOES = 5

CONFIGURACOES = (
    ("small.en (ANTIGO)", "mlx-community/whisper-small.en-mlx", "en"),
    ("small multi + en fixo (recuo)", "mlx-community/whisper-small-mlx", "en"),
    ("small multi + deteccao (NOVO)", "mlx-community/whisper-small-mlx", None),
)

INSUMOS = ("pt-br-curto", "amazing-project", "curto", "longo")


def mede(repo: str, language: str | None, audio_nome: str, n: int) -> dict[str, Any]:
    audio, _ = sf.read(INPUT_DIR / f"{audio_nome}.wav", dtype="float32")
    duracao = len(audio) / SAMPLE_RATE

    def uma_vez() -> dict[str, Any]:
        saida = mlx_whisper.transcribe(
            audio, path_or_hf_repo=repo, language=language, verbose=None
        )
        return {"text": str(saida["text"]).strip(), "language": saida["language"]}

    tempos, saida = cronometra(uma_vez, n)
    return {
        "repo": repo,
        "language_configurado": language,
        "audio": audio_nome,
        **resume(tempos, duracao),
        "texto": saida["text"],
        "language_detectado": saida["language"],
    }


def main() -> None:
    resultados = []
    for nome_config, repo, language in CONFIGURACOES:
        for audio_nome in INSUMOS:
            r = mede(repo, language, audio_nome, REPETICOES)
            resultados.append({"config": nome_config, **r})
            print(
                f"{nome_config:32s} {audio_nome:16s} "
                f"p50={r['p50_s']:6.2f}s lang={r['language_detectado']:3s} "
                f"texto={r['texto'][:60]!r}",
                flush=True,
            )
    print(f"\nresultados em {grava('stt_deteccao_idioma', resultados)}")


if __name__ == "__main__":
    main()
