"""`spoken_reply` é a primeira chave — o teste que o ADR-0022, item 4, exigiu.

Sem ele o ADR erode sozinho, e **em silêncio**: reordenar os campos não quebra
resposta nenhuma, não deixa teste vermelho e não aparece em review. Só a latência
sobe. Quem editar o prompt daqui a três meses não tem motivo para suspeitar que
a ordem importa — este arquivo é o motivo.
"""

from __future__ import annotations

import re

from voicecoach.adapters.llm.anthropic_teacher import CAMPOS, TOOL_SCHEMA
from voicecoach.adapters.llm.factory import load_teacher_prompt

# A ordem do ADR-0022, com o delta do CARD-013: os quatro campos texto saíram
# (viraram `corrections`, derivados na borda) e o array entrou por ÚLTIMO. O que
# o ADR decidiu e continua valendo é a regra, não a lista: `spoken_reply`
# primeiro porque é o único no caminho crítico, e o mais caro de gerar por
# último porque cada byte antes de a fala fechar é atraso no primeiro áudio.
ORDEM_DA_RESPOSTA = [
    "spoken_reply",
    "translation_pt",
    "corrections",
]


def chaves_do_prompt() -> list[str]:
    """As chaves do bloco de schema do prompt, na ordem em que aparecem."""
    prompt = load_teacher_prompt()
    bloco = re.search(r"\{(.*?)\n\}", prompt, re.S)
    assert bloco is not None, "o prompt não tem o bloco de schema JSON"
    # Exatamente dois espaços: as chaves de PRIMEIRO nível. Com `\s*` o regex
    # também pegava `type`, `severity` e as outras de dentro de `corrections`,
    # e o teste passaria a afirmar uma ordem que o ADR-0022 não decide — a
    # ordem dentro de uma correção não está no caminho crítico de nada.
    return re.findall(r'^  "(\w+)":', bloco.group(1), re.M)


def test_spoken_reply_e_a_primeira_chave_do_prompt() -> None:
    assert chaves_do_prompt()[0] == "spoken_reply"


def test_ordem_completa_do_prompt_e_a_do_adr_0022() -> None:
    assert chaves_do_prompt() == ORDEM_DA_RESPOSTA


def test_schema_da_tool_tem_a_mesma_ordem_do_prompt() -> None:
    """Duas declarações da mesma ordem: o prompt e o schema da tool.

    O `input_schema` é o que o provedor impõe; o prompt é o que ele lê. Se as
    duas divergirem, o modelo recebe instruções contraditórias — e a que vence
    não é observável daqui.
    """
    assert list(CAMPOS) == ORDEM_DA_RESPOSTA
    assert TOOL_SCHEMA["required"] == ORDEM_DA_RESPOSTA


def test_corrections_e_o_ultimo() -> None:
    """O campo mais LONGO fica onde ele não atrasa o primeiro áudio (CARD-013).

    Era `translation_pt` — o mais descartável — até o array de correções existir.
    A regra do ADR-0022 não mudou; o que mudou é qual campo ela aponta, porque o
    critério é "o que custa mais para gerar vai depois do que está no caminho
    crítico", e `corrections` passou `translation_pt` nesse critério.
    """
    assert chaves_do_prompt()[-1] == "corrections"


def test_prompt_manda_preservar_a_ordem() -> None:
    """A ordem é pedida explicitamente, não só sugerida pela diagramação.

    O spike mediu o preço de não pedir: no texto livre o modelo reordenou as
    chaves em 1 de 3 execuções.
    """
    assert "first key" in load_teacher_prompt()


def test_prompt_nao_tem_conteudo_volatil() -> None:
    """Higiene de prefixo do ADR-0021, item 2 — custa zero e preserva a opção.

    Timestamp, id de request ou contador de turn no prefixo invalidariam o cache
    a cada chamada no dia em que o caching for ligado.
    """
    prompt = load_teacher_prompt()

    assert not re.search(r"\d{4}-\d{2}-\d{2}", prompt)
    assert "{" + "date" not in prompt
