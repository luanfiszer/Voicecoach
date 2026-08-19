"""Utilidades compartilhadas pelos benchmarks.

Elas existem para que o *protocolo* de medição seja o mesmo em todos os
scripts — percentil calculado igual, aquecimento descartado igual, caminhos
resolvidos igual. Protocolo que varia entre scripts produz números que não se
comparam.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from time import perf_counter
from typing import Any

# Os insumos e resultados ficam ao lado dos scripts. Nada de caminho absoluto:
# benchmark que só roda na máquina de quem o escreveu não é instrumento.
BENCH_DIR = Path(__file__).resolve().parent
INPUT_DIR = BENCH_DIR / "inputs"
RESULT_DIR = BENCH_DIR / "results"

SAMPLE_RATE = 16_000


def percentil(valores: Sequence[float], p: int) -> float:
    """Percentil por posição, sem interpolação.

    Com n pequeno (5 execuções) interpolar dá falsa precisão: o p95 de cinco
    amostras é o maior valor, e é honesto dizer isso em vez de inventar um
    número entre dois pontos.
    """
    ordenados = sorted(valores)
    indice = min(len(ordenados) - 1, round((p / 100) * (len(ordenados) - 1)))
    return round(ordenados[indice], 3)


def cronometra(fn: Callable[[], Any], repeticoes: int) -> tuple[list[float], Any]:
    """Roda `fn` uma vez a mais que o pedido e DESCARTA a primeira.

    A primeira execução carrega caches, aloca buffers e aquece o modelo — ela
    não é latência de turno. Descartá-la é parte do protocolo, não um detalhe.
    """
    tempos: list[float] = []
    resultado: Any = None
    for i in range(repeticoes + 1):
        inicio = perf_counter()
        resultado = fn()
        decorrido = perf_counter() - inicio
        if i:
            tempos.append(decorrido)
    return tempos, resultado


def resume(tempos: list[float], duracao_audio: float | None = None) -> dict[str, float]:
    """p50, p95 e — quando o insumo é áudio — o fator de tempo real."""
    p50 = percentil(tempos, 50)
    saida = {
        "p50_s": p50,
        "p95_s": percentil(tempos, 95),
        "min_s": round(min(tempos), 3),
        "max_s": round(max(tempos), 3),
        "n": float(len(tempos)),
    }
    if duracao_audio:
        saida["rtf"] = round(p50 / duracao_audio, 3)
    return saida


def grava(nome: str, dados: object) -> Path:
    RESULT_DIR.mkdir(exist_ok=True)
    destino = RESULT_DIR / f"{nome}.json"
    destino.write_text(
        json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return destino
