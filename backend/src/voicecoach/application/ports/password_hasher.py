"""Porta de hash de senha — argon2id, decidido no ADR-0007 (CARD-049).

**Por que os métodos são ``async`` para uma operação sem IO nenhum.**
``argon2id`` é uma KDF *deliberadamente* cara de CPU (é a defesa contra força
bruta offline) — o mesmo motivo por que ``run_in_executor`` existe para o
`put_object` síncrono do S3 (ADR-0034), aplicado aqui a um cálculo em vez de
uma chamada de rede: ~50-100ms bloqueando o event loop único da API
serializaria TODA requisição concorrente atrás de um login. O adapter
concreto empurra o cálculo para um executor; a porta só promete que quem
chama pode ``await`` sem travar o processo.
"""

from __future__ import annotations

from typing import Protocol


class PasswordHasher(Protocol):
    """Hash e verificação de senha, nunca reversível."""

    async def hash(self, password: str) -> str:
        """O hash a persistir — carrega o salt e os parâmetros dentro de si
        (formato ``$argon2id$...``), então não há coluna de salt separada.
        """
        ...

    async def verify(self, password: str, password_hash: str) -> bool:
        """``True`` se ``password`` produz ``password_hash``.

        **Chamar sempre**, mesmo quando o e-mail não existe — é o que faz o
        tempo de resposta do login não distinguir "senha errada" de "conta
        não existe" (critério de aceite do CARD-049). Quem decide isso é
        ``LoginStudentHandler``, comparando contra um hash de preenchimento
        quando a credencial não é encontrada.
        """
        ...
