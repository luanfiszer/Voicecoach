"""O cortador de sentenças, e os dois modos de falha opostos que ele evita."""

from __future__ import annotations

import pytest

from voicecoach.adapters.llm.sentences import MAX_CHUNK_CHARS, SentenceCutter


def corta_tudo(fala: str) -> list[str]:
    """Alimenta caractere a caractere, como o stream faria, e fecha no fim."""
    cortador = SentenceCutter()
    trechos: list[str] = []
    for i in range(1, len(fala) + 1):
        trechos.extend(cortador.feed(fala[:i]))
    trechos.extend(cortador.flush(fala))
    return trechos


# --- cortar cedo demais ------------------------------------------------------


@pytest.mark.parametrize(
    "fala",
    [
        pytest.param("I met Mr. Smith yesterday at the office.", id="mr"),
        pytest.param("It took me 3.5 hours to finish the whole thing.", id="decimal"),
        pytest.param("You should rest, i.e. take a real break today.", id="i.e."),
        pytest.param("Ask Dr. Alves about it when you see her.", id="dr"),
        pytest.param("His name is J. Smith and he teaches here.", id="inicial"),
    ],
)
def test_abreviacao_e_decimal_nao_partem_a_sentenca(fala: str) -> None:
    assert corta_tudo(fala) == [fala]


# --- cortar tarde demais -----------------------------------------------------


def test_ultima_sentenca_so_sai_no_flush() -> None:
    """Enquanto a geração corre, o fim do buffer pode sempre crescer.

    Sem esta regra, "How are yo" viraria áudio e o aluno ouviria meia palavra.
    """
    cortador = SentenceCutter()

    assert cortador.feed("Hi there, my friend. How are yo") == ["Hi there, my friend."]
    assert cortador.feed("Hi there, my friend. How are you") == []
    assert cortador.flush("Hi there, my friend. How are you?") == ["How are you?"]


def test_delimitador_no_fim_do_buffer_ainda_nao_conta() -> None:
    """Um ponto no último caractere pode ser "3." de "3.5" — falta o que vem depois."""
    cortador = SentenceCutter()

    assert cortador.feed("It cost 3.") == []
    assert cortador.feed("It cost 3.5") == []


# --- política de tamanho -----------------------------------------------------


def test_primeira_sentenca_sai_sozinha_e_o_resto_e_agrupado() -> None:
    """É a primeira que define o tempo até o primeiro áudio; ela não espera ninguém."""
    fala = (
        "That sounds great. I really think you should try it again next week, "
        "because practice is what makes the difference over time, and you already "
        "know most of the words you need. What do you think about that idea?"
    )
    trechos = corta_tudo(fala)

    assert trechos[0] == "That sounds great."
    assert len(trechos) < len(fala.split(". "))  # o resto foi agrupado
    assert " ".join(trechos) == fala


def test_sentenca_curta_demais_nao_sai_sozinha() -> None:
    """ "Hi." vira um arquivo de áudio de 300 ms com prosódia estranha."""
    trechos = corta_tudo("Hi. That is wonderful news, congratulations!")

    assert trechos[0].startswith("Hi. That is")


def test_agrupamento_respeita_o_teto() -> None:
    fala = " ".join(f"This is sentence number {n} in the reply." for n in range(1, 20))

    trechos = corta_tudo(fala)

    # O último trecho é o resto do flush e pode passar; os demais são o corte.
    assert all(len(t) <= MAX_CHUNK_CHARS * 2 for t in trechos)
    assert " ".join(trechos) == fala


# --- invariantes -------------------------------------------------------------


def test_nada_se_perde_e_nada_se_repete() -> None:
    fala = "First one here. Second one now! Third and last one?"

    assert " ".join(corta_tudo(fala)) == fala


def test_fala_vazia_nao_emite_nada() -> None:
    cortador = SentenceCutter()

    assert cortador.feed("") == []
    assert cortador.flush("") == []
