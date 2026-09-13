"""A tradução sob demanda de um texto já produzido pelo produto (CARD-036).

**Por que fora do agregado ``Turn``**, e o precedente é o ADR-0051: o
``UsageEvent`` ficou de fora para que o ciclo de vida do turn não arrastasse o
registro financeiro. Aqui vale o mesmo e mais um motivo — traduzir **não** é
uma interação pedagógica (RF2): não cria turn, não muda o histórico do
professor e não mexe na cota de minutos. Pendurá-la em ``Turn.translations``
faria toda leitura de turn carregar (ou declarar que não carrega) uma coleção
que o caminho crítico de 1,8 s nunca usa.

**Por que é dado persistido e não cache** (RNF1, a espinha do card): o texto de
origem é imutável depois de gravado, então a tradução **nunca invalida**. Não
há TTL a escolher nem gatilho de invalidação a escrever — o que existe é a
pergunta "já traduzi isto?", que é uma consulta, não um cache. E o preço de
errar é dinheiro: cache que expira faz o produto pagar de novo pela mesma
tradução (RF4).

**Isto não é o dado derivado que o ADR-0016/0049 recusou.** Lá, o campo
espelhado podia ser recalculado por uma função pura e por isso duplicava
verdade. Traduzir não é derivação: é uma chamada paga a um provedor externo,
não-determinística. Guardar o resultado é memoização de trabalho caro, não
segunda fonte de verdade.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    from decimal import Decimal
    from uuid import UUID


class TranslationTarget(StrEnum):
    """Qual texto **do produto** foi traduzido (RF1).

    Enum fechado, e é ele que implementa a decisão de segurança do RF1: o
    cliente escolhe entre alvos conhecidos, nunca manda o texto. Um endpoint
    que traduzisse texto livre seria um proxy de LLM aberto pago por nós — o
    risco que o card nomeia primeiro.

    Acrescentar membro é aditivo e permitido (ADR-0008); renomear invalida
    linha gravada, como em todo enum persistido deste projeto (ADR-0049).
    """

    REPLY = "reply"
    CORRECTION = "correction"


@dataclass(frozen=True, slots=True)
class Translation:
    """Uma tradução gravada, com o custo congelado na escrita (RF3/ADR-0051).

    ``index`` completa a identidade natural dentro do turn — a mesma
    disciplina do ``TurnAudioChunk`` (ADR-0023) e do ``Correction``
    (ADR-0049): sem id surrogate, chave primária composta
    ``(turn_id, target, index)``. Para ``REPLY`` ele é sempre ``0`` (há uma
    resposta por turn); para ``CORRECTION`` é o índice da correção, que já é
    a ordem pedagógica.

    ``estimated_cost_usd`` é ``None`` quando o modelo não está na tabela de
    preços — nunca zero. É a mesma regra do ``UsageEvent`` e pelo mesmo
    motivo: zero é um custo verdadeiro (o STT e o TTS locais custam zero),
    e escrever zero aqui faria o gasto com tradução parecer grátis em vez de
    desconhecido.
    """

    turn_id: UUID
    target: TranslationTarget
    index: int
    text: str
    model: str
    created_at: datetime
    estimated_cost_usd: Decimal | None

    def __post_init__(self) -> None:
        if self.index < 0:
            message = "Translation: index é 0-based e não pode ser negativo."
            raise ValueError(message)
        if not self.text.strip():
            message = "Translation: texto traduzido vazio não é tradução."
            raise ValueError(message)
