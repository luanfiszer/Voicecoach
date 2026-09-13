"""Tradução sob demanda: o que se paga, o que não se paga e o que se recusa.

O instrumento central é ``FakeTranslator.chamadas``: "não pagar duas vezes"
(RF4) não é observável no texto devolvido — os dois caminhos devolvem o mesmo —,
só na contagem de chamadas ao provedor.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from fakes_pipeline import (
    FakeServiceBudget,
    FakeSessionRepository,
    FakeTranslationRepository,
    FakeTranslator,
    FakeTurnRepository,
    FakeUnitOfWork,
    tradutor_fora_do_ar,
)
from voicecoach.application.ports.repositories import ConflictingWriteError
from voicecoach.application.ports.translator import TranslatorError
from voicecoach.application.result import Err, Ok
from voicecoach.application.use_cases.translate_text import (
    NothingToTranslate,
    ServiceBudgetExceeded,
    TranslateText,
    TranslateTextHandler,
    TurnNotFound,
)
from voicecoach.config import preco_do_modelo
from voicecoach.domain.correction import Correction, CorrectionType, Severity
from voicecoach.domain.session import Session
from voicecoach.domain.translation import Translation, TranslationTarget
from voicecoach.domain.turn import Turn

ALUNO = UUID("00000000-0000-0000-0000-000000000001")
OUTRO_ALUNO = UUID("00000000-0000-0000-0000-000000000002")
AGORA = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)

CORRECAO = Correction(
    index=0,
    type=CorrectionType.PREPOSITION,
    original_excerpt="in the beach",
    corrected_form="at the beach",
    explanation="Use 'at' for a location you visit.",
    severity=Severity.MINOR,
)


def sessao_do(student_id: UUID = ALUNO) -> Session:
    return Session(id=uuid4(), student_id=student_id, started_at=AGORA)


def turn_respondido(
    sessao: Session, *, reply: str | None = "Which beach did you go to?"
) -> Turn:
    turn = sessao.start_turn(
        turn_id=uuid4(),
        input_audio_ref="dev/entrada.m4a",
        audio_duration=timedelta(seconds=4),
        now=AGORA,
    )
    turn.start_processing(AGORA)
    turn.attach_transcript("I go in the beach", AGORA)
    if reply is not None:
        turn.attach_reply(reply, AGORA)
        turn.attach_corrections([CORRECAO])
    return turn


def montar(
    *,
    turn: Turn,
    sessao: Session,
    tradutor: FakeTranslator | None = None,
    translations: FakeTranslationRepository | None = None,
    budget: FakeServiceBudget | None = None,
) -> tuple[
    TranslateTextHandler,
    FakeTranslator,
    FakeTranslationRepository,
    FakeUnitOfWork,
    FakeServiceBudget,
]:
    tradutor = tradutor or FakeTranslator()
    translations = translations or FakeTranslationRepository()
    budget = budget or FakeServiceBudget()
    uow = FakeUnitOfWork()
    handler = TranslateTextHandler(
        turns=FakeTurnRepository(turn),
        sessions=FakeSessionRepository(sessao),
        translations=translations,
        translator=tradutor,
        service_budget=budget,
        unit_of_work=uow,
        clock=lambda: AGORA,
        llm_price=preco_do_modelo,
    )
    return handler, tradutor, translations, uow, budget


def comando(
    turn: Turn,
    *,
    target: TranslationTarget = TranslationTarget.REPLY,
    index: int = 0,
    student_id: UUID = ALUNO,
) -> TranslateText:
    return TranslateText(
        turn_id=turn.id, target=target, index=index, student_id=student_id
    )


async def test_traduz_a_resposta_do_professor_e_grava_o_custo() -> None:
    """Critério de aceite: recebo o texto em português e o custo é registrado."""
    sessao = sessao_do()
    turn = turn_respondido(sessao)
    handler, tradutor, translations, uow, _budget = montar(turn=turn, sessao=sessao)

    resultado = await handler.handle(comando(turn))

    assert isinstance(resultado, Ok)
    assert resultado.value.text == "Qual praia você foi?"
    assert resultado.value.cached is False
    # O provedor recebeu o texto DO PRODUTO, não algo vindo do cliente (RF1).
    assert tradutor.chamadas == ["Which beach did you go to?"]

    gravada = translations.translations[(turn.id, TranslationTarget.REPLY, 0)]
    assert gravada.model == "claude-haiku-4-5-20251001"
    # Custo congelado na escrita (RF3/ADR-0051), em Decimal e nunca zero.
    assert isinstance(gravada.estimated_cost_usd, Decimal)
    assert gravada.estimated_cost_usd > 0
    assert uow.commits == 1


async def test_a_mesma_traducao_nao_e_paga_duas_vezes() -> None:
    """Critério de aceite central (RF4): a segunda vez não chama o provedor."""
    sessao = sessao_do()
    turn = turn_respondido(sessao)
    handler, tradutor, translations, _uow, budget = montar(turn=turn, sessao=sessao)

    primeira = await handler.handle(comando(turn))
    segunda = await handler.handle(comando(turn))

    assert isinstance(primeira, Ok)
    assert isinstance(segunda, Ok)
    assert segunda.value.text == primeira.value.text
    assert segunda.value.cached is True
    # A prova: UMA chamada ao provedor, UMA linha, UM lançamento no orçamento.
    assert len(tradutor.chamadas) == 1
    assert len(translations.translations) == 1
    assert len(budget.somado) == 1


async def test_traduz_a_explicacao_de_uma_correcao() -> None:
    sessao = sessao_do()
    turn = turn_respondido(sessao)
    handler, tradutor, translations, _uow, _budget = montar(turn=turn, sessao=sessao)

    resultado = await handler.handle(
        comando(turn, target=TranslationTarget.CORRECTION, index=0)
    )

    assert isinstance(resultado, Ok)
    assert tradutor.chamadas == ["Use 'at' for a location you visit."]
    assert (turn.id, TranslationTarget.CORRECTION, 0) in translations.translations


async def test_resposta_e_correcao_sao_traducoes_diferentes() -> None:
    """A chave é composta: traduzir a resposta não marca a correção como feita."""
    sessao = sessao_do()
    turn = turn_respondido(sessao)
    handler, tradutor, _translations, _uow, _budget = montar(turn=turn, sessao=sessao)

    await handler.handle(comando(turn))
    await handler.handle(comando(turn, target=TranslationTarget.CORRECTION, index=0))

    assert len(tradutor.chamadas) == 2


async def test_o_consumo_soma_no_orcamento_global() -> None:
    """RNF3: é gasto de IA como qualquer outro — entra no mesmo contador."""
    sessao = sessao_do()
    turn = turn_respondido(sessao)
    handler, _tradutor, translations, _uow, budget = montar(turn=turn, sessao=sessao)

    await handler.handle(comando(turn))

    gravada = translations.translations[(turn.id, TranslationTarget.REPLY, 0)]
    assert budget.somado == [gravada.estimated_cost_usd]


async def test_kill_switch_recusa_e_nao_chama_o_provedor() -> None:
    """Critério de aceite: recusa em Problem Details, texto original intacto."""
    sessao = sessao_do()
    turn = turn_respondido(sessao)
    handler, tradutor, translations, uow, _budget = montar(
        turn=turn, sessao=sessao, budget=FakeServiceBudget(excedido=True)
    )

    resultado = await handler.handle(comando(turn))

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, ServiceBudgetExceeded)
    assert tradutor.chamadas == []
    assert translations.translations == {}
    assert uow.commits == 0


async def test_kill_switch_nao_bloqueia_traducao_ja_paga() -> None:
    """A consulta vem ANTES do orçamento: o que já foi pago não passa no pedágio."""
    sessao = sessao_do()
    turn = turn_respondido(sessao)
    ja_existe = FakeTranslationRepository(
        Translation(
            turn_id=turn.id,
            target=TranslationTarget.REPLY,
            index=0,
            text="Qual praia você foi?",
            model="claude-haiku-4-5-20251001",
            created_at=AGORA,
            estimated_cost_usd=Decimal("0.00012000"),
        )
    )
    handler, tradutor, _translations, _uow, _budget = montar(
        turn=turn,
        sessao=sessao,
        translations=ja_existe,
        budget=FakeServiceBudget(excedido=True),
    )

    resultado = await handler.handle(comando(turn))

    assert isinstance(resultado, Ok)
    assert resultado.value.cached is True
    assert tradutor.chamadas == []


async def test_turn_sem_resposta_ainda_nao_tem_o_que_traduzir() -> None:
    sessao = sessao_do()
    turn = turn_respondido(sessao, reply=None)
    handler, tradutor, _translations, _uow, _budget = montar(turn=turn, sessao=sessao)

    resultado = await handler.handle(comando(turn))

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, NothingToTranslate)
    assert tradutor.chamadas == []


async def test_correcao_de_indice_inexistente_e_nothing_to_translate() -> None:
    sessao = sessao_do()
    turn = turn_respondido(sessao)
    handler, tradutor, _translations, _uow, _budget = montar(turn=turn, sessao=sessao)

    resultado = await handler.handle(
        comando(turn, target=TranslationTarget.CORRECTION, index=7)
    )

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, NothingToTranslate)
    assert tradutor.chamadas == []


async def test_turn_inexistente_e_err_e_nao_excecao() -> None:
    sessao = sessao_do()
    turn = turn_respondido(sessao)
    handler, _tradutor, _translations, _uow, _budget = montar(turn=turn, sessao=sessao)

    resultado = await handler.handle(
        TranslateText(
            turn_id=uuid4(),
            target=TranslationTarget.REPLY,
            index=0,
            student_id=ALUNO,
        )
    )

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, TurnNotFound)


async def test_turn_de_outro_aluno_e_mascarado_como_not_found() -> None:
    """Mesma disciplina do CARD-032: um 404 idêntico, sem oráculo de posse."""
    sessao = sessao_do()
    turn = turn_respondido(sessao)
    handler, tradutor, _translations, _uow, _budget = montar(turn=turn, sessao=sessao)

    resultado = await handler.handle(comando(turn, student_id=OUTRO_ALUNO))

    assert isinstance(resultado, Err)
    assert isinstance(resultado.error, TurnNotFound)
    assert tradutor.chamadas == []


async def test_provedor_fora_do_ar_sobe_como_erro_de_porta() -> None:
    """RF6: não é `Err` — é infraestrutura, e a borda a traduz em 503."""
    sessao = sessao_do()
    turn = turn_respondido(sessao)
    handler, _tradutor, translations, uow, _budget = montar(
        turn=turn, sessao=sessao, tradutor=tradutor_fora_do_ar()
    )

    with pytest.raises(TranslatorError):
        await handler.handle(comando(turn))

    assert translations.translations == {}
    assert uow.commits == 0


async def test_perder_a_corrida_devolve_a_traducao_de_quem_chegou_antes() -> None:
    """A consulta é uma foto; a chave composta é a lei (mesmo desenho do ADR-0042)."""
    sessao = sessao_do()
    turn = turn_respondido(sessao)
    vencedora = Translation(
        turn_id=turn.id,
        target=TranslationTarget.REPLY,
        index=0,
        text="A tradução de quem chegou primeiro",
        model="claude-haiku-4-5-20251001",
        created_at=AGORA,
        estimated_cost_usd=Decimal("0.00012000"),
    )
    translations = FakeTranslationRepository()

    class UnitOfWorkQueColide(FakeUnitOfWork):
        """No commit: outra requisição já gravou a mesma chave."""

        async def commit(self) -> None:
            translations.translations[
                (vencedora.turn_id, vencedora.target, vencedora.index)
            ] = vencedora
            message = "duplicate key value violates unique constraint"
            raise ConflictingWriteError(message)

    handler = TranslateTextHandler(
        turns=FakeTurnRepository(turn),
        sessions=FakeSessionRepository(sessao),
        translations=translations,
        translator=FakeTranslator(),
        service_budget=FakeServiceBudget(),
        unit_of_work=UnitOfWorkQueColide(),
        clock=lambda: AGORA,
        llm_price=preco_do_modelo,
    )

    resultado = await handler.handle(comando(turn))

    assert isinstance(resultado, Ok)
    assert resultado.value.text == "A tradução de quem chegou primeiro"
    assert resultado.value.cached is True


async def test_modelo_fora_da_tabela_grava_custo_nulo_e_nao_soma_orcamento() -> None:
    """Nulo é "não sabemos precificar", nunca zero — a regra do ADR-0051."""
    sessao = sessao_do()
    turn = turn_respondido(sessao)
    handler, _tradutor, translations, _uow, budget = montar(
        turn=turn,
        sessao=sessao,
        tradutor=FakeTranslator(model="modelo-que-ninguem-precificou"),
    )

    resultado = await handler.handle(comando(turn))

    assert isinstance(resultado, Ok)
    gravada = translations.translations[(turn.id, TranslationTarget.REPLY, 0)]
    assert gravada.estimated_cost_usd is None
    assert budget.somado == []
