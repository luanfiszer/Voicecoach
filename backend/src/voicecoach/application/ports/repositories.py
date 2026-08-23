"""Portas de persistência (ADR-0004).

Declaradas como ``Protocol``: tipagem **estrutural**. Um adapter satisfaz a
porta por ter os métodos com a assinatura certa — não herda nada, não se
registra em lugar nenhum, e o ``domain``/``application`` nunca importa o
adapter. É a diferença para C#, onde a classe precisa declarar ``: IRepository``
para o compilador aceitar.

Consequência prática em teste: um fake é uma classe comum com os métodos
certos, sem framework de mock. E o erro de um fake que não satisfaz a porta
aparece no ``mypy``, **antes** de qualquer execução — não no meio do teste.

**Quem faz commit não é o repositório.** Estes métodos registram a intenção na
unidade de trabalho; confirmar a transação é decisão de quem a abriu (a borda,
por request — CARD-010). O contrário — cada repositório comitando o que fez —
tornaria impossível salvar Turn e Correction atomicamente no mesmo turno.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from voicecoach.domain.session import Session
    from voicecoach.domain.student import Student
    from voicecoach.domain.turn import Turn


class UnitOfWork(Protocol):
    """Confirma o que os repositórios registraram.

    O docstring deste módulo já dizia que **quem comita não é o repositório**;
    faltava dizer quem é. Na API será a borda, uma vez por request. No worker é
    o **caso de uso**, e por uma razão que não existia até o CARD-009: a cascata
    entrega o áudio em trechos, e um trecho que o aluno já ouviu tem de estar
    gravado antes do próximo — é dele que a retomada por ``Last-Event-ID``
    reconstrói o que se perdeu (ADR-0026, item 3). Uma transação só, aberta no
    início do turn e confirmada no fim, deixaria os trechos invisíveis
    exatamente durante os ~2 s em que alguém pode reconectar.

    Logo, o turn não é uma transação: é uma sequência de marcos confirmados.
    A consequência aceita é que um turn interrompido no meio deixa estado
    parcial gravado — que é precisamente o que o ADR-0023 quer (falhar não
    apaga trecho), e não um acidente.

    ``rollback`` não está aqui: quem descarta a transação é quem a abriu (o
    ``async with`` da task), e um caso de uso capaz de desfazer o que outro
    marco já confirmou seria uma promessa falsa.
    """

    async def commit(self) -> None: ...


class StudentRepository(Protocol):
    """Acesso às contas de aluno."""

    async def add(self, student: Student) -> None: ...

    async def get(self, student_id: UUID) -> Student | None: ...


class SessionRepository(Protocol):
    """Acesso às conversas."""

    async def add(self, session: Session) -> None: ...

    async def get(self, session_id: UUID) -> Session | None: ...

    async def update(self, session: Session) -> None: ...


class TurnRepository(Protocol):
    """Acesso aos turnos.

    ``update`` existe porque a entidade de domínio **não** é o objeto mapeado
    pelo SQLAlchemy (ADR-0004): mudar o `Turn` em memória não sensibiliza
    sessão nenhuma, então o pipeline do worker (CARD-009) precisa dizer
    explicitamente que quer gravar o novo estado. É o preço consciente do
    mapeamento entidade↔linha — e o contraste com o change tracking do EF Core.
    """

    async def add(self, turn: Turn) -> None: ...

    async def get(self, turn_id: UUID) -> Turn | None: ...

    async def update(self, turn: Turn) -> None: ...

    async def list_by_session(self, session_id: UUID, *, limit: int) -> list[Turn]:
        """Os últimos turnos **concluídos** da sessão, do mais antigo para o
        mais novo.

        Existe por uma razão de produto, não de infraestrutura: sem ela o
        professor recebe um histórico de um item só e responde como se cada fala
        fosse a primeira da conversa (ADR-0031 — o histórico entra por parâmetro
        porque o adapter não guarda estado). Um professor com amnésia entre
        turnos é um produto diferente.

        **Só ``completed``**, e é aqui que a decisão mora em vez de no caso de
        uso: um turn que falhou não tem os dois lados do diálogo (pode ter
        transcrição e não ter resposta), e um turn em processamento é o próprio
        turn atual. Alimentar o professor com metade de uma troca ensinaria a
        ele um padrão de conversa que não existe.

        ``limit`` é obrigatório e nomeado. Não há default: quem chama tem de
        declarar quanto contexto está disposto a pagar em tokens de entrada, e
        um default escondido aqui seria uma decisão de custo (ADR-0010) tomada
        na camada errada. A ordem é do mais antigo para o mais novo porque é
        assim que o histórico é montado; o ``limit`` corta os mais **velhos**.
        """
        ...
