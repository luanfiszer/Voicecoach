"""Tradução sob demanda de um texto do produto (CARD-036, artboard 06).

**A ordem das operações é a decisão cara aqui, e ela é sobre dinheiro.** A
consulta ao que já foi traduzido vem ANTES de tudo (RF4): antes do kill switch,
antes de carregar o turn, antes de qualquer chamada ao provedor. Uma tradução
já paga é resposta pronta — recusá-la porque o orçamento do dia estourou seria
cobrar o aluno pelo estado do caixa sem que nenhuma chamada nova fosse feita.
É o mesmo raciocínio do reenvio idempotente no ``StartTurnHandler`` (F11 do
CARD-015): o que já foi pago não passa pelo pedágio de novo.

**O que este caso de uso deliberadamente NÃO faz** (RF2): não cria ``Turn``,
não toca no histórico do professor e não escreve ``UsageEvent``. Traduzir é
leitura assistida, não interação pedagógica — se aparecesse no histórico, o
professor passaria a "lembrar" de uma conversa que não aconteceu, e a cota de
minutos do aluno mudaria por um botão que não gasta minuto nenhum.

**Onde o custo é registrado, e por que não é um ``UsageEvent``.** O RF3 pede
"registrado como consumo (``UsageEvent``)", mas a chave primária daquela tabela
é o ``turn_id`` — "um turn, um evento", invariante que o CARD-014 protege com
teste. Um turn traduzido já tem o evento da conversa, e um segundo INSERT é
recusado pelo banco. O custo é então congelado na **própria linha da tradução**
(``estimated_cost_usd``, mesma precisão e mesma regra de nulo) e somado ao
``ServiceBudget`` — que é o mecanismo que de fato faz o RNF3 valer. Ver a
decisão registrada no ADR-0066.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicecoach.application.ports.repositories import ConflictingWriteError
from voicecoach.application.result import Err, Ok, Result
from voicecoach.domain.translation import Translation, TranslationTarget
from voicecoach.domain.usage import estimate_llm_cost

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from decimal import Decimal
    from uuid import UUID

    from voicecoach.application.ports.repositories import (
        SessionRepository,
        TranslationRepository,
        TurnRepository,
        UnitOfWork,
    )
    from voicecoach.application.ports.service_budget import ServiceBudget
    from voicecoach.application.ports.teacher_llm import TokenUsage
    from voicecoach.application.ports.translator import Translator
    from voicecoach.domain.turn import Turn
    from voicecoach.domain.usage import LlmPrice

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TranslateText:
    """O comando: QUAL texto do produto, nunca o texto em si (RF1).

    ``target`` + ``index`` são uma **referência a recurso**. É a decisão de
    segurança do card: um campo ``text: str`` aqui transformaria o endpoint num
    proxy de LLM aberto, pago por nós.
    """

    turn_id: UUID
    target: TranslationTarget
    index: int
    student_id: UUID


@dataclass(frozen=True, slots=True)
class TranslationReady:
    """O texto em português. ``cached`` distingue "achei" de "acabei de pagar".

    O cliente pode ignorar o campo — o corpo é o mesmo nos dois casos —, mas é
    ele que torna o RF4 **observável** em teste e em log, em vez de uma
    promessa que ninguém consegue verificar de fora. Mesmo papel do
    ``replayed`` no ``TurnAccepted``.
    """

    text: str
    cached: bool


@dataclass(frozen=True, slots=True)
class TurnNotFound:
    """O turn não existe, OU não é do aluno da requisição.

    Um tipo só para os dois casos, como no CARD-032: um 404 idêntico não
    confirma a existência de um id para quem não é dono dele.
    """

    turn_id: UUID


@dataclass(frozen=True, slots=True)
class NothingToTranslate:
    """O recurso existe, mas aquele texto ainda não — ou nunca vai existir.

    O turn pode não ter resposta (ainda em processamento, ou falhou antes do
    professor) ou não ter a correção de índice pedido. Não é erro de
    infraestrutura nem bug de quem chamou: é o estado do recurso, e o cliente
    resolve mostrando o original.
    """

    turn_id: UUID
    target: TranslationTarget
    index: int


@dataclass(frozen=True, slots=True)
class ServiceBudgetExceeded:
    """O orçamento do produto estourou (RNF3) — vale para traduzir também.

    Vazio pela mesma razão do homônimo em ``start_turn``: não há "quando
    volta" que a API possa prometer com confiança, e a borda responde 503.
    """


type TranslateTextRejection = TurnNotFound | NothingToTranslate | ServiceBudgetExceeded


class TranslateTextHandler:
    """Devolve a tradução — da tabela quando já existe, do provedor quando não."""

    def __init__(
        self,
        *,
        turns: TurnRepository,
        sessions: SessionRepository,
        translations: TranslationRepository,
        translator: Translator,
        service_budget: ServiceBudget,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime],
        llm_price: Callable[[str], LlmPrice | None],
    ) -> None:
        self._turns = turns
        self._sessions = sessions
        self._translations = translations
        self._translator = translator
        self._budget = service_budget
        self._uow = unit_of_work
        self._clock = clock
        self._llm_price = llm_price

    async def handle(
        self, command: TranslateText
    ) -> Result[TranslationReady, TranslateTextRejection]:
        ja_traduzido = await self._translations.get(
            command.turn_id, command.target, command.index
        )
        if ja_traduzido is not None:
            # RF4: nem provedor, nem orçamento, nem custo. Já foi pago.
            return Ok(TranslationReady(text=ja_traduzido.text, cached=True))

        turn = await self._turns.get(command.turn_id)
        if turn is None:
            return Err(TurnNotFound(command.turn_id))

        session = await self._sessions.get(turn.session_id)
        if session is None or session.student_id != command.student_id:
            return Err(TurnNotFound(command.turn_id))

        origem = _texto_de_origem(turn, command.target, command.index)
        if origem is None:
            return Err(
                NothingToTranslate(command.turn_id, command.target, command.index)
            )

        agora = self._clock()
        # O kill switch vem DEPOIS da consulta (RF4 acima) e ANTES da chamada:
        # é o último ponto em que recusar ainda não custou dinheiro.
        if await self._budget.is_exceeded(when=agora):
            return Err(ServiceBudgetExceeded())

        traduzido = await self._translator.to_portuguese(origem)
        custo = self._custo(traduzido.usage)

        await self._translations.add(
            Translation(
                turn_id=command.turn_id,
                target=command.target,
                index=command.index,
                text=traduzido.text,
                model=traduzido.usage.model,
                created_at=agora,
                estimated_cost_usd=custo,
            )
        )
        try:
            await self._uow.commit()
        except ConflictingWriteError:
            # Outra requisição traduziu o MESMO texto entre a nossa consulta e o
            # nosso INSERT. As duas pagaram — a janela é real e aceita (ADR-0066)
            # —, mas só uma linha existe, e é a dela que o aluno lê.
            return await self._resolver_corrida(command)

        if custo is not None:
            # RNF3: entra no mesmo contador que o kill switch lê. Depois do
            # commit, porque somar ao orçamento um gasto cuja linha não foi
            # gravada faria o teto morder por um custo que ninguém consegue
            # auditar depois.
            await self._budget.add_cost(custo, when=agora)

        return Ok(TranslationReady(text=traduzido.text, cached=False))

    def _custo(self, usage: TokenUsage) -> Decimal | None:
        """Congela o custo na escrita (ADR-0051), ou ``None`` se não há preço.

        Mesma regra do ``ProcessTurn``: modelo fora da tabela **não vira zero**
        — zero é o custo verdadeiro do STT e do TTS locais, e gravar zero aqui
        faria o gasto com tradução parecer grátis em vez de desconhecido. O
        ERROR no log é o que torna a lacuna visível.
        """
        preco = self._llm_price(usage.model)
        if preco is None:
            logger.error(
                "tradução: modelo %r fora da tabela de preços; "
                "custo gravado como desconhecido",
                usage.model,
            )
            return None
        return estimate_llm_cost(
            input_tokens=usage.input_tokens,
            cache_creation_tokens=usage.cache_creation_input_tokens,
            cache_read_tokens=usage.cache_read_input_tokens,
            output_tokens=usage.output_tokens,
            price=preco,
        )

    async def _resolver_corrida(
        self, command: TranslateText
    ) -> Result[TranslationReady, TranslateTextRejection]:
        vencedora = await self._translations.get(
            command.turn_id, command.target, command.index
        )
        if vencedora is None:  # pragma: no cover - a chave composta torna impossível
            message = (
                f"unicidade recusou a tradução de {command.target}/{command.index} "
                f"do turn {command.turn_id}, mas nenhuma linha existe — "
                f"restrição diferente da esperada violou o INSERT."
            )
            raise ConflictingWriteError(message)
        return Ok(TranslationReady(text=vencedora.text, cached=True))


def _texto_de_origem(turn: Turn, target: TranslationTarget, index: int) -> str | None:
    """Resolve a referência do RF1 no texto real, ou ``None`` se não há texto.

    Função de módulo e não método: ela não depende de nenhuma porta, só do
    turn já carregado — e como função pura ela é testável sem montar o handler
    inteiro.
    """
    match target:
        case TranslationTarget.REPLY:
            return turn.reply_text
        case TranslationTarget.CORRECTION:
            if index >= len(turn.corrections):
                return None
            return turn.corrections[index].explanation
