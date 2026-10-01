# ADR-0076 — Um Dockerfile, dois alvos; os pesos do worker entram no build

- **Status:** aceito
- **Data:** 2026-10-01
- **Relacionado:** ADR-0010 (tags fixadas), ADR-0025 (modelo residente, readiness), ADR-0027 (`mlx` só em Apple Silicon), ADR-0032 (Piper), ADR-0060 (servidor sem `mlx`), ADR-0075 (retenção no boot), CARD-024, CARD-055
- **Critérios de obrigatoriedade:** **1 — dependência externa** (imagens base `python` e `uv`), **3 — custo** (tamanho de imagem, latência do caminho sem `mlx`) e **5 — difícil de reverter** (o formato de empacotamento que o deploy vai herdar).

## Contexto

API e worker só rodavam como processos do host. O CARD-024 pede a imagem do
worker com os modelos dentro; o CARD-055 aponta que a API também não tem
`Dockerfile` e não tem card. As duas compartilham código e lockfile e
divergem em ~1 GB de artefato de modelo.

## Decisão

1. **`backend/Dockerfile` com estágios `deps` → (`api` | `modelos` → `worker`).**
   As duas imagens partem do mesmo `deps`; só o `worker` copia os pesos.
2. **`uv` copiado de `ghcr.io/astral-sh/uv:0.11.14`** (binário oficial, versão
   fixa), `uv sync --frozen --no-dev` em duas etapas (dependências, depois o
   projeto) para o cache de camada não reinstalar tudo a cada mudança de código.
   Python da imagem base `python:3.12.14-slim-bookworm`, `UV_PYTHON_DOWNLOADS=never`.
3. **Pesos no build:** o estágio `modelos` instancia `WhisperModel` (o mesmo
   código de carga do adapter) e roda `piper.download_voices`. No runtime,
   `HF_HUB_OFFLINE=1`: peso ausente faz o worker falhar na subida em vez de
   baixar em silêncio. Verificado com `docker run --network none`.
4. **Usuário sem privilégio** (`uid 10001`) nas duas imagens; `.dockerignore`
   exclui `.env`, `voices/`, testes e benchmarks.
5. **No compose, profile `app`** com `migrate` (`alembic upgrade head`) e
   `storage-setup` (ADR-0075) como passos únicos antes de `api` e `worker`.
   Profile e não default: no Mac o desenvolvimento continua no host com `mlx`,
   e dois workers disputariam a fila.

## Alternativas consideradas

### A — Uma imagem só para os dois processos
- **Por que foi rejeitada:** o deploy da API arrastaria ~1 GB de pesos que ela
  nunca carrega (CARD-055, item 1).

### B — Baixar os pesos no primeiro boot (volume de cache)
- **Prós:** imagem 1 GB menor, build mais rápido.
- **Por que foi rejeitada:** o primeiro boot depois de cada deploy num volume
  novo baixaria 36–99 s de pesos — o "pior turn ao primeiro aluno" que o
  ADR-0025 existe para impedir — e dependeria do Hugging Face estar no ar na
  hora do deploy.

### C — `pip`/`requirements.txt` exportado do lock
- **Por que foi rejeitada:** um segundo formato de dependência para manter; o
  `uv.lock` já é a fonte e o `--frozen` falha se ele divergir do `pyproject`.

## Consequências

- **Tamanho:** `api` 970 MB, `worker` 2,02 GB. A API é grande porque
  `faster-whisper`, `piper-tts`, `onnxruntime` e `av` são dependências **base**
  do pacote. **Dívida:** movê-las para um extra `worker` encolheria a API;
  gatilho: tempo de pull no deploy do CARD-055 incomodar.
- **Latência medida** (`docs/medicao-latencia.md` §14): o container com
  `faster-whisper` custa +2,9 s no p50 até o primeiro trecho contra o host com
  `mlx` — o dobro da estimativa pessimista do ADR-0060. Entra no CARD-055 como
  insumo para escolher o servidor.
- Docker no Mac roda arm64; o servidor provavelmente será x86. O Dockerfile não
  fixa plataforma — `ctranslate2`, `onnxruntime` e `av` publicam wheels para as
  duas —, mas a imagem x86 só será construída e medida no CARD-055.
