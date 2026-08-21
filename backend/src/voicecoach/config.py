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

from decimal import Decimal
from enum import StrEnum
from functools import lru_cache

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
    s3_access_key: str = "voicecoach"
    s3_secret_key: str = "voicecoach-dev-secret"
    s3_bucket: str = "voicecoach-media"
    s3_region: str = "us-east-1"


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
