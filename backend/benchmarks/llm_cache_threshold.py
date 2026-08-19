"""Determina empiricamente o prefixo mínimo cacheável, e o custo de errar.

Origem: o ADR-0020 assumiu ~1.024 tokens sem medir e decidiu implementar
prompt caching. Medido para `claude-haiku-4-5`, o limiar é **4.096** — que uma
conversa deste produto não alcança. O ADR-0021 substituiu aquela decisão.

Este script existe para que o número seja reexecutável: ele muda quando o
modelo muda, e a decisão de caching depende inteiramente dele.

CUSTA DINHEIRO. ~20 chamadas pequenas, na ordem de US$ 0,10.
Requer `ANTHROPIC_API_KEY` no ambiente.
"""

from __future__ import annotations

import os
from time import time
from typing import Any

from _common import grava
from anthropic import Anthropic
from anthropic.types import Usage
from llm_haiku import carrega_system_prompt

MODELO = os.environ.get("TEACHER_MODEL", "claude-haiku-4-5")
RECHEIO = "Aluno diz algo errado; professor corrige com paciencia e exemplo.\n"
TAMANHOS = (60, 100, 120, 140, 150, 180, 220)


def sonda(cliente: Anthropic, sistema: str, linhas: int) -> tuple[int, bool]:
    """Uma chamada com prefixo de tamanho controlado; devolve (tokens, engatou)."""
    texto = sistema + "\n" + RECHEIO * linhas
    uso = cliente.messages.create(
        model=MODELO,
        max_tokens=8,
        system=[
            {"type": "text", "text": texto, "cache_control": {"type": "ephemeral"}}
        ],
        messages=[{"role": "user", "content": "hi"}],
    ).usage
    total = (
        uso.input_tokens + uso.cache_creation_input_tokens + uso.cache_read_input_tokens
    )
    return total, uso.cache_creation_input_tokens > 0


def custo_de_entrada(uso: Usage) -> float:
    """US$ da entrada, com escrita a 1,25x e leitura a 0,1x (Haiku: US$ 1/MTok)."""
    unidades = (
        uso.input_tokens
        + uso.cache_creation_input_tokens * 1.25
        + uso.cache_read_input_tokens * 0.1
    )
    return round(unidades / 1e6, 6)


def main() -> None:
    cliente = Anthropic()
    sistema = carrega_system_prompt()
    resultados: dict[str, Any] = {"limiar": [], "estavel_vs_volatil": []}

    print("=== onde o cache passa a engatar ===", flush=True)
    for linhas in TAMANHOS:
        tokens, engatou = sonda(cliente, sistema, linhas)
        resultados["limiar"].append({"prefixo_tokens": tokens, "engatou": engatou})
        print(
            f"prefixo={tokens:6d} tok | {'ENGATOU' if engatou else '—'}",
            flush=True,
        )

    print("\n=== acima do limiar: prefixo estável vs. com timestamp ===", flush=True)
    base = sistema + "\n" + RECHEIO * 220
    for rotulo, volatil in (("estável", False), ("timestamp", True)):
        for chamada in (1, 2, 3):
            texto = (f"Data e hora: {time()}\n" if volatil else "") + base
            uso = cliente.messages.create(
                model=MODELO,
                max_tokens=8,
                system=[
                    {
                        "type": "text",
                        "text": texto,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": "hi"}],
            ).usage
            linha = {
                "prefixo": rotulo,
                "chamada": chamada,
                "escrita": uso.cache_creation_input_tokens,
                "leitura": uso.cache_read_input_tokens,
                "usd_entrada": custo_de_entrada(uso),
            }
            resultados["estavel_vs_volatil"].append(linha)
            print(
                f"{rotulo:10s} chamada {chamada}: escrita={linha['escrita']:6d} "
                f"leitura={linha['leitura']:6d} US$={linha['usd_entrada']:.6f}",
                flush=True,
            )

    print(f"\nresultados em {grava('llm_cache_threshold', resultados)}")


if __name__ == "__main__":
    main()
