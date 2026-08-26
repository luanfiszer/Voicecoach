"""Configuração tipada do backend, carregada de variáveis de ambiente.

Este módulo mora **fora das cinco camadas** de propósito (ADR-0013):
configuração é detalhe de composição, não regra. `domain` e `application` não
podem importá-lo — o contrato do import-linter garante isso; eles recebem os
valores de que precisam por parâmetro.

Equivalente mental .NET: `IOptions<T>` com validação no startup. A diferença é
que aqui a validação é do pydantic e acontece quando a classe é *instanciada*,
não quando o módulo é importado — ver `get_settings()`.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SttProvider(StrEnum):
    """Qual adapter de STT o processo usa (ADR-0027, item 2).

    O valor vem de `STT_PROVIDER`. O pydantic valida contra os membros desta
    enum: um valor inválido derruba a construção da `Settings` com a lista dos
    aceitos — fail-fast de configuração, sem `if` espalhado depois.

    `AUTO` é o default e **não** é um adapter: é a instrução "resolva pela
    plataforma no boot". A resolução mora em `adapters/stt/factory.py`.
    """

    AUTO = "auto"
    MLX = "mlx"
    FASTER_WHISPER = "faster_whisper"
    OPENAI = "openai"


class TtsProvider(StrEnum):
    """Qual motor de voz o processo usa (ADR do CARD-008).

    Não há `auto` aqui, ao contrário do STT: lá a escolha dependia da
    plataforma (o `mlx` só existe em Apple Silicon) e resolver no boot era a
    única saída honesta. O Piper roda igual nos quatro alvos que publica wheel,
    então "resolva sozinho" seria indireção sem pergunta a responder.

    `KOKORO` continua no enum porque o motor continua utilizável e a medição
    que o destronou pode ser refeita em outra máquina — mas exige as três
    dependências de sistema da §4.3 e não é instalado por default.
    """

    PIPER = "piper"
    KOKORO = "kokoro"


class Settings(BaseSettings):
    """Configuração da aplicação, validada na construção.

    Cada atributo vira uma variável de ambiente em maiúsculas
    (`teacher_model` <- `TEACHER_MODEL`); a busca é case-insensitive.

    Precedência (do mais forte para o mais fraco), definida pelo
    pydantic-settings: argumento explícito no construtor > variável de
    ambiente > arquivo `.env` > default declarado aqui.
    """

    # `model_config` é o idioma do pydantic v2 para configurar a *classe* (não
    # a instância): um atributo de classe com um TypedDict de opções. Não há
    # paralelo direto em C# — o mais próximo seriam atributos em cima da classe
    # de opções, mas aqui é um dicionário comum, inspecionável em runtime.
    model_config = SettingsConfigDict(
        # Dois caminhos porque o `.env` mora na raiz do repositório (onde o
        # docker compose o lê sozinho) e o backend costuma rodar de `backend/`.
        # Resolvidos relativos ao diretório de trabalho, na ordem: o primeiro
        # que existir vence.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        # O `.env` da raiz também tem variáveis que só o compose usa
        # (POSTGRES_PORT, MINIO_CONSOLE_PORT...). Sem isto, elas viram erro de
        # validação por campo desconhecido.
        extra="ignore",
        # Imutável depois de construída (≈ `record` com `init`-only). Config que
        # muda em runtime é bug difícil de achar.
        frozen=True,
    )

    # --- Segredo obrigatório -------------------------------------------------
    # Sem default: é o que faz a aplicação recusar subir. Preserva o fail-fast
    # do `_required()` do protótipo, agora com a mensagem vindo do pydantic.
    anthropic_api_key: str = Field(min_length=1)

    # --- Modelos de IA (ADR-0009, ajustado pelo ADR-0010) --------------------
    teacher_model: str = "claude-haiku-4-5"
    assistant_model: str = "claude-haiku-4-5"

    # --- Professor (ADR-0022, ADR-0030) --------------------------------------
    # Teto de saída. 700 é o valor com que a latência foi medida (§5.1): baixá-lo
    # trunca a resposta no meio, subi-lo não acelera nada porque o modelo para
    # quando termina. É configurável e não constante de módulo porque o eval da
    # Fase 4 pode querer respostas mais longas sem mexer em código.
    teacher_max_tokens: int = Field(default=700, gt=0)

    # Timeout de UMA tentativa, não do turno inteiro: o SDK tenta 2 vezes por
    # default, então o tempo de parede pode chegar a 3x este valor. O retry só
    # acontece antes do primeiro trecho de fala — depois dele a conexão já está
    # aberta e recomeçar faria o aluno ouvir a resposta do zero (ADR-0030).
    teacher_timeout_seconds: float = Field(default=30.0, gt=0)

    # --- STT (ADR-0011, ADR-0027) --------------------------------------------
    # `auto` resolve pela plataforma no boot: mlx em Apple Silicon (0,59 s no
    # small.en), faster-whisper no resto (1,18 s). Escolha explícita
    # incompatível FALHA na subida — nunca cai para o outro adapter, porque
    # fallback silencioso esconderia uma regressão de 2x atrás de um log.
    stt_provider: SttProvider = SttProvider.AUTO

    # Dois campos e não um: os adapters NÃO compartilham a string do modelo. No
    # faster-whisper é o nome do modelo CTranslate2; no mlx é o repositório do
    # Hugging Face com os pesos já convertidos. Um campo só obrigaria uma
    # tradução entre os dois, que é justamente o tipo de "esperteza" que
    # esconde erro de configuração.
    #
    # `small.en` é o default e a escolha de modelo está BLOQUEADA (ADR-0027,
    # item 7) até existir insumo com voz real de aprendiz: latência está
    # medida, qualidade não. Trocar por `base.en` NÃO é a otimização óbvia que
    # parece — remedido, ele ficou mais LENTO no mlx.
    stt_model_faster_whisper: str = "small.en"
    stt_model_mlx: str = "mlx-community/whisper-small.en-mlx"

    # --- TTS (ADR-0011, e o ADR de troca do CARD-008) ------------------------
    # Piper por default: 10x mais rápido para carregar, 4x menor RTF e ZERO
    # dependência de sistema (medição §9). A troca é configuração porque a porta
    # a torna barata — é a primeira vez que o investimento em portas se cobra
    # numa substituição de motor inteira.
    tts_provider: TtsProvider = TtsProvider.PIPER

    # A voz é um par `.onnx` + `.onnx.json` baixado à parte (60 MB), não algo
    # embarcado no pacote. É o análogo dos pesos do Whisper, com uma diferença
    # que importa: o Piper NÃO baixa sozinho em runtime, então o arquivo tem de
    # existir antes — e o adapter falha na subida dizendo qual arquivo falta.
    tts_voice: str = "en_US-lessac-medium"

    # Onde as vozes moram. Default relativo ao processo, sobrescrito por env em
    # container. Um caminho e não um "modelo": vozes são arquivos, e fingir que
    # são identificadores esconderia o download que alguém precisa fazer.
    tts_voices_dir: Path = Path("voices")

    # --- Mídia e retenção (ADR-0024) -----------------------------------------
    # TTL da URL assinada. A regra do ADR-0024 é uma só: MAIOR que o playback do
    # turn inteiro. Uma resposta típica tem ~17 s de áudio; 15 minutos dão folga
    # para o aluno pausar, atender o telefone e voltar — e continuam curtos o
    # bastante para que uma URL vazada não seja um link permanente.
    media_url_ttl: timedelta = timedelta(minutes=15)

    # Retenção assimétrica do ADR-0024. O trecho some primeiro porque é a cópia
    # mais numerosa e vira redundante assim que `full` existe; `full` é o que o
    # histórico reproduz; `input` existe para reprocessamento e debug.
    retention_reply_chunk: timedelta = timedelta(days=1)
    retention_reply_full: timedelta = timedelta(days=90)
    retention_input: timedelta = timedelta(days=7)

    # Teto de duração de UMA fala do aluno. Não é a quota (essa é em minutos por
    # dia, CARD-015): é o limite de um upload só. Existe porque a borda decodifica
    # o áudio para medi-lo, e decodificar é trabalho proporcional ao tamanho —
    # sem teto, um arquivo de uma hora ocuparia uma thread do executor da API por
    # segundos. 120 s é ~6x a fala típica medida (~20 s).
    max_turn_audio_duration: timedelta = timedelta(seconds=120)

    # --- Entrega progressiva (ADR-0026, item 5) ------------------------------
    # Prazo do stream SSE INTEIRO, não de cada evento. Um turn saudável fecha em
    # ~2 s; este número existe para o turn que travou. Estourado, o servidor
    # encerra e o `EventSource` do cliente reconecta sozinho com o
    # `Last-Event-ID` — nada se perde, porque a retomada lê do banco. Stream sem
    # prazo é conexão vazando, e cada uma segura uma conexão de Redis.
    sse_timeout: timedelta = timedelta(seconds=60)

    # --- Proteção de custo (ADR-0010, visão §D) ------------------------------
    # Decimal, não float: dinheiro em binário de ponto flutuante acumula erro.
    # Equivalente mental exato: `decimal` do C#.
    daily_audio_minutes_per_student: int = Field(default=10, gt=0)
    daily_budget_usd: Decimal = Field(default=Decimal("1.00"), gt=0)
    monthly_budget_usd: Decimal = Field(default=Decimal("10.00"), gt=0)

    # --- Infraestrutura local (ADR-0004 / 0005 / 0006) -----------------------
    # Estas TÊM default porque o docker-compose.yml deste repositório é quem as
    # provê: o default não pode estar errado, ele descreve o compose ao lado.
    # Segredo de provedor externo é o oposto — não existe default correto.
    database_url: str = (
        "postgresql+asyncpg://voicecoach:voicecoach@localhost:5432/voicecoach"
    )
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"

    # **O host com que a URL assinada é ASSINADA** — separado do de cima porque
    # os dois têm consumidores diferentes (ADR-0045). O worker e a API falam com
    # o MinIO por `s3_endpoint_url`; quem baixa o trecho é o **aparelho do
    # aluno**, e para ele `localhost` é o próprio telefone.
    #
    # Não é cosmético: no SigV4 o `Host` entra no cálculo (a query traz
    # `X-Amz-SignedHeaders=host`), então trocar o host DEPOIS de assinar devolve
    # `SignatureDoesNotMatch` — medido no CARD-012. Não há conserto do lado do
    # cliente; ou o servidor assina com um host alcançável, ou o áudio não toca.
    #
    # `None` (o default) significa "mesmo host": em Simulador e em CI nada muda.
    # Em aparelho físico, aponte para o IP da máquina na LAN.
    s3_public_endpoint_url: str | None = None
    s3_access_key: str = "voicecoach"
    s3_secret_key: str = "voicecoach-dev-secret"
    s3_bucket: str = "voicecoach-media"
    s3_region: str = "us-east-1"

    @property
    def s3_signing_endpoint_url(self) -> str:
        """O host que vai na URL assinada — o público, se houver.

        Uma propriedade e não um segundo campo com o mesmo default: dois campos
        com o mesmo literal saem de sincronia no dia em que alguém mudar um só.
        """
        return self.s3_public_endpoint_url or self.s3_endpoint_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devolve a configuração única do processo, construída na primeira chamada.

    `@lru_cache` memoiza a função: a partir da segunda chamada devolve a mesma
    instância. É o idioma Python para singleton preguiçoso — em .NET seria
    registrar `IOptions<Settings>` como singleton no container.

    Por que preguiçoso e não `settings = Settings()` no topo do módulo: assim a
    validação acontece quando alguém *pede* a configuração (o `create_app()`,
    no boot), e não quando alguém *importa* o módulo. Instanciar no import faria
    `import voicecoach.config` explodir sem `.env` — inclusive na coleta dos
    testes e em qualquer ferramenta que só queira ler o módulo.
    """
    # O pydantic preenche os campos a partir do ambiente; o type checker não
    # sabe disso e cobraria os argumentos obrigatórios no construtor.
    return Settings()  # type: ignore[call-arg]
