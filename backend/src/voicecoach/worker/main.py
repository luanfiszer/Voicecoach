"""Composition root do worker (ADR-0005, ADR-0025).

**Esta é a única parte do backend que monta o pipeline inteiro.** É o análogo do
`Program.cs` de um host de `BackgroundService`: resolve configuração, constrói as
implementações concretas e as entrega ao caso de uso, que não sabe qual é qual.

**O `ctx` do arq é o idioma que não tem paralelo em C#, e é o coração do ADR-0025.**
Ele é um dicionário comum que o worker cria uma vez, passa ao `on_startup` para
ser populado, e depois entrega **a toda task como primeiro argumento**. Não há
container, não há escopo, não há resolução: é um `dict` vivo pelo processo
inteiro. O equivalente mental é registrar singletons no container do host e
resolvê-los no `ExecuteAsync` — com a diferença de que aqui a disciplina de "não
construa modelo dentro da task" é **regra escrita**, não erro de compilação. Uma
task que chamasse `create_text_to_speech(settings)` passaria em todos os gates e
só apareceria como 0,43 s a mais por turno.

**A barreira de prontidão é comportamento da biblioteca, não código nosso:**
o `arq` só entra no laço de polling depois que `on_startup` retorna
(verificado em `arq.worker.Worker.main`). Logo, nenhum job é consumido antes de
os modelos existirem — e a chave de readiness, gravada no fim do `on_startup`,
nunca pode anunciar prontidão cedo demais.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from arq import Retry, cron, func, run_worker
from arq.connections import RedisSettings

from voicecoach.adapters.events.redis_turn_events import RedisTurnEvents
from voicecoach.adapters.llm.factory import create_teacher_llm
from voicecoach.adapters.persistence.engine import (
    create_engine,
    create_session_factory,
)
from voicecoach.adapters.persistence.repositories import (
    SqlAlchemySessionRepository,
    SqlAlchemyTurnRepository,
    SqlAlchemyUsageEventRepository,
)
from voicecoach.adapters.queue.arq_turn_queue import PROCESS_TURN_TASK
from voicecoach.adapters.storage.s3_media_storage import create_media_storage
from voicecoach.adapters.stt.factory import create_speech_to_text, resolve_stt_provider
from voicecoach.adapters.tts.encoding import AacAudioEncoder
from voicecoach.adapters.tts.factory import create_text_to_speech
from voicecoach.application.use_cases.process_turn import (
    ProcessTurn,
    ProcessTurnHandler,
    RetryableTurnFailureError,
)
from voicecoach.application.use_cases.sweep_stale_turns import (
    SweepStaleTurns,
    SweepStaleTurnsHandler,
)
from voicecoach.config import get_settings, preco_do_modelo
from voicecoach.worker.readiness import WorkerReadiness

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)

# Duas tentativas, não três: o retry aqui só cobre falha ANTES do primeiro
# trecho (a guarda está no caso de uso), e o que se protege é a intermitência de
# rede — provedor fora do ar por mais tempo que isso não melhora na terceira.
#
# **Este número só passou a significar alguma coisa no CARD-025** (ADR-0052).
# Até lá o caso de uso levantava a exceção crua achando que o `arq` a devolveria
# à fila; medido, ele NÃO devolve — só `Retry`, `CancelledError` e `RetryJob`
# caem no ramo de retry. `max_tries` sempre foi um teto sobre um contador que
# nunca passava de 1. Quem faz a tradução agora é `process_turn`, aqui embaixo.
MAX_TRIES = 2

# Quantos turnos anteriores da sessão alimentam o professor. Cada turno são duas
# falas; 6 turnos são ~12 mensagens, que num diálogo deste produto ficam bem
# abaixo do limiar de 4.096 tokens onde o prompt caching passaria a valer a pena
# (ADR-0021). Subir isto é decisão de custo, não de conveniência.
HISTORY_TURNS = 6

# Um turn por vez neste worker. Não é limitação técnica: os modelos de STT e TTS
# disputam a MESMA CPU (ADR-0025), e dois turns concorrentes se atrasariam
# mutuamente dentro de um orçamento de 1,8 s. Paralelismo aqui é entre as etapas
# de um turn, não entre turns. Gatilho para subir: medição mostrando CPU ociosa
# com fila cheia.
MAX_JOBS = 1


def _agora() -> datetime:
    """O relógio injetado no caso de uso.

    Uma função, e não `datetime.now` direto, porque o caso de uso pede
    `Callable[[], datetime]` e é ela que o teste substitui para poder afirmar
    que o primeiro trecho existiu antes de `replied_at`.
    """
    from datetime import UTC, datetime

    return datetime.now(UTC)


async def startup(ctx: dict[str, Any]) -> None:
    """Carrega tudo que é caro, **uma vez** (ADR-0025, itens 1 e 3).

    A ordem importa: a chave de readiness é a **última** coisa. Gravá-la antes
    da carga faria a API anunciar um worker que ainda não consegue transcrever —
    a mentira que o ADR-0025 existe para matar.
    """
    settings = get_settings()
    ctx["settings"] = settings

    inicio = time.perf_counter()
    ctx["stt"] = create_speech_to_text(settings)
    # O nome do motor que de fato foi carregado, não o que a config pediu:
    # `STT_PROVIDER=auto` resolve para `mlx` ou `faster_whisper` aqui no boot
    # (ADR-0027), e é este nome que vai para a linha de custo do CARD-014.
    # Gravar "auto" seria gravar o nome de motor nenhum.
    ctx["stt_provider"] = resolve_stt_provider(settings.stt_provider).value
    stt_s = time.perf_counter() - inicio
    # A carga do adapter ATIVO, cronometrada em separado — é a dívida do
    # ADR-0025, item 7, e agora que o Piper baixou o TTS para 0,43 s ela é a
    # maior parcela da subida.
    logger.info("worker: STT carregado em %.2f s", stt_s)

    inicio_tts = time.perf_counter()
    ctx["tts"] = create_text_to_speech(settings)
    logger.info("worker: TTS carregado em %.2f s", time.perf_counter() - inicio_tts)

    # O professor é o único "modelo" que NÃO carrega nada: é um cliente HTTP.
    # Ele vem para o `ctx` mesmo assim porque construir o `AsyncAnthropic` por
    # job criaria um pool de conexões novo a cada turno — e reaproveitar conexão
    # TLS é o que tira ~100 ms do handshake no caminho crítico.
    ctx["teacher"] = create_teacher_llm(settings)
    ctx["encoder"] = AacAudioEncoder()
    ctx["storage"] = create_media_storage(settings)

    engine = create_engine(settings.database_url)
    ctx["engine"] = engine
    ctx["session_factory"] = create_session_factory(engine)

    # `ctx["redis"]` é o pool que o próprio arq já abriu antes de nos chamar —
    # reusá-lo evita uma segunda conexão para publicar eventos e heartbeat.
    ctx["events"] = RedisTurnEvents(ctx["redis"])
    readiness = WorkerReadiness(ctx["redis"])
    await readiness.start()
    ctx["readiness"] = readiness

    logger.info("worker: pronto em %.2f s", time.perf_counter() - inicio)


async def shutdown(ctx: dict[str, Any]) -> None:
    """Simétrico ao startup (ADR-0025, item 2).

    O `dispose()` do engine devolve as conexões do pool; sem ele, subir e
    derrubar o worker num teste de integração vazaria conexões entre casos.
    """
    readiness: WorkerReadiness | None = ctx.get("readiness")
    if readiness is not None:
        await readiness.stop()
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


async def process_turn(ctx: dict[str, Any], turn_id: str) -> None:
    """A task. Abre a unidade de trabalho, monta o handler e delega.

    **A sessão de banco nasce e morre aqui, por job.** Fora do FastAPI não há
    `Depends`, então o escopo é explícito: o `async with` da fábrica é o
    equivalente ao escopo de DI por mensagem consumida. Uma sessão de vida longa
    seguraria uma conexão do pool o tempo todo e, no décimo turno, o pool seca —
    sintoma que não aparece no primeiro.

    Repare no que **não** acontece aqui: nada é construído além do que é barato.
    Os modelos vêm do `ctx`; construí-los aqui custaria ~1 s por turno e não
    quebraria teste nenhum.
    """
    session_factory = ctx["session_factory"]
    tentativa: int = ctx.get("job_try", 1)

    async with session_factory() as session:
        handler = ProcessTurnHandler(
            turns=SqlAlchemyTurnRepository(session),
            sessions=SqlAlchemySessionRepository(session),
            usage_events=SqlAlchemyUsageEventRepository(session),
            unit_of_work=session,
            storage=ctx["storage"],
            speech_to_text=ctx["stt"],
            teacher=ctx["teacher"],
            text_to_speech=ctx["tts"],
            encoder=ctx["encoder"],
            events=ctx["events"],
            clock=_agora,
            history_turns=HISTORY_TURNS,
            # A função, não a tabela: `application` não pode importar `config`
            # (ADR-0013), então quem conhece a forma da tabela de preços é esta
            # composition root. O caso de uso só conhece a pergunta.
            llm_price=preco_do_modelo,
            stt_provider=ctx["stt_provider"],
            tts_provider=ctx["settings"].tts_provider.value,
        )
        try:
            await handler.handle(
                ProcessTurn(
                    turn_id=UUID(turn_id),
                    # A tradução de "mecânica de fila" para "o handler tem mais
                    # uma chance?". O caso de uso não conhece `job_try` nem
                    # `max_tries`.
                    final_attempt=tentativa >= MAX_TRIES,
                )
            )
        except RetryableTurnFailureError as exc:
            # **A outra metade da tradução, e a que faltava** (ADR-0052).
            #
            # `arq.Retry` é a ÚNICA forma de pedir reexecução: uma exceção comum
            # cai no ramo `else` do `run_job`, que loga `failed` e encerra o job
            # — medido contra o `arq` 0.28, não lido. Enquanto isso não existia,
            # o turn ficava `processing` para sempre e o aluno, na tela de
            # espera. Não é uma otimização: era um caminho de falha sem dono.
            #
            # A tradução mora aqui e não no caso de uso porque `application` não
            # pode importar `arq` (ADR-0012) — o mesmo motivo pelo qual
            # `final_attempt` é um `bool` e não o `ctx` do arq.
            #
            # `defer=0`: reexecutar imediatamente. O backoff que interessa já
            # aconteceu dentro do adapter do professor (o SDK tenta 2x com
            # espera própria); somar outro aqui só aumentaria o tempo em que o
            # aluno olha uma tela sem saber de nada.
            logger.warning("turn %s: pedindo nova tentativa ao arq (%s)", turn_id, exc)
            raise Retry(defer=0) from exc


async def sweep_stale_turns(ctx: dict[str, Any]) -> None:
    """A varredura de turns travados, disparada pelo `cron_jobs` (CARD-025).

    **`cron_jobs` é um scheduler EMBUTIDO no worker, e a diferença para um
    `IHostedService` com `PeriodicTimer` é onde o relógio mora.** No .NET o timer
    é do processo: duas réplicas, dois timers, duas execuções — e resolver isso é
    o que leva ao Quartz com cluster e uma tabela de locks. No `arq` o relógio
    também é de cada processo, mas o que ele faz na hora marcada é **enfileirar**
    um job, e o `job_id` desse job é determinístico:

        job_id = f'{cron_job.name}:{to_unix_ms(cron_job.next_run)}'

    (`arq/worker.py`, no `run_cron`, com `unique=True` — o default de
    `arq.cron`). Como o `enqueue_job` recusa um id que já existe, a segunda
    réplica que tenta enfileirar a MESMA marca de tempo é rejeitada em silêncio.
    **O arq resolve com o Redis o que o Quartz resolve com uma tabela** — sem
    lock explícito, porque a unicidade é a própria chave.

    O que ele NÃO resolve, e vale saber: relógios muito fora de sincronia entre
    réplicas produzem `next_run` diferentes, logo ids diferentes, logo duas
    execuções. Aqui isso é inofensivo — a varredura é idempotente, e o turn que a
    segunda rodada encontrar já estará `failed`, caindo no ramo que ignora.

    Não recebe parâmetro: o `ctx` já traz tudo, e o prazo é configuração.
    """
    settings = ctx["settings"]
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        handler = SweepStaleTurnsHandler(
            turns=SqlAlchemyTurnRepository(session),
            unit_of_work=session,
            events=ctx["events"],
            clock=_agora,
            # A config atravessa aqui, não lá dentro: `application` não pode
            # importar `voicecoach.config` (ADR-0013).
            stale_after=settings.stale_turn_after,
            batch_limit=settings.stale_sweep_batch_limit,
        )
        await handler.handle(SweepStaleTurns())


class WorkerSettings:
    """O que o `arq worker` lê. Uma classe usada como namespace, não instanciada.

    Idioma do `arq`: o CLI recebe o caminho desta classe
    (`arq voicecoach.worker.main.WorkerSettings`) e lê os atributos dela. Não há
    paralelo direto em C# — o mais próximo é um `Startup` por convenção, do tipo
    que o ASP.NET Core clássico usava antes do `Program.cs` de nível superior.
    """

    # `func(..., name=...)` em vez de passar a função crua: sem o nome
    # explícito, o `arq` registra a task pelo `__qualname__`, e o nome da fila
    # passaria a depender do caminho do módulo — renomear este arquivo quebraria
    # os jobs já enfileirados. A borda publica pela mesma constante.
    functions = [  # noqa: RUF012 — contrato do arq, não é anotável
        func(process_turn, name=PROCESS_TURN_TASK)
    ]
    # A varredura do CARD-025. `second=0` com os demais campos nulos significa
    # "todo minuto, no segundo zero" — a granularidade de detecção é, portanto,
    # `stale_turn_after` + até 60 s, e é de propósito: um turn parado há 5 min não
    # fica melhor por ser encontrado 30 s antes, e um cron mais frequente
    # disputaria o `MAX_JOBS = 1` com o aluno vivo sem nada em troca.
    #
    # `run_at_startup` fica FALSO (o default). Ligá-lo faria toda subida de
    # worker varrer — inclusive a subida que acontece logo depois de um deploy,
    # quando os turns em voo estão legitimamente parados havia segundos.
    cron_jobs = [  # noqa: RUF012 — contrato do arq, não é anotável
        cron(sweep_stale_turns, second=0)
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_tries = MAX_TRIES
    max_jobs = MAX_JOBS


def run() -> None:
    """Entrypoint do processo: ``uv run voicecoach-worker``.

    **Por que uma função e não `redis_settings` como atributo da classe.** O
    `arq` lê os atributos de `WorkerSettings` no momento em que a classe é
    usada, então um `redis_settings = RedisSettings.from_dsn(get_settings()...)`
    ali dentro seria avaliado no **import** do módulo — e `get_settings()`
    valida o `.env`. Importar este arquivo passaria a exigir configuração
    completa, inclusive na coleta dos testes, que é exatamente a armadilha que o
    `get_settings()` preguiçoso do CARD-002 existe para evitar.

    `run_worker` aceita sobrescritas por kwarg, então a configuração entra aqui,
    onde alguém de fato pediu para rodar o worker.
    """
    logging.basicConfig(level=logging.INFO)
    run_worker(
        WorkerSettings,  # type: ignore[arg-type]  # `WorkerSettingsType` é um Protocol que o arq não exporta de forma satisfazível por uma classe simples; gatilho para remover: o arq publicar o Protocol.
        redis_settings=RedisSettings.from_dsn(get_settings().redis_url),
    )
