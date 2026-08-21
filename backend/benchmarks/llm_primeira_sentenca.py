"""Tempo até a PRIMEIRA SENTENÇA, medido através do adapter de produção.

É o número que o CARD-007 existe para produzir, e ele não é o TTFT: entre o
primeiro token e a primeira sentença emitida existe o parser incremental e o
corte por sentença. **O delta entre os dois é o custo do meu código** — e é a
única maneira de saber se o corte por sentença está pagando por si.

Mede o adapter de verdade (`AnthropicTeacher`), não uma reimplementação: um
benchmark que mede outro caminho de código mede outra coisa.

CUSTA DINHEIRO. 2 casos x 4 chamadas = 8 chamadas ao Haiku, ~US$ 0,02.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from time import perf_counter
from typing import Any

from _common import grava, percentil
from llm_haiku import FALA_CURTA, FALA_LONGA

from voicecoach.adapters.llm.factory import create_teacher_llm, load_teacher_prompt
from voicecoach.application.ports.teacher_llm import (
    FeedbackReady,
    Speaker,
    SpokenSentence,
    Utterance,
)
from voicecoach.config import Settings

REPETICOES = 3

# As mesmas seis trocas do `llm_haiku.py`, para o tamanho de entrada bater com a
# linha de base medida em §5.1 (1.084 tokens). Insumo diferente mede outra coisa.
_FALAS_HISTORICO = (
    "I work in a hospital as a nurse",
    "Yesterday I go to the beach with my family",
    "My favorite food is feijoada, is very delicious",
    "I am studying English for two years",
    "I want travel to Canada next year",
    "The weather here is very hot in summer",
)
_RESPOSTA = (
    "That sounds really interesting! I would love to hear more about that. "
    "What made you decide to do it that way?"
)


def sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def historico(fala: str) -> list[Utterance]:
    falas: list[Utterance] = []
    for anterior in _FALAS_HISTORICO:
        falas.append(Utterance(speaker=Speaker.STUDENT, text=anterior))
        falas.append(Utterance(speaker=Speaker.TEACHER, text=_RESPOSTA))
    falas.append(Utterance(speaker=Speaker.STUDENT, text=fala))
    return falas


async def _uma_rodada(professor: Any, fala: str) -> dict[str, Any]:  # noqa: ANN401 — é a porta; anotar aqui arrastaria o import só para o benchmark
    inicio = perf_counter()
    primeira: float | None = None
    trechos = 0
    entrada = saida = 0

    async for evento in professor.respond_streaming(historico(fala)):
        if isinstance(evento, SpokenSentence):
            trechos += 1
            if primeira is None:
                primeira = perf_counter() - inicio
        elif isinstance(evento, FeedbackReady):
            entrada = evento.usage.input_tokens
            saida = evento.usage.output_tokens

    return {
        "primeira_sentenca": primeira,
        "total": perf_counter() - inicio,
        "trechos": trechos,
        "entrada": entrada,
        "saida": saida,
    }


async def mede(professor: Any, fala: str, nome: str) -> dict[str, Any]:  # noqa: ANN401 — idem
    rodadas: list[dict[str, Any]] = []
    for i in range(REPETICOES + 1):  # a primeira é aquecimento, descartada
        r = await _uma_rodada(professor, fala)
        if i:
            rodadas.append(r)

    return {
        "caso": nome,
        "chars_da_fala": len(fala),
        "sha256_da_fala": sha256(fala),
        "primeira_sentenca_p50": percentil(
            [r["primeira_sentenca"] for r in rodadas], 50
        ),
        "primeira_sentenca_p95": percentil(
            [r["primeira_sentenca"] for r in rodadas], 95
        ),
        "total_p50": percentil([r["total"] for r in rodadas], 50),
        "trechos_p50": percentil([float(r["trechos"]) for r in rodadas], 50),
        "tokens_entrada": rodadas[0]["entrada"],
        "tokens_saida_p50": percentil([float(r["saida"]) for r in rodadas], 50),
        "_uso": [(r["entrada"], r["saida"]) for r in rodadas],
    }


async def main() -> None:
    settings = Settings(anthropic_api_key=os.environ["ANTHROPIC_API_KEY"])
    professor = create_teacher_llm(settings)

    prompt = load_teacher_prompt()
    print(f"modelo={settings.teacher_model}  prompt=v1.md sha256:{sha256(prompt)}")
    print(f"histórico: {len(_FALAS_HISTORICO)} trocas  sha256:{sha256(_RESPOSTA)}\n")

    resultados: list[dict[str, Any]] = []
    usados: list[tuple[int, int]] = []
    for nome, fala in (("curta", FALA_CURTA), ("longa", FALA_LONGA)):
        r = await mede(professor, fala, nome)
        usados.extend(r.pop("_uso"))
        resultados.append(r)
        print(
            f"{nome:6s} 1a-sentença p50={r['primeira_sentenca_p50']:.2f}s "
            f"p95={r['primeira_sentenca_p95']:.2f}s | "
            f"total p50={r['total_p50']:.2f}s | "
            f"{r['trechos_p50']:.0f} trechos | "
            f"{r['tokens_entrada']} tok entrada"
        )

    entrada = sum(e for e, _ in usados)
    saida = sum(s for _, s in usados)
    custo = entrada / 1_000_000 * 1.00 + saida / 1_000_000 * 5.00
    print(f"\ncusto desta execução: US$ {custo:.4f}")
    print(f"resultados em {grava('llm_primeira_sentenca', resultados)}")
    print(
        f"prompt v1.md sha256 completo: {hashlib.sha256(prompt.encode()).hexdigest()}"
    )


if __name__ == "__main__":
    asyncio.run(main())
