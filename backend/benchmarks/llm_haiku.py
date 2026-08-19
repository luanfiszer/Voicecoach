"""LLM: tempo até o primeiro token vs. tempo até o JSON completo.

A diferença entre os dois é exatamente o que a resposta em streaming
economiza — e é o número que sustenta o desenho em cascata (ADR-0022).

CUSTA DINHEIRO. São ~12 chamadas ao Haiku, na ordem de US$ 0,05.
Requer `ANTHROPIC_API_KEY` no ambiente.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from time import perf_counter
from typing import Any

from _common import grava, percentil
from anthropic import Anthropic

MODELO = os.environ.get("TEACHER_MODEL", "claude-haiku-4-5")
PROMPT_PADRAO = (
    Path(__file__).resolve().parents[2] / "english_teacher_bot" / "teacher.py"
)

FALA_CURTA = "I think my job is very stressful sometimes"
FALA_LONGA = (
    "So yesterday I was talking with my colleague about the new project and she "
    "told me that we need finish it until friday, but I think is impossible "
    "because we have many other things to do, and the manager he don't understand "
    "how much time this take, so I am little worried about this situation"
)

_RESPOSTA = (
    '{{"has_mistakes": false, "original": "{0}", "corrected": "", "tip": "", '
    '"spoken_reply": "That sounds really interesting! I would love to hear more '
    'about that. What made you decide to do it that way?", "translation_pt": '
    '"Isso parece muito interessante! Eu adoraria ouvir mais sobre isso."}}'
)
_FALAS_HISTORICO = (
    "I work in a hospital as a nurse",
    "Yesterday I go to the beach with my family",
    "My favorite food is feijoada, is very delicious",
    "I am studying English for two years",
    "I want travel to Canada next year",
    "The weather here is very hot in summer",
)


def carrega_system_prompt() -> str:
    """Lê o SYSTEM_PROMPT do protótipo, para medir com o prompt REAL.

    Medir com um prompt inventado mede outra coisa: o tamanho da entrada é
    metade do custo e influencia o tempo até o primeiro token.
    """
    fonte = PROMPT_PADRAO.read_text(encoding="utf-8")
    achado = re.search(r'SYSTEM_PROMPT = """(.*?)"""', fonte, re.S)
    if not achado:
        message = f"SYSTEM_PROMPT não encontrado em {PROMPT_PADRAO}"
        raise RuntimeError(message)
    return achado.group(1)


def historico() -> list[dict[str, str]]:
    mensagens: list[dict[str, str]] = []
    for fala in _FALAS_HISTORICO:
        mensagens.append({"role": "user", "content": fala})
        mensagens.append({"role": "assistant", "content": _RESPOSTA.format(fala)})
    return mensagens


def mede(cliente: Anthropic, sistema: str, fala: str, n: int) -> dict[str, Any]:
    ttfts: list[float] = []
    totais: list[float] = []
    tokens_saida = 0

    for i in range(n + 1):  # a primeira é aquecimento
        inicio = perf_counter()
        primeiro: float | None = None
        with cliente.messages.stream(
            model=MODELO,
            max_tokens=700,
            system=sistema,
            messages=[*historico(), {"role": "user", "content": fala}],
        ) as fluxo:
            for _ in fluxo.text_stream:
                if primeiro is None:
                    primeiro = perf_counter() - inicio
            mensagem = fluxo.get_final_message()
        total = perf_counter() - inicio
        if i and primeiro is not None:
            ttfts.append(primeiro)
            totais.append(total)
            tokens_saida = mensagem.usage.output_tokens

    return {
        "chars_da_fala": len(fala),
        "tokens_saida": tokens_saida,
        "ttft_p50": percentil(ttfts, 50),
        "ttft_p95": percentil(ttfts, 95),
        "total_p50": percentil(totais, 50),
        "total_p95": percentil(totais, 95),
        "tokens_por_segundo": round(
            tokens_saida / (percentil(totais, 50) - percentil(ttfts, 50)), 1
        ),
    }


def main() -> None:
    cliente = Anthropic()
    sistema = carrega_system_prompt()
    resultados = []
    for nome, fala in (("curta", FALA_CURTA), ("longa", FALA_LONGA)):
        r = mede(cliente, sistema, fala, 5)
        resultados.append({"caso": nome, **r})
        print(
            f"{nome:6s} ttft p50={r['ttft_p50']:.2f}s | "
            f"total p50={r['total_p50']:.2f}s | saída={r['tokens_saida']} tok | "
            f"{r['tokens_por_segundo']} tok/s",
            flush=True,
        )
    print(f"\nresultados em {grava('llm_haiku', resultados)}")


if __name__ == "__main__":
    main()
