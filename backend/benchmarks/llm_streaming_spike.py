"""Spike do CARD-007: qual mecanismo de saída estruturada preserva a ordem das
chaves EM STREAMING, e em quanto tempo o primeiro delta de `spoken_reply` chega.

O ADR-0022 decidiu que `spoken_reply` é o primeiro campo e deixou explícito o
risco que só a execução fecha: **ordem de chave em JSON gerado por LLM é
aderência a prompt, não garantia**. Este script é a verificação empírica que
aquele ADR exigiu.

Quatro mecanismos, não três (o card listou três; o quarto é GA desde então):

  A  tool use + `input_json_delta`, com `eager_input_streaming`
  B  texto livre + parser parcial
  C  duas chamadas (aqui: só a chamada da fala, que é a que está no caminho
     crítico — a segunda não afeta o tempo até o primeiro áudio)
  D  `output_config={"format": {"type": "json_schema", ...}}`

CUSTA DINHEIRO. ~16 chamadas ao Haiku, na ordem de US$ 0,04. O custo real sai
impresso no fim, calculado a partir do `usage` de cada chamada.
"""

from __future__ import annotations

import hashlib
import json
import os
import traceback
from pathlib import Path
from time import perf_counter
from typing import Any

import jiter
from _common import grava, percentil
from anthropic import Anthropic
from llm_haiku import FALA_LONGA, historico

MODELO = os.environ.get("TEACHER_MODEL", "claude-haiku-4-5")
REPETICOES = 3
MAX_TOKENS = 700

# Preços do Haiku 4.5, US$ por milhão de tokens. Constantes locais do benchmark:
# servem só para imprimir o custo desta execução (ADR-0010 manda contar).
USD_POR_MTOK_ENTRADA = 1.00
USD_POR_MTOK_SAIDA = 5.00

PROMPT_V1 = (
    Path(__file__).resolve().parent.parent
    / "src/voicecoach/adapters/llm/prompts/teacher/v1.md"
)

# O schema, na ordem do ADR-0022. `additionalProperties: false` + `required`
# com TODAS as chaves é o que o modo estrito exige.
CAMPOS = {
    "spoken_reply": {"type": "string"},
    "has_mistakes": {"type": "boolean"},
    "original": {"type": "string"},
    "corrected": {"type": "string"},
    "tip": {"type": "string"},
    "translation_pt": {"type": "string"},
}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": CAMPOS,
    "required": list(CAMPOS),
    "additionalProperties": False,
}


def sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def primeira_fala(buffer: bytes) -> str | None:
    """Devolve `spoken_reply` já legível no buffer truncado, ou None.

    `partial_mode="trailing-strings"` é o que faz a string INCOMPLETA vir. Com
    `partial_mode=True` a chave incompleta seria descartada e este spike mediria
    o tempo até a chave FECHAR — que é justamente o que a cascata evita.
    """
    try:
        dados = jiter.from_json(buffer, partial_mode="trailing-strings")
    except ValueError:
        return None
    if not isinstance(dados, dict):
        return None
    valor = dados.get("spoken_reply")
    return valor if isinstance(valor, str) and valor else None


def _uma_rodada(
    cliente: Anthropic, sistema: str, fala: str, opcao: str
) -> dict[str, Any]:
    """Uma chamada; devolve tempo até o primeiro `spoken_reply` e a ordem das chaves."""
    mensagens = [*historico(), {"role": "user", "content": fala}]
    comum: dict[str, Any] = {
        "model": MODELO,
        "max_tokens": MAX_TOKENS,
        "messages": mensagens,
    }

    if opcao == "A":
        comum["system"] = sistema
        comum["tools"] = [
            {
                "name": "teacher_feedback",
                "description": "Devolve a resposta do professor.",
                "input_schema": SCHEMA,
                # Sem isto o `input_json_delta` pode não vir na granularidade
                # que a cascata precisa — e o spike mediria a coisa errada.
                "eager_input_streaming": True,
            }
        ]
        comum["tool_choice"] = {"type": "tool", "name": "teacher_feedback"}
    elif opcao == "D":
        comum["system"] = sistema
        comum["output_config"] = {"format": {"type": "json_schema", "schema": SCHEMA}}
    elif opcao == "C":
        comum["system"] = (
            "You are a friendly English teacher chatting with a Brazilian "
            "student over WhatsApp voice messages. Reply conversationally in "
            "3-5 sentences MAX, plain text only — it becomes audio. React to "
            "what they said and ask a follow-up. No JSON, no markdown."
        )
    else:  # B
        comum["system"] = sistema

    inicio = perf_counter()
    ttft: float | None = None
    t_fala: float | None = None
    buffer = b""
    texto = ""

    with cliente.messages.stream(**comum) as fluxo:
        for evento in fluxo:
            if evento.type != "content_block_delta":
                continue
            delta = evento.delta
            pedaco = getattr(delta, "partial_json", None) or getattr(delta, "text", "")
            if not pedaco:
                continue
            if ttft is None:
                ttft = perf_counter() - inicio
            texto += pedaco
            buffer += pedaco.encode("utf-8")
            if t_fala is None:
                if opcao == "C":
                    t_fala = ttft  # a resposta INTEIRA é a fala
                elif primeira_fala(buffer) is not None:
                    t_fala = perf_counter() - inicio
        mensagem = fluxo.get_final_message()

    total = perf_counter() - inicio

    if opcao == "C":
        ordem = ["spoken_reply"]
    else:
        try:
            ordem = list(json.loads(texto).keys())
        except (ValueError, AttributeError):
            ordem = [f"<não parseou: {texto[:60]!r}>"]

    return {
        "ttft": ttft,
        "t_primeira_fala": t_fala,
        "total": total,
        "ordem": ordem,
        "entrada": mensagem.usage.input_tokens,
        "saida": mensagem.usage.output_tokens,
        "cache_creation": getattr(mensagem.usage, "cache_creation_input_tokens", None),
        "cache_read": getattr(mensagem.usage, "cache_read_input_tokens", None),
    }


