"""Routers HTTP. Cada módulo traduz HTTP para caso de uso e de volta.

**O ``/v1`` é declarado UMA vez, aqui.** O ADR-0008 fez do prefixo uma fronteira
de contrato — dentro dele só há evolução aditiva, e um breaking change abre
``/v2`` convivendo. Uma fronteira dessas não pode estar espalhada por um
``include_router(prefix="/v1")`` em cada rota: o dia em que o ``/v2`` existir,
alguém teria de encontrar todos.

Os routers filhos **não** carregam o prefixo. É o que os torna montáveis em
``/v2`` sem edição, quando for a hora.

``health`` fica de fora do ``/v1`` de propósito: probe de infraestrutura não é
contrato de produto e não versiona junto com ele (ADR-0014).
"""

from fastapi import APIRouter

from voicecoach.api.routes import sessions, turns

v1 = APIRouter(prefix="/v1")
v1.include_router(sessions.router)
v1.include_router(turns.router)

__all__ = ["v1"]
