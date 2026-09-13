"""Porta da tradução sob demanda (CARD-036, ADR-0009).

**Porta própria, e não mais um método em ``TeacherLlm``** — é a pergunta que o
objetivo de aprendizado do card faz, e a resposta sai da regra que o projeto já
usa: *nome de porta é a capacidade* (visão §D). "Ser professor" e "traduzir"
são capacidades diferentes, e a diferença é observável em quatro eixos:

===============  ==========================  ================================
                 ``TeacherLlm``              ``Translator``
===============  ==========================  ================================
forma            fluxo de eventos            uma chamada, um valor
latência         caminho crítico de 1,8 s    o aluno pediu e espera (RNF5)
modelo           o forte (ADR-0009)          o barato (RF5)
estado           histórico da conversa       nenhum: texto entra, texto sai
===============  ==========================  ================================

Um método a mais na porta do professor obrigaria todo dublê de ``TeacherLlm``
(são vários) a implementar tradução para continuar satisfazendo o ``Protocol``,
e amarraria a troca do modelo forte à do barato. Duas portas custam um arquivo;
uma porta com dois papéis custa em todo teste que a substitui.

**``TokenUsage`` vem de ``teacher_llm`` de propósito.** Ele não é vocabulário do
professor: é "o que o provedor cobrou", e é o insumo de preço de qualquer porta
que fale com LLM. Duplicá-lo aqui criaria dois tipos que sairiam de sincronia no
primeiro campo novo (o ADR-0021 já prevê mais campos de cache). **Gatilho para
extraí-lo para um módulo próprio:** uma terceira porta de LLM aparecer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from voicecoach.application.ports.teacher_llm import TokenUsage


class TranslatorError(RuntimeError):
    """O tradutor não devolveu tradução utilizável — caiu, demorou ou recusou.

    ``RuntimeError`` e **não** ``DomainError``, pela mesma razão do
    ``LlmError`` (ADR-0017): não há invariante de negócio violada, há um
    provedor que não colaborou. A borda a traduz para o desfecho de
    dependência indisponível (503), que é o RF6 do card: o texto original
    continua legível e a UI diz que não deu.

    Não há distinção entre "caiu" e "respondeu mal" como em
    ``TeacherUnavailableError``, e a omissão é decisão: aquela distinção
    existe para alimentar o breaker e para escolher entre duas telas
    diferentes. Aqui só há uma tela ("não deu para traduzir agora") e não há
    breaker — ver a decisão de resiliência no ADR-0066.
    """


@dataclass(frozen=True, slots=True)
class Translated:
    """O texto traduzido e o que ele custou em tokens.

    ``usage`` viaja junto porque **contagem sem modelo não tem preço**
    (a mesma nota do ``TokenUsage``): quem grava a linha precisa dos dois
    para congelar o custo na escrita (RF3, ADR-0051).
    """

    text: str
    usage: TokenUsage


class Translator(Protocol):
    """Traduz para português um texto que o produto já produziu."""

    async def to_portuguese(self, text: str) -> Translated:
        """Traduz ``text``, ou levanta ``TranslatorError``.

        O idioma de destino está no **nome do método**, e não num parâmetro,
        porque ele não é escolha de quem chama: é pt-BR, decidido no escopo do
        card ("escolha de idioma de destino é card futuro com gatilho"). Um
        parâmetro convidaria a borda a repassar um idioma vindo do cliente —
        que é a mesma classe de brecha que o RF1 fecha para o texto.
        """
        ...
