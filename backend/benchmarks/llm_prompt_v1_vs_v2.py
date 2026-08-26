"""Compara os prompts v1 e v2 do professor com os MESMOS casos fixos (CARD-013).

**Por que este script existe.** O CARD-013 troca o contrato do professor —
`has_mistakes`/`original`/`corrected`/`tip` saem, `corrections[]` entra — e o
eval formal só chega na Fase 4. Sem baseline, a única rede é esta: os dois
prompts, as mesmas falas, o resultado escrito. Mesmo precedente do ADR-0021, que
registrou o número que **não** deu certo.

**Os dois braços rodam com o schema de tool que é o seu**, não com o do outro:
comparar o v1 forçado a devolver `corrections[]` mediria uma coisa que nunca
existiu. O que é idêntico entre eles é tudo o mais — modelo, `max_tokens`, as
falas, a mecânica de streaming e o corte de sentença.

O que se mede, e por que cada um:

- **tokens de saída** — o array de objetos é mais caro de gerar que três
  strings; parar de pedir os quatro campos velhos devolve parte disso. Só o
  número diz de que lado a conta fechou;
- **tempo até a primeira sentença falável** — é o ADR-0022 sendo verificado, e é
  o único número deste script que o aluno sente;
- **as correções em si** — para ler e julgar. Nenhuma métrica automática
  substitui olhar se o professor ficou mais ou menos conservador.

Uso, da pasta `backend/`:  `uv run python benchmarks/llm_prompt_v1_vs_v2.py`
"""

from __future__ import annotations

import asyncio
import json
import os
from time import perf_counter
from typing import Any

from anthropic import AsyncAnthropic

from voicecoach.adapters.llm.anthropic_teacher import (
    TOOL_NAME,
    TOOL_SCHEMA,
    # Os dois privados: o benchmark mede a mecânica REAL do adapter, e uma
    # cópia aqui mediria a cópia. É o único lugar do repositório que os importa.
    _delta_de_json,
    _fala_parcial,
)
from voicecoach.adapters.llm.factory import load_teacher_prompt
from voicecoach.adapters.llm.sentences import SentenceCutter

# O schema do v1, congelado aqui. Ele saiu do adapter no CARD-013 e este é o
# único lugar do repositório que ainda precisa dele — para poder medir contra o
# que existia. Apagar junto com o `v1.md`, quando o eval da Fase 4 existir.
CAMPOS_V1: dict[str, dict[str, str]] = {
    "spoken_reply": {"type": "string"},
    "has_mistakes": {"type": "boolean"},
    "original": {"type": "string"},
    "corrected": {"type": "string"},
    "tip": {"type": "string"},
    "translation_pt": {"type": "string"},
}
TOOL_SCHEMA_V1: dict[str, Any] = {
    "type": "object",
    "properties": CAMPOS_V1,
    "required": list(CAMPOS_V1),
    "additionalProperties": False,
}

# Casos fixos: os mesmos para os dois prompts, escolhidos para cobrir os
# desfechos que separam um professor conservador de um professor chato.
CASOS = [
    ("sem erro", "I work in a hospital and I really like my job."),
    ("um erro de gramática", "I has a dog and he are very friendly."),
    ("preposição", "I am arriving in home at six o'clock."),
    ("ordem das palavras", "Always I go to the gym before the work."),
    ("vários erros de uma vez", "Yesterday I go to store and buyed two book."),
    ("informal mas correto", "Yeah, it was kinda cool, you know?"),
]

MODELO = os.environ.get("TEACHER_MODEL", "claude-haiku-4-5")
MAX_TOKENS = 700


async def roda(cliente: AsyncAnthropic, versao: str, fala: str) -> dict[str, Any]:
    """Uma execução, com o prompt e o schema daquela versão."""
    schema = TOOL_SCHEMA_V1 if versao == "v1" else TOOL_SCHEMA
    cortador = SentenceCutter()
    buffer = b""
    inicio = perf_counter()
    primeira: float | None = None

    contexto = cliente.messages.stream(
        model=MODELO,
        max_tokens=MAX_TOKENS,
        system=load_teacher_prompt(versao),
        messages=[{"role": "user", "content": fala}],
        tools=[
            {
                "name": TOOL_NAME,
                "description": "Devolve a resposta do professor ao aluno.",
                "input_schema": schema,
                "eager_input_streaming": True,
            }
        ],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        timeout=30.0,
    )
    async with contexto as fluxo:
        async for evento in fluxo:
            pedaco = _delta_de_json(evento)
            if not pedaco:
                continue
            buffer += pedaco.encode("utf-8")
            for _ in cortador.feed(_fala_parcial(buffer)):
                if primeira is None:
                    primeira = perf_counter() - inicio
        mensagem = await fluxo.get_final_message()

    bruto: dict[str, Any] = next(
        b.input for b in mensagem.content if b.type == "tool_use"
    )
    return {
        "primeira_sentenca_s": round(primeira, 3) if primeira else None,
        "total_s": round(perf_counter() - inicio, 3),
        "output_tokens": mensagem.usage.output_tokens,
        "input_tokens": mensagem.usage.input_tokens,
        "resposta": bruto,
    }


def _resumo_das_correcoes(versao: str, resposta: dict[str, Any]) -> list[str]:
    if versao == "v1":
        if not resposta.get("has_mistakes"):
            return []
        return [
            f"{resposta['original']!r} → {resposta['corrected']!r} | {resposta['tip']}"
        ]
    return [
        f"[{c['type']}/{c['severity']}] "
        f"{c['original_excerpt']!r} → {c['corrected_form']!r} | {c['explanation']}"
        for c in resposta.get("corrections", [])
    ]


async def main() -> None:
    cliente = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    linhas: list[dict[str, Any]] = []
    for rotulo, fala in CASOS:
        print(f"\n=== {rotulo}\n    {fala}")
        atual: dict[str, Any] = {"caso": rotulo, "fala": fala}
        for versao in ("v1", "v2"):
            r = await roda(cliente, versao, fala)
            atual[versao] = r
            correcoes = _resumo_das_correcoes(versao, r["resposta"])
            print(
                f"  {versao}: entrada {r['input_tokens']} tok, "
                f"saída {r['output_tokens']} tok, "
                f"1ª sentença {r['primeira_sentenca_s']}s, "
                f"total {r['total_s']}s, {len(correcoes)} correção(ões)"
            )
            for c in correcoes:
                print(f"       - {c}")
        linhas.append(atual)

    print("\n--- totais nos 6 casos ---")
    for versao in ("v1", "v2"):
        entrada = sum(linha[versao]["input_tokens"] for linha in linhas)
        saida = sum(linha[versao]["output_tokens"] for linha in linhas)
        primeiras = [
            linha[versao]["primeira_sentenca_s"]
            for linha in linhas
            if linha[versao]["primeira_sentenca_s"]
        ]
        media = sum(primeiras) / len(primeiras) if primeiras else 0
        print(
            f"  {versao}: {entrada} tok entrada, {saida} tok saída, "
            f"1ª sentença média {media:.3f}s"
        )

    destino = "benchmarks/results/llm_prompt_v1_vs_v2.json"
    with open(destino, "w", encoding="utf-8") as arquivo:
        json.dump(linhas, arquivo, ensure_ascii=False, indent=2)
    print(f"\nbruto em {destino}")


if __name__ == "__main__":
    asyncio.run(main())
