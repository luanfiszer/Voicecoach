"""Porta de enfileiramento de turns (ADR-0005).

Uma operação só, e de propósito. A borda que aceita o áudio do aluno (CARD-010)
precisa dizer "processe este turn" e devolver a resposta HTTP **antes** de o
trabalho começar; tudo o mais que uma biblioteca de fila oferece — prioridade,
agendamento, resultado do job, tentativas restantes — é mecânica do adapter e
não pergunta que a aplicação faça.

**Por que ``enqueue`` não devolve nada.** O ``arq`` devolve um ``Job``, com id e
estado, e seria natural repassá-lo. Não pode: tipar o retorno com ele arrastaria
o ``arq`` para dentro de ``application`` — verificado nesta sessão, o contrato
``forbidden`` reprova (``3 kept, 1 broken``). E não é só o lint: o estado do
trabalho já tem dono, que é o ``Turn`` no banco (ADR-0023). Um segundo lugar
dizendo "como vai o processamento" é a duplicação que o ADR-0016 rejeitou.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID


class TurnQueueError(RuntimeError):
    """Não foi possível enfileirar o turn.

    Mora na porta pela mesma razão do ``LlmError`` e do ``TtsError`` (ADR-0031,
    item 5): quem captura é a borda, em ``api``, para responder 503 em vez de
    aceitar um turn que ninguém vai processar — e ``application`` não pode
    importar ``adapters``.
    """


class TurnQueue(Protocol):
    """Manda um turn para o worker."""

    async def enqueue(self, turn_id: UUID) -> None: ...
