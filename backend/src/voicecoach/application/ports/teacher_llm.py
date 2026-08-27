"""Porta do professor (ADR-0022, ADR-0030, ADR-0031).

**O que atravessa esta porta é um fluxo, não um objeto** — é a diferença entre
o produto ter 1,8 s ou 3,7 s de primeiro áudio, e é a única decisão deste card
que não pode ser convertida depois (ADR-0031).

Enquanto o modelo ainda está escrevendo a resposta, o adapter já emite as
sentenças de `spoken_reply` que dá para ler. O consumidor (CARD-009) manda cada
uma para o TTS sem esperar o JSON fechar. Por isso a assinatura devolve
``AsyncIterator`` e não ``TeacherFeedback``: um objeto só existe depois de
pronto; um fluxo existe enquanto acontece.

A porta **não** conhece TTS, storage nem fila, e o adapter **não guarda
estado**: o histórico entra por parâmetro. Foi o estado global de módulo do
protótipo (``_history``, ``_last_reply``) que travou a evolução dele.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from voicecoach.domain.correction import Correction

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence


class LlmError(RuntimeError):
    """O professor não produziu uma resposta utilizável.

    Herda de ``RuntimeError`` e **não** de ``DomainError``, pela mesma razão
    escrita em ``SttProviderUnavailableError`` (ADR-0017): invariante de domínio
    violada é bug do chamador e levanta ``DomainError``; isto aqui é o provedor
    devolvendo algo fora do schema, estourando o prazo ou caindo. É falha de
    infraestrutura, não regra de negócio quebrada.

    **Mora na porta, não no adapter** — e essa é a diferença em relação ao
    ``SttProviderUnavailableError``, que vive em ``adapters/stt/factory.py``.
    Aquele é erro de subida que ninguém captura. Este o caso de uso do CARD-009
    **vai** capturar, e ``application`` não pode importar ``adapters``: seta que
    sobe, ``lint-imports`` vermelho. Onde o erro mora é consequência de quem
    precisa capturá-lo.
    """


class Speaker(StrEnum):
    """Quem falou. Duas vozes, e a enum existe para não trafegar ``str`` cru."""

    STUDENT = "student"
    TEACHER = "teacher"


@dataclass(frozen=True, slots=True)
class Utterance:
    """Uma fala do histórico. O **último** item é a fala nova do aluno.

    Deliberadamente pobre, como o ``AudioInput`` do STT (ADR-0029): nada do
    formato de mensagem do provedor atravessa a porta. Traduzir isto para o que
    o SDK espera é trabalho do adapter.
    """

    speaker: Speaker
    text: str


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """As três contagens de entrada, separadas, mais a saída (ADR-0021, item 3).

    O prompt caching está **adiado**, não esquecido: o limiar medido para o
    Haiku 4.5 é 4.096 tokens e uma conversa deste produto não chega lá. Estes
    campos são o instrumento que detecta a mudança de regime — sem eles, não há
    como saber que o caching passou a valer a pena. O CARD-014 os persiste.

    **``model`` entrou no CARD-014**, e a razão é de precificação, não de
    telemetria: contagem de tokens sem o modelo que as consumiu **não tem
    preço**. O valor é o que a resposta declara (`message.model`), não o que a
    configuração pediu — `TEACHER_MODEL` costuma ser um alias
    (`claude-haiku-4-5`) que resolve para um id datado, e um dia o alias aponta
    para outro lugar. Perguntar à config qual modelo *deveria* ter respondido
    tornaria a linha de custo impossível de auditar no dia em que os dois
    divergissem — que é justamente o dia em que alguém iria querer auditá-la.
    """

    model: str
    input_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class TeacherFeedback:
    """A resposta completa do professor, já validada.

    A ordem dos campos aqui espelha o ADR-0022 e **não é escolha de
    legibilidade**: ``spoken_reply`` primeiro porque é o único campo no caminho
    crítico até o aluno ouvir alguma coisa. Mexer nisto exige ADR novo.

    **O que mudou no CARD-013.** ``has_mistakes``, ``original``, ``corrected`` e
    ``tip`` saíram daqui e ``corrections`` entrou no lugar. Três consequências
    que valem estar escritas:

    1. **Isto não fere o ADR-0008.** A política aditiva protege o contrato
       ``/v1``, que é HTTP; esta é uma **porta interna**, e os quatro campos
       continuam existindo na borda — derivados por ``legacy_summary``.
    2. **O modelo passa a gerar menos**, não mais. Trocar três strings por um
       array de objetos aumentaria a saída; parar de pedir as três de volta
       compensa parte disso, e o número real está medido no CARD-013.
    3. ``corrections`` vem **por último** de propósito: é o campo mais longo, e
       cada byte gerado antes de ``spoken_reply`` fechar é atraso no primeiro
       áudio audível. É o ADR-0022 aplicado a um campo que ele não previa.

    ``tuple`` e não ``list``: o ``frozen=True`` só congela as *referências* — uma
    lista dentro de um dataclass congelado continua mutável, e o objeto deixaria
    de ser hasheável. É a diferença entre um ``record`` com ``IReadOnlyList`` e
    um com ``List`` em C#, com a agravante de que aqui o compilador não avisa.
    """

    spoken_reply: str
    translation_pt: str
    corrections: tuple[Correction, ...]


@dataclass(frozen=True, slots=True)
class SpokenSentence:
    """Um trecho de fala pronto para virar áudio, emitido durante a geração.

    ``frozen=True`` dá ``__eq__`` por valor de graça, e é isso que faz o teste
    do fluxo poder comparar **listas inteiras de eventos** com um ``==`` só.
    """

    text: str


@dataclass(frozen=True, slots=True)
class FeedbackReady:
    """O último evento do fluxo: a resposta inteira, validada, com o custo.

    Vem **depois** de todas as ``SpokenSentence`` e fecha o fluxo. Quem só quer
    falar ignora este evento; quem persiste correções (CARD-013) e custo
    (CARD-014) só precisa dele.
    """

    feedback: TeacherFeedback
    usage: TokenUsage


# União FECHADA. `type` é a forma do Python 3.12 de declarar um alias de tipo
# (PEP 695): preguiçoso, avaliado só quando o type checker precisa. O paralelo
# em C# seria uma hierarquia selada — com a diferença de que aqui não há classe
# base nenhuma, e é o `|` que fecha o conjunto.
#
# Quem consome faz `match` sobre os dois casos e termina com `assert_never`: sem
# ele, acrescentar um evento novo passa VERDE no mypy e explode em runtime.
type TeacherEvent = SpokenSentence | FeedbackReady


class TeacherLlm(Protocol):
    """Responde ao aluno, em cascata.

    **Repare que o método NÃO é ``async def``** — e isso não é descuido. Uma
    função ``async def`` com ``yield`` é um *gerador assíncrono*: chamá-la
    devolve o gerador **na hora**, sem ``await``, e nada dentro dela executa até
    alguém iterar com ``async for``. Declarar a porta como ``async def ... ->
    AsyncIterator`` significaria outra coisa — uma corrotina que, depois de
    aguardada, devolve um iterador — e nenhum gerador assíncrono a satisfaz.

    O equivalente mental é ``IAsyncEnumerable<T>`` com ``yield return``, com uma
    diferença que muda o desenho: em C# o cancelamento é um ``CancellationToken``
    que alguém tem de passar adiante; aqui ele vem do próprio protocolo do
    gerador — **abandonar o ``async for`` fecha o fluxo**, e o adapter só precisa
    não atrapalhar.
    """

    def respond_streaming(
        self, history: Sequence[Utterance]
    ) -> AsyncIterator[TeacherEvent]: ...
