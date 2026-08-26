"""``Correction`` — a entidade mais valiosa do produto (visão §A).

Até o CARD-013 a correção só **transitava**: nascia no LLM, virava um evento SSE,
aparecia na tela e sumia. Nada era guardado, e por isso três coisas não existiam
— o histórico (CARD-016), a retomada completa do SSE (ADR-0041 item 5) e o
padrão de erro recorrente (pós-MVP).

**O que este módulo decide, e o card não antecipava.** O contrato ``/v1`` tem
quatro campos texto herdados do protótipo (``has_mistakes``, ``original``,
``corrected``, ``tip``) que o ADR-0008 **proíbe** remover. Eles não desaparecem —
passam a ser **derivados** de ``corrections`` por ``legacy_summary``, numa função
pura usada tanto pelo evento ao vivo quanto pela retomada do banco. A alternativa
(persistir também as quatro colunas) seria a mesma verdade gravada duas vezes,
que é exatamente o que o ADR-0023 recusa ao derivar ``stage``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


class CorrectionType(StrEnum):
    """A natureza do erro. Enum **fechado**, como ``TurnStatus``.

    Acrescentar um valor é aditivo e permitido; renomear não é (ADR-0008), e a
    consequência de renomear é dupla — quebra o cliente antigo **e** invalida
    todo valor já gravado na coluna, porque o Postgres guarda o texto do membro.

    ``OTHER`` existe para que o modelo tenha para onde ir quando a correção não
    couber nas outras quatro. Sem essa saída, o custo de uma classificação
    impossível seria uma resposta fora do schema — ou seja, ``LlmError`` e turn
    falho por um erro de taxonomia.
    """

    GRAMMAR = "grammar"
    VOCABULARY = "vocabulary"
    PREPOSITION = "preposition"
    WORD_ORDER = "word_order"
    OTHER = "other"


class Severity(StrEnum):
    """Quanto o erro pesa. Três níveis, e o número é a decisão.

    A UI apresenta severidade em **palavras** ("pequeno ajuste", "vale revisar")
    — o que só é traduzível a partir de uma escala pequena e estável. Três é o
    menor número que ainda permite ordenar e destacar sem virar escala falsa;
    dois perderiam o meio-termo, e um quarto nível ("critical") seria um rótulo
    que nem o modelo nem o produto sabem definir num tutor de conversa, ainda
    mais sem eval (Fase 4).

    **O rótulo em pt-BR não mora aqui.** Tradução é apresentação e vive no
    cliente (CARD-016): o dia em que a mesma correção precisar aparecer em duas
    línguas, o domínio não muda.
    """

    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"


@dataclass(frozen=True, slots=True)
class Correction:
    """Uma correção da fala do aluno, já classificada.

    ``frozen=True`` pelo mesmo motivo de ``TurnAudioChunk``: correção emitida não
    muda. E é ele que gera ``__eq__`` **por valor**, o que permite ao teste de
    roundtrip comparar a lista inteira que voltou do Postgres com a lista
    original usando um ``==`` só — sem isso, a comparação seria por identidade de
    objeto e passaria a exigir um laço campo a campo.

    ``index`` é 0-based e denso, como o do trecho de áudio, e pela mesma razão:
    ele é a **identidade natural** dentro do turn, o que dispensa um id
    surrogate e dá a chave primária composta ``(turn_id, index)``. Aqui ele
    carrega um segundo significado — é a **ordem pedagógica** em que o professor
    priorizou as correções, e é dela que ``legacy_summary`` tira a correção que
    representa o turn nos campos velhos do contrato.

    Não há ``created_at``: todas as correções de um turn nascem no mesmo
    instante, o do ``replied_at`` do próprio Turn. Uma coluna por linha para
    repetir um valor que já existe uma vez é o dado duplicado do ADR-0016.
    """

    index: int
    type: CorrectionType
    original_excerpt: str
    corrected_form: str
    explanation: str
    severity: Severity


@dataclass(frozen=True, slots=True)
class LegacyFeedbackSummary:
    """Os quatro campos texto do contrato ``/v1``, derivados de ``corrections``.

    **Por que isto existe.** O ADR-0008 proíbe remover ou renomear campo dentro
    de ``/v1``, e a restrição dura que o motivou é o app na loja que não
    atualiza quando queremos. Então ``has_mistakes``, ``original``, ``corrected``
    e ``tip`` continuam no ``GET`` e no evento ``feedback`` — só que agora com
    **uma** regra escrita dizendo quem os preenche quando há duas correções, em
    vez de a resposta ser "a primeira" implícita em algum ``[0]`` perdido no
    código.

    **Quando eles morrem:** no ``/v2``, ou antes disso, quando o app mínimo
    suportado já ler ``corrections[]`` — pergunta que o ``GET /v1/meta`` sabe
    responder. Enquanto os dois convivem, esta é a única tradução entre eles.
    """

    has_mistakes: bool
    original: str
    corrected: str
    tip: str


def legacy_summary(corrections: Sequence[Correction]) -> LegacyFeedbackSummary:
    """Os campos velhos do contrato, a partir da **primeira** correção.

    A primeira, e não a mais severa: o prompt v2 ordena ``corrections[]`` por
    prioridade pedagógica, então o índice 0 já **é** a correção que o professor
    destacaria. Escolher pela severidade acoplaria o campo legado à escala do
    enum — acrescentar um nível (movimento aditivo e permitido) passaria a mudar
    o que um cliente antigo vê, que é o oposto do que o ADR-0008 promete.

    Sem correção nenhuma, os três textos são string vazia e ``has_mistakes`` é
    ``False``. É exatamente o contrato que o ``v1.md`` já descrevia ("leave
    corrected and tip as empty strings"), preservado por construção.
    """
    if not corrections:
        return LegacyFeedbackSummary(
            has_mistakes=False, original="", corrected="", tip=""
        )
    primeira = corrections[0]
    return LegacyFeedbackSummary(
        has_mistakes=True,
        original=primeira.original_excerpt,
        corrected=primeira.corrected_form,
        tip=primeira.explanation,
    )
