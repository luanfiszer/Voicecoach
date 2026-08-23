# CARD-024 — Dockerfile do worker, com os modelos dentro da imagem

- **ID:** CARD-024
- **Épico:** Fase 1 — Fatia vertical em cascata (infra de execução)
- **Esforço:** M
- **Status:** backlog
- **Dependências:** CARD-009 (concluído); ADR-0025, ADR-0032, ADR-0010

## Contexto

Adiado explicitamente **duas vezes**: o CARD-002 o deixou para quando houvesse
worker, e o CARD-008 reescreveu o critério *"dado o container"* com este gatilho.
O CARD-009 criou o worker; a decisão de fazê-lo em card próprio foi do
desenvolvedor na abertura daquela sessão.

O que mudou desde o primeiro adiamento: **a imagem ficou muito mais simples.** O
Piper substituiu o Kokoro (ADR-0032) e não tem nenhuma das três dependências de
sistema que o Kokoro exigia (`espeak-ng`, o reaponte do `EspeakWrapper`, o
`en_core_web_sm` do spaCy).

## Problema

Hoje o worker só roda com `uv run voicecoach-worker` na máquina do
desenvolvedor. O `docker-compose.yml` sobe Postgres, Redis e MinIO, mas não sobe
o processo que consome a fila — então "o sistema roda" depende de alguém abrir um
terminal a mais e lembrar da ordem.

Dois detalhes medidos no CARD-009 que a imagem tem de tratar, e que não são
óbvios:

1. **Os pesos do STT.** A primeira carga do `mlx-whisper` num processo limpo
   custou **17,15 s** (medição §10.1), e a primeira execução numa máquina sem
   cache baixa 36-99 s de pesos. Uma imagem que baixe modelo no primeiro job
   entrega o pior turn possível ao primeiro aluno depois de cada deploy — que é
   exatamente o que o ADR-0025 existe para impedir.
2. **A voz do Piper** é um par `.onnx` + `.onnx.json` de 60 MB que o Piper
   **não** baixa sozinho em runtime (ADR-0032, §9.2). Sem ela no lugar certo, o
   adapter falha na subida.

Além disso: `mlx-whisper` só existe em Apple Silicon (ADR-0027) e a imagem
provavelmente roda em x86 — o container usa o `faster-whisper`, que é um caminho
com latência diferente e **não medido em composição** (dívida do CARD-009).

## Proposta técnica

- `backend/Dockerfile`, multi-stage: um estágio que resolve dependências com
  `uv sync --frozen` e um estágio de runtime enxuto.
- **Pesos e voz no build, não em runtime.** Um passo de build baixa o modelo do
  `faster-whisper` e a voz do Piper para dentro da imagem. Consequência a
  aceitar e escrever: a imagem fica grande (centenas de MB) e o build fica lento
  — em troca, `voicecoach:worker:ready` aparece em segundos e não em minutos.
- Serviço `worker` no `docker-compose.yml`, com `depends_on` de Postgres, Redis
  e MinIO, e tag de imagem base **fixada** (ADR-0010).
- Decidir e escrever se o `healthcheck` do compose lê a chave de readiness.

## Escopo

- **In:** Dockerfile do worker, serviço no compose, artefatos de modelo na
  imagem, documentação no `backend/README.md`.
- **Out:** Dockerfile da API (card próprio ou o mesmo, a decidir); deploy
  hospedado; registry.

## Critérios de aceite

- **Dado** `docker compose up`, **quando** os serviços sobem, **então**
  `GET /health/ready` responde 200 **incluindo** a entrada `worker` — sem
  ninguém rodar comando extra.
- **Dado** o container recém-iniciado, **quando** se mede o tempo até a chave
  `voicecoach:worker:ready` existir, **então** ele não inclui download de
  modelo (comparar com a rede desligada).
- **Dado** um turn enfileirado com o worker em container, **então** ele é
  processado ponta a ponta.
- **Dado** o caminho x86/`faster-whisper` no container, **então** a latência de
  composição é medida e registrada em `docs/medicao-latencia.md` — fechando a
  dívida da §10.4.

## Riscos

- **Tamanho da imagem** vs. tempo de subida: o trade-off é real e a decisão tem
  de ser escrita, não deduzida do Dockerfile.
- **`uv` em imagem** tem mais de um idioma aceito; escolher um e explicar.
- Rodar a suíte dentro do container pode expor divergências de plataforma que
  hoje ninguém vê (o CI é x86, a máquina de dev é ARM).

## Objetivo de aprendizado

Como um projeto Python empacota **artefato de modelo** — a diferença entre
dependência (resolvida pelo gerenciador de pacotes) e peso de IA (baixado por
código, cacheado em `~/.cache`), e por que a segunda categoria não tem
equivalente no `dotnet publish`.
