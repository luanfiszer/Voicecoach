# CARD-008 — TTS por sentença + MediaStorage por trecho (e a decisão Kokoro vs Piper)

- **ID:** CARD-008 · **Épico:** Fase 1 — Fatia vertical em cascata
- **Plataforma:** backend/IA · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-002, CARD-006 (padrão de porta), CARD-018, ADR-0024

## Contexto

ADR-0011 (TTS local) e [ADR-0024](../adr/0024-midia-por-trecho-chave-url-assinada-e-retencao-assimetrica.md)
(mídia por trecho, URL assinada junto do evento, retenção assimétrica).

Medido: sintetizar a resposta **inteira** custa 1,68 s; **uma frase**, 0,41 s —
e o RTF é constante (~0,10), ou seja, o custo é linear no texto, sem penalidade
fixa. É isso que torna a cascata barata: cortar em frases não desperdiça nada.

## Por que agora

0,41 s da primeira frase é o último termo do orçamento de 1,8 s. E a porta
precisa nascer **por sentença**: um `synthesize(texto_inteiro)` seria a versão
batch que a regra de desempate manda não construir.

## Problema

Dois, e o segundo não estava mapeado:

1. O storage precisa aceitar N objetos por turn, ordenáveis, com URL assinada
   emitida **junto** do trecho (ADR-0024) — não sob demanda.
2. **O Kokoro não roda out-of-the-box** (medição §4.3): `espeakng-loader` publica
   um `.dylib` com o caminho de dados da máquina de CI compilado dentro;
   o conserto exige apontar o `EspeakWrapper` para um `espeak-ng` **de sistema**
   *depois* do `import kokoro`; e ele puxa spaCy exigindo `en_core_web_sm`, que
   não vem declarado. São **dependências de sistema num container** — Dockerfile,
   não `pyproject.toml`.

## Proposta técnica

- Porta `TextToSpeech`: `synthesize(text: str) -> AudioData`, chamada **uma vez
  por sentença**. A porta não muda de forma para o V2 (ADR-0003): o que muda é
  quem chama e com que granularidade.
- **Decisão Kokoro vs Piper neste card**, com critério escrito antes de medir:
  tempo de carga (Kokoro: 5,63 s medidos — é o dono dos ~6 s do ADR-0025),
  RTF, número de dependências de sistema, e qualidade percebida numa amostra
  fixa. O Piper embarca os próprios dados de espeak, que é exatamente a dor
  medida. **Se o Piper empatar em qualidade, ele ganha por empacotamento** — e
  a decisão vira ADR (critério 1: troca de dependência externa).
- Porta `MediaStorage`: `put(key, data)`, `presigned_get_url(key, ttl)`,
  `delete_prefix(prefix)`; adapter S3 (boto3 contra MinIO).
- Chaves do ADR-0024, com `{index:03d}` zero-padded — a ordem lexicográfica do
  bucket passa a ser a ordem de playback.
- Concatenação do áudio inteiro (`reply/full.*`) ao completar: como o TTS local
  devolve PCM, concatenar antes de codificar é barato e sem recodificação.
- Lifecycle assimétrico do ADR-0024 (trecho 1 dia, `full` 90 dias, input 7 dias)
  em código de setup, com os valores em `Settings`.
- **Dívida do ADR-0014 fecha aqui:** o readiness do MinIO deixa de ser
  `GET /minio/health/live` genérico e vira `head_bucket` com credencial real,
  agora que o cliente S3 existe.

## Escopo

- **In:** porta de TTS por sentença, adapter local escolhido com critério,
  `MediaStorage` com chave por trecho, concatenação, lifecycle, `head_bucket`.
- **Out:** orquestração da cascata (CARD-009); emissão de eventos (CARD-010);
  `delete_prefix` no fluxo de conta (CARD-017 e Fase 5); TTS em stream
  intra-frase (V2).

## Critérios de aceite

- **Dado** uma frase, **quando** sintetizada e gravada, **então** existe um
  objeto em `.../reply/000.*` e a URL assinada devolvida toca — e **expira**
  depois do TTL (teste com TTL curto).
- **Dado** 4 trechos gravados, **quando** o turn completa, **então**
  `reply/full.*` existe, dura a soma das partes (±100 ms) e a listagem por
  prefixo devolve os trechos **na ordem**.
- **Dado** acesso direto ao bucket sem assinatura, **então** o objeto não é
  legível.
- **Dado** o container do worker, **então** o TTS sintetiza sem intervenção
  manual — as três dependências escondidas estão no Dockerfile, e há teste que
  falha se faltarem.
- **Dado** o lifecycle configurado, **então** as três regras existem com os TTLs
  da config (lido do MinIO em teste de integração).

## Riscos

- A decisão Kokoro/Piper pode empatar e virar preferência estética. Mitigação: o
  critério está escrito **acima**, antes da medição — e o desempate declarado é
  empacotamento.
- MinIO ≠ S3 em lifecycle (herdado do ADR-0006/0024): o teste cobre MinIO;
  revalidar no provedor real ao migrar.

## Objetivo de aprendizado

URLs pré-assinadas (quem assina, o que a assinatura carrega, por que o backend
sai do caminho dos bytes) e boto3 síncrono dentro de app async — escolher
conscientemente entre executor e `aioboto3`, com o trade-off documentado.
