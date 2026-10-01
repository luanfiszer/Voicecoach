# syntax=docker/dockerfile:1.7
#
# UM Dockerfile, DOIS alvos (CARD-024, ADR-0076):
#
#   docker build --target api    -t voicecoach-api    backend/
#   docker build --target worker -t voicecoach-worker backend/
#
# Os dois compartilham o estágio `deps` (o mesmo lockfile, o mesmo código) e
# divergem no que precisa estar presente para o processo estar PRONTO: a API
# não carrega modelo nenhum; o worker carrega ~500 MB de pesos (Whisper + a voz
# do Piper), baixados aqui no build — nunca no primeiro job (ADR-0025).
#
# Tags FIXADAS (ADR-0010): imagem base que muda sozinha é build que muda
# sozinho.

ARG PYTHON_IMAGE=python:3.12.14-slim-bookworm

# --- uv: o binário oficial, copiado de uma imagem com versão fixa ------------
FROM ghcr.io/astral-sh/uv:0.11.14 AS uv

# --- base: Python + uv, sem o projeto ----------------------------------------
FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # `copy` e não hardlink: o cache do uv está num mount do BuildKit, outro
    # sistema de arquivos — hardlink falharia e o uv avisaria a cada build.
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    # O Python é o da imagem base; o uv não baixa outro.
    UV_PYTHON_DOWNLOADS=never
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app

# --- deps: dependências primeiro, código depois (cache de camada) -------------
FROM base AS deps
COPY pyproject.toml uv.lock ./
# `--no-install-project`: só as dependências. Esta camada só é refeita quando o
# lockfile muda — mudar uma linha de código não reinstala o mundo.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
# Sem `--extra mlx`: o mlx só existe em Apple Silicon (ADR-0027); no container
# o STT é o faster-whisper.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# --- modelos: os pesos do worker, baixados uma vez, no build ------------------
FROM deps AS modelos
ARG STT_MODEL=small
ARG TTS_VOICE=en_US-lessac-medium
ENV HF_HOME=/opt/hf
RUN /app/.venv/bin/python -c "from faster_whisper import WhisperModel; WhisperModel('${STT_MODEL}', device='cpu', compute_type='float32')" \
 && /app/.venv/bin/python -m piper.download_voices "${TTS_VOICE}" --download-dir /opt/voices

# --- runtime comum: usuário sem privilégio, venv no PATH ----------------------
FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH
RUN useradd --create-home --uid 10001 voicecoach
WORKDIR /app
COPY --from=deps --chown=voicecoach:voicecoach /app /app
USER voicecoach

# --- alvo: api -----------------------------------------------------------------
FROM runtime AS api
EXPOSE 8000
CMD ["uvicorn", "voicecoach.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

# --- alvo: worker --------------------------------------------------------------
FROM runtime AS worker
COPY --from=modelos --chown=voicecoach:voicecoach /opt/hf /opt/hf
COPY --from=modelos --chown=voicecoach:voicecoach /opt/voices /app/voices
ENV HF_HOME=/opt/hf \
    # A prova do critério "sem download em runtime": com isto, um peso que não
    # veio no build faz o worker FALHAR na subida, em vez de baixar em silêncio.
    HF_HUB_OFFLINE=1 \
    TTS_VOICES_DIR=/app/voices \
    STT_PROVIDER=faster_whisper
CMD ["voicecoach-worker"]
