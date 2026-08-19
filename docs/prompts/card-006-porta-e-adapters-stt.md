# Prompt — CARD-006: Porta `SpeechToText` + adapters `mlx-whisper` e `faster-whisper`

- **Tipo:** prompt de sessão, complemento de `/executa-card 006`
- **Escrito em:** 2026-08-19, no fechamento do CARD-018
- **Status:** não executado

> **Este prompt não substitui o `/executa-card`.** Aquele comando carrega o
> protocolo (branch, ordem de leitura, premissas antes do plano, DoD item a
> item, convenção de commit). **Rode `/executa-card 006` e leia isto junto** —
> aqui está só o que é específico deste card, a arqueologia já feita, e o que o
> texto do card não antecipa.

---

## 0. Antes do plano: a fila do explicador tem dívida que é DESTE card

`docs/perguntas-em-aberto.md` tem **8 perguntas abertas**, e o arquivo já
aponta três para cá. Reapresente-as **na abertura, antes do plano** — não no
fim:

| # | Pergunta | Por que é deste card |
|---|---|---|
| **Q7** | O que `Protocol` faz que dispensa um framework de mock, e **em que momento** se descobre que um fake não satisfaz a porta? | O CARD-006 cria o **primeiro fake de porta** do projeto. O arquivo diz literalmente "volta no CARD-006/007". Antes respondida **errado** (o dev falou de CORS) |
| **Q3** | Contrato de **dependência** vs. contrato de **direção** no import-linter: em que cenário só o segundo pega a violação? | Este card acrescenta `faster-whisper` e `mlx-whisper` às listas `forbidden` — é o momento em que a distinção morde |
| **Q9** | Igualdade de `@dataclass`: por que dois objetos com um campo diferente não são iguais, e por que o Python **proíbe** usá-los como chave de dict/set? | A porta devolve `Transcript`, um tipo próprio que será `@dataclass` |

> **Aviso de processo, do CARD-018:** naquela sessão o agente afirmou que
> `docs/perguntas-em-aberto.md` **não existia** — porque rodou o `cat` com o
> diretório de trabalho ainda em `backend/`, herdado de um comando anterior. A
> fila não foi reapresentada. **Confira o caminho a partir da raiz do
> repositório** antes de concluir que um arquivo do harness não existe.

Q7 é a candidata natural a **uma** das duas perguntas do explicador desta
sessão, e ela tem resposta conferível rodando: veja §4.2.

---

## 1. Por que este é o próximo card

Caminho crítico da reconstrução: `018 → **006** → 007 → 008 → 009 → 010 → 012`.
O CARD-018 fechou (branch `card-018-turn-com-trechos-de-audio`), então a
entidade que recebe os trechos existe. O 006 vem agora porque **o STT custa
0,59 s do orçamento de 1,8 s** — um terço — e nada do resto é mensurável
enquanto ele não existir.

**Esforço M**, e é o primeiro card de IA do repositório: não existe adapter de
provider nenhum ainda.

---

## 2. A decisão já está tomada: leia o ADR antes do código

[**ADR-0027**](../adr/0027-adapter-duplo-de-stt-com-default-resolvido-pela-plataforma.md)
é a fonte de verdade, e ele **complementa** (não substitui) o
[ADR-0011](../adr/0011-stt-e-tts-locais-como-default.md). Leia os dois.

Seis coisas que o ADR decide e **não** se rediscutem nesta sessão — todas
contra medição, não contra gosto:

1. **`float32`, não `int8`.** Medido: `int8` é **mais lento** neste hardware
   (1,48 s → 1,18 s ao *abandonar* a quantização). Adotar `int8` "porque é mais
   leve" é otimização por hábito que a medição já desmentiu.
2. **`beam_size=1`**, não 5. Corta ~30%.
3. **`small.en` é o default e a escolha de modelo está BLOQUEADA** (item 7). O
   `base.en` **não** é a alternativa rápida que parecia — reexecutado, deu
   0,78 s contra os 0,20 s da primeira medição. Não "otimize" trocando de
   modelo.
