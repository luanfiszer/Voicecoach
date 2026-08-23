# CARD-008 — TTS por sentença + MediaStorage por trecho (e a decisão Kokoro vs Piper)

- **ID:** CARD-008 · **Épico:** Fase 1 — Fatia vertical em cascata
- **Plataforma:** backend/IA · **Esforço:** M · **Status:** **concluído** (2026-08-23)
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


---

## Execução (2026-08-23)

Branch `card-008-tts-por-sentenca-e-media-storage`, a partir de `main` (`1c6bfe8`,
já com o PR #12 do CARD-007 mergeado).

### O que entrou

| Arquivo | O que é |
|---|---|
| `domain/media_keys.py` | esquema de chaves do ADR-0024 + `RetentionClass` derivada da chave |
| `application/ports/text_to_speech.py` | porta por sentença, `SynthesizedAudio(pcm, sample_rate)`, `concat`, `TtsError`, `SampleRateMismatchError` |
| `application/ports/media_storage.py` | `put` / `presigned_get_url(ttl)` / `delete_prefix`, `MediaStorageError` |
| `adapters/tts/piper_adapter.py` + `factory.py` + `encoding.py` | Piper em executor, fábrica que falha na subida, compressão AAC com o PyAV já instalado |
| `adapters/storage/s3_media_storage.py` + `lifecycle.py` | boto3 em executor, tag de retenção no `put`, as três regras |
| `adapters/health.py` | `check_minio` → `head_bucket` com credencial (dívida do ADR-0014) |
| `docker-compose.yml` | sidecar `createbuckets` |
| `benchmarks/tts_piper.py` | instrumento novo, protocolo do `_common.py` |
| `docs/medicao-latencia.md` §9 | a comparação, com insumo hasheado |
| 3 ADRs | 0032 (troca de motor), 0033 (fronteira da porta), 0034 (adapter S3 e retenção) |

### Critérios de aceite, um a um

| Critério | Desfecho | Evidência |
|---|---|---|
| Frase sintetizada e gravada; URL assinada toca; expira depois do TTL | ✅ | `test_grava_e_a_url_assinada_baixa_o_mesmo_conteudo`, `test_url_assinada_expira` (TTL 1 s, espera 2 s) — 200 antes, **403** depois |
| 4 trechos; `full` existe, dura a soma (±100 ms); listagem em ordem | ✅ | `test_full_concatenado_dura_a_soma_e_ainda_toca` (4,0 s ±0,1) e `test_listagem_por_prefixo_devolve_os_trechos_na_ordem_de_playback` (12 trechos, gravados fora de ordem) |
| Objeto não legível sem assinatura | ✅ | `test_objeto_nao_e_legivel_sem_assinatura` → **403** |
| **"Dado o container do worker, o TTS sintetiza sem intervenção manual"** | ⚠️ **reescrito** | **Não existe Dockerfile no repositório** (verificado antes do plano). Decisão do desenvolvedor: reescrever o critério e adiar o container para o CARD-009, que é quem terá worker para conteinerizar. O critério vira *"as dependências estão declaradas e há teste que falha se faltarem"*, cumprido por `test_voz_ausente_falha_na_subida_dizendo_como_resolver`. **E o ADR-0032 encolheu a dívida sozinho:** o Piper não tem dependência de sistema nenhuma |
| Lifecycle: 3 regras com os TTLs da config, lidas do MinIO | ✅ | `test_as_tres_regras_de_lifecycle_existem_com_os_ttls_da_config` — compara com `Settings`, não com números repetidos no teste |

### Gates (saída real)

```
$ uv run ruff format --check src tests   → 70 files already formatted
$ uv run ruff check src tests            → All checks passed!
$ uv run mypy                            → Success: no issues found in 69 source files
$ uv run lint-imports                    → Contracts: 4 kept, 0 broken.
$ uv run pytest --cov --cov-fail-under=80
  165 passed, 7 deselected in 7.32s
  Required test coverage of 80% reached. Total coverage: 91.77%
$ uv run coverage report --include="*/domain/*,*/application/*" --fail-under=90
  TOTAL  270  0  38  0  100%
```

**O gate morde — par completo demonstrado.** A mesma linha (`import boto3` em
`application/ports/media_storage.py`):

```
com "boto3" na lista forbidden:
  voicecoach.application is not allowed to import boto3:
  -   voicecoach.application.ports.media_storage -> boto3 (l.15)

com "boto3" REMOVIDO da lista, mesma violação:
  Contracts: 4 kept, 0 broken.
```

### Item de ADR da DoD (LEARNING-0003 — critério citado, não julgado de memória)

Conferido contra "Quando um ADR é OBRIGATÓRIO" (`docs/adr/README.md`):

- **ADR-0032** — critério **1** (troca de dependência externa: o motor de TTS);
- **ADR-0033** — critério **2** (define uma fronteira: o tipo que atravessa a
  porta `TextToSpeech`);
- **ADR-0034** — critérios **1** (`boto3`), **2** (a retenção deixa de ser
  expressável por prefixo e muda o contrato do `put`) e **4** (é o mecanismo que
  faz a retenção de voz acontecer).

### Achados que o card não previa

1. **A retenção assimétrica do ADR-0024 não é expressável por prefixo.** As
   chaves começam pelo `student_id`, e o lifecycle do S3 filtra por prefixo ou
   tag — nunca por sufixo. O ADR-0024 escreveu a tabela supondo, sem dizer, uma
   regra de prefixo. Resolvido por tag derivada da chave (ADR-0034).
2. **O Piper ganhou por muito mais do que o esperado**, e isso reabre um número
   de outro ADR: a carga do worker do ADR-0025 cai de ~6 s para ~1 s.
3. **O Kokoro baixa dois artefatos em runtime** (`en_core_web_sm` e os pesos do
   HF), observado ao vivo num ambiente limpo. Num container sem rede, é falha.
4. **O AAC acrescenta ~70 ms de *priming***, dentro da tolerância do card. O
   teste verifica que a diferença não cresce com o tamanho — o que indicaria
   perda de quadros no fim.

### Dívidas registradas

| Dívida | Gatilho / card que resolve |
|---|---|
| ~~Qualidade percebida da voz não julgada~~ — **fechada em 2026-08-23**: o desenvolvedor ouviu as amostras (incluindo uma correção pedagógica real, via `benchmarks/tts_audicao.py`) e aprovou a voz do Piper. O ADR-0032 passa a ter os quatro eixos do critério cobertos | — |
| Dockerfile do worker | CARD-009 |
| Lifecycle verificado só contra MinIO | migração para provedor real (ressalva do ADR-0006/0024, agora com 3 regras) |
| `lessac` vs. `amy` não foi comparação explícita: a aprovação recaiu sobre o default | trocar de voz é uma linha de config |
| Objeto gravado por fora do adapter não recebe tag e viveria para sempre | sem defesa técnica; o teste falha se o adapter parar de marcar |

### Regra do explicador — desfecho honesto

**Nenhuma das três perguntas foi respondida ou dispensada pelo desenvolvedor.**

| Pergunta | Desfecho |
|---|---|
| **Q7** (`Protocol` e o momento em que um fake não satisfaz a porta) | **em aberto** — reapresentada na abertura, antes do plano. Sem resposta e sem dispensa. Continua na fila |
| **Q9** (igualdade de `@dataclass`) | **em aberto** — idem |
| **Nova (§4.1 do prompt):** "se eu chamar `put_object` direto dentro de uma corrotina, o que acontece com as outras corrotinas — e como provaria num teste?" | **em aberto** — feita **no ponto da decisão**, antes de escrever o adapter, e não respondida. O agente demonstrou com execução (122 ms de loop congelado, heartbeat com 0 voltas) e a demonstração virou o teste `test_o_upload_nao_bloqueia_o_event_loop` — mas **demonstração do agente não fecha o item** (LEARNING-0004) |

As três continuam em `docs/perguntas-em-aberto.md` e abrem o CARD-009.
