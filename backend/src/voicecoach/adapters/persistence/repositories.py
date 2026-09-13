"""Repositórios concretos sobre SQLAlchemy (ADR-0004).

Nenhuma destas classes declara que implementa a porta: elas satisfazem o
``Protocol`` de ``application/ports`` **estruturalmente**, por ter os métodos
com a assinatura certa. A verificação acontece no ``mypy``, no ponto em que uma
delas é atribuída a uma variável tipada com a porta — não em runtime.

Nenhum método comita. A transação pertence a quem abriu a sessão (ADR-0004:
unidade de trabalho explícita) — do contrário seria impossível gravar Turn e
Correction atomicamente no mesmo turno (CARD-013).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

# **Em runtime, não sob `TYPE_CHECKING`**: `dict[UUID, int](...)` e
# `dict[CorrectionType, int](...)` SUBSCREVEM o genérico, e subscrever avalia
# o nome de verdade — `from __future__ import annotations` adia anotações,
# não expressões. Um nome só para o type checker aqui vira `NameError` na
# primeira chamada real, invisível para mypy e para qualquer teste com fake.
from uuid import UUID

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.orm import selectinload

from voicecoach.adapters.persistence import mappers
from voicecoach.adapters.persistence.models import (
    CorrectionRow,
    CredentialRow,
    EmailVerificationTokenRow,
    PasswordResetTokenRow,
    RefreshTokenRow,
    SessionRow,
    StudentRow,
    TranslationRow,
    TurnRow,
    UsageEventRow,
)

# A exceção mora na PORTA desde o CARD-034: quem a captura é `application`,
# que não pode importar `adapters`. Daqui ela é apenas levantada.
from voicecoach.application.ports.repositories import RowNotFoundError
from voicecoach.domain.correction import CorrectionType
from voicecoach.domain.session import SessionDigest as _SessionDigest
from voicecoach.domain.session import SessionSummary
from voicecoach.domain.turn import TurnStatus
from voicecoach.domain.usage import StudentUsageTotals

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from voicecoach.domain.auth import (
        Credential,
        EmailVerificationToken,
        PasswordResetToken,
        RefreshToken,
    )
    from voicecoach.domain.session import Session, SessionDigest
    from voicecoach.domain.student import Student
    from voicecoach.domain.translation import Translation, TranslationTarget
    from voicecoach.domain.turn import Turn
    from voicecoach.domain.usage import UsageEvent


class SqlAlchemyStudentRepository:
    """Implementa ``application.ports.repositories.StudentRepository``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, student: Student) -> None:
        self._session.add(mappers.student_to_row(student))

    async def get(self, student_id: UUID) -> Student | None:
        row = await self._session.get(StudentRow, student_id)
        return None if row is None else mappers.student_from_row(row)

    async def mark_deleted(self, student_id: UUID, when: datetime) -> None:
        stmt = (
            update(StudentRow)
            .where(StudentRow.id == student_id, StudentRow.deleted_at.is_(None))
            .values(deleted_at=when)
        )
        await self._session.execute(stmt)

    async def list_pending_purge(self, *, limit: int) -> list[UUID]:
        stmt = (
            select(StudentRow.id)
            .where(StudentRow.deleted_at.isnot(None))
            .order_by(StudentRow.deleted_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, student_id: UUID) -> None:
        stmt = delete(StudentRow).where(StudentRow.id == student_id)
        await self._session.execute(stmt)


class SqlAlchemyCredentialRepository:
    """Implementa ``application.ports.auth_repositories.CredentialRepository``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, credential: Credential) -> None:
        self._session.add(mappers.credential_to_row(credential))

    async def get_by_email(self, email: str) -> Credential | None:
        stmt = select(CredentialRow).where(CredentialRow.email == email)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if row is None else mappers.credential_from_row(row)

    async def get_by_student_id(self, student_id: UUID) -> Credential | None:
        stmt = select(CredentialRow).where(CredentialRow.student_id == student_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if row is None else mappers.credential_from_row(row)

    async def mark_email_verified(self, student_id: UUID, when: datetime) -> None:
        stmt = (
            update(CredentialRow)
            .where(CredentialRow.student_id == student_id)
            .values(email_verified_at=when)
        )
        await self._session.execute(stmt)

    async def update_password_hash(self, student_id: UUID, password_hash: str) -> None:
        stmt = (
            update(CredentialRow)
            .where(CredentialRow.student_id == student_id)
            .values(password_hash=password_hash)
        )
        await self._session.execute(stmt)


class SqlAlchemyRefreshTokenRepository:
    """Implementa ``application.ports.auth_repositories.RefreshTokenRepository``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: RefreshToken) -> None:
        self._session.add(mappers.refresh_token_to_row(token))

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshTokenRow).where(RefreshTokenRow.token_hash == token_hash)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if row is None else mappers.refresh_token_from_row(row)

    async def mark_revoked(self, token_id: UUID, when: datetime) -> None:
        stmt = (
            update(RefreshTokenRow)
            .where(RefreshTokenRow.id == token_id)
            .values(revoked_at=when)
        )
        await self._session.execute(stmt)

    async def revoke_family(self, family_id: UUID, when: datetime) -> None:
        """Revoga todos os elos VIVOS da família — a detecção de reuso do ADR-0007.

        ``revoked_at.is_(None)`` no ``WHERE`` é o que preserva o instante
        original de cada revogação anterior: sem ele, um reuso detectado
        pisaria no ``revoked_at`` de um elo que já tinha sido rotacionado
        normalmente antes, trocando "quando" por "agora" sem motivo.
        """
        stmt = (
            update(RefreshTokenRow)
            .where(
                RefreshTokenRow.family_id == family_id,
                RefreshTokenRow.revoked_at.is_(None),
            )
            .values(revoked_at=when)
        )
        await self._session.execute(stmt)

    async def revoke_all_for_student(self, student_id: UUID, when: datetime) -> None:
        """Troca de senha desloga tudo — todas as famílias, não só uma."""
        stmt = (
            update(RefreshTokenRow)
            .where(
                RefreshTokenRow.student_id == student_id,
                RefreshTokenRow.revoked_at.is_(None),
            )
            .values(revoked_at=when)
        )
        await self._session.execute(stmt)