4. **`auto` é o default de `STT_PROVIDER`**, resolvido pela plataforma no boot.
5. **Escolha incompatível falha no boot.** `STT_PROVIDER=mlx` em x86 **não**
   cai para o outro adapter: fallback silencioso esconderia regressão de 2,4×
   atrás de um log.
6. **Língua forçada `en`.** Não é autodetecção.

---

## 3. Arqueologia já feita — não repita

Verificado no repositório em 2026-08-19, depois do commit do CARD-018:

| Fato | Consequência para você |
|---|---|
| `src/voicecoach/adapters/` só tem `health.py` e `persistence/`. **Não existe `adapters/stt/`** | Você cria o pacote. Primeiro adapter de provider do projeto |
| `application/ports/` só tem `repositories.py` | A porta nova é o segundo arquivo lá |
| `src/voicecoach/worker/` tem **só o `__init__.py`** | Não há entrypoint de worker ainda; a carga residente é do CARD-009 (ADR-0025), **fora** deste card |
| `config.py` já tem `teacher_model`, `assistant_model`, `daily_budget_usd`, `database_url`, `redis_url`. **Não tem nada de STT** | `stt_provider` e afins entram lá, e o `Settings` é `frozen=True` |
| `benchmarks/` já existe com `stt_mlx.py` e `stt_faster_whisper.py` **funcionando** | Eles são a fonte dos parâmetros exatos. Copie os valores medidos de lá, não do que a documentação da lib sugere |
| `benchmarks/requirements.txt` é **deliberadamente separado** do `pyproject.toml` | Diz por escrito: *"quando os adapters de IA existirem (CARDs 006/007/008), as bibliotecas que eles realmente usarem entram no pyproject pela porta da frente"*. É este card |
| A chamada real: `mlx_whisper.transcribe(audio, path_or_hf_repo="mlx-community/whisper-small.en-mlx", language="en", verbose=None)` | O repo HF é o identificador do modelo no `mlx`, e é diferente do nome do `faster-whisper` — **os dois adapters não compartilham a string do modelo** |
| A chamada real: `WhisperModel(modelo, device="cpu", compute_type="float32")` + `motor.transcribe(audio, language="en", beam_size=1, vad_filter=...)` | O `faster-whisper` devolve um **generator** de segmentos, não uma string — ver §4.4 |
| Os benchmarks leem o áudio com `soundfile` (`sf.read(..., dtype="float32")`), a 16 kHz mono | A porta precisa decidir o que é `AudioInput` — ver §4.3 |

### A armadilha de infraestrutura mais cara

**`benchmarks/inputs/` está no `.gitignore`.** Os arquivos `curto.wav` e
`longo.wav` existem na máquina do desenvolvedor e **não estão versionados**. O
`make_inputs.py` os reconstrói a partir de *"uma pasta de origem"* que também
não está no repositório.

