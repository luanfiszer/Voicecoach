# Briefing — qualidade da conversa: cinco apontamentos do primeiro uso real

- **Data:** 2026-09-09
- **Origem:** primeira sessão de uso do produto **em aparelho físico**, com fala
  humana real (CARD-037). Todos os cinco pontos abaixo vieram do desenvolvedor
  usando o app, não de análise de código.
- **Status:** briefing de investigação. **Nada aqui é decisão** — o que vira
  decisão sai da investigação, em ADR, e o trabalho sai em cards.

> Por que este documento existe antes dos cards: quatro dos cinco pontos tocam
> decisões já registradas em ADR (Piper, Whisper, turn-based, CEFR na visão).
> Investigação que ignora ADR fechado reabre discussão encerrada e produz card
> que contradiz o repositório. Cada ponto abaixo começa pelo que **já está
> decidido**, e só então pelo que falta saber.

---

## 1. A voz do professor soa robótica

**O que foi observado:** a voz é inteligível, mas mecânica. O desenvolvedor quer
naturalidade e, no futuro, **sotaques** (e outros idiomas) — mas o foco agora é
inglês.

**O que já está no repositório:**

| Fato | Onde |
|---|---|
| O motor é o **Piper**, escolhido sobre o Kokoro | [ADR-0032](adr/0032-piper-substitui-o-kokoro-como-motor-de-voz.md) |
| A voz é `en_US-lessac-medium` — **qualidade "medium"**, uma voz americana | `backend/src/voicecoach/config.py:336` |
| A voz é **configurável** (`tts_voice`), e o diretório de vozes também (`tts_voices_dir`) | `config.py:336,341` |
| O TTS roda **local, por sentença**, e é parte do caminho de latência | ADR-0033, ADR-0037 |

**O que investigar, em ordem de custo:**

