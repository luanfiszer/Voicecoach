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
from typing import TYPE_CHECKING

from voicecoach.application.ports.repositories import ConflictingWriteError
from voicecoach.application.result import Err, Ok, Result
from voicecoach.domain.media_keys import input_key

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime, timedelta
    from uuid import UUID

    from voicecoach.application.ports.media_storage import MediaStorage
    from voicecoach.application.ports.repositories import (
        SessionRepository,
        TurnRepository,
        UnitOfWork,
    )
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


class StartTurnHandler:
    """Recebe o áudio, cria o Turn e o entrega à fila."""

    def __init__(
        self,
        *,
        turns: TurnRepository,
        sessions: SessionRepository,
        unit_of_work: UnitOfWork,
        storage: MediaStorage,
        queue: TurnQueue,
        clock: Callable[[], datetime],
        new_turn_id: Callable[[], UUID],
    ) -> None:
        self._turns = turns
        self._sessions = sessions
        self._uow = unit_of_work
        self._storage = storage
        self._queue = queue
        self._clock = clock
        self._new_turn_id = new_turn_id

    async def handle(self, command: StartTurn) -> Result[TurnAccepted, SessionNotFound]:
        ja_existe = await self._turns.get_by_idempotency_key(command.idempotency_key)
        if ja_existe is not None:
            return await self._repetir(ja_existe.id)

        session = await self._sessions.get(command.session_id)
        if session is None:
            return Err(SessionNotFound(command.session_id))

        turn_id = self._new_turn_id()
        chave = input_key(session.student_id, session.id, turn_id, command.extension)
        # Storage ANTES do banco: a mesma ordem do `_gravar_trecho` do worker, e
        # pelo mesmo motivo. Uma linha apontando para um objeto que não subiu é
        # um 404 na mão do aluno; o inverso é lixo com retenção de 7 dias.
        await self._storage.put(chave, command.audio, command.content_type)

        # A fábrica é da `Session` e não um construtor de `Turn`: só quem conhece
        # o próprio estado pode recusar mais um turno. Sessão encerrada levanta
        # `InvalidStateTransitionError` — invariante, não desfecho (ADR-0017).
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
