"""Camada de worker — o adapter de entrada assíncrono (arq sobre Redis).

**Pode importar:** ``application``, ``adapters`` e ``domain``.

**PROIBIDO:** ser importada por qualquer outra camada, e conter regra de
negócio. O worker é entrypoint: pega o job da fila, chama o caso de uso,
trata falha e retry.

É aqui que o pipeline pesado de um Turn roda (STT → LLM → TTS), fora do
request HTTP — a API responde ``202`` e devolve o ``turn_id`` (ADR-0005).

Note que ``api`` e ``worker`` são irmãos e **não se importam**: são dois
entrypoints do mesmo núcleo. O contrato do import-linter trata os dois como
uma camada só, justamente para proibir a seta entre eles.

Equivalente mental .NET: o host de um ``BackgroundService`` — processo
separado, mesma Application por baixo.
"""
