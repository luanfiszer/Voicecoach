"""Circuit breaker de processo, para adapters que falam com provedor remoto.

**Por que código próprio e não uma biblioteca** (ADR-0053, decisão 2). A
pergunta não é "existe biblioteca?" — existe. É *"a biblioteca embrulha a coisa
que eu tenho?"*, e aqui não embrulha: o professor é um **gerador assíncrono com
ponto de não-retorno** (ADR-0030). A janela em que falhar conta como "provedor
fora" termina no primeiro ``yield``; depois dele o provedor está claramente vivo
— ele já entregou fala — e uma falha é outra coisa. Toda biblioteca de breaker
do ecossistema decora uma **corrotina**, cujo desfecho é um valor só: sucesso ou
exceção, no fim. Aplicá-la aqui contaria como falha do provedor um erro que
aconteceu depois de o aluno já estar ouvindo a resposta, e abriria o circuito
pelo motivo errado. Adaptar o gerador à biblioteca seria mais código que as ~50
linhas abaixo, e código de contorno em vez de código de decisão.

**Equivalente mental .NET, e onde a analogia com o Polly quebra.** No Polly a
política é um objeto registrado no contêiner e aplicado pelo
``HttpClientFactory`` — o pipeline de handlers fica longe do código de negócio
quase por acidente do framework. Em Python não existe esse acidente: um
decorator é só uma função que embrulha outra, e **nada impede** que alguém o
ponha em cima de um caso de uso. O ``lint-imports`` pega o *import*, não o
conceito (ADR-0012, ADR-0052). Por isso esta classe é um objeto explícito que o
adapter chama em três pontos nomeados, e não um ``@decorator`` de uso livre: a
forma torna difícil pendurá-la no lugar errado.

**O estado é do PROCESSO, e isso é aceito, não esquecido** (ADR-0053,
consequência negativa). API e worker abrem circuitos independentes; duas
réplicas de worker, idem. Hoje é irrelevante — o professor só é chamado do
worker, com ``MAX_JOBS = 1`` (ADR-0025), ou seja **uma chamada por vez**. Um
breaker aqui não protege contra concorrência: protege contra **repetição em
série**, que é exatamente o modo de falha do produto (um aluno depois do outro
pagando 60 s para descobrir a mesma coisa).

**Gatilho para compartilhar o estado:** mais de uma réplica de worker chamando o
professor. O vocabulário a imitar então **não é um lock distribuído** — é o que o
``arq`` já faz com ``cron_jobs``: uma chave no Redis cujo significado é a
coordenação (ADR-0052). O Redis já está aberto no ``lifespan`` e no ``ctx``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime, timedelta


class CircuitOpenError(RuntimeError):
    """O circuito está aberto: a chamada nem foi tentada.

    Genérica de propósito — este módulo não conhece professor, storage nem
    tradução. **Quem traduz é o adapter**, para o erro da sua porta
    (``TeacherUnavailableError``), porque é a porta que o caso de uso conhece.
    Um erro de infraestrutura de `adapters` chegando cru a `application` seria a
    seta que o ADR-0012 proíbe — e o `lint-imports` não a pegaria, porque o
    import continuaria na direção certa.
    """


class CircuitBreaker:
    """Fecha a porta depois de N falhas seguidas e a reabre por tempo.

    Três estados, e o do meio é o que faz o circuito não ficar aberto para
    sempre:

    - **fechado** — passa tudo; falha consecutiva incrementa o contador;
    - **aberto** — recusa na hora, sem abrir conexão, até vencer a janela;
    - **meio-aberto** — deixa passar **uma** sonda. Ela decide: sucesso fecha o
      circuito e zera o contador; falha reabre e reinicia a janela.

    **Não há lock, e isso é decisão, não descuido.** Todos os métodos são
    síncronos e nenhum tem ``await`` dentro: sob ``asyncio`` eles rodam inteiros
    entre dois pontos de suspensão, então duas corrotinas nunca os intercalam.
    É a diferença que mais surpreende quem vem do .NET — lá este contador
    exigiria ``Interlocked`` ou ``lock`` porque as threads são preemptivas; aqui
    a ausência de ``await`` **é** a região crítica. (O que isto NÃO protege é
    contra outra *thread* ou outro *processo*: ver o docstring do módulo.)
    """

    def __init__(
        self,
        *,
        failure_threshold: int,
        recovery: timedelta,
        clock: Callable[[], datetime],
        name: str,
    ) -> None:
        self._limite = failure_threshold
        self._recuperacao = recovery
        self._clock = clock
        self._nome = name
        self._falhas = 0
        self._aberto_em: datetime | None = None
        # Uma sonda por janela. Sem isto, dez turns chegando no instante em que
        # a janela vence passariam TODOS — e o benefício do breaker
        # desapareceria exatamente no momento em que ele mais importa.
        self._sondando = False

    def antes_de_chamar(self) -> None:
        """Levanta ``CircuitOpenError`` se a chamada não deve nem ser tentada.

        Chamado **antes** de abrir conexão: é isso que torna a falha barata (o
        critério de aceite do card fala em "sem abrir conexão e em tempo
        desprezível").
        """
        if self._aberto_em is None:
            return

        if self._clock() - self._aberto_em < self._recuperacao:
            message = (
                f"circuito aberto para {self._nome}: "
                f"{self._falhas} falhas seguidas, chamada recusada sem tentar"
            )
            raise CircuitOpenError(message)

        if self._sondando:
            # A janela venceu, mas outra chamada já é a sonda desta janela.
            message = (
                f"circuito aberto para {self._nome}: "
                f"uma sonda de recuperação já está em andamento"
            )
            raise CircuitOpenError(message)

        self._sondando = True

    def sucesso(self) -> None:
        """O provedor respondeu. Fecha o circuito e zera a contagem.

        Zera, e não decrementa: o que o breaker mede é falha **consecutiva**.
        Um provedor que alterna sucesso e falha está degradado, não fora do ar,
        e o desfecho certo para ele é o turn falhar — não o produto inteiro
        parar.
        """
        self._falhas = 0
        self._aberto_em = None
        self._sondando = False

    def falha(self) -> None:
        """Uma falha de DISPONIBILIDADE. Quem filtra o que conta é o adapter.

        Este objeto não sabe distinguir "provedor fora" de "provedor respondeu
        besteira" — só o adapter conhece os tipos do SDK. Chamar isto para uma
        falha de conteúdo é o bug que faz um breaker abrir sozinho em produção
        (§4.7 do prompt do card), e é por isso que a filtragem mora do lado de
        quem tem a informação.
        """
        self._falhas += 1
        self._sondando = False
        if self._falhas >= self._limite:
            self._aberto_em = self._clock()

    @property
    def aberto(self) -> bool:
        """Para log e teste. Não é usado para decidir — quem decide é o método."""
        return self._aberto_em is not None