def mede(cliente: Anthropic, sistema: str, fala: str, opcao: str) -> dict[str, Any]:
    rodadas: list[dict[str, Any]] = []
    for i in range(REPETICOES + 1):  # a primeira é aquecimento, descartada
        r = _uma_rodada(cliente, sistema, fala, opcao)
        if i:
            rodadas.append(r)

    falas = [r["t_primeira_fala"] for r in rodadas if r["t_primeira_fala"] is not None]
    return {
        "opcao": opcao,
        "ttft_p50": percentil([r["ttft"] for r in rodadas], 50),
        "primeira_fala_p50": percentil(falas, 50) if falas else None,
        "total_p50": percentil([r["total"] for r in rodadas], 50),
        "ordem_das_chaves": [r["ordem"] for r in rodadas],
        "ordem_estavel": len({tuple(r["ordem"]) for r in rodadas}) == 1,
        "spoken_reply_primeiro": all(
            r["ordem"] and r["ordem"][0] == "spoken_reply" for r in rodadas
        ),
        "tokens_entrada": rodadas[0]["entrada"],
        "tokens_saida_p50": percentil([float(r["saida"]) for r in rodadas], 50),
        "cache_creation": rodadas[0]["cache_creation"],
        "cache_read": rodadas[0]["cache_read"],
        "_uso": [(r["entrada"], r["saida"]) for r in rodadas],
    }


def main() -> None:
    cliente = Anthropic()
    sistema = PROMPT_V1.read_text(encoding="utf-8")

    print(f"modelo={MODELO}  prompt=v1.md sha256:{sha256(sistema)}")
    print(f"fala   sha256:{sha256(FALA_LONGA)} ({len(FALA_LONGA)} chars)\n")

    resultados: list[dict[str, Any]] = []
    usados: list[tuple[int, int]] = []

    for opcao in ("A", "B", "C", "D"):
        try:
            r = mede(cliente, sistema, FALA_LONGA, opcao)
        except Exception as erro:  # noqa: BLE001 — spike: uma opção que falha é RESULTADO, não interrupção
            print(f"{opcao}: FALHOU — {type(erro).__name__}: {erro}\n")
            traceback.print_exc()
            resultados.append(
                {"opcao": opcao, "falhou": f"{type(erro).__name__}: {erro}"}
            )
            continue
        usados.extend(r.pop("_uso"))
        resultados.append(r)
        pf = r["primeira_fala_p50"]
        print(
            f"{opcao}: ttft={r['ttft_p50']:.2f}s  "
            f"1a-fala={pf if pf is None else f'{pf:.2f}s'}  "
            f"total={r['total_p50']:.2f}s  "
            f"spoken_reply-primeiro={r['spoken_reply_primeiro']}  "
            f"ordem-estavel={r['ordem_estavel']}"
        )
        print(f"   ordem: {r['ordem_das_chaves'][0]}\n")

    entrada = sum(e for e, _ in usados)
    saida = sum(s for _, s in usados)
    custo = (
        entrada / 1_000_000 * USD_POR_MTOK_ENTRADA
        + saida / 1_000_000 * USD_POR_MTOK_SAIDA
    )
    print(
        f"custo desta execução: US$ {custo:.4f} ({entrada} tok entrada, {saida} saída)"
    )
    print(f"resultados em {grava('llm_streaming_spike', resultados)}")


if __name__ == "__main__":
    main()
