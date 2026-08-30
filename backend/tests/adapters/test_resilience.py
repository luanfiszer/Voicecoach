"""O circuit breaker: as três transições e o que ele NÃO faz (CARD-026).

Teste de unidade puro — o breaker não faz IO. O relógio é injetado, então a
janela de recuperação é exercitada **sem esperar 30 s de verdade**: o teste
avança o relógio, que é o mesmo motivo pelo qual `clock` entra por parâmetro em
todo o resto do projeto.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from voicecoach.adapters.resilience import CircuitBreaker, CircuitOpenError

INICIO = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)
RECUPERACAO = timedelta(seconds=30)


class Relogio:
    """Relógio controlado pelo teste. `avanca` é o que substitui o `sleep`."""

    def __init__(self, agora: datetime = INICIO) -> None:
        self.agora = agora

    def __call__(self) -> datetime:
        return self.agora

    def avanca(self, delta: timedelta) -> None:
        self.agora += delta


def breaker(relogio: Relogio, *, limite: int = 3) -> CircuitBreaker:
    return CircuitBreaker(
        failure_threshold=limite,
        recovery=RECUPERACAO,
        clock=relogio,
        name="teste",
    )


def test_fechado_deixa_passar_e_nao_levanta() -> None:
    disjuntor = breaker(Relogio())

    for _ in range(100):
        disjuntor.antes_de_chamar()  # não levanta

    assert not disjuntor.aberto


def test_abre_exatamente_na_enesima_falha_seguida() -> None:
    """N-1 falhas ainda passam; a N-ésima fecha a porta.

    O limite é `>=`, não `>`: com `failure_threshold=3`, a terceira falha abre.
    Errar isto por um faria o breaker abrir tarde demais — e "tarde demais" aqui
    custa 60 s de espera a mais para um aluno.
    """
    disjuntor = breaker(Relogio(), limite=3)

    disjuntor.falha()
    disjuntor.falha()
    disjuntor.antes_de_chamar()  # duas falhas: ainda fechado
    assert not disjuntor.aberto

    disjuntor.falha()

    assert disjuntor.aberto
    with pytest.raises(CircuitOpenError, match="3 falhas seguidas"):
        disjuntor.antes_de_chamar()


def test_sucesso_zera_a_contagem_porque_o_que_conta_e_falha_CONSECUTIVA() -> None:  # noqa: N802 — o nome É a asserção
    """Provedor que alterna sucesso e falha está degradado, não fora do ar.

    Se o contador não zerasse, um provedor com 10% de erro abriria o circuito
    depois de algumas dezenas de turns — derrubando o produto inteiro por uma
    taxa de falha que o retry já absorve.
    """
    disjuntor = breaker(Relogio(), limite=3)

    for _ in range(20):
        disjuntor.falha()
        disjuntor.falha()
        disjuntor.sucesso()

    assert not disjuntor.aberto
    disjuntor.antes_de_chamar()


def test_o_circuito_nao_fica_aberto_para_sempre() -> None:
    """Critério de aceite do card: vencida a janela, a chamada seguinte tenta.

    Um breaker sem esta transição transforma uma indisponibilidade de 1 minuto
    numa indisponibilidade permanente — precisaria de restart do processo para
    voltar, que é o pior modo de falha possível para uma proteção.
    """
    relogio = Relogio()
    disjuntor = breaker(relogio, limite=1)
    disjuntor.falha()

    relogio.avanca(RECUPERACAO - timedelta(seconds=1))
    with pytest.raises(CircuitOpenError):
        disjuntor.antes_de_chamar()

    relogio.avanca(timedelta(seconds=2))
    disjuntor.antes_de_chamar()  # a sonda passa


def test_apenas_UMA_sonda_atravessa_a_janela_vencida() -> None:  # noqa: N802 — o nome É a asserção
    """Sem isto o breaker desaparece justamente quando mais importa.

    Vencida a janela, dez turns enfileirados passariam TODOS e pagariam os 60 s
    cada um — exatamente o custo que o breaker existe para não pagar. A sonda é
    uma só até ela decidir.
    """
    relogio = Relogio()
    disjuntor = breaker(relogio, limite=1)
    disjuntor.falha()
    relogio.avanca(RECUPERACAO)

    disjuntor.antes_de_chamar()  # a sonda

    with pytest.raises(CircuitOpenError, match="sonda de recuperação"):
        disjuntor.antes_de_chamar()


def test_sonda_que_falha_reabre_e_reinicia_a_janela() -> None:
    relogio = Relogio()
    disjuntor = breaker(relogio, limite=1)
    disjuntor.falha()
    relogio.avanca(RECUPERACAO)
    disjuntor.antes_de_chamar()

    disjuntor.falha()

    assert disjuntor.aberto
    relogio.avanca(RECUPERACAO - timedelta(seconds=1))
    with pytest.raises(CircuitOpenError):
        disjuntor.antes_de_chamar()


def test_sonda_que_da_certo_fecha_o_circuito_de_vez() -> None:
    relogio = Relogio()
    disjuntor = breaker(relogio, limite=1)
    disjuntor.falha()
    relogio.avanca(RECUPERACAO)
    disjuntor.antes_de_chamar()

    disjuntor.sucesso()

    assert not disjuntor.aberto
    for _ in range(10):
        disjuntor.antes_de_chamar()
