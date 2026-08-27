"""``UsageEvent`` — o custo real de um turn (visão §D, CARD-014).

Até aqui o custo do produto era **estimativa**: a §2 de
`docs/analise-custo-e-precificacao.md` supunha um system prompt de ~700 tokens e
dividia o turn "meio a meio" entre entrada e saída. O `TokenUsage` real
atravessava a porta do professor desde o CARD-007 e era **descartado** pelo caso
de uso. Este módulo é o outro lado dessa conta.

**O que este módulo decide, e o card não antecipava.**

1. **O custo é congelado na escrita, não recalculado na leitura** (ADR-0051).
   Consequência direta: a tabela de preços é *config descartável* — ela responde
   "quanto custa hoje", nunca "quanto custava em julho". Quem responde a segunda
   é a linha gravada.
2. **Preço desconhecido é ``None``, nunca ``0``.** Zero é o custo verdadeiro do
   STT e do TTS locais; ausência de preço é outra coisa. Gravar zero faria a
   cota do CARD-015 ler como grátis um turn que ninguém sabe precificar.
3. **A duração do áudio do aluno é ``timedelta``**, o mesmo tipo e a mesma
   unidade de ``Turn.audio_duration``. O card pedia ``stt_seconds``; um ``float``
   de segundos ao lado de um ``timedelta`` criaria justamente a divergência de
   unidade que o CARD-015 teria de resolver.

**O idioma de Python que não é o do C#:** o ``decimal`` daqui **não** é o
``decimal`` da linguagem. Em C# ele é um tipo primitivo de 128 bits com escala
fixa; em Python é uma classe da stdlib cuja precisão vive num **contexto global e
mutável** (28 dígitos significativos por default, alterável em runtime). Por isso
o arredondamento aqui é **explícito** (``quantize``), e nunca implícito.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime, timedelta
    from uuid import UUID

# Um milhão. Preço de modelo é cotado por MTok, e a divisão por este número é o
# único lugar do cálculo em que a conta deixa de ser aritmética de inteiros.
TOKENS_POR_MILHAO = Decimal(1_000_000)

# Oito casas decimais, e o número tem motivo: um turn custa ~US$ 0,004.
# Arredondar a 2 casas — o instinto de quem lida com dinheiro de varejo —
# gravaria **zero** em todo turn deste produto. A escala é a do custo unitário,
# não a da fatura.
CENTAVO_DE_MILIONESIMO = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class LlmPrice:
    """O preço de um modelo, em dólares por milhão de tokens, com data.

    ``effective_from`` não é enfeite nem auditoria: é o que torna a tabela
    **verificável**. Sem ela, "o preço está desatualizado?" é uma pergunta que só
    se responde abrindo a página do provedor; com ela, a resposta está no
    repositório, e o teste que compara o custo gravado com a tabela sabe contra
    qual versão da tabela ele está comparando.

    As **três** entradas separadas existem porque cacheamento tem preço próprio
    nos dois sentidos (ADR-0021): escrever cache custa **1,25x** a entrada normal
    e ler custa **0,1x**. Hoje as duas últimas nunca são acionadas — o limiar
    medido do Haiku 4.5 é 4.096 tokens e a conversa não chega lá. Elas estão aqui
    pelo mesmo motivo que as contagens estão no `UsageEvent`: o dia em que
    deixarem de ser zero é o gatilho de reabrir o caching, e um instrumento que
    só se constrói depois do fato não mede o fato.
    """

    input_usd_per_mtok: Decimal
    cache_creation_usd_per_mtok: Decimal
    cache_read_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    effective_from: date


def estimate_llm_cost(
    *,
    input_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
    output_tokens: int,
    price: LlmPrice,
) -> Decimal:
    """O custo em dólares das quatro contagens, arredondado uma vez só.

    **O arredondamento acontece no fim, e essa é a decisão.** Quantizar cada
    parcela e somar depois perderia precisão exatamente nos turns baratos, que
    são todos os turns deste produto: 180 tokens de saída a US$ 5/MTok são
    US$ 0,0009, e três dessas parcelas arredondadas a 2 casas somam zero.

    ``ROUND_HALF_UP`` e não o default do Python (``ROUND_HALF_EVEN``, o
    arredondamento bancário) porque a métade exata é o caso que um humano vai
    conferir na calculadora ao ler a tabela de preços — e a calculadora dele
    arredonda para cima.

    Todos os parâmetros são **nomeados** (o ``*`` na assinatura): são quatro
    inteiros do mesmo tipo, e trocar dois deles de posição seria um erro que
    nenhum type checker pega e que sub-relata custo em silêncio.
    """
    bruto = (
        input_tokens * price.input_usd_per_mtok
        + cache_creation_tokens * price.cache_creation_usd_per_mtok
        + cache_read_tokens * price.cache_read_usd_per_mtok
        + output_tokens * price.output_usd_per_mtok
    ) / TOKENS_POR_MILHAO
    return bruto.quantize(CENTAVO_DE_MILIONESIMO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class UsageEvent:
    """O que um turn consumiu, e o que isso custou.

    **Não é entidade filha do `Turn`** (ADR-0051, decisão 2), ao contrário de
    `Correction` e `TurnAudioChunk`. Três razões, e nenhuma é estilo:

    - ele é lido em **agregação** ("quanto este aluno gastou hoje"), nunca na
      leitura de um turn. Carregá-lo em todo ``TurnRepository.get()`` seria peso
      puro no caminho crítico de 1,8 s, para um dado que aquela leitura não usa;
    - ``student_id`` mora aqui **desnormalizado**, e é isso que faz a agregação
      do CARD-015 não precisar de join com `turns` — ela vai rodar dentro do
      `POST`, para decidir se o aluno ainda tem cota;
    - ele responde a perguntas de outra natureza (custo, margem) e sobrevive a
      decisões de retenção próprias.

    ``frozen=True`` porque medição não se corrige: o turn consumiu o que
    consumiu. Se o cálculo estiver errado, o conserto é uma linha nova com o
    motivo, não a reescrita silenciosa de um número que alguém já somou.

    **Nenhum campo é coleção.** É deliberado, e é a resposta à pergunta que
    ficou aberta no CARD-013 (Q15): num `@dataclass(frozen=True, slots=True)`,
    `frozen` congela a *ligação*, não o objeto — um `list[...]` continuaria
    mutável por dentro, com `mypy --strict` verde, e só `hash()` denunciaria. Um
    registro de medição com coleção mutável seria a pior versão disso: o teste de
    roundtrip compararia iguais dois eventos que divergiram.
    """

    turn_id: UUID
    student_id: UUID
    occurred_at: datetime

    # -- LLM: a única parcela que custa dinheiro (análise de custo §2) --------
    #
    # O modelo é gravado por linha e vem da **resposta**, não da configuração:
    # `TEACHER_MODEL` diz o que foi pedido, `message.model` diz o que respondeu.
    # Um alias (`claude-haiku-4-5`) resolve para um id datado, e é o datado que
    # tem preço. Guardar o pedido em vez do servido tornaria a linha impossível
    # de reprecificar depois.
    llm_model: str
    llm_input_tokens: int
    # As duas contagens de cache, separadas (ADR-0021, item 3). Hoje são 0 em
    # toda chamada — e o valor 0 é **dado**, não ausência: é ele que sustenta a
    # afirmação "o caching continua não valendo a pena" com evidência em vez de
    # com memória.
    llm_cache_creation_tokens: int
    llm_cache_read_tokens: int
    llm_output_tokens: int

    # -- STT e TTS: custo zero, volume registrado ----------------------------
    #
    # `timedelta`, como `Turn.audio_duration`, de onde este valor vem. Ele é
    # copiado para cá em vez de lido por join pela mesma razão que `student_id`:
    # a agregação de minutos falados é a outra metade da decisão de cota do
    # CARD-015, e ela roda no caminho de um request.
    stt_audio_duration: timedelta
    stt_provider: str
    # A soma de `len(texto)` das sentenças que foram sintetizadas. Volume, não
    # custo: o Piper roda local (ADR-0032). Existe para que a conta continue
    # verdadeira no dia em que o TTS virar API paga — sem ele, essa migração
    # começaria sem nenhuma série histórica.
    tts_chars: int
    tts_provider: str

    # `None` significa **"não sabemos precificar este modelo"**, e é diferente de
    # `Decimal(0)`, que é o custo verdadeiro do STT e do TTS locais. A distinção
    # é a mesma que o card faz sobre `cache_read = 0` ("zero é dado, não
    # ausência"), aplicada ao outro lado: gravar zero num modelo fora da tabela
    # faria o kill switch do CARD-015 ler como grátis um turn que ninguém sabe
    # quanto custou.
    estimated_cost_usd: Decimal | None


@dataclass(frozen=True, slots=True)
class StudentUsageTotals:
    """O que um aluno consumiu numa janela — **em minutos e em turns**.

    As duas unidades juntas, e não uma, porque a unidade da cota está em aberto:
    a análise de custo §8 mediu uma divergência de 3x entre "minutos falados" (o
    que o produto promete) e "turns" (o que de fato gera custo), e o ADR que
    resolve isso está listado como pendente de decisão de produto. Uma agregação
    que devolvesse só uma das duas escolheria a resposta antes da pergunta.

    ``cost_usd`` é a soma do que **foi possível precificar**. Linhas com
    ``estimated_cost_usd`` nulo entram em ``turns`` e em ``spoken`` e ficam de
    fora daqui — por isso ``unpriced_turns`` existe: sem ele, um custo
    subestimado seria indistinguível de um custo baixo.
    """

    turns: int
    spoken: timedelta
    cost_usd: Decimal
    unpriced_turns: int
