"""Camada de API — o adapter de entrada HTTP (FastAPI).

**Pode importar:** ``application``, ``adapters`` (para compor as dependências)
e ``domain``.

**PROIBIDO:** ser importada por qualquer outra camada, e conter regra de
negócio. Router que decide algo além de "traduzir HTTP para caso de uso e o
Result de volta para HTTP" está fazendo o trabalho de ``application``.

O que mora aqui: routers sob ``/v1``, schemas pydantic do contrato, auth,
exception handlers (Problem Details), composition root.

Os schemas pydantic daqui **não** são as entidades de ``domain``: são o
contrato público, que evolui apenas aditivamente porque o app instalado no
celular do usuário não atualiza quando queremos (ADR-0008).

Equivalente mental .NET: o projeto ``API`` — controllers, DTOs e o
``Program.cs`` que registra tudo no contêiner.
"""
