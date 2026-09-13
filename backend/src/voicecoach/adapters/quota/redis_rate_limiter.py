"""``RateLimiter`` sobre um contador de janela fixa em Redis (ADR-0063, item 3).

**Por que um script Lua, e não `INCR` seguido de `EXPIRE`.** Duas chamadas
separadas não são atômicas entre si: o processo pode morrer — ou só ser lento
— entre as duas, deixando uma chave sem TTL que nunca expira (o contador fica
"travado" contando para sempre). O `EVAL` roda o script inteiro num único
passo do Redis, que é single-threaded para execução de comandos: nenhuma outra
operação intercala.

**Fixed window por TTL, não por relógio de parede.** A janela de um contador
começa no primeiro `hit` e dura `window` a partir dali — não é alinhada a
`:00`/`:30` do relógio. É a diferença entre "os últimos 60s móveis a partir de
quando alguém bateu primeiro" e "o minuto corrente do relógio"; a segunda
forma existiria só se o produto prometesse UX baseada nisso (como a cota
diária, que promete "renova à meia-noite" e por isso usa calendário fixo,
não TTL). Aqui não há promessa nenhuma ao aluno — é proteção de
infraestrutura, e o TTL é mais barato de implementar corretamente.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import timedelta

    from redis.asyncio import Redis

PREFIXO = "voicecoach:ratelimit:"

# `INCR` e, só na primeira vez que a chave passa a existir (`current == 1`),
# `PEXPIRE` — isto É a atomicidade: as duas operações acontecem no mesmo
# passo do Redis, sem janela para outra requisição intercalar entre elas.
_SCRIPT = """
local atual = redis.call("INCR", KEYS[1])
if atual == 1 then
    redis.call("PEXPIRE", KEYS[1], ARGV[1])
end
return atual
"""


class RedisRateLimiter:
    """Implementa ``RateLimiter`` com um script Lua registrado uma vez.

    ``register_script`` compila o Lua e devolve um chamável que o `redis-py`
    reenvia por hash (`EVALSHA`) nas chamadas seguintes — evitar reenviar o
    texto do script inteiro a cada `hit` é otimização do próprio cliente, não
    deste adapter.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._script = redis.register_script(_SCRIPT)

    async def hit(self, key: str, *, window: timedelta, limit: int) -> bool:
        janela_ms = int(window.total_seconds() * 1000)
        atual = await self._script(keys=[f"{PREFIXO}{key}"], args=[janela_ms])
        return int(atual) <= limit
