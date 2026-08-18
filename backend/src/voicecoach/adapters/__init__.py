"""Camada de adapters — implementações concretas das portas.

**Pode importar:** ``voicecoach.application`` (para implementar suas portas),
``voicecoach.domain`` e qualquer biblioteca externa.

**PROIBIDO:** importar de ``voicecoach.api`` ou ``voicecoach.worker`` — adapter
não conhece quem o usa. E nada de regra de negócio: se apareceu um ``if`` que
decide algo pedagógico, ele está na camada errada.

O que mora aqui: repositórios SQLAlchemy, STT/LLM/TTS (locais e de provider),
storage S3/MinIO, fila arq, cliente Redis.

Esta é a camada que existe para ser trocada: substituir o TTS por outro
provider é um arquivo novo aqui e zero mudança acima.

Equivalente mental .NET: o projeto ``Infrastructure``.
"""