class SqlAlchemyEmailVerificationTokenRepository:
    """Implementa ``EmailVerificationTokenRepository`` (``ports/auth_repositories``)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: EmailVerificationToken) -> None:
        self._session.add(mappers.verification_token_to_row(token))

    async def get_by_hash(self, token_hash: str) -> EmailVerificationToken | None:
        stmt = select(EmailVerificationTokenRow).where(
            EmailVerificationTokenRow.token_hash == token_hash
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if row is None else mappers.verification_token_from_row(row)

    async def mark_used(self, token_id: UUID, when: datetime) -> None:
        stmt = (
            update(EmailVerificationTokenRow)
            .where(EmailVerificationTokenRow.id == token_id)
            .values(used_at=when)
        )
        await self._session.execute(stmt)


class SqlAlchemyPasswordResetTokenRepository:
    """Implementa ``PasswordResetTokenRepository`` (``ports/auth_repositories``)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: PasswordResetToken) -> None:
        self._session.add(mappers.password_reset_token_to_row(token))

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        stmt = select(PasswordResetTokenRow).where(
            PasswordResetTokenRow.token_hash == token_hash
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if row is None else mappers.password_reset_token_from_row(row)

    async def mark_used(self, token_id: UUID, when: datetime) -> None:
        stmt = (
            update(PasswordResetTokenRow)
            .where(PasswordResetTokenRow.id == token_id)
            .values(used_at=when)
        )
        await self._session.execute(stmt)


class SqlAlchemySessionRepository:
    """Implementa ``application.ports.repositories.SessionRepository``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: Session) -> None:
        self._session.add(mappers.session_to_row(session))

    async def get(self, session_id: UUID) -> Session | None:
        row = await self._session.get(SessionRow, session_id)
        return None if row is None else mappers.session_from_row(row)

    async def update(self, session: Session) -> None:
        row = await self._session.get(SessionRow, session.id)
        if row is None:
            message = f"Session {session.id} não existe."
            raise RowNotFoundError(message)
        mappers.apply_session(session, row)

    async def list_inactive(self, *, before: datetime, limit: int) -> list[UUID]:
        """Uma query agregada, com a inatividade decidida no ``HAVING``.

        ``coalesce(max(created_at), started_at)`` é o marco de atividade (RF2):
        o último turn quando existe, o início da sessão quando não. Sem o
        ``coalesce``, a sessão sem turn nenhum teria marco ``NULL`` — e
        ``NULL < :before`` é ``NULL``, não ``true``, então ela nunca seria
        candidata. É o mesmo buraco que o ``list_stale`` já tinha nomeado para
        o turn ``queued``.

        ``count(...) filter (where ...)`` é o `FILTER` do Postgres — um
        agregado condicional. Ele implementa o RF3: a sessão com qualquer turn
        em ``queued``/``processing`` é excluída pelo ``HAVING``, não por um
        segundo round-trip.
        """
        em_andamento = func.count(TurnRow.id).filter(
            TurnRow.status.in_((TurnStatus.QUEUED, TurnStatus.PROCESSING))
        )
        marco = func.coalesce(func.max(TurnRow.created_at), SessionRow.started_at)
        stmt = (
            select(SessionRow.id)
            .select_from(SessionRow)
            .outerjoin(TurnRow, TurnRow.session_id == SessionRow.id)
            .where(SessionRow.ended_at.is_(None))
            .group_by(SessionRow.id, SessionRow.started_at)
            .having(marco < before)
            .having(em_andamento == 0)
            .order_by(marco)
            .limit(limit)
        )
        return list((await self._session.scalars(stmt)).all())

    async def try_end(self, session_id: UUID, now: datetime) -> datetime:
        """`UPDATE` condicional, atômico — a resolução real do RNF4.

        `COALESCE(ended_at, :now)` só troca o valor se ele ainda for nulo;
        senão mantém o que já estava lá. Não há leitura-depois-escrita: é UM
        `UPDATE`, e o Postgres serializa dois `UPDATE` concorrentes na MESMA
        linha por construção (o segundo espera o primeiro comitar e só então
        aplica o seu `COALESCE` — que a essa altura já vê o valor definitivo).
        Não existe forma de dois processos, cada um numa conexão própria,
        produzirem `ended_at` diferentes por esta via.
        """
        stmt = (
            update(SessionRow)
            .where(SessionRow.id == session_id)
            .values(ended_at=func.coalesce(SessionRow.ended_at, now))
            .returning(SessionRow.ended_at)
        )
        resultado = (await self._session.execute(stmt)).one_or_none()
        if resultado is None:
            message = f"Session {session_id} não existe."
            raise RowNotFoundError(message)
        ended_at: datetime = resultado[0]
        return ended_at

    async def list_for_student(
        self, student_id: UUID, *, since: datetime
    ) -> list[SessionDigest]:
        """DUAS queries agregadas, não uma por sessão (RNF1) — e não UMA só.

        **Por que duas e não um `JOIN` triplo.** `Correction` pende de `Turn`,
        que pende de `Session`: juntar as três numa query só multiplicaria cada
        turn pelo número de correções dele, e `SUM(audio_duration)` passaria a
        contar o mesmo áudio N vezes. É o *fan-out* clássico, e ele não dá
        erro — dá um número maior, em silêncio. Duas agregações separadas, cada
        uma com o seu `GROUP BY`, custam uma query a mais e não têm esse modo
        de falha. O que o RNF1 exige é que o número **não cresça com o número
        de sessões**, e duas é constante.

        **`outerjoin` e não `join`** (o objetivo de aprendizado do card): com
        `join` interno, a sessão que o aluno abriu e abandonou simplesmente
        some da listagem — e o RF4 pede que ela apareça com zeros.
        """
        agregado = (
            select(
                SessionRow.id,
                SessionRow.started_at,
                SessionRow.ended_at,
                func.count(TurnRow.id),
                func.coalesce(func.sum(TurnRow.audio_duration), timedelta(0)),
                func.max(TurnRow.created_at),
            )
            .select_from(SessionRow)
            .outerjoin(TurnRow, TurnRow.session_id == SessionRow.id)
            .where(SessionRow.student_id == student_id, SessionRow.started_at >= since)
            .group_by(SessionRow.id, SessionRow.started_at, SessionRow.ended_at)
            .order_by(SessionRow.started_at.desc())
        )
        linhas = (await self._session.execute(agregado)).all()

        correcoes = await self._session.execute(
            select(TurnRow.session_id, func.count())
            .select_from(CorrectionRow)
            .join(TurnRow, TurnRow.id == CorrectionRow.turn_id)
            .join(SessionRow, SessionRow.id == TurnRow.session_id)
            .where(SessionRow.student_id == student_id, SessionRow.started_at >= since)
            .group_by(TurnRow.session_id)
        )
        por_sessao = dict[UUID, int](correcoes.tuples().all())

        return [
            _SessionDigest(
                id=session_id,
                started_at=comecou,
                ended_at=terminou,
                spoken=falado,
                turns=quantos,
                corrections=por_sessao.get(session_id, 0),
                last_turn_at=ultimo,
            )
            for session_id, comecou, terminou, quantos, falado, ultimo in linhas
        ]

    async def summary_for(self, session_id: UUID) -> SessionSummary:
        """Duas queries agregadas — nunca uma por turn (mesma disciplina do
        `totals_for_student`, CARD-014)."""
        turnos = (
            await self._session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(TurnRow.audio_duration), timedelta(0)),
                ).where(TurnRow.session_id == session_id)
            )
        ).one()
        turns, spoken = turnos

        correcoes = await self._session.execute(
            select(CorrectionRow.type, func.count())
            .select_from(CorrectionRow)
            .join(TurnRow, TurnRow.id == CorrectionRow.turn_id)
            .where(TurnRow.session_id == session_id)
            .group_by(CorrectionRow.type)
        )
        # `.tuples()` e não `.all()`: um `Row` do SQLAlchemy é iterável em
        # runtime mas não é um `tuple` para o mypy — `.tuples()` é quem
        # devolve o tipo que o `dict()` abaixo consegue verificar.
        por_tipo = dict[CorrectionType, int](correcoes.tuples().all())

        return SessionSummary(spoken=spoken, turns=turns, corrections_by_type=por_tipo)

    async def delete_all_for_student(self, student_id: UUID) -> int:
        """Chamado depois de `TurnRepository.delete_all_for_student` (CARD-051,
        ADR-0069) — `turns.session_id` não tem `ON DELETE CASCADE`, então uma
        sessão com turn vivo bloquearia este `DELETE`."""
        stmt = delete(SessionRow).where(SessionRow.student_id == student_id)
        result = await self._session.execute(stmt)
        # `Result[Any]` é o tipo genérico de `execute`; um `DELETE` sempre
        # devolve o `CursorResult` concreto, que é quem tem `.rowcount`.
        rowcount: int = result.rowcount  # type: ignore[attr-defined]
        return rowcount


class SqlAlchemyTurnRepository:
    """Implementa ``application.ports.repositories.TurnRepository``.

    **Toda leitura de ``TurnRow`` carrega os trechos junto** (ADR-0023). Não é
    otimização: no SQLAlchemy async **não existe lazy loading**. Quem carregasse
    a linha sem pedir a coleção receberia um `Turn` que estoura ao ser mapeado —
    `MissingGreenlet`, ou o `InvalidRequestError` explícito do
    `lazy="raise_on_sql"` declarado no modelo.

    É o contraste que morde para quem vem do EF Core: lá, esquecer o
    ``.Include()`` custa um SELECT N+1 silencioso e o código continua correto.
    Aqui, esquecer é erro em runtime — o que é pior de descobrir e melhor de
    ter descoberto, porque carregamento vira decisão explícita por caso de uso
    em vez de default herdado.
    """

    # `selectinload` emite um SELECT extra com `WHERE turn_id IN (...)`, em vez
    # do JOIN do `joinedload`. Para coleção é a escolha certa: o JOIN
    # multiplicaria as colunas do turn por trecho (produto cartesiano) e o
    # `order_by` do relationship teria que competir com a ordenação da query.
    #
    # **São dois, e a lista é o contrato de carregamento deste repositório.**
    # Esquecer o segundo não é N+1 silencioso — é
    # `InvalidRequestError: 'TurnRow.corrections' is not available due to
    # lazy='raise_on_sql'`, na hora, demonstrado no CARD-013 injetando a omissão.
    # É o contraste que morde para quem vem do EF Core: lá o `.Include()`
    # esquecido custa desempenho e o código continua correto; aqui ele para o
    # pipeline, o que é pior de descobrir e muito melhor de ter descoberto.
    _COM_FILHAS = (
        selectinload(TurnRow.audio_chunks),
        selectinload(TurnRow.corrections),
    )

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, turn: Turn) -> None:
        self._session.add(mappers.turn_to_row(turn))

    async def get(self, turn_id: UUID) -> Turn | None:
        row = await self._session.get(TurnRow, turn_id, options=self._COM_FILHAS)
        return None if row is None else mappers.turn_from_row(row)

    async def get_by_idempotency_key(self, key: str) -> Turn | None:
        """Busca pelo índice único parcial ``ix_turns_idempotency_key``.

        O eager load dos trechos vem junto pelo mesmo motivo do ``get``: sem
        ele o mapeador estoura ao tocar a coleção (``lazy="raise_on_sql"``).
        """
        stmt = (
            select(TurnRow)
            .where(TurnRow.idempotency_key == key)
            .options(*self._COM_FILHAS)
        )
        row = (await self._session.scalars(stmt)).one_or_none()
        return None if row is None else mappers.turn_from_row(row)

    async def update(self, turn: Turn) -> None:
        """Grava o novo estado de um Turn já persistido.

        Precisa existir porque a entidade não é o objeto mapeado: mudá-la em
        memória não sensibiliza sessão nenhuma. É o oposto do change tracking do
        EF Core — aqui, gravar é sempre um pedido explícito.

        O eager load é tão obrigatório aqui quanto no ``get``: ``apply_turn``
        precisa comparar os trechos já gravados com os da entidade para saber
        quais acrescentar.
        """
        row = await self._session.get(TurnRow, turn.id, options=self._COM_FILHAS)
        if row is None:
            message = f"Turn {turn.id} não existe."
            raise RowNotFoundError(message)
        mappers.apply_turn(turn, row)

    async def try_discard(self, turn_id: UUID, now: datetime) -> datetime | None:
        """`CASE` atômico: as duas condições do RF2 num só `UPDATE` (CARD-032).

        Quando ``status != completed``: `COALESCE(discarded_at, now)` — marca
        se ainda não estava marcado, mantém se já estava (RNF1). Quando
        ``status == completed``: mantém ``discarded_at`` como está — que é
        `None` se nunca foi descartado (RF2 recusa) ou o instante antigo se
        JÁ tinha sido descartado antes de completar (RF6: o desfecho é
        "descartado e completo ao mesmo tempo", não uma corrida com vencedor
        arbitrário).
        """
        novo_valor = case(
            (
                TurnRow.status != TurnStatus.COMPLETED.value,
                func.coalesce(TurnRow.discarded_at, now),
            ),
            else_=TurnRow.discarded_at,
        )
        stmt = (
            update(TurnRow)
            .where(TurnRow.id == turn_id)
            .values(discarded_at=novo_valor)
            .returning(TurnRow.discarded_at)
        )
        resultado = (await self._session.execute(stmt)).one_or_none()
        if resultado is None:
            message = f"Turn {turn_id} não existe."
            raise RowNotFoundError(message)
        discarded_at: datetime | None = resultado[0]
        return discarded_at

    async def delete_all_for_student(self, student_id: UUID) -> int:
        """Cascateia (`ON DELETE CASCADE`) para correção, trecho e tradução —
        **não** para `usage_events`, cuja FK de `turn_id` o ADR-0069 removeu
        exatamente para que o custo já incorrido sobreviva a este `DELETE`.
        """
        subquery = select(SessionRow.id).where(SessionRow.student_id == student_id)
        stmt = delete(TurnRow).where(TurnRow.session_id.in_(subquery))
        result = await self._session.execute(stmt)
        rowcount: int = result.rowcount  # type: ignore[attr-defined]  # ver SessionRepository
        return rowcount

    async def list_by_session(self, session_id: UUID, *, limit: int) -> list[Turn]:
        """Os últimos ``limit`` turnos concluídos da sessão, em ordem cronológica.

        **A query ordena ao contrário do resultado, e isso é o ponto.** Para
        pegar os N mais RECENTES é preciso ordenar decrescente e cortar; para
        montar o histórico do professor é preciso a ordem cronológica. Inverter
        no banco e reinverter em Python é mais barato e mais óbvio que uma
        subquery, e o `limit` mantém o custo constante numa sessão longa.

        O eager load dos trechos vem junto por obrigação, não por escolha: sem
        ele o `turn_from_row` estoura com `MissingGreenlet` ao tocar a coleção
        (`lazy="raise_on_sql"` no modelo). O histórico não usa os trechos — mas
        o mapeador é um só, e ter um mapeador "parcial" para economizar um
        SELECT seria trocar um custo medido por um modo de falha novo.
        """
        stmt = (
            select(TurnRow)
            .where(
                TurnRow.session_id == session_id,
                TurnRow.status == TurnStatus.COMPLETED,
            )
            .order_by(TurnRow.created_at.desc())
            .limit(limit)
            .options(*self._COM_FILHAS)
        )
        linhas = (await self._session.scalars(stmt)).all()
        return [mappers.turn_from_row(linha) for linha in reversed(linhas)]

    async def list_stale(self, *, before: datetime, limit: int) -> list[UUID]:
        """Os ids dos turns travados. **A única leitura deste repositório sem
        ``_COM_FILHAS``, e a ausência é o desenho.**

        Ela não mapeia entidade nenhuma: o ``select(TurnRow.id)`` traz colunas,
        não linhas mapeadas, então não há coleção para o ``lazy="raise_on_sql"``
        recusar. Quem varre relê cada turn pelo ``get`` — que carrega os trechos
        por obrigação — e é de lá que sai o ``delivered_partially`` do evento.

        ``coalesce`` e não dois ramos: um turn ``queued`` tem
        ``started_processing_at`` nulo, e ``NULL < :before`` é ``NULL`` em SQL,
        não ``true``. Sem o ``coalesce``, todo turn que o worker nunca pegou
        ficaria invisível para a varredura **exatamente no caso** que o CARD-025
        existe para cobrir — e o teste de status passaria, porque o caso de
        ``processing`` funcionaria.

        ``order_by`` pelo mesmo marco: com o lote limitado, o mais antigo é quem
        tem mais direito à vaga. Sem ordenação explícita o Postgres não promete
        ordem nenhuma, e o turn travado há uma hora poderia ficar de fora de toda
        rodada, para sempre.
        """
        parado_desde = func.coalesce(TurnRow.started_processing_at, TurnRow.created_at)
        stmt = (
            select(TurnRow.id)
            .where(
                TurnRow.status.in_((TurnStatus.QUEUED, TurnStatus.PROCESSING)),
                parado_desde < before,
            )
            .order_by(parado_desde.asc())
            .limit(limit)
        )
        return list((await self._session.scalars(stmt)).all())


class SqlAlchemyUsageEventRepository:
    """Implementa ``application.ports.repositories.UsageEventRepository``.

    **Nenhum ``selectinload`` aqui, e a ausência é o desenho** (ADR-0051): esta
    tabela não tem relacionamento carregável nenhum. É o contraste deliberado com
    o ``SqlAlchemyTurnRepository``, cuja lista ``_COM_FILHAS`` é o contrato de
    carregamento do agregado.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: UsageEvent) -> None:
        self._session.add(mappers.usage_event_to_row(event))

    async def get(self, turn_id: UUID) -> UsageEvent | None:
        row = await self._session.get(UsageEventRow, turn_id)
        return None if row is None else mappers.usage_event_from_row(row)

    async def totals_for_student(
        self, student_id: UUID, *, since: datetime, until: datetime
    ) -> StudentUsageTotals:
        """Soma **no banco**, sem carregar entidade nenhuma.

        `func.sum` e `func.count` do SQLAlchemy montam a agregação em SQL: o que
        volta são quatro escalares, não N linhas mapeadas para N objetos. Numa
        tabela que cresce um registro por turn do produto inteiro, a diferença
        entre as duas leituras é a diferença entre uma query constante e uma que
        piora todo mês — e esta aqui é a única deste card que o CARD-015 vai
        chamar **dentro do POST**.

        Equivalente mental: é um `SELECT COUNT/SUM` escrito à mão, não um
        `.ToList().Sum()` do LINQ to Objects — que é exatamente o erro que a
        forma preguiçosa do EF Core torna fácil de cometer sem perceber.

        **Os `coalesce` não são zelo.** `SUM` de conjunto vazio devolve `NULL`,
        não zero: sem eles, perguntar o consumo de um aluno que ainda não falou
        hoje — o caso mais comum de todos, no primeiro turn do dia — devolveria
        `None` onde o chamador espera número, e o kill switch quebraria
        justamente no caso feliz.

        `estimated_cost_usd` nulo (modelo fora da tabela de preços) é **ignorado
        pela soma** — é assim que `SUM` trata `NULL`, e é o que se quer: somar
        como zero mentiria dizendo que aquele turn foi grátis. Quem conta esses
        turns é `unpriced_turns`, para que custo subestimado não seja
        indistinguível de custo baixo.

        A janela é meio-aberta (`>= since`, `< until`) para que dois dias
        consecutivos não contem o mesmo turn duas vezes.
        """
        stmt = select(
            func.count(),
            func.coalesce(func.sum(UsageEventRow.stt_audio_duration), timedelta(0)),
            func.coalesce(func.sum(UsageEventRow.estimated_cost_usd), 0),
            func.count().filter(UsageEventRow.estimated_cost_usd.is_(None)),
        ).where(
            UsageEventRow.student_id == student_id,
            UsageEventRow.occurred_at >= since,
            UsageEventRow.occurred_at < until,
        )
        turns, falados, custo, sem_preco = (await self._session.execute(stmt)).one()
        return StudentUsageTotals(
            turns=turns,
            spoken=falados,
            # `Decimal(custo)` e não `float(custo)`: o asyncpg já devolve NUMERIC
            # como `Decimal`, e a conversão existe só para o caso do `coalesce`
            # ter entregado o literal inteiro `0`.
            cost_usd=Decimal(custo),
            unpriced_turns=sem_preco,
        )


class SqlAlchemyTranslationRepository:
    """Implementa ``application.ports.repositories.TranslationRepository``.

    Duas operações e nenhum ``update``: tradução não se corrige (ver o
    docstring da porta). O ``add`` não trata colisão — quem traduz a violação
    da chave primária em ``ConflictingWriteError`` é a unidade de trabalho, no
    ``commit``, exatamente como no índice único de ``idempotency_key``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, turn_id: UUID, target: TranslationTarget, index: int
    ) -> Translation | None:
        row = await self._session.get(TranslationRow, (turn_id, target, index))
        return None if row is None else mappers.translation_from_row(row)

    async def add(self, translation: Translation) -> None:
        self._session.add(mappers.translation_to_row(translation))
