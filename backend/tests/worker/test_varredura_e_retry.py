"""O que só o `arq` de verdade pode provar (CARD-025, ADR-0052).

Os dois fatos deste card que **nenhum dublê demonstraria**, porque são
comportamento da biblioteca e não do nosso código:

1. **exceção comum não é retentada** — e portanto `raise Retry` é a única forma
   de pedir reexecução. Foi a descoberta que reabriu o card: o `ProcessTurn`
   levantava a exceção crua achando que voltava para a fila, e o turn ficava
   `processing` para sempre;
2. **`cron_jobs` com duas réplicas roda UMA vez**, não duas — o oposto do que o
   card supunha. O `unique=True` do `arq.cron` monta um `job_id` determinístico
   a partir do horário previsto, e o segundo `enqueue_job` é recusado pelo
   Redis. É o que o Quartz resolve com cluster e uma tabela de locks.

Redis de verdade em container próprio, como o `test_turn_events_integracao.py`:
o teste não depende de o `docker compose` do desenvolvedor estar de pé.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from arq import Retry, create_pool, cron, func
from arq.connections import RedisSettings
from arq.constants import default_queue_name
from arq.worker import Worker
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from voicecoach.application.use_cases.process_turn import RetryableTurnFailureError


@pytest.fixture(scope="module")
def redis_settings() -> Iterator[RedisSettings]:
    container = (
        DockerContainer("redis:7-alpine")
        .with_exposed_ports(6379)
        .waiting_for(LogMessageWaitStrategy("Ready to accept connections"))
    )
    with container:
        host = container.get_container_host_ip()
        porta = container.get_exposed_port(6379)
        yield RedisSettings.from_dsn(f"redis://{host}:{porta}")


async def test_excecao_comum_nao_volta_para_a_fila(
    redis_settings: RedisSettings,
) -> None:
    """**A medição que reabriu o card.**

    Se este teste um dia passar a contar 2, o `arq` mudou de comportamento e o
    `RetryableTurnFailureError` do `ProcessTurn` deixou de ser necessário —
    junto com metade da justificativa do prazo de 5 minutos. É por isso que ele
    existe aqui em vez de virar um parágrafo num ADR.
    """
    chamadas: list[int] = []

    async def levanta_como_o_caso_de_uso_levantava(ctx: dict[str, Any]) -> None:
        chamadas.append(ctx["job_try"])
        message = "falhou antes do primeiro trecho"
        raise RetryableTurnFailureError(message)

    await _rodar_ate_esvaziar(
        redis_settings, levanta_como_o_caso_de_uso_levantava, "tarefa"
    )

    assert chamadas == [1]


async def test_retry_e_a_unica_forma_de_pedir_reexecucao(
    redis_settings: RedisSettings,
) -> None:
    """O outro lado do par: a tradução que o `worker/main.py` faz.

    Mesma exceção, mesmo `max_tries` — o que muda é o `raise Retry(...) from
    exc`. Duas chamadas, com `job_try` crescente: é o retry que o comentário do
    `MAX_TRIES` sempre descreveu e que, até este card, não existia.
    """
    chamadas: list[int] = []

    async def traduz_como_a_composition_root(ctx: dict[str, Any]) -> None:
        chamadas.append(ctx["job_try"])
        try:
            message = "falhou antes do primeiro trecho"
            raise RetryableTurnFailureError(message)
        except RetryableTurnFailureError as exc:
            raise Retry(defer=0) from exc

    await _rodar_ate_esvaziar(redis_settings, traduz_como_a_composition_root, "tarefa2")

    assert chamadas == [1, 2]


async def test_o_cron_com_duas_replicas_executa_uma_vez_so(
    redis_settings: RedisSettings,
) -> None:
    """O objetivo de aprendizado do card, e ele sai **invertido**.

    O CARD-025 afirmava que "um `cron_job` do arq executa em todas as réplicas".
    Não executa: os dois workers calculam o mesmo `next_run`, montam o mesmo
    `job_id` (`f'{name}:{to_unix_ms(next_run)}'`) e o segundo `enqueue_job` é
    recusado. A coordenação existe — ela só não se parece com um lock, porque é
    a unicidade da chave.

    O teste chama `run_cron` direto em vez de rodar os dois laços: o que está sob
    teste é o **enfileiramento**, e um worker em `burst` com `cron_jobs` não sai
    sozinho (verificado nesta sessão — o pytest ficou pendurado).
    """

    async def varre(ctx: dict[str, Any]) -> None:
        del ctx

    async def replica() -> Worker:
        # Um pool por réplica, como dois processos: `redis_pool` no construtor é
        # o jeito suportado de dar ao worker uma conexão já aberta — o `pool` é
        # uma property somente-leitura.
        return Worker(
            functions=[],
            cron_jobs=[cron(varre, name="varredura", second=0, run_at_startup=True)],
            redis_pool=await create_pool(redis_settings),
            max_jobs=1,
            poll_delay=0.1,
        )

    # `run_cron` é o método que o laço do worker chama a cada iteração: é ele que
    # decide se a próxima marca de tempo já entrou na janela e ENFILEIRA o job.
    # `run_at_startup=True` só para não esperar a virada do minuto — na primeira
    # passada sem ele o `run_cron` apenas CALCULA o `next_run` e sai pelo
    # `continue`, sem enfileirar nada. Em produção ele fica falso.
    # Chamá-lo direto, em vez de rodar os dois workers, torna o teste
    # determinístico — o que está sob teste é o enfileiramento, não o laço.
    agora = datetime.now(UTC)
    a, b = await replica(), await replica()
    fila_antes = await _tamanho_da_fila(redis_settings)
    await a.run_cron(agora, 0.5)
    await b.run_cron(agora, 0.5)
    enfileirados = (await _tamanho_da_fila(redis_settings)) - fila_antes
    await a.close()
    await b.close()

    # Duas réplicas, um job. O segundo `enqueue_job` foi recusado porque o
    # `job_id` já existia — coordenação sem lock, pela unicidade da chave.
    assert enfileirados == 1


async def _rodar_ate_esvaziar(
    settings: RedisSettings, coroutine: Any, nome: str
) -> None:
    """Enfileira um job e roda o worker em `burst` até a fila secar.

    Duas passadas: `burst=True` faz o worker sair quando a fila esvazia, e um
    job adiado por `Retry` pode não estar visível na primeira. Sem a segunda
    passada, o teste do retry contaria 1 pelo motivo errado — e concordaria com
    o teste do caso sem retry por acidente.
    """
    pool = await create_pool(settings)
    await pool.enqueue_job(nome)
    for _ in range(2):
        worker = Worker(
            functions=[func(coroutine, name=nome)],
            redis_settings=settings,
            max_tries=2,
            max_jobs=1,
            burst=True,
            poll_delay=0.1,
        )
        await worker.async_run()
        await worker.close()
    await pool.aclose()


async def _tamanho_da_fila(settings: RedisSettings) -> int:
    """Quantos jobs estão na fila padrão do arq, lidos do Redis.

    `default_queue_name` é o sorted set onde o `enqueue_job` grava; contá-lo é a
    forma mais direta de perguntar "quantos jobs foram de fato aceitos?" sem
    depender de o worker chegar a executá-los.
    """
    pool = await create_pool(settings)
    try:
        return int(await pool.zcard(default_queue_name))
    finally:
        await pool.aclose()
