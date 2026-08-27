"""O cálculo de custo, com aritmética conferível à mão.

Todos os números aqui saem da tabela de preços real (`config.LLM_PRICES`) e dos
tokens que o fake do professor já usava desde o CARD-007
(`input_tokens=1084, output_tokens=180`). É deliberado: um teste de custo com
preços inventados prova que a multiplicação funciona, não que o produto sabe
quanto gasta.

**Igualdade exata, nunca `pytest.approx`.** Se um número de dinheiro só bate por
aproximação, o tipo está errado — e o tipo errado é `float`, que é exatamente o
que o ADR-0013 proíbe.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from voicecoach.config import LLM_PRICES, preco_do_modelo
from voicecoach.domain.usage import (
    LlmPrice,
    StudentUsageTotals,
    UsageEvent,
    estimate_llm_cost,
)

HAIKU = LLM_PRICES["claude-haiku-4-5"]


def test_o_custo_bate_exato_com_a_tabela_de_precos() -> None:
    """1084 entrada + 180 saída no Haiku = US$ 0,001984, na vírgula.

    A conta, à mão: 1084 x US$ 1 / 1.000.000 = 0,001084; 180 x US$ 5 / 1.000.000
    = 0,000900. Soma: 0,001984.
    """
    custo = estimate_llm_cost(
        input_tokens=1084,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        output_tokens=180,
        price=HAIKU,
    )

    assert custo == Decimal("0.00198400")


def test_um_turn_arredondado_a_dois_digitos_seria_zero() -> None:
    """O motivo de a escala ser 8 e não 2, demonstrado em vez de afirmado.

    Este é o teste que justifica a coluna `NUMERIC(12, 8)`: com o instinto de
    quem lida com dinheiro de varejo, **todo** turn deste produto gravaria zero,
    e a soma de mil turns também.
    """
    custo = estimate_llm_cost(
        input_tokens=1084,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        output_tokens=180,
        price=HAIKU,
    )

    assert round(custo, 2) == Decimal("0.00")
    assert custo > Decimal(0)


def test_as_tres_entradas_sao_precificadas_por_tarifas_diferentes() -> None:
    """Cache não é desconto uniforme: escrever custa 1,25x e ler custa 0,1x.

    Hoje nenhuma das duas é acionada (ADR-0021), e é justamente por isso que o
    cálculo precisa estar certo **antes** — no dia em que o gatilho for atingido,
    ninguém vai reconferir esta conta.
    """
    custo = estimate_llm_cost(
        input_tokens=1_000_000,
        cache_creation_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        output_tokens=0,
        price=HAIKU,
    )

    # US$ 1,00 + US$ 1,25 + US$ 0,10 — as três tarifas de entrada da tabela.
    assert custo == Decimal("2.35000000")


def test_escrever_cache_com_prefixo_volatil_sai_mais_caro_que_nao_cachear() -> None:
    """A multa do ADR-0021 em forma de teste: errar não é perder desconto.

    Um prefixo que muda a cada chamada faz **toda** chamada pagar a escrita
    (1,25x) e nenhuma pagar a leitura (0,1x). O resultado é 25% mais caro que
    simplesmente não cachear — que é a razão de o ADR-0021 ter adiado o
    mecanismo em vez de "tentar e ver".
    """
    sem_cache = estimate_llm_cost(
        input_tokens=4096,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        output_tokens=0,
        price=HAIKU,
    )
    escrevendo_sempre = estimate_llm_cost(
        input_tokens=0,
        cache_creation_tokens=4096,
        cache_read_tokens=0,
        output_tokens=0,
        price=HAIKU,
    )

    assert escrevendo_sempre == sem_cache * Decimal("1.25")


def test_o_preco_e_encontrado_pelo_id_datado_que_a_api_devolve() -> None:
    """A busca é por prefixo, e é isso que evita uma linha nova por snapshot.

    A config pede `claude-haiku-4-5`; a API responde com o id resolvido. Casar
    por igualdade exigiria acrescentar uma chave a cada snapshot que o provedor
    publicasse — e o dia em que alguém esquecesse essa linha, o custo do produto
    pararia de ser medido em silêncio.
    """
    assert preco_do_modelo("claude-haiku-4-5-20251001") is HAIKU
    assert preco_do_modelo("claude-haiku-4-5") is HAIKU


def test_modelo_fora_da_tabela_nao_tem_preco_e_isso_nao_e_zero() -> None:
    """`None`, e não `Decimal(0)`. A distinção é o que o CARD-015 vai ler.

    Zero é o custo verdadeiro do STT e do TTS locais. "Não sabemos precificar" é
    outra coisa, e confundir as duas faria a cota tratar como grátis um turn cujo
    custo ninguém conhece.
    """
    assert preco_do_modelo("gpt-5-turbo") is None


def test_a_tabela_de_precos_declara_a_data_de_cada_preco() -> None:
    """Sem data, "o preço está desatualizado?" só se responde fora do repositório."""
    for modelo, preco in LLM_PRICES.items():
        assert preco.effective_from is not None, modelo


def test_a_tabela_de_precos_nao_aceita_escrita() -> None:
    """Constante de módulo mutável é global mutável — o `MappingProxyType` fecha isso.

    Sem ele, qualquer import poderia acrescentar um preço em runtime, e o
    `frozen=True` do `LlmPrice` não protegeria de nada: ele congela cada preço,
    não a tabela.
    """
    with pytest.raises(TypeError):
        LLM_PRICES["claude-haiku-4-5"] = HAIKU  # type: ignore[index]  # é exatamente o que o teste prova ser impossível


def test_dois_usage_events_iguais_sao_iguais_por_valor() -> None:
    """`frozen=True` dá `__eq__` por valor — é o que o roundtrip contra Postgres usa.

    Sem isto, o teste de persistência compararia identidade de objeto e teria de
    virar um laço campo a campo, que é onde um campo novo passa despercebido.
    """
    campos = {
        "turn_id": uuid4(),
        "student_id": uuid4(),
        "occurred_at": datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        "llm_model": "claude-haiku-4-5-20251001",
        "llm_input_tokens": 1084,
        "llm_cache_creation_tokens": 0,
        "llm_cache_read_tokens": 0,
        "llm_output_tokens": 180,
        "stt_audio_duration": timedelta(seconds=4),
        "stt_provider": "faster_whisper",
        "tts_chars": 91,
        "tts_provider": "piper",
        "estimated_cost_usd": Decimal("0.00198400"),
    }

    assert UsageEvent(**campos) == UsageEvent(**campos)  # type: ignore[arg-type]  # dict de kwargs heterogêneo; os tipos são verificados na definição acima
    assert UsageEvent(**{**campos, "tts_chars": 92}) != UsageEvent(**campos)  # type: ignore[arg-type]  # idem


def test_o_evento_de_custo_e_imutavel() -> None:
    """Medição não se corrige: o turn consumiu o que consumiu."""
    evento = UsageEvent(
        turn_id=uuid4(),
        student_id=uuid4(),
        occurred_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        llm_model="claude-haiku-4-5-20251001",
        llm_input_tokens=1084,
        llm_cache_creation_tokens=0,
        llm_cache_read_tokens=0,
        llm_output_tokens=180,
        stt_audio_duration=timedelta(seconds=4),
        stt_provider="faster_whisper",
        tts_chars=91,
        tts_provider="piper",
        estimated_cost_usd=Decimal("0.00198400"),
    )

    with pytest.raises(AttributeError):
        evento.llm_input_tokens = 2  # type: ignore[misc]  # é o erro que o teste prova existir


def test_totais_de_aluno_carregam_as_duas_unidades_da_cota() -> None:
    """Minutos **e** turns, porque a unidade da cota ainda não foi decidida.

    A análise de custo §8 mediu 3x de divergência entre as duas, e o ADR que
    escolhe está listado como pendente de decisão de produto. Um total que
    trouxesse só uma responderia a pergunta antes de ela ser feita.
    """
    totais = StudentUsageTotals(
        turns=3,
        spoken=timedelta(seconds=12),
        cost_usd=Decimal("0.00595200"),
        unpriced_turns=0,
    )

    assert totais.turns == 3
    assert totais.spoken == timedelta(seconds=12)


def test_o_preco_e_um_value_object_imutavel() -> None:
    """Um preço que mudasse em runtime tornaria "custo congelado" uma promessa falsa."""
    preco = LlmPrice(
        input_usd_per_mtok=Decimal("1.00"),
        cache_creation_usd_per_mtok=Decimal("1.25"),
        cache_read_usd_per_mtok=Decimal("0.10"),
        output_usd_per_mtok=Decimal("5.00"),
        effective_from=datetime(2026, 8, 27, tzinfo=UTC).date(),
    )

    with pytest.raises(AttributeError):
        preco.input_usd_per_mtok = Decimal("999")  # type: ignore[misc]  # idem
