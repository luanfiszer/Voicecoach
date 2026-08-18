"""Camada de domínio — entidades, value objects e regras puras.

**Pode importar:** apenas a biblioteca padrão do Python e outros módulos de
``voicecoach.domain``.

**PROIBIDO:** qualquer framework, SDK de provider ou IO — FastAPI, pydantic,
SQLAlchemy, httpx, redis, anthropic, openai, sistema de arquivos, rede,
relógio de parede sem injeção.

Se uma regra aqui precisa saber a hora, receber um repositório ou falar com um
provider, ela não pertence a esta camada — pertence a ``application``.

Equivalente mental .NET: o projeto ``Domain``, que não referencia nenhum outro.
"""