1. **A voz, não o motor.** O Piper publica vozes `low`/`medium`/**`high`** e
   dezenas de vozes por idioma (`en_US-*`, `en_GB-*`). Trocar `tts_voice` é uma
   linha de configuração. **Medir**: quanto a `high` melhora percepção e quanto
   custa em latência (o TTS está no caminho crítico — ver §4 dos números do
   CARD-037, onde "até o primeiro chunk" domina).
2. **Só então o motor.** Se nem a melhor voz do Piper satisfizer, aí a pergunta
   é de substituição — e ela **exige ADR novo que substitua o 0032**, com as
   mesmas medições que ele fez (latência, RTF, tamanho do modelo, custo).
   Candidatos a considerar honestamente: Kokoro (rejeitado antes, mas o motivo
   pode ter mudado), XTTS/Coqui, e APIs pagas (que **colidem com o ADR-0010** e
   exigiriam ADR de custo).
3. **Voz personalizada e sotaque** são a evolução natural do item 1, não um
   projeto à parte: se a arquitetura já lê a voz de configuração, "sotaque" é
   uma escolha de voz por aluno — e aí a pergunta vira **de produto** (quem
   escolhe? é preferência de conta? muda no meio da sessão?).

**Armadilha:** naturalidade é subjetiva e some no ruído se avaliada de memória.
A investigação precisa de um **método de comparação** — as mesmas 3 frases,
geradas por cada candidata, ouvidas em sequência, com o tempo de geração ao lado.

---

## 2. Regravar não interrompe o professor

**O que foi observado:** ao errar a gravação e tentar recomeçar, o app **continua
falando**. O comportamento desejado: começar a gravar **para o playback na hora**
e cancela o turn em curso — o professor cala a boca para ouvir o aluno.

**O que já está no repositório:**

| Fato | Onde |
|---|---|
| O V1 é **turn-based**; barge-in de verdade (falar por cima) é V2 | [ADR-0003](adr/0003-interacao-v1-turn-based-preparada-para-v2-realtime.md) |
| A fila de playback é **um player por trecho**, com cancelamento previsto | [ADR-0047](adr/0047-fila-de-playback-com-um-player-por-trecho-e-a-rota-de-medicao.md) |
| `useTurno` já tem `limpar()` e um `AbortController` que cancela a conexão viva | `apps/mobile/src/features/turno/useTurno.ts` |
| O turn é entregue **em cascata**, então há sempre um "meio do caminho" a abortar | ADR-0023, ADR-0037 |

**Isto é o mais barato dos cinco pontos, e provavelmente não precisa de ADR.**
As peças existem: parar a fila e abortar o acompanhamento já são operações do
hook. O que a investigação precisa decidir é **o que acontece do lado do
servidor**, e aí há uma escolha de produto com custo real:

- **(a) o turn em voo continua no servidor** e só é ignorado pelo cliente —
  simples, e **paga LLM + TTS por uma resposta que ninguém vai ouvir**;
- **(b) o cliente avisa o servidor para cancelar** — economiza custo, mas
  precisa de endpoint novo, de um estado de `Turn` que acomode cancelamento
  (o ADR-0003 item 2 diz que a entidade foi modelada para isso) e de decidir o
  que fazer com o áudio já gerado;
- **(c) o app impede regravar enquanto o professor fala** — mais simples de
  todas e **pior de usar**: é justamente o que incomodou.

**Pergunta que a investigação responde primeiro:** quanto custa, em dinheiro,
um turn abandonado? O `UsageEvent` ([ADR-0051](adr/0051-usage-event-fora-do-agregado-com-custo-congelado-na-escrita.md))
já registra custo real por turn — **US$ 0,002678/turn medido no CARD-014**. Se
abandonar for barato, (a) resolve hoje e (b) vira melhoria; se não, (b) sobe de
prioridade.

---

## 3. O STT entende errado — e "deduz" inglês quando falo português

**O que foi observado:** o professor frequentemente entende outra coisa; falando
**português**, ele inventa algo em inglês. O desejo: entender o que foi dito em
**qualquer idioma** e, quando não entender, **não deduzir**.

**Este ponto tem causa provável já identificada, no código:**

```
backend/src/voicecoach/config.py:322-323
    stt_model_faster_whisper: str = "small.en"
    stt_model_mlx: str = "mlx-community/whisper-small.en-mlx"

backend/src/voicecoach/adapters/stt/mlx_whisper_adapter.py:27
    LANGUAGE = "en"          ← constante de módulo, não configuração
backend/src/voicecoach/adapters/stt/faster_whisper_adapter.py:37-38
    BEAM_SIZE = 1            ← otimização de latência do CARD-006
    LANGUAGE = "en"
```

Três fatos que se somam, e explicam o sintoma **sem precisar de investigação**:

1. **O modelo é `.en`** — a variante *English-only* do Whisper. Ela não tem
   como transcrever português: foi treinada para produzir inglês. Diante de
   fala em outro idioma, produzir algo em inglês **é o comportamento esperado
   dela**, não um defeito.
2. **`language="en"` está fixo** no adapter, como constante de módulo — nem
   configuração é. Mesmo trocando o modelo, a detecção de idioma continuaria
   desligada.
3. **`beam_size=1`** foi escolhido no CARD-006 para cortar ~30% da latência.
   Menos busca = mais erro de transcrição. É um trade-off **deliberado e
   documentado** — e agora temos, pela primeira vez, evidência do lado do custo.

**O que a investigação precisa medir (e não decidir de véspera):**

- **`small.en` → `small`/`medium` multilíngue**: quanto muda em acerto e quanto
  custa em latência? Lembrando o achado do CARD-037: o pipeline do servidor já
  é **2,4 s dos 3,0 s**, então cada milissegundo aqui aparece no produto.
- **`beam_size` 1 → 5**: mesmo par de perguntas. O comentário do adapter diz que
  vale ~30%.
- **Detectar o idioma em vez de fixá-lo**: com modelo multilíngue, o Whisper
  devolve o idioma detectado (`info.language` já é lido em
  `faster_whisper_adapter.py:141`). Isso abre a porta para o comportamento que
  o desenvolvedor pediu: *o aluno falou português — responder a isso como
  professor, em vez de fingir que ouviu inglês.*
- **"Não deduzir" tem nome técnico**: `no_speech_threshold`, `logprob_threshold`
  e `compression_ratio_threshold` do Whisper, além da confiança por segmento.
  Hoje **nenhum deles é usado**. Um turn cuja transcrição tem confiança baixa
  poderia virar um desfecho explícito ("não entendi, pode repetir?") em vez de
  uma resposta a algo que o aluno não disse — e o `Result` do
  [ADR-0039](adr/0039-result-minimo-para-desfecho-esperado-de-caso-de-uso.md)
  já é o mecanismo certo para um desfecho esperado como esse.

**Ligação com o §5:** um aluno iniciante fala português no meio da frase o tempo
todo. O que o professor faz nesse caso é **decisão pedagógica**, não técnica.

---

## 4. O professor não percebe entonação

**O que foi observado:** como o pipeline é STT → LLM → TTS, tudo que não é
palavra se perde. A pergunta do desenvolvedor: dá para recuperar alguma coisa?

**O diagnóstico é correto, e a arquitetura o explica:** o que atravessa a porta
de STT são **bytes de áudio** que voltam como **texto** ([ADR-0029](adr/0029-o-que-atravessa-a-porta-de-stt-sao-bytes-codificados.md)),
e o que atravessa a porta do professor é um **fluxo de eventos de texto**
([ADR-0031](adr/0031-o-que-atravessa-a-porta-do-professor-e-um-fluxo-de-eventos.md)).
Prosódia (altura, ritmo, ênfase, hesitação) morre no primeiro passo — por
desenho, não por esquecimento.

**Três caminhos, em ordem crescente de ambição — a investigação diz qual cabe:**

1. **Extrair características acústicas no worker** e passá-las ao professor como
   *metadados* junto do texto: taxa de fala, pausas longas, energia, variação de
   pitch. Não é "entender entonação", é dar ao LLM **dados sobre como foi dito**.
   Cabe nas portas atuais como extensão do que o STT devolve, e é o único dos
   três que não muda a arquitetura.
2. **Usar os segmentos que o Whisper já devolve** — ele dá tempos por segmento,
   e daí saem pausa e ritmo de graça, sem biblioteca nova. É o subconjunto
   barato do item 1 e provavelmente o primeiro experimento.
3. **Modelo que ouve áudio direto** (speech-to-speech ou LLM com entrada de
   áudio). Muda o pipeline inteiro, colide com o custo zero do ADR-0010 se for
   API paga, e é a conversa do **V2** (ADR-0003). Não entra por este briefing.

**Pergunta de produto antes da técnica:** o que o professor **faria** com essa
informação? "Você falou muito rápido" e "você hesitou aqui" são feedback
pedagógico real; sem uma resposta a isso, o item 1 vira dado que ninguém usa.

---

## 5. O nível do aluno não entra na conversa

**O que foi observado:** a conversa não é adaptada ao nível. O desenvolvedor
quer que ela seja — por escolha do aluno, por desempenho ao longo dos turns, ou
por um mini-teste inicial. E já existe **uma tela prevista** para exibir isso.

**Este é o ponto com maior distância entre visão e backlog:**

| Fato | Onde |
|---|---|
| **`CefrAssessment` é conceito de domínio** — "estimativa de nível (A1–C2) com confiança, reavaliada por janela de sessões", apresentada **como faixa** ("A2–B1"), nunca como veredito | `docs/visao-produto-e-arquitetura-alvo.md:35` |
| A visão diz que ele **entra no MVP na forma barata**: estimativa por LLM com confiança, recalculada a cada N turns | `visao-produto-e-arquitetura-alvo.md:40` |
| **Não existe card nenhum** sobre isso. A única linha no backlog é *"Produto pedagógico completo (CEFR, resumo, tradução) — Fase 7 — a detalhar"* | `docs/backlog/README.md:54` |
| O prompt do professor **não recebe nível** hoje | adapter do professor |

Ou seja: **a visão diz MVP, o backlog diz Fase 7, e não há card.** Isso é um
buraco de planejamento, e o uso real acabou de cobrá-lo.

**O que a investigação precisa separar — são três features, não uma:**

1. **Nível declarado pelo aluno** (onboarding: "como você se avalia?"). Barato,
   imediato, e resolve o problema hoje: o nível entra no prompt do professor e
   muda vocabulário, velocidade e tolerância a erro.
2. **Nível estimado pelo desempenho** — o `CefrAssessment` da visão. Exige
   decidir *a partir de quê* (as `Correction` já são persistidas e tipadas desde
   o [ADR-0049](adr/0049-correction-e-entidade-persistida-e-os-campos-texto-viram-derivacao.md)),
   com que janela, e **como não parecer veredito** (a visão é explícita: faixa,
   com confiança).
3. **Mini-teste inicial** — é produto e conteúdo, não só engenharia. É o mais
   caro dos três e o mais fácil de adiar.

**A pergunta que ordena os três:** qual deles muda a conversa *amanhã*? Quase
certamente o 1 — e ele é pré-requisito dos outros dois, porque cria o campo, a
tela e o caminho do nível até o prompt.

---

## Prompt para a sessão de investigação

> Copie daqui para baixo numa sessão nova. Ele é deliberadamente uma sessão de
> **investigação**, não de implementação: o produto dela são ADRs onde couber e
> cards no backlog, não código.

```
Sessão de investigação — qualidade da conversa (origem: docs/briefing-qualidade-da-conversa-2026-09-09.md)

Leia primeiro, nesta ordem: CLAUDE.md; o briefing acima inteiro; os ADRs que ele
cita em cada ponto (0003, 0010, 0029, 0031, 0032, 0033, 0037, 0039, 0047, 0049,
0051); a Parte F da visão (anti-overengineering); e docs/learnings/ inteiro.

Regras desta sessão:

1. Declare as premissas de escopo antes de qualquer conclusão (regra do
   LEARNING-0002), incluindo o que é permanente e o que é andaime.
2. NADA é decidido sem medição quando a medição é possível. Os cinco pontos têm
   custo em latência, e o CARD-037 mediu que o pipeline do servidor já é 2,4 s
   dos 3,0 s do produto: qualquer proposta que aumente esse número precisa dizer
   quanto, com o comando rodado e a saída colada.
3. Onde um ADR já decidiu (Piper no 0032, turn-based no 0003, custo zero no
   0010), a investigação NÃO reabre por preferência. Reabre com evidência nova,
   e o resultado é um ADR que substitui o antigo, com as mesmas medições que ele
   fez. Se a evidência não existir, a conclusão é "fica como está" — e isso é um
   resultado válido.
4. Separe, em cada ponto, o que é decisão de PRODUTO (que é minha) do que é
   decisão TÉCNICA (que você recomenda). Não decida produto sozinho: pergunte.
5. O ponto 3 tem causa provável JÁ IDENTIFICADA no briefing (modelo .en +
   language fixo + beam_size=1). Comece por confirmá-la ou derrubá-la com um
   experimento real, antes de propor qualquer coisa.

Entregáveis, nesta ordem:

a) Para cada um dos cinco pontos: o que foi medido, com evidência colada; o que
   ficou provado; o que continua hipótese.
b) A ordem em que os cinco devem ser atacados, com o critério explícito da
   ordenação (custo × impacto na experiência × risco de latência). Diga qual
   resolve amanhã e qual é projeto.
c) Os cards, criados com /card, um por unidade de trabalho independente — cada
   um com objetivo de aprendizado, critérios de aceite verificáveis e o
   refinamento obrigatório (cache, limites, timeout/retry/desfecho).
d) Os ADRs que a investigação tornou obrigatórios, criados com /adr, citando o
   critério de docs/adr/README.md que se aplicou.
e) O que você recomenda NÃO fazer, com o motivo — a Parte F da visão vale aqui
   tanto quanto nos cards.

Ordem sugerida de investigação (mude se a evidência mandar, e diga por quê):
ponto 3 (STT: causa já localizada, e é o que mais estraga a experiência) →
ponto 2 (interromper: peças já existem, decisão de produto sobre custo do turn
abandonado) → ponto 5 (nível: visão diz MVP e backlog diz Fase 7, sem card) →
ponto 1 (voz: trocar a voz antes de discutir o motor) → ponto 4 (entonação: o
mais exploratório, e o único que pode terminar em "não agora").
```

---

## O que este briefing NÃO faz

- **Não cria cards.** Três dos cinco pontos dependem de medição para saber o
  tamanho do trabalho, e card estimado sem isso vira ficção.
- **Não reabre o ADR-0032 (Piper) nem o ADR-0003 (turn-based).** O ponto 1 pode
  levar a substituir o primeiro; o ponto 2 **não** precisa mexer no segundo, e
  a investigação deve resistir à tentação de transformar "parar o áudio ao
  regravar" em barge-in do V2.
- **Não decide nada de produto.** Sotaque por aluno, o que fazer quando o aluno
  fala português, e como o nível é escolhido são perguntas para o desenvolvedor.

---

## O que a investigação produziu (2026-09-09, mesmo dia)

O prompt acima foi executado. **Status deste documento: consumido** — ele deixa
de ser pauta e passa a ser o registro de origem.

**O que foi medido, e o que a medição mudou:**

| Ponto | Resultado |
|---|---|
| **3** | Hipótese **confirmada** (modelo `.en` + língua fixa), com um achado a mais: o `avg_logprob` separa alucinação (−1,1 a −5,9) de acerto (−0,13 a −0,32). **Derrubado:** o `beam_size=1` não explica nada do observado — ele só existe no adapter `faster-whisper`, e o Mac roda o `mlx`. Trocar por multilíngue custa **zero**; detectar custa **+0,17 s fixo** |
| **2** | **A premissa do briefing estava errada, e para melhor:** não é feature faltando, é bug. `TelaConversa.tsx:86` já chama `turno.limpar()`, que já aborta e já limpa a fila. Hipótese: `remove()` sem `pause()` |
| **5** | Confirmado o buraco: visão diz MVP, backlog dizia Fase 7, `student.py:9` diz Fase 6, e não havia card. Agora há três |
| **1** | Medido: entre vozes `medium` a troca é de graça; `high` custa **6,5x** (RTF 0,177 vs 0,028) e levaria o p50 a ~3,6 s. Amostras geradas para escuta |
| **4** | Diagnóstico confirmado, e **nenhum card criado** — de propósito. Os `start`/`end` entram de graça no `Transcript` (ADR-0056) e ficam sem consumidor; a pergunta *"o que o professor faria com isso?"* segue sem resposta, e a Parte F decide |

**Entregáveis:** ADRs [0055](adr/0055-o-stt-ouve-qualquer-idioma-modelo-multilingue-e-deteccao.md),
[0056](adr/0056-o-transcript-ganha-confianca-e-segmentos.md),
[0057](adr/0057-transcricao-de-baixa-confianca-e-desfecho-esperado.md),
[0058](adr/0058-o-aluno-cancela-o-turn-e-o-servidor-e-avisado.md) e
[0059](adr/0059-o-prompt-do-professor-recebe-contexto-do-aluno.md); cards
**039–047**; a ordem de ataque e o "não fazer" no final de
[`docs/backlog/README.md`](backlog/README.md).

**Quatro decisões de produto foram tomadas nesta sessão** e estão registradas,
cada uma, no ADR que a consumiu — com a alternativa recusada e o motivo.
