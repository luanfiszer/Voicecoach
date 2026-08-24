"""Problem Details para respostas de erro HTTP — RFC 9457 (ADR-0008, item 5).

**Por que um formato de erro é contrato de API e não detalhe.** Dois clientes
TypeScript consomem esta API (ADR-0002) e precisam distinguir programaticamente
"a sessão acabou" de "o storage caiu" — sem um formato, cada endpoint inventaria
o seu e o cliente faria `if` sobre string de mensagem. Sob o ADR-0008 o contrato
só evolui aditivamente, então o formato do erro é tão contrato quanto o do
sucesso.

**O ``type`` é a chave semântica**, não o texto. ``title`` e ``detail`` são para
humano e podem mudar; ``type`` é o que o cliente compara. Usamos URN
(``urn:voicecoach:problem:...``) em vez de URL porque a RFC pede um URI estável
e não exige que ele resolva — e um ``https://`` apontando para um domínio que o
projeto não possui seria uma promessa falsa de documentação.

O content type é ``application/problem+json``, e ele importa: é o que permite a
um interceptador do cliente reconhecer um erro sem inspecionar o corpo.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

CONTENT_TYPE = "application/problem+json"

BASE = "urn:voicecoach:problem"

TYPE_VALIDATION = f"{BASE}:validation"
TYPE_SESSION_NOT_FOUND = f"{BASE}:session-not-found"
TYPE_TURN_NOT_FOUND = f"{BASE}:turn-not-found"
TYPE_INVALID_STATE = f"{BASE}:invalid-state"
TYPE_INVALID_EVENT_ID = f"{BASE}:invalid-event-id"
TYPE_DEPENDENCY_UNAVAILABLE = f"{BASE}:dependency-unavailable"


class ProblemDetails(BaseModel):
    """O corpo de toda resposta de erro da API.

    ``model_config = ConfigDict(extra="allow")`` deixa cada problema acrescentar
    os seus próprios campos — é o que a RFC 9457 chama de *extension members*, e
    é o que permite ao ``session-not-found`` carregar o ``session_id`` sem
    inventar um envelope. Sem isso, ou o modelo teria um campo por caso, ou a
    informação útil viraria texto dentro de ``detail``.
    """

    model_config = ConfigDict(extra="allow")

    type: str = Field(description="URN estável do tipo de problema.")
    title: str = Field(description="Resumo legível, o mesmo para todo tipo.")
    status: int = Field(description="O código HTTP, repetido no corpo.")
    detail: str | None = Field(
        default=None, description="O que houve nesta ocorrência específica."
    )
