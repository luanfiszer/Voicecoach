"""Camada de aplicação — casos de uso, portas e Result.

**Pode importar:** ``voicecoach.domain`` e a biblioteca padrão.

**PROIBIDO:** FastAPI, SQLAlchemy, SDKs de IA, cliente Redis, cliente S3 —
qualquer coisa que amarre um caso de uso a uma tecnologia concreta.

O que mora aqui:

- **Casos de uso** (handlers CQS): orquestram domínio + portas.
- **Portas** em ``ports/``, declaradas como ``typing.Protocol``: ``SpeechToText``,
  ``TeacherLlm``, ``TextToSpeech``, ``MediaStorage``, ``TurnQueue``.

``Protocol`` é tipagem estrutural — um adapter satisfaz a porta por ter os
métodos com a assinatura certa, sem herdar nada nem se registrar em lugar
nenhum. É a diferença para C#, onde a classe precisa declarar ``: IPorta``.
Consequência prática boa: em teste, um fake é uma classe comum com os métodos
certos — nenhum framework de mock envolvido.

Equivalente mental .NET: o projeto ``Application``, com as interfaces das
dependências definidas aqui e implementadas fora (inversão de dependência).
"""
