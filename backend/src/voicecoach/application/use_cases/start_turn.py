"""Aceita a fala do aluno e devolve na hora — o caso de uso da borda (CARD-010).

**O que este handler é.** O espelho do ``ProcessTurn``: aquele faz o trabalho e
demora ~1,6 s; este aceita o trabalho e responde em milissegundos. É a divisão
que o ADR-0005 comprou — a API nunca fica esperando o professor pensar.

**Ele é o primeiro caso de uso do projeto a devolver ``Result``**, e a razão
está no ADR-0017: o gatilho que ficou escrito lá (*"o primeiro desfecho que é
normal do negócio e não bug"*) dispara aqui, com uma sutileza que o gatilho não
antecipou e que vale registrar.

O ADR-0017 listou ``Idempotency-Key`` repetida como candidata a **falha
esperada**. Ela não é falha nenhuma: a resposta certa é ``202`` com o **mesmo**
``turn_id``, o que é um desfecho de sucesso — só que um sucesso diferente do
outro, e o cliente pode querer saber qual dos dois foi. Por isso a repetição
vira ``Ok(TurnAccepted(..., replayed=True))``, e não ``Err``.

O que sobra como falha esperada de verdade é ``SessionNotFound``: o cliente
mandou uma sessão que não existe (id velho guardado no aparelho, banco
recriado em desenvolvimento). Não é bug de quem chama — é entrada do mundo — e
por isso não é exceção.

**O que continua sendo exceção**, e a fronteira precisa ficar visível:

- ``Session.start_turn`` numa sessão encerrada levanta
  ``InvalidStateTransitionError`` (ADR-0017 item 1). É invariante do agregado, e
  o agregado é quem a defende;
- ``TurnQueueError``, ``MediaStorageError`` e ``ConflictingWriteError`` são
  infraestrutura. Sobem, e a borda as traduz.

**A ordem das operações é a decisão cara**, e é a mesma regra do
``_gravar_trecho`` do worker: *storage antes do banco*. Uma linha apontando para
um objeto que não subiu é um 404 na mão do aluno; um objeto sem linha é lixo que
a retenção de 7 dias do ADR-0024 recolhe sozinha.

**A janela entre "criei" e "enfileirei" tem três estados de crash**, e ela é o
risco que o card nomeia:

1. crash antes do commit — nada aconteceu: nem chave, nem Turn. O retry do
   cliente cria normalmente (é o que a chave no Postgres compra sobre o
   ``SETNX``: lá a chave sobreviveria apontando para nada);
2. crash **entre o commit e o enfileiramento** — fica um Turn ``queued`` que
   ninguém vai processar. Duas saídas, e as duas existem: o retry do cliente com
   a mesma chave cai no caminho ``replayed`` e **enfileira de novo** (por isso o
   ``enqueue`` acontece também nesse caminho, e é seguro — o ``_job_id`` do
   ``ArqTurnQueue`` o torna idempotente); e o **CARD-025** varre os que ninguém
   reenviar;
3. crash depois de enfileirar, antes de responder — o retry recebe o mesmo
   ``turn_id`` e o mesmo job. Nada duplica.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from voicecoach.application.ports.repositories import ConflictingWriteError
from voicecoach.application.quota_window import janela_diaria
from voicecoach.application.result import Err, Ok, Result
from voicecoach.domain.media_keys import input_key

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from voicecoach.application.ports.media_storage import MediaStorage
    from voicecoach.application.ports.repositories import (
        SessionRepository,
        TurnRepository,
        UnitOfWork,
        UsageEventRepository,
    )
    from voicecoach.application.ports.service_budget import ServiceBudget
    from voicecoach.application.ports.turn_queue import TurnQueue


@dataclass(frozen=True, slots=True)
class StartTurn:
    """O comando: a fala do aluno, já lida e medida pela borda.

    ``audio`` são os **bytes codificados**, exatamente como chegaram — a mesma
    decisão do ``AudioInput`` do ADR-0029. O caso de uso não decodifica nada;
    quem precisou dos números (duração) foi a borda, que valida a entrada.

    ``extension`` e ``content_type`` andam juntos e não são a mesma coisa: a
    extensão entra na **chave** do storage (ADR-0024) e o content type vai no
    objeto, porque quem baixa é o player do aluno direto do bucket.

    ``idempotency_key`` é obrigatória e sem default. Um default aqui (``None``,
    "gera uma") transformaria "o cliente esqueceu o cabeçalho" num turn extra
    cobrado, em silêncio.
    """

    session_id: UUID
    idempotency_key: str
    audio: bytes
    content_type: str
    extension: str
    audio_duration: timedelta


@dataclass(frozen=True, slots=True)
class TurnAccepted:
    """O turn está aceito e a caminho.

    ``replayed`` distingue "criei agora" de "você já tinha mandado esta". O
    cliente pode ignorar o campo — o contrato do ``202`` é o mesmo nos dois
    casos —, mas ele é o que torna a idempotência **observável** em teste e em
    log, em vez de uma promessa que ninguém consegue verificar de fora.
    """

    turn_id: UUID
    replayed: bool


@dataclass(frozen=True, slots=True)
class SessionNotFound:
    """A sessão referida no caminho não existe.

    Um **valor**, não uma exceção (ADR do ``Result``): carrega o id para que a
    borda monte o Problem Details sem precisar reler o comando.
    """

    session_id: UUID


@dataclass(frozen=True, slots=True)
class DailyQuotaExceeded:
    """O student excedeu a cota diária, em minutos OU em turns (ADR-0063).

    ``reset_at`` é a próxima meia-noite no fuso da cota — a borda o expõe como
    ``retry_after`` do Problem Details. Não diz QUAL dos dois tetos mordeu: a
    tela promete minutos, e expor "foi o teto de turns" vazaria mecânica de
    custo interna que o aluno não contratou saber (CARD-033, RF5).
    """

    reset_at: datetime


@dataclass(frozen=True, slots=True)
class ServiceBudgetExceeded:
    """O orçamento do produto (diário ou mensal) estourou — não é do student.

    Vazio de propósito: ao contrário da cota, não há "quando volta" que a API
    possa prometer com confiança (o teto mensal só reseta no fim do mês), e a
    borda responde ``503`` — o mesmo vocabulário de "dependência indisponível"
    que o resto da API já usa para "tente de novo mais tarde".
    """


@dataclass(frozen=True, slots=True)
class SessionEnded:
    """A sessão já foi encerrada — a fala chegou atrasada (CARD-031, RF3).

    **Não é um bug de quem chamou.** Uma fala gravada offline pode chegar ao
    servidor depois de o aluno ter encerrado a sessão no meio do caminho —
    o próprio `Session.start_turn` documenta o cenário. Antes deste card, o
    mesmo fato virava `InvalidStateTransitionError` → 409 `invalid-state`,
    indistinguível de qualquer outra violação de estado. Agora tem URN
    própria: o app consegue dizer "sua fala de ontem não entrou porque a
    sessão fechou", em vez de "algo deu errado".
    """

    session_id: UUID


# União fechada do que a borda faz da API de fora de "aceito" (`TurnAccepted`).
# `match` + `assert_never` na rota é o que garante que acrescentar um motivo
# aqui sem tratá-lo lá quebre no mypy, não em produção (mesmo padrão do
# `TeacherEvent`/`RejectionReason`).
type StartTurnRejection = (
    SessionNotFound | DailyQuotaExceeded | ServiceBudgetExceeded | SessionEnded
)


class StartTurnHandler:
    """Recebe o áudio, cria o Turn e o entrega à fila."""

    def __init__(
        self,
        *,
        turns: TurnRepository,
        sessions: SessionRepository,
        usage_events: UsageEventRepository,
        unit_of_work: UnitOfWork,
        storage: MediaStorage,
        queue: TurnQueue,
        service_budget: ServiceBudget,
        clock: Callable[[], datetime],
        new_turn_id: Callable[[], UUID],
        daily_quota_spoken: timedelta,
        daily_quota_turns: int,
    ) -> None:
        self._turns = turns
        self._sessions = sessions
        self._usage = usage_events
        self._uow = unit_of_work
        self._storage = storage
        self._queue = queue
        self._budget = service_budget
        self._clock = clock
        self._new_turn_id = new_turn_id
        # Números crus, não `Settings`: `application` não importa `config`
        # (ADR-0013) — a composition root já leu e resolveu os dois valores.
        self._daily_quota_spoken = daily_quota_spoken
        self._daily_quota_turns = daily_quota_turns

    async def handle(
        self, command: StartTurn
    ) -> Result[TurnAccepted, StartTurnRejection]:
        ja_existe = await self._turns.get_by_idempotency_key(command.idempotency_key)
        if ja_existe is not None:
            # F11 (CARD-015): reenvio idempotente NUNCA consome cota de novo —
            # é o mesmo turn, não um turn a mais. Por isso o replay sai ANTES
            # de qualquer checagem de cota ou orçamento.
            return await self._repetir(ja_existe.id)

        session = await self._sessions.get(command.session_id)
        if session is None:
            return Err(SessionNotFound(command.session_id))

        agora = self._clock()
        # Kill switch ANTES da cota por student: é a checagem mais barata (uma
        # leitura Redis, sem índice de banco nenhum) e é a que protege o
        # orçamento do produto inteiro, não só deste aluno.
        if await self._budget.is_exceeded(when=agora):
            return Err(ServiceBudgetExceeded())

        inicio_do_dia, inicio_de_amanha = janela_diaria(agora)
        consumo = await self._usage.totals_for_student(
            session.student_id, since=inicio_do_dia, until=inicio_de_amanha
        )
        # `unpriced_turns` não pede tratamento à parte aqui (ADR-0063): a soma
        # de `turns`/`spoken` já inclui todo turn, com preço conhecido ou não.
        if (
            consumo.turns >= self._daily_quota_turns
            or consumo.spoken >= self._daily_quota_spoken
        ):
            return Err(DailyQuotaExceeded(reset_at=inicio_de_amanha))

        # RF3/RNF2 (CARD-031): quem pergunta antes é a aplicação — a invariante
        # continua morando em `Session.start_turn` (chamado abaixo, que também
        # recusaria), mas aqui ela vira `Err` tipado ANTES de qualquer efeito
        # colateral (nada sobe ao storage por uma sessão que já terminou).
        if not session.is_active:
            return Err(SessionEnded(session.id))

        turn_id = self._new_turn_id()
        chave = input_key(session.student_id, session.id, turn_id, command.extension)
        # Storage ANTES do banco: a mesma ordem do `_gravar_trecho` do worker, e
        # pelo mesmo motivo. Uma linha apontando para um objeto que não subiu é
        # um 404 na mão do aluno; o inverso é lixo com retenção de 7 dias.
        await self._storage.put(chave, command.audio, command.content_type)

        # A fábrica é da `Session`, e a checagem de `is_active` já aconteceu
        # acima — esta chamada nunca deveria recusar na prática. Ela continua
        # aqui como defesa em profundidade do agregado (RNF2): se um dia outro
        # caminho de código chamar `start_turn` sem checar antes, a invariante
        # ainda protege, só que como exceção (bug de orquestração), não `Err`.
        turn = session.start_turn(
            turn_id=turn_id,
            input_audio_ref=chave,
            audio_duration=command.audio_duration,
            now=self._clock(),
            idempotency_key=command.idempotency_key,
        )
        await self._turns.add(turn)

        try:
            await self._uow.commit()
        except ConflictingWriteError:
            # Perdemos a corrida: outra requisição com a MESMA chave comitou
            # entre a nossa consulta e o nosso INSERT. Quem chegou primeiro tem
            # o turn válido; nós reconsultamos e devolvemos o id dele. O objeto
            # que subimos ao storage fica órfão e a retenção o recolhe.
            return await self._resolver_corrida(command.idempotency_key)

        return await self._repetir(turn.id, replayed=False)

    async def _repetir(
        self, turn_id: UUID, *, replayed: bool = True
    ) -> Ok[TurnAccepted]:
        """Enfileira e responde — o caminho comum ao turn novo e ao repetido.

        Enfileirar **também** no caminho repetido é o que cura o estado de crash
        2 (Turn gravado, job nunca publicado): o retry natural do cliente
        conserta sozinho. É seguro porque o ``ArqTurnQueue`` publica com
        ``_job_id=turn:{id}`` — o segundo pedido do mesmo turn não vira segundo
        job, e um turn já concluído é no-op no handler do worker (ADR-0037).
        """
        await self._queue.enqueue(turn_id)
        return Ok(TurnAccepted(turn_id=turn_id, replayed=replayed))

    async def _resolver_corrida(self, key: str) -> Ok[TurnAccepted]:
        vencedor = await self._turns.get_by_idempotency_key(key)
        if vencedor is None:  # pragma: no cover - o índice único torna impossível
            message = (
                f"unicidade recusou a chave {key!r}, mas nenhum turn a possui — "
                f"restrição diferente da esperada violou o INSERT."
            )
            raise ConflictingWriteError(message)
        return await self._repetir(vencedor.id)
