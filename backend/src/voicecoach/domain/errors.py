"""Erros de domínio (ADR-0017).

A regra do ADR-0017 em uma frase: **invariante violada é bug do chamador**, não
desfecho previsto do negócio — por isso levanta exceção, e não devolve um valor
que alguém pode esquecer de olhar.

Falha *esperada* de caso de uso (quota estourada, chave de idempotência
repetida) é outra coisa e ainda não tem forma decidida: o ADR-0017 deixou o
``Result`` como TBD, com gatilho no primeiro caso de uso real (CARD-010/015).

``DomainError`` existe como raiz para a borda capturar em **um** lugar só e
traduzir para Problem Details (RFC 9457, CARD-010). O núcleo não sabe o que é
HTTP.
"""

from __future__ import annotations


class DomainError(Exception):
    """Raiz de todo erro de regra de negócio deste domínio."""


class InvalidStateTransitionError(DomainError):
    """A transição pedida não existe a partir do estado atual.

    Carrega os três dados que tornam a mensagem útil sem precisar de debugger:
    o que se tentou fazer, de que estado, e sobre qual entidade.
    """

    def __init__(self, *, entity: str, action: str, state: str) -> None:
        self.entity = entity
        self.action = action
        self.state = state
        super().__init__(f"{entity}: não é possível '{action}' no estado '{state}'.")
