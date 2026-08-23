# Prompt — CARD-008: TTS por sentença + `MediaStorage` por trecho (Kokoro vs Piper)

- **Tipo:** prompt de sessão, complemento de `/executa-card 008`
- **Escrito em:** 2026-08-21, no fechamento do CARD-007 (PR #12, `43c2c7e`)
- **Status:** não executado

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 008` e leia isto junto** —
> aqui está só o que é específico deste card, a arqueologia já feita, e as
> **quatro coisas que o card assume e que não existem no repositório**.

---

## 0. Antes do plano: a fila do explicador tem dívida que é DESTE card

`docs/perguntas-em-aberto.md` tem **6 perguntas abertas**. Duas foram
reapresentadas na abertura do CARD-007 e **não fecharam** — sem resposta e sem
dispensa. Reapresente-as **na abertura, antes do plano**:

| # | Pergunta | Por que é deste card |
|---|---|---|
| **Q7** | O que `Protocol` faz que dispensa um framework de mock, e **em que momento** se descobre que um fake não satisfaz a porta? | Este card cria **duas** portas novas (`TextToSpeech` e `MediaStorage`) e seus fakes. No CARD-007 o `mypy` reprovou **três** vezes um dublê que tinha "tudo o que se lê" — `@property` vs. atributo, e invariância de membro de `Protocol`. A demonstração já existe duas vezes; falta a resposta |
| **Q9** | Igualdade de `@dataclass`: por que dois objetos com um campo diferente não são iguais, e por que o Python **proíbe** usá-los como chave de dict/set? | `TurnAudioChunk` é `frozen=True` e o teste de ordenação vai comparar coleções de trechos. É a terceira vez que ela toca um card |

> **Precedente do CARD-007, para repetir:** a pergunta nova saiu **errada**, foi
> demonstrada colando três linhas no `uv run python`, **reformulada uma vez** e
> fechou. Esse é o padrão — pergunta sobre consequência observável, conferida
> rodando na hora. A melhor candidata desta sessão está em **§4.1**.

---

## 1. Por que este é o próximo card

Caminho crítico: `018 → 006 → 007 → **008** → 009 → 010 → 012`. O CARD-007 está
em PR (#12) com os gates verdes: a porta do professor, o adapter em streaming e
a medição existem.

O 008 vem agora porque **0,41 s da primeira frase é o último termo do orçamento
de 1,8 s** — e porque a porta precisa **nascer por sentença**. Um
`synthesize(texto_inteiro)` seria a versão batch que a regra de desempate manda
não construir, exatamente como o adapter batch de LLM que o 007 recusou.

O que já está pago pela cascata, medido no CARD-007 (§8.2 da medição): a
primeira sentença sai em **0,68–0,76 s**. Somando 0,41 s de síntese, o primeiro
áudio fica em **~1,1 s** — dentro do alvo, com folga, **se** o TTS não trouxer
custo fixo escondido.

---

## 2. O que já está decidido e não se rediscute

- [**ADR-0024**](../adr/0024-midia-por-trecho-chave-url-assinada-e-retencao-assimetrica.md)
  — o esquema de chaves, a URL assinada **junto do evento** (nunca sob demanda),
  e a retenção assimétrica (trecho 1 dia, `full` 90 dias, `input` 7 dias).
  `{index:03d}` é zero-padded para a ordem lexicográfica do bucket **ser** a
  ordem de playback.
- [**ADR-0011**](../adr/0011-stt-e-tts-locais-como-default.md) + **ADR-0010** —
  TTS **local**. Gasto de API é restrito ao Claude; OpenAI TTS não entra.
- [**ADR-0023**](../adr/0023-ciclo-de-vida-do-turn-com-entrega-em-cascata.md) /
  [**ADR-0028**](../adr/0028-derivacao-da-etapa-do-turn-mora-no-dominio.md) — a
  etapa do `Turn` é **derivada**, e a ordem de avaliação é contrato: **trecho de
  áudio antes de `transcript`**. Não acrescente coluna nem valor a `TurnStatus`.
- [**ADR-0029**](../adr/0029-o-que-atravessa-a-porta-de-stt-sao-bytes-codificados.md)
  — o precedente da fronteira: **nenhum tipo de biblioteca atravessa uma porta**.
  `numpy` está no `forbidden` de `domain` e `application` exatamente porque
  `NDArray[np.float32]` é o tipo *natural* para áudio. Ver §4.2: este card tem
  o mesmo problema, e o card resolve na direção contrária sem perceber.
- [**ADR-0025**](../adr/0025-modelos-residentes-no-worker-e-readiness-que-distingue-pronto.md)
  — o modelo fica **residente no worker**; a carga acontece no boot, não por job.
  O Kokoro medido leva **5,63 s** para ficar pronto, e é o dono dos ~6 s.
- **ADR-0030 / ADR-0031** (CARD-007) — o precedente de porta em fluxo, de erro
  que mora na porta quando o caso de uso vai capturá-lo, e de validação à mão
  em vez de pydantic fora da borda `api/`.

---

## 3. Arqueologia — verificada no repositório em 2026-08-21

### 3.1 Quatro coisas que o card assume e que NÃO EXISTEM

Leia esta seção antes do plano. **Uma delas torna um critério de aceite
impossível de cumprir como está escrito.**

| O card assume | O que se verificou | Consequência |
|---|---|---|
| *"**Dado o container do worker**, então o TTS sintetiza sem intervenção manual — as três dependências escondidas estão no Dockerfile"* | **Não existe Dockerfile no repositório.** `find . -name "Dockerfile*"` (fora de `node_modules` e `.venv`) não devolve nada. O `docker-compose.yml` só sobe Postgres, Redis, MinIO e Jaeger — **imagens prontas, nenhum build** | **Decisão de escopo, e é sua, não minha.** Ou o card cria o Dockerfile do worker (que é obra própria, provavelmente card separado), ou o critério vira *"as dependências de sistema estão declaradas e há teste que falha se faltarem"*, com o container ficando para o CARD-009, que é quem tem worker. **Pergunte antes de decidir** |
| O bucket existe | **O bucket nunca é criado.** `s3_bucket` aparece **só** em `config.py:131`; não há sidecar `createbuckets` no compose nem código que o crie. O primeiro `put_object` falha com `NoSuchBucket` | Alguém tem de criá-lo. Sidecar `mc mb` no compose, ou `head_bucket`+`create_bucket` no setup — e a escolha muda quem é dono do lifecycle |
| `boto3` disponível | **Não está instalado** e não está no `pyproject.toml`. E **não publica `py.typed`** | Dependência nova → **critério 1** de ADR. E decisão de tipagem: override pontual de `mypy` (como `asyncpg` e `faster_whisper`) **ou** `types-boto3` (1.43.78, casado com `boto3` 1.43.78). O projeto tem precedente para o override; o `types-boto3` é uma dependência a mais para um ganho real. Decida por escrito |
| `testcontainers` cobre MinIO | **`testcontainers.minio` está DEPRECIADO** (emite `DeprecationWarning` apontando para `testcontainers.community.minio`), e o módulo novo faz `from minio import Minio` — o pacote **`minio` não está instalado** | Usar o helper puxa um **segundo cliente S3** só para teste, enquanto o adapter usa `boto3`. As saídas: instalar `minio` como dev dep, usar `DockerContainer` genérico com a imagem do MinIO, ou reusar o MinIO do compose. **O ADR-0018 escolheu testcontainers para Postgres; ele não decide isto** |

### 3.2 O estado do código, conferido

| Fato | Consequência para você |
|---|---|
| `application/ports/` tem `repositories.py`, `speech_to_text.py` e `teacher_llm.py`. As portas novas são o quarto e o quinto arquivo | `teacher_llm.py` é o modelo mais recente: `Protocol`, dataclasses `frozen=True, slots=True`, erro da porta morando **na porta**, docstring que explica o que atravessa a fronteira **e por quê** |
| **`TurnAudioChunk` já existe** em `domain/turn.py` com `index`, `storage_key`, `duration_seconds`, `text`, `created_at` — e `Turn.append_audio_chunk` **já exige índice denso e em ordem** (`OutOfOrderAudioChunkError`) | Você **não inventa** esse modelo: respeita. E a docstring já diz que a ordenação é por `index`, **nunca** por `created_at` |
| `adapters/health.py::check_minio` tem a dívida do ADR-0014 escrita no próprio docstring: *"deliberadamente NÃO valida credencial nem existência do bucket: isso exige um cliente S3 (boto3), que entra com a porta `MediaStorage` no CARD-008"* | A dívida fecha aqui, e o docstring precisa mudar junto. É o tipo de comentário que envelhece em silêncio |
| `adapters/` tem `persistence/`, `stt/`, `llm/` e `health.py`. `stt/factory.py` e `llm/factory.py` são o padrão de fábrica: resolve no boot, **imports locais à função**, log do que foi escolhido | Copie o padrão. Importar a fábrica não pode arrastar SDK nenhum |
| `src/voicecoach/worker/` continua **só com `__init__.py`** | Terceiro card seguido sem consumidor. Se `arq` aparecer no diff, o escopo vazou |
| Suíte hoje: **122 passed, 92,78% global; `domain` + `application` 100%** | O piso é 90% no núcleo e 80% global. Não deixe cair |
| Marker `slow` existe e é deselecionado por default | Aqui ele custa **tempo de CPU e download de vozes**, não dinheiro — diferente do CARD-007. Diga isso no docstring, porque a diferença importa para quem decide rodar |
| `benchmarks/tts_kokoro.py` existe e documenta o conserto do espeak | É o insumo da comparação. **Não** existe `benchmarks/tts_piper.py` — você o escreve |

### 3.3 Kokoro vs Piper: metade do critério já está verificada

O card mandou escrever o critério **antes** de medir, e escreveu:
*"tempo de carga, RTF, número de dependências de sistema, e qualidade percebida
numa amostra fixa. **Se o Piper empatar em qualidade, ele ganha por
empacotamento**"*.

O eixo de empacotamento **já se decide sem rodar nada**, e está verificado hoje:

| | `kokoro` 0.9.4 | `piper-tts` 1.7.0 |
|---|---|---|
| Dependências base | spaCy (+ modelo `en_core_web_sm` **não declarado**), `espeakng-loader`, `misaki`, torch | **`onnxruntime` e `pathvalidate`. Só.** |
| Fonemização | `espeak-ng` **de sistema**, reapontado à mão **depois** do `import kokoro` | dentro da extensão compilada |
| Wheels | — | `macosx_11_0_arm64`, `manylinux_2_28_x86_64`, `manylinux…aarch64`, `win_amd64` |
| Carga medida | **5,63 s** (1,91 s de import + 3,72 s de pipeline) | **não medido — é o que falta** |
| RTF medido | ~0,10, constante | **não medido** |

**O que ninguém mapeou ainda, e você tem de tratar:** o Piper **não embarca
vozes**. Cada voz é um par `.onnx` + `.onnx.json` baixado à parte — o análogo
exato dos pesos do Whisper (36–99 s na primeira execução, CARD-006). Trocar
"três dependências de sistema" por "um download de modelo versionado" é
provavelmente um bom negócio, mas **é uma troca, não uma eliminação**, e o card
não a menciona.

Falta medir: **carga, RTF e qualidade percebida** do Piper, com a mesma amostra
fixa do `tts_kokoro.py` (os textos `TIPICO` e `FRASE` já estão lá). Sem isso o
desempate é estético, que é exatamente o risco que o card nomeou.

---

## 4. As armadilhas — o que o texto do card não antecipa

### 4.1 `boto3` é síncrono, e o argumento do CARD-006 NÃO transfere

O objetivo de aprendizado do card pede escolher conscientemente entre executor e
`aioboto3`. Cuidado com a analogia fácil: no CARD-006 o `run_in_executor`
funcionou porque **o CTranslate2 solta o GIL** enquanto roda código nativo —
está escrito no docstring do `faster_whisper_adapter.py`.

**`boto3` é IO de rede, não CPU.** A natureza do problema é outra, e a conclusão
não se herda: a thread fica bloqueada em `socket.recv`, o GIL é solto pelo
próprio IO, e o que se está comprando com o executor é **não bloquear o event
loop**, não paralelismo. `aioboto3` (15.5.0) faz IO async de verdade, ao custo
de uma dependência a mais que envolve `aiobotocore`.

**Esta é a melhor pergunta do explicador desta sessão**, e tem consequência
observável: *"se eu chamar `client.put_object(...)` direto dentro de uma
corrotina, o que acontece com as outras corrotinas do worker enquanto o upload
corre — e como eu provaria isso num teste?"*

### 4.2 O que atravessa a porta de TTS: o card contradiz o ADR-0029 sem notar

O card propõe `synthesize(text: str) -> AudioData` e, três linhas abaixo:

> *"Concatenação do áudio inteiro (`reply/full.*`) ao completar: como o TTS local
> devolve **PCM**, concatenar antes de codificar é barato e sem recodificação."*

Só que o ADR-0029 decidiu que **bytes codificados** atravessam a porta de STT, e
o `forbidden` proíbe `numpy` em `application` justamente porque `ndarray` é o
tipo natural para áudio. Se `AudioData` carrega `ndarray`, a regra quebra; se
carrega MP3, concatenar exige **recodificar**, e o "barato e sem recodificação"
evapora.

**Não é armadilha teórica — é a decisão de fronteira deste card**, e o candidato
óbvio a ADR (critério 2). Uma saída que respeita as duas coisas existe e cabe
numa dataclass: **PCM como `bytes`, com a taxa de amostragem junto**. `bytes` não
é tipo de biblioteca, `b"".join(...)` concatena, e a codificação vira
responsabilidade de quem grava. **Mas confirme com o desenvolvedor antes de
escrever** — o precedente dos CARDs 018, 006 e 007 é que decisão de fronteira vai
ao dono do projeto antes da primeira linha de código; foi assim que nasceram os
ADRs 0028, 0029 e 0031.

E há um detalhe que decide sozinho parte disso: **Kokoro sintetiza a 24.000 Hz;
as vozes do Piper são tipicamente 22.050 Hz**, e a taxa é propriedade do
**modelo**, não da porta. Concatenar PCM de taxas diferentes produz áudio com a
velocidade errada — e o modo de falha é *audível*, não uma exceção.

### 4.3 URL assinada: o que ela custa, e o que ela não faz

Assinar é **HMAC local** — não faz chamada de rede, custa microssegundos. É por
isso que o ADR-0024 pôde decidir "assina junto do evento" sem pagar roundtrip.
Duas consequências práticas:

- **O teste de expiração precisa de TTL curto e espera real.** Um teste que
  dorme 60 s não entra na suíte default; um que dorme 2 s com TTL de 1 s é
  aceitável e ainda assim é o candidato natural a ficar *flaky* no CI.
- **A URL assinada carrega o endpoint que o cliente S3 usou para assiná-la.**
  Gerada de dentro de um teste que fala com o MinIO por um host/porta e
  consumida de outro contexto, ela aponta para o lugar errado — e o erro aparece
  como assinatura inválida, não como host errado.

### 4.4 O lifecycle é do MinIO, e MinIO ≠ S3

O ADR-0024 herdou a ressalva do ADR-0006 e agora tem **três** regras para
divergir. O teste cobre MinIO; ele **não** é evidência sobre o provedor real.
Escreva isso no card em vez de deixar o teste verde sugerir o contrário.

### 4.5 Não implemente o consumidor

Este card **não** orquestra a cascata (CARD-009), **não** emite eventos nem SSE
(CARD-010/ADR-0026), **não** implementa `delete_prefix` no fluxo de conta
(CARD-017), e **não** faz TTS em stream intra-frase (V2, ADR-0003). As portas
existem, os adapters existem, os testes provam — e acaba aí.

### 4.6 A medição é entregável

O CARD-007 produziu o número que ele existia para produzir e registrou o insumo
com **hash**. Repita: a comparação Kokoro vs Piper vira seção nova em
`docs/medicao-latencia.md`, com o insumo hasheado, e o benchmark novo
(`benchmarks/tts_piper.py`) segue o protocolo do `_common.py` — aquecimento
descartado, percentil por posição, sem interpolação.

---

## 5. Escopo — o que corta se estourar

Regra de desempate da reconstrução: **cede escopo, nunca latência.**

- **Não corte:** a porta `TextToSpeech` **por sentença**, a porta
  `MediaStorage`, a chave do ADR-0024 com `{index:03d}`, a medição comparativa
  Kokoro vs Piper, e os fakes de `application`.
- **Pode virar card próprio:** o **Dockerfile do worker** (§3.1 — é obra
  própria, e o CARD-009 é quem tem worker para conteinerizar); o lifecycle das
  três regras; a concatenação `reply/full.*`, se a decisão de §4.2 ficar em
  aberto.
- **Se a comparação empatar em qualidade**, o desempate **já está declarado no
  card**: empacotamento, e os dados de §3.3 apontam para o Piper. Registre a
  decisão como ADR (critério 1), não como parágrafo de card.

---

## 6. Governança

1. **Item de ADR da DoD — este card quase certamente gera ADR** (confira contra
   a lista de `docs/adr/README.md` e **cite o critério**, LEARNING-0003):
   - **Critério 1 (dependência externa):** entram `boto3` (+ possivelmente
     `types-boto3`, `aioboto3` ou `minio`) e **o TTS escolhido**. A troca
     Kokoro → Piper é literalmente "trocar uma dependência externa";
   - **Critério 2 (fronteira):** o que atravessa a porta de TTS (§4.2) — é o
     mesmo tipo de decisão que gerou o ADR-0029 no CARD-006 e o ADR-0031 no 007;
   - **Critério 4 (privacidade):** o ADR-0024 já decidiu retenção e exposição de
     voz. Se o seu lifecycle divergir do que ele escreveu, é **ADR novo**, não
     ajuste de constante.
2. **Skill `voicecoach-arquitetura`:** cobre os ADRs 0001–0023 e 0030–0031;
   **0024–0029 ainda não foram destilados**. Se ela contradisser um ADR, **o ADR
   ganha** e a skill se corrige na mesma sessão — foi o que o CARD-007 fez.
3. **Decisão que os ADRs não cobrem vai ao desenvolvedor ANTES da primeira linha
   de código.** Nesta sessão são três, e todas estão acima: o Dockerfile (§3.1),
   o que atravessa a porta de TTS (§4.2) e quem cria o bucket (§3.1).

---

## 7. Definition of Done específica deste card

Além da DoD do `CLAUDE.md`:

- [ ] **Comparação Kokoro vs Piper medida e registrada** em
      `docs/medicao-latencia.md`, com carga, RTF, dependências de sistema e
      qualidade percebida na amostra fixa — e o insumo hasheado. A decisão vira
      **ADR**, não seção de card.
- [ ] Porta `TextToSpeech` chamada **uma vez por sentença**, com o que atravessa
      a fronteira decidido por escrito (§4.2) e coerente com o ADR-0029.
- [ ] Porta `MediaStorage` com `put`, `presigned_get_url(ttl)` e
      `delete_prefix`; chaves exatamente como o ADR-0024 escreveu, com
      `{index:03d}`.
- [ ] Teste que prova que a **listagem por prefixo devolve os trechos na ordem**
      — e que ele falharia sem o zero-padding.
- [ ] Teste que prova que o objeto **não é legível sem assinatura**.
- [ ] Teste de **expiração** da URL, com TTL curto (§4.3), e uma nota honesta
      sobre o risco de flakiness.
- [ ] `check_minio` migrado para `head_bucket` com credencial real — **e o
      docstring que aponta para o CARD-008 atualizado junto** (a dívida do
      ADR-0014 fecha aqui).
- [ ] Decisão registrada sobre **boto3 síncrono em app async**: executor ou
      `aioboto3`, com o trade-off escrito e o motivo pelo qual o argumento do
      CARD-006 não transfere (§4.1).
- [ ] `uv run lint-imports` verde, com **as dependências novas** nas listas
      `forbidden` de `domain` e `application` **no mesmo commit** que as instala.
      Prove que o gate morde injetando a violação e revertendo — o par completo,
      como nos CARDs 006 e 007.
- [ ] Cobertura: núcleo ≥ 90%, global ≥ 80%. **Está em 100% / 92,78% hoje.**
- [ ] Testes de `application` com **fakes em memória**, sem tocar boto3 nem o
      TTS — e são eles que fecham a Q7.
- [ ] O critério *"dado o container do worker"* **resolvido explicitamente**:
      cumprido, ou reescrito com o motivo e o card que o assume (§3.1).
- [ ] Q7 e Q9 reapresentadas na abertura, com desfecho registrado no card:
      respondida / dispensada pelo dev / em aberto. **Item fechado pelo agente
      com a própria explicação não conta** (LEARNING-0004).
- [ ] Card atualizado e tabela de `docs/backlog/README.md` atualizada.

---

## 8. Restrições

- **Branch própria** a partir de `main`. `main` é protegida. Se o PR #12 ainda
  não tiver sido mergeado, **pergunte** se a branch sai de `main` ou da
  `card-007-…` — o CARD-008 não depende do 007, então `main` deve bastar.
- Commit **nunca** leva trailer `Co-Authored-By`
  ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
- **Não pushe nem abra PR sem perguntar.** O padrão de PR é o do #11 e #12:
  título `CARD-XXX: <frase>`, e as seções *O que entra* → *a decisão do ADR* →
  *achados/divergências* → *Gates* (saída real colada) → *Dívidas registradas no
  card* → *Regra do explicador*.
- **Custo zero é requisito** (ADR-0010), não preferência: TTS **local**, nada de
  OpenAI TTS, nada que exija conta paga. Este card **não gasta dinheiro** —
  diferente do 007.
- **Não antecipe o V2** (ADR-0003): nada de TTS em streaming intra-frase.
- Responda em português. O desenvolvedor é sênior em C#/.NET e **iniciante em
  Python**: ao citar biblioteca, diga qual, por que ela e não a alternativa, e o
  equivalente mental em .NET. Idioma sem paralelo em C# — **executor vs. IO
  async, `bytes` vs. `memoryview`, context manager** — pare e explique em 3
  linhas. Sem aula de injeção de dependência, repositório ou camadas.
