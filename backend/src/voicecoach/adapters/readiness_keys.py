"""O nome da chave de prontidão do worker — vocabulário dos DOIS processos.

**Por que isto é um módulo próprio.** A chave é escrita pelo `worker` e lida
pela `api` (ADR-0025, itens 3 e 4), e `api` e `worker` são camadas **irmãs que
não se importam** (ADR-0012). O primeiro desenho pôs a constante em
`worker/readiness.py` e o `check_worker` a importou de lá; o `lint-imports`
reprovou na hora:

    voicecoach.adapters is not allowed to import voicecoach.worker:
    - voicecoach.adapters.health -> voicecoach.worker.readiness (l.125)

É o mesmo problema que `PROCESS_TURN_TASK` resolve do lado da fila, e a mesma
solução: uma string num módulo que **ambos** podem importar é o acoplamento
mínimo entre um escritor e um leitor que não se conhecem. Duplicar o literal nos
dois lados seria pior — divergiriam em silêncio, e o sintoma seria uma API
afirmando "não há worker" com o worker rodando.
"""

from __future__ import annotations

from datetime import timedelta

WORKER_READY_KEY = "voicecoach:worker:ready"

# O TTL é o tempo máximo que a API pode acreditar num worker já morto.
WORKER_READY_TTL = timedelta(seconds=30)

# Um terço do TTL: duas renovações podem falhar (rede instável, event loop
# ocupado por um turn longo) sem que a chave caia. Metade do TTL derrubaria o
# worker do readiness por uma única renovação perdida.
WORKER_HEARTBEAT_INTERVAL = WORKER_READY_TTL / 3
