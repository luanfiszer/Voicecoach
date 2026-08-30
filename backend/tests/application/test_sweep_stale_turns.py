"""A varredura de turns travados (CARD-025), com fakes e relógio controlado.

**Prazo se testa com relógio, nunca com `sleep`.** Um teste que dormisse 5 min
para provar que o prazo é de 5 min seria inútil e lento; um que dormisse 0,01 s
com o prazo baixado para 0,005 s provaria que o código roda, não que ele decide
certo. Aqui o relógio é injetado e o "passado" é construído: o turn nasce com
`created_at` seis minutos atrás e o agora é fixo.

O que cada bloco prova:

1. **turn `queued` além do prazo vira `failed` com motivo e evento** — o caso do
   worker que nunca apareceu, que é o que o `coalesce` do repositório cobre;
2. **turn `processing` com trechos sai `failed` com os trechos INTACTOS** e
   `delivered_partially` verdadeiro (ADR-0023, item 6);
3. **turn dentro do prazo não é tocado**, e `completed`/`failed` nunca entram;
4. **a corrida não derruba o lote** — o turn que terminou entre a listagem e a
   marcação é ignorado, e os travados atrás dele continuam sendo encerrados;
5. **falha ao publicar não desfaz a marcação** (ADR-0035);
6. **o lote respeita o teto**.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes_pipeline import FakeTurnEvents, FakeTurnRepository, FakeUnitOfWork
from voicecoach.application.ports.repositories import TurnRepository, UnitOfWork
from voicecoach.application.ports.turn_events import (
    Failed,
    TurnEvents,
    TurnEventsError,
)
from voicecoach.application.use_cases.sweep_stale_turns import (
    MOTIVO,
    SweepReport,
    SweepStaleTurns,
    SweepStaleTurnsHandler,
)
from voicecoach.domain.turn import Turn, TurnStatus

AGORA = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
PRAZO = timedelta(minutes=5)
SESSION_ID = uuid4()
INPUT_KEY = "students/x/sessions/y/turns/z/input.aac"


def relogio_fixo() -> datetime:
    """Um relógio parado, e a imobilidade é o ponto.

    O `RelogioFalso` do `fakes_pipeline` avança 1 s por leitura, o que é certo
    para provar ordem entre eventos. Aqui a pergunta é outra — "este turn está
    parado há mais que o prazo?" — e um relógio que anda tornaria a resposta
    dependente de quantas vezes o código o leu.
    """
    return AGORA


def turn_parado_desde(
    inicio: datetime, *, status: TurnStatus = TurnStatus.QUEUED, trechos: int = 0
) -> Turn:
    """Um turn no estado que a varredura vai encontrar.

    Construído passo a passo pelos métodos da entidade, não por atribuição
    direta: é o que garante que o estado montado aqui é um estado que o produto
    consegue de fato produzir.
    """
    turn = Turn(
        id=uuid4(),
        session_id=SESSION_ID,
        input_audio_ref=INPUT_KEY,
        audio_duration=timedelta(seconds=4),
        created_at=inicio,
    )
    if status is TurnStatus.QUEUED:
        return turn

    turn.start_processing(inicio)
    for i in range(trechos):
        turn.append_audio_chunk(
            index=i,
            storage_key=f"chunk-{i}.aac",
            duration_seconds=1.0,
            text=f"sentença {i}",
            now=inicio,
        )
    return turn


class Montagem:
    """Handler e dublês, com o prazo e o lote explícitos."""

    def __init__(
        self,
        *turns: Turn,
        events: FakeTurnEvents | None = None,
        batch_limit: int = 50,
    ) -> None:
        self.turns = FakeTurnRepository(*turns)
        self.uow = FakeUnitOfWork()
        self.events = events or FakeTurnEvents()
        self.handler = SweepStaleTurnsHandler(
            turns=self.turns,
            unit_of_work=self.uow,
            events=self.events,
            clock=relogio_fixo,
            stale_after=PRAZO,
            batch_limit=batch_limit,
        )

    async def varrer(self) -> SweepReport:
        return await self.handler.handle(SweepStaleTurns())


def test_o_handler_recebe_as_portas_que_declara() -> None:
    """A linha que o `mypy` confere: os dublês satisfazem os `Protocol`.

    É esta atribuição — e não uma execução — que reprova um fake fora de
    sincronia com a porta. Aconteceu neste card: `list_stale` entrou em
    `TurnRepository` e 29 erros apareceram antes de qualquer teste rodar.
    """
    repo: TurnRepository = FakeTurnRepository()
    uow: UnitOfWork = FakeUnitOfWork()
    canal: TurnEvents = FakeTurnEvents()

    assert (repo, uow, canal) is not None


async def test_turn_queued_alem_do_prazo_vira_failed_com_motivo_e_evento() -> None:
    """O worker que nunca apareceu.

    Repare que este turn **nunca teve** `started_processing_at`: é exatamente o
    caso que uma query comparando só esse campo deixaria invisível para sempre,
    porque `NULL < :before` é `NULL` em SQL, não `true`.
    """
    turn = turn_parado_desde(AGORA - timedelta(minutes=6))
    m = Montagem(turn)

    await m.varrer()

    gravado = m.turns.turns[turn.id]
    assert gravado.status is TurnStatus.FAILED
    assert gravado.failure_reason == MOTIVO
    assert gravado.failed_at == AGORA
    evento = m.events.publicados[0].event
    assert isinstance(evento, Failed)
    assert evento.reason == MOTIVO
    assert evento.delivered_partially is False


async def test_turn_processing_com_trechos_sai_failed_com_os_trechos_intactos() -> None:
    """A invariante do ADR-0023, item 6 — e a asserção olha a COLEÇÃO.

    Um teste que só conferisse o status passaria com uma implementação que
    limpasse os trechos ao falhar. O aluno já ouviu duas frases, e o registro
    tem de continuar dizendo que ele ouviu.
    """
    turn = turn_parado_desde(
        AGORA - timedelta(minutes=6), status=TurnStatus.PROCESSING, trechos=2
    )
    m = Montagem(turn)

    await m.varrer()

    gravado = m.turns.turns[turn.id]
    assert gravado.status is TurnStatus.FAILED
    assert len(gravado.audio_chunks) == 2
    assert [c.text for c in gravado.audio_chunks] == ["sentença 0", "sentença 1"]
    assert gravado.delivered_partially is True
    evento = m.events.publicados[0].event
    assert isinstance(evento, Failed)
    assert evento.delivered_partially is True


async def test_turn_dentro_do_prazo_nao_e_tocado() -> None:
    """Quatro minutos parados, com prazo de cinco: ainda pode dar certo."""
    turn = turn_parado_desde(AGORA - timedelta(minutes=4), status=TurnStatus.PROCESSING)
    m = Montagem(turn)

    await m.varrer()

    assert m.turns.turns[turn.id].status is TurnStatus.PROCESSING
    assert m.events.publicados == []
    assert m.uow.commits == 0


async def test_turn_completed_nunca_e_considerado() -> None:
    """Mesmo velhíssimo. A varredura pergunta pelo estado, não pela idade."""
    turn = turn_parado_desde(
        AGORA - timedelta(days=3), status=TurnStatus.PROCESSING, trechos=1
    )
    turn.attach_transcript("hello", AGORA - timedelta(days=3))
    turn.attach_reply("hi", AGORA - timedelta(days=3))
    turn.attach_reply_audio("full.aac", AGORA - timedelta(days=3))
    turn.complete(AGORA - timedelta(days=3))
    m = Montagem(turn)

    await m.varrer()

    assert m.turns.turns[turn.id].status is TurnStatus.COMPLETED
    assert m.events.publicados == []


class RepositorioQueConclui(FakeTurnRepository):
    """Conclui um turn específico **entre** a listagem e a leitura.

    É a corrida do §4.2 do card reproduzida sem concorrência real: o `get` do id
    marcado devolve um turn já `completed`, que é exatamente o que o Postgres
    devolveria se o worker tivesse comitado nesse intervalo. Reproduzir a corrida
    com duas tasks de verdade tornaria o teste intermitente e provaria menos.
    """

    def __init__(self, *turns: Turn, concluir: UUID) -> None:
        super().__init__(*turns)
        self._concluir = concluir

    async def get(self, turn_id: UUID) -> Turn | None:
        turn = await super().get(turn_id)
        if turn is not None and turn_id == self._concluir:
            turn.attach_transcript("hello", AGORA)
            turn.attach_reply("hi", AGORA)
            turn.attach_reply_audio("full.aac", AGORA)
            turn.complete(AGORA)
        return turn


async def test_a_corrida_nao_derruba_o_lote_nem_deixa_dois_estados() -> None:
    """O turn que terminou durante a varredura é ignorado; os outros seguem.

    A asserção que importa é a **segunda**: se a `InvalidStateTransitionError`
    subisse, o turn travado atrás do concluído nunca seria encerrado — e a
    próxima rodada tropeçaria no mesmo lugar, para sempre.
    """
    vencedor = turn_parado_desde(
        AGORA - timedelta(minutes=7), status=TurnStatus.PROCESSING, trechos=1
    )
    travado = turn_parado_desde(AGORA - timedelta(minutes=6))
    repo = RepositorioQueConclui(vencedor, travado, concluir=vencedor.id)
    m = Montagem()
    m.turns = repo
    m.handler = SweepStaleTurnsHandler(
        turns=repo,
        unit_of_work=m.uow,
        events=m.events,
        clock=relogio_fixo,
        stale_after=PRAZO,
        batch_limit=50,
    )

    relatorio = await m.handler.handle(SweepStaleTurns())

    assert repo.turns[vencedor.id].status is TurnStatus.COMPLETED
    assert repo.turns[travado.id].status is TurnStatus.FAILED
    assert (relatorio.examinados, relatorio.encerrados, relatorio.ignorados) == (
        2,
        1,
        1,
    )


async def test_falha_ao_publicar_nao_desfaz_a_marcacao() -> None:
    """ADR-0035: o banco é a verdade, o canal é cortesia.

    O aluno cujo turn travou há seis minutos não está mais com o stream aberto
    (`sse_timeout` = 60 s) — quem descobre a falha é o `GET` na volta do app.
    Deixar o Redis derrubar a marcação transformaria uma indisponibilidade de
    caminho rápido em turn travado para sempre.
    """
    turn = turn_parado_desde(AGORA - timedelta(minutes=6))
    m = Montagem(turn, events=FakeTurnEvents(erro=TurnEventsError("redis fora")))

    relatorio = await m.varrer()

    assert m.turns.turns[turn.id].status is TurnStatus.FAILED
    assert m.uow.commits == 1
    assert relatorio.encerrados == 1


async def test_o_lote_respeita_o_teto_e_o_resto_fica_para_a_proxima() -> None:
    """`MAX_JOBS = 1`: enquanto a varredura roda, nenhum aluno é atendido.

    A varredura é **convergente, não exaustiva** — o que sobra é encerrado um
    minuto depois, na próxima rodada do cron.
    """
    turns = [turn_parado_desde(AGORA - timedelta(minutes=6 + i)) for i in range(5)]
    m = Montagem(*turns, batch_limit=2)

    relatorio = await m.varrer()

    assert relatorio.examinados == 2
    assert relatorio.encerrados == 2
    encerrados = [t for t in m.turns.turns.values() if t.status is TurnStatus.FAILED]
    assert len(encerrados) == 2
    # Os DOIS MAIS ANTIGOS, não dois quaisquer: sem ordenação, o turn travado há
    # mais tempo poderia ficar de fora de toda rodada.
    assert {t.id for t in encerrados} == {turns[4].id, turns[3].id}


async def test_lote_vazio_nao_comita_nada() -> None:
    m = Montagem()

    relatorio = await m.varrer()

    assert (relatorio.examinados, relatorio.encerrados) == (0, 0)
    assert m.uow.commits == 0


def test_o_motivo_e_uma_frase_para_humano() -> None:
    """O motivo vai para `failure_reason`, que a API expõe ao app.

    Não é um código: o CARD-027 vai mostrá-lo numa tela, e "o turno excedeu o
    prazo" é o que dá ao aluno a diferença entre "deu erro" e "isto demorou
    demais e foi encerrado".
    """
    assert "prazo" in MOTIVO
    assert MOTIVO.strip() == MOTIVO


class RepositorioQuePerdeALinha(FakeTurnRepository):
    """Lista um id que o `get` não acha — retenção ou delete no intervalo."""

    async def list_stale(self, *, before: datetime, limit: int) -> list[UUID]:
        del before, limit
        return [uuid4()]


async def test_id_que_sumiu_entre_a_listagem_e_a_leitura_e_ignorado() -> None:
    """Um turn que não existe não está travado.

    A alternativa — levantar — transformaria a retenção do ADR-0024 rodando ao
    mesmo tempo que a varredura num job vermelho todo minuto.
    """
    repo = RepositorioQuePerdeALinha()
    handler = SweepStaleTurnsHandler(
        turns=repo,
        unit_of_work=FakeUnitOfWork(),
        events=FakeTurnEvents(),
        clock=relogio_fixo,
        stale_after=PRAZO,
        batch_limit=50,
    )

    relatorio = await handler.handle(SweepStaleTurns())

    assert (relatorio.examinados, relatorio.encerrados, relatorio.ignorados) == (
        1,
        0,
        1,
    )
