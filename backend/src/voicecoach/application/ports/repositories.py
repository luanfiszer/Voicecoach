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
    from datetime import datetime
    from uuid import UUID

    from voicecoach.domain.session import Session
    from voicecoach.domain.student import Student
    from voicecoach.domain.turn import Turn
    from voicecoach.domain.usage import StudentUsageTotals, UsageEvent


class ConflictingWriteError(RuntimeError):
    """O armazenamento recusou a escrita por violar uma restrição de unicidade.

    Mora na porta, como o ``TurnQueueError`` e o ``MediaStorageError``, e pela
    mesma razão (ADR-0031, item 5): quem a captura é o caso de uso, em
    ``application``, que não pode importar ``adapters`` para conhecer o
    ``IntegrityError`` do SQLAlchemy.

    **Ela existe por causa de uma corrida específica**, e vale nomeá-la: entre
    "consultei se esta ``Idempotency-Key`` já existe" e "inseri o Turn", outra
    requisição com a mesma chave pode ter inserido. A consulta é uma foto, o
    índice único é a lei — e sem esta tradução o desfecho seria um 500 em cima
    de um duplo toque no botão, que é o caso mais banal que a idempotência
    existe para tratar.

    Não é ``DomainError``: nenhuma invariante de negócio foi violada (ADR-0017).
    É o armazenamento informando um fato que só ele sabia.
    """


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

    async def get_by_idempotency_key(self, key: str) -> Turn | None:
        """O turn que já nasceu daquela chave de idempotência, se existir.

        Existe porque a chave é **unicidade do banco**, e um índice único só
        conta a história pela metade: ele impede o segundo INSERT, mas quem
        precisa responder ao cliente precisa do ``turn_id`` do PRIMEIRO. Sem
        este método, o caso de uso saberia que houve repetição e não saberia
        dizer de quê — que é o oposto do que o ``202`` promete.

        Devolve ``None`` quando a chave é nova. Ausência aqui é o caminho
        feliz, não erro: a esmagadora maioria dos POSTs traz chave inédita.
        """
        ...

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


class UsageEventRepository(Protocol):
    """Acesso ao custo real de cada turn (CARD-014, ADR-0051).

    **Porta própria, e não uma coleção do agregado ``Turn``** — a decisão está no
    ADR-0051 e contraria o precedente fresco do CARD-013, então vale a razão por
    escrito: ``Correction`` é lida *junto do turn* e ``UsageEvent`` é lido *em
    agregação*. Carregá-lo em todo ``TurnRepository.get()`` seria peso no caminho
    crítico de 1,8 s para um dado que aquela leitura não usa, e amarraria a
    retenção do custo à do turn.

    Note o que **não** está aqui: nenhum ``update``. Medição não se corrige — o
    turn consumiu o que consumiu. A ausência do método é a invariante.
    """

    async def add(self, event: UsageEvent) -> None: ...

    async def get(self, turn_id: UUID) -> UsageEvent | None:
        """O evento daquele turn, se já houver. Existe para o teste de roundtrip.

        Um evento por turn é regra do **banco** (a chave primária é o
        ``turn_id``), não convenção: uma segunda escrita não passa em silêncio,
        ela vira ``ConflictingWriteError`` no ``commit``.
        """
        ...

    async def totals_for_student(
        self, student_id: UUID, *, since: datetime, until: datetime
    ) -> StudentUsageTotals:
        """O consumo de um aluno numa janela — em minutos **e** em turns.

        **Esta é a única query deste card que vai para o caminho crítico de um
        request:** o CARD-015 vai chamá-la dentro do ``POST`` para decidir se o
        aluno ainda tem cota. Daí duas exigências que estão no adapter e não
        aqui: a soma acontece **no banco** (``SUM``/``COUNT``, sem carregar
        linha) e existe um índice composto ``(student_id, occurred_at)`` para
        sustentá-la. Sem o índice, é uma varredura que fica lenta em silêncio,
        proporcional ao total de turns já processados no produto inteiro.

        A janela é meio-aberta — ``since`` inclusivo, ``until`` exclusivo — para
        que dois dias consecutivos não contem o mesmo turn duas vezes. Ambos
        obrigatórios e nomeados: uma agregação sem janela é a fatura da vida
        inteira do aluno, que nunca é a pergunta.

        Aluno sem nenhum turn na janela devolve os zeros, **não** ``None``:
        "não gastou nada" é uma resposta, e obrigar o chamador a tratar ausência
        para dizer zero moveria a decisão de cota para dentro de um ``if`` de
        borda.
        """
        ...