Isso colide de frente com o primeiro critério de aceite (*"dado um wav
conhecido..."*). **Resolva isso no plano, antes de escrever teste**, e traga a
questão ao desenvolvedor: gerar um wav sintético minúsculo no próprio teste
(uma senoide não transcreve nada útil), versionar um clipe curto de voz real
(bytes no repositório, e é voz — dado pessoal, visão §E), ou marcar o teste de
integração como `slow` e dependente de insumo local. **Não invente a resposta.**

---

## 4. As armadilhas — o que o texto do card não antecipa

### 4.1 O import tardio é um idioma que engana três ferramentas ao mesmo tempo

`mlx-whisper` é extra opcional e o ADR-0027 manda importar **dentro da
construção do adapter**. Consequência: `ruff` e `mypy` veem o módulo, a máquina
de CI não tem o pacote. O card já prevê o override de `mypy` **pontual e
comentado com o gatilho de remoção** (regra do `CLAUDE.md`). O que ele não
prevê: `import-linter` também analisa o import, e ele precisa entrar na lista
`forbidden` de `domain` e `application` **no mesmo commit** (ADR-0012) — a lista
não se atualiza sozinha, e é o elo fraco assumido.

### 4.2 Q7 tem demonstração executável, e é a melhor pergunta desta sessão

O fake de `SpeechToText` no teste de `application` não declara herança nenhuma.
A pergunta *"em que momento se descobre que ele não satisfaz a porta?"* se
confere assim: quebre a assinatura do fake (mude um nome de parâmetro, troque o
tipo de retorno) e rode `uv run mypy` **e** `uv run pytest`. Um dos dois fica
vermelho e o outro não — e qual é qual é exatamente o conteúdo da pergunta.
Pergunte **antes** de escrever o fake.

### 4.3 A porta não pode vazar tipo de biblioteca, e "áudio" é onde isso vaza

`transcribe(audio: AudioInput) -> Transcript`. `AudioInput` **não** pode ser um
`numpy.ndarray` — `numpy` viraria dependência de `application`, e o contrato do
import-linter deve pegar isso. Decida no plano se a porta recebe `bytes`, um
caminho de arquivo, ou um tipo próprio, e quem paga a decodificação. O
benchmark tira a decodificação de dentro da medição de propósito; o adapter real
não tem esse luxo, e o custo dela **conta no orçamento de 1,8 s**.

### 4.4 O `faster-whisper` devolve um generator preguiçoso

`motor.transcribe(...)` retorna `(segmentos, info)` onde `segmentos` é um
**generator** — a transcrição só acontece quando você o consome. Duas
consequências: cronometrar sem consumir mede zero, e o trabalho de CPU acontece
**fora** da chamada que você mandou para o executor, se você não tomar cuidado.
Isto interage direto com o `run_in_executor` do próximo item. (`generator` é um
dos idiomas de Python sem paralelo direto em C# que o `CLAUDE.md` manda parar e
explicar — o mais próximo é `IEnumerable` com `yield return`, e a diferença aqui
é *onde o trabalho roda*.)

### 4.5 `run_in_executor` e o GIL

CPU-bound em código async. `run_in_executor` é o paralelo de `Task.Run`, com
uma diferença que muda o resultado: em .NET, `Task.Run` num pool de threads
paraleliza de verdade; em Python, o GIL serializa bytecode, e o ganho só existe
porque a biblioteca **solta o GIL** enquanto roda código nativo. Vale para o
`faster-whisper`; para o `mlx-whisper` a conta é outra (o trabalho vai para a
GPU). Não presuma simetria entre os dois adapters.

### 4.6 Não implemente o consumidor

Este card **não** carrega modelo residente (CARD-009, ADR-0025), não orquestra
pipeline, não persiste `transcript` (a entidade já sabe fazer isso desde o
CARD-005), não emite evento e não mede latência ponta a ponta (CARD-012). Se
aparecer `arq` no diff, o escopo vazou.

---

## 5. Escopo — o que corta se estourar

Regra de desempate da reconstrução: **cede escopo, nunca latência**.

- **Não corte:** a porta, os dois adapters locais, a seleção por config com
  falha no boot, o fake de `application`.
- **Pode virar card próprio:** o **esqueleto do adapter OpenAI** (modo
  qualidade). É o único item do card que não desbloqueia o 008/009 e não tem
  latência a defender.

---

## 6. Governança

1. **O `CLAUDE.md` vigente vence.** A emenda proposta na reconstrução (§5 do
   documento) **não foi aceita**: valem a regra do explicador com desfecho
   registrado no card, o item correspondente da DoD, e o campo "Objetivo de
   aprendizado".
2. **A skill `voicecoach-arquitetura` foi parcialmente atualizada no CARD-018**
   (ciclo de vida do `Turn` e derivação da etapa, ADRs 0023/0028). Ela **ainda
   não reflete os ADRs 0024–0027** — inclusive o 0027, que é o deste card.
   Dívida registrada no log do `REFERENCE.md` e no CARD-004. Se a skill
   contradisser o ADR-0027, **o ADR ganha** e a skill se corrige na mesma
   sessão; nunca afrouxe em silêncio nos dois sentidos.
3. **Item de ADR da DoD:** este card **implementa** o ADR-0027 e, em princípio,
   não gera ADR novo — as dependências e a fronteira já estão registradas lá
   (critérios 1 e 2). **Mas confira, não presuma:** se a decisão sobre o que é
   `AudioInput` (§4.3) ou sobre o insumo de teste (§3) definir uma fronteira
   nova, o critério 2 dispara. Registre o critério que se aplicou **ou** por que
   nenhum se aplicou (LEARNING-0003).
4. **Precedente útil do CARD-018:** houve uma decisão que os ADRs não cobriam
   (onde mora a derivação da etapa). Ela foi **levada ao desenvolvedor antes da
   primeira linha de código**, e a escolha dele gerou o ADR-0028. Faça o mesmo:
   pare e pergunte, não decida e documente depois.

---

## 7. Definition of Done específica deste card

Além da DoD do `CLAUDE.md`:

- [ ] Os quatro critérios de aceite do card verificados **com saída de comando
      colada** — em especial o boot que falha em plataforma incompatível
      ("testado, não presumido", diz o card).
- [ ] O adapter escolhido por `auto` é **logado na subida**. Latência que não é
      explicável depois é latência que não se otimiza.
- [ ] `uv run lint-imports` verde, com `faster_whisper` e `mlx_whisper` nas
      listas `forbidden` de `domain` e `application` **no mesmo commit** que os
      instala. Se os contratos não morderem sozinhos, prove que mordem
      injetando a violação e revertendo.
- [ ] O override de `mypy` para `mlx_whisper` é **pontual, comentado e com
      gatilho de remoção escrito** — nunca afrouxamento do modo global.
- [ ] Cobertura: núcleo (`domain` + `application`) ≥ 90%; global ≥ 80%. **Está
      em 100% / 91% hoje** (fim do CARD-018) — não deixe cair.
- [ ] Teste de `application` usa **fake em memória**, sem tocar em biblioteca
      de STT (é o que prova que a porta é porta).
- [ ] Q7 reapresentada na abertura e com desfecho registrado no card —
      respondida / dispensada pelo dev / em aberto. **Item fechado pelo agente
      com a própria explicação não conta** (LEARNING-0004).
- [ ] Card atualizado e tabela de `docs/backlog/README.md` atualizada.

---

## 8. Restrições

- **Branch própria** (`card-006-porta-e-adapter-stt-local`); `main` é protegida.
  Note que o CARD-018 está em `card-018-turn-com-trechos-de-audio` e **ainda não
  foi mergeado** — confirme com o desenvolvedor de onde partir.
- Commit **nunca** leva trailer `Co-Authored-By`
  ([LEARNING-0001](../learnings/0001-commit-com-coautoria-indesejada-do-agente.md)).
- **Não pushe nem abra PR sem perguntar.**
- **Custo zero é requisito** (ADR-0010): STT local, nada que exija conta paga.
  O adapter OpenAI é esqueleto atrás de config, não caminho default.
- **Não antecipe o V2** — STT incremental/streaming é ADR-0003, e nenhuma das
  três condições do gatilho foi atingida.
- Responda em português. O desenvolvedor é sênior em C#/.NET e **iniciante em
  Python**: ao citar biblioteca, diga qual, por que ela e não a alternativa, e o
  equivalente mental em .NET. Idioma sem paralelo em C# (`generator`,
  `Protocol`, import tardio, `run_in_executor`) — pare e explique em 3 linhas.
  Sem aula de injeção de dependência, repositório ou camadas.
