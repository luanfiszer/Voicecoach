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

from arq import func, run_worker
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
)
from voicecoach.config import get_settings, preco_do_modelo
from voicecoach.worker.readiness import WorkerReadiness

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)

# Duas tentativas, não três: o retry aqui só cobre falha ANTES do primeiro
# trecho (a guarda está no caso de uso), e o que se protege é a intermitência de
# rede — provedor fora do ar por mais tempo que isso não melhora na terceira.
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
        await handler.handle(
            ProcessTurn(
                turn_id=UUID(turn_id),
                # A tradução de "mecânica de fila" para "o handler tem mais uma
                # chance?". O caso de uso não conhece `job_try` nem `max_tries`.
                final_attempt=tentativa >= MAX_TRIES,
            )
        )


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
