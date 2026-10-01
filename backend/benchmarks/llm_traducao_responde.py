"""Quantas vezes o tradutor RESPONDE ao texto em vez de traduzi-lo (CARD-063).

Achado no QA de 2026-10-01: pedida a tradução de "That's great! I'd love to
hear more about it. What kind of project are you working on? Tell me what
makes it so amazing for you.", o `claude-haiku-4-5` devolveu, em inglês, "I
appreciate your interest, but I should clarify: I'm an AI assistant without
personal projects...". Intermitente: a rodada seguinte traduziu certo.

Compara duas variantes do prompt, N vezes cada, sobre falas do professor que
terminam em pergunta (o caso que convida a responder):

- **v1** — o prompt de produção até o CARD-063: o texto entra cru como
  mensagem do usuário;
- **v2** — o texto entra delimitado em ``<texto>``, e a instrução diz que o
  que está ali é material, nunca uma mensagem dirigida ao modelo.

Roda no venv do PROJETO (precisa do `anthropic`), de `backend/`:

    uv run python benchmarks/llm_traducao_responde.py 10

**GASTA DINHEIRO** (~US$ 0,02 com N=10). Imprime o custo real a partir do
`usage`. A classificação "respondeu em vez de traduzir" é heurística (palavras
funcionais de cada língua); toda falha é impressa para conferência à mão.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from decimal import Decimal

from anthropic import AsyncAnthropic

from voicecoach.adapters.llm.anthropic_translator import (
    _INSTRUCAO as INSTRUCAO_V2,
)
from voicecoach.adapters.llm.anthropic_translator import (
    mensagem_do_usuario,
)

MODELO = os.environ.get("ASSISTANT_MODEL", "claude-haiku-4-5")
# Preço por milhão de tokens do claude-haiku-4-5 (entrada, saída).
PRECO_ENTRADA = Decimal("1.00")
PRECO_SAIDA = Decimal("5.00")

INSTRUCAO_V1 = (
    "Você traduz para português do Brasil. Devolva SOMENTE a tradução do texto "
    "recebido, sem aspas, sem comentários e sem responder ao conteúdo. "
    "Preserve o tom e mantenha em inglês os termos que o texto ensina."
)

TEXTOS = [
    "That's great! I'd love to hear more about it. What kind of project are "
    "you working on? Tell me what makes it so amazing for you.",
    "Which beach did you go to? Did you swim or just relax in the sun?",
    "Nice! What do you usually do on weekends? Tell me about your favorite one.",
]

EN = {"the", "you", "i", "i'm", "is", "are", "what", "and", "to", "it", "my", "me"}
PT = {"que", "você", "é", "de", "o", "a", "para", "um", "uma", "isso", "me", "eu"}


def respondeu_em_ingles(saida: str) -> bool:
    palavras = re.findall(r"[a-zà-ú']+", saida.lower())
    en = sum(p in EN for p in palavras)
    pt = sum(p in PT for p in palavras)
    return en >= pt


async def rodar(
    cliente: AsyncAnthropic, nome: str, sistema: str, montar: object, n: int
) -> tuple[int, int, Decimal]:
    falhas, total, custo = 0, 0, Decimal(0)
    for texto in TEXTOS:
        for _ in range(n):
            conteudo = montar(texto) if callable(montar) else texto
            msg = await cliente.messages.create(
                model=MODELO,
                max_tokens=500,
                system=sistema,
                messages=[{"role": "user", "content": conteudo}],
            )
            saida = "".join(b.text for b in msg.content if b.type == "text").strip()
            custo += (
                PRECO_ENTRADA * msg.usage.input_tokens
                + PRECO_SAIDA * msg.usage.output_tokens
            ) / Decimal(1_000_000)
            total += 1
            if respondeu_em_ingles(saida):
                falhas += 1
                print(f"  [{nome}] FALHA: {saida[:140]!r}")
    return falhas, total, custo


async def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    cliente = AsyncAnthropic()
    print(f"modelo={MODELO}, N={n} por texto, {len(TEXTOS)} textos")
    custo_total = Decimal(0)
    for nome, sistema, montar in (
        ("v1", INSTRUCAO_V1, None),
        ("v2", INSTRUCAO_V2, mensagem_do_usuario),
    ):
        falhas, total, custo = await rodar(cliente, nome, sistema, montar, n)
        custo_total += custo
        print(f"{nome}: {falhas}/{total} responderam em vez de traduzir")
    print(f"custo da execução: US$ {custo_total:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
