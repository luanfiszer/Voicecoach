# CARD-044 — A voz do professor, escolhida por escuta comparada e não de memória

- **ID:** CARD-044
- **Épico:** Qualidade da conversa (briefing 2026-09-09, ponto 1)
- **Esforço:** P
- **Status:** bloqueado (2026-09-13) — ver "Execução" abaixo
- **Dependências:** ADR-0032, ADR-0033

## Contexto

Primeiro apontamento do uso real: *a voz do professor soa robótica*. Inteligível,
mas mecânica.

O briefing manda a ordem certa — **a voz, não o motor** — e avisa da armadilha:
*"naturalidade é subjetiva e some no ruído se avaliada de memória"*. A
investigação de 2026-09-09 já rodou a parte cara disso, e o resultado muda o que
o card precisa fazer.

**Débito de negócio.** O `en_US-lessac-medium` foi escolhido como default
razoável, não como resposta a um critério de qualidade que ninguém tinha
formulado. A implementação está correta — a voz é configuração desde o ADR-0032.

## Problema

A voz atual é `medium`, e ninguém comparou nada. **Medido em 2026-09-09**, três
frases de professor por voz, três execuções, mediana:

| voz | carga | geração/frase | RTF | tamanho |
|---|---|---|---|---|
| `en_US-lessac-medium` (atual) | 0,48 s | **0,099 s** | 0,028 | 63 MB |
| `en_US-amy-medium` | 0,46 s | 0,112 s | 0,024 | 63 MB |
| `en_US-hfc_female-medium` | 0,47 s | 0,101 s | 0,026 | 63 MB |
| `en_US-lessac-high` | 0,54 s | **0,645 s** | 0,177 | 114 MB |
| `en_US-ryan-high` | 0,41 s | 0,605 s | 0,179 | 121 MB |

**As duas conclusões:**

1. **Trocar entre vozes `medium` é de graça.** Diferença dentro do ruído.
2. **`high` custa 6,5x.** E a primeira sentença está no caminho crítico: o p50
   medido no aparelho iria de **3.037 ms para ~3.600 ms** (+18%).

### Segunda rodada (2026-09-10): candidatas femininas, e um achado que muda o card

Primeira escuta: **`ryan-high` agradou**, mas a professora deve ter voz
feminina e menos artificial. Segunda leva medida, com F0 estimado por
autocorrelação para triar as femininas antes de gerar:

| candidata | geração/frase | RTF | F0 |
|---|---|---|---|
| `en_US-ljspeech-high` | 0,744 s | 0,122 | 201 Hz |
| `en_GB-cori-high` (britânica) | 0,739 s | 0,147 | 202 Hz |
| `en_US-libritts-high`, falantes 0/9/12/15/18/21 | 0,70–0,81 s | 0,137–0,154 | 174–232 Hz |

Amostras em `~/Desktop/voicecoach-vozes-femininas/`, com o `ryan-high` junto
para referência.

**O achado que importa mais que a escuta:** `en_US-libritts-high` é
**multi-falante — 904 vozes num único arquivo de modelo** (137 MB), e trocar de
voz nele é passar um `speaker_id: int`, não carregar outro modelo. O catálogo
tem outros (`libritts_r-medium` 904, `en_GB-vctk-medium` 109,
`en_US-l2arctic-medium` 24).

**Isso acopla este card ao CARD-048** (voz escolhida pelo aluno), e o
acoplamento é numa direção só: **escolher aqui uma voz de falante único torna o
CARD-048 caro** (N modelos residentes, contra a premissa do ADR-0025);
**escolher o `libritts-high` o torna quase de graça** (um modelo residente, um
inteiro por aluno). A decisão de hoje compra ou encarece a feature de depois, e
por isso ela está escrita aqui e não descoberta lá.

**O que falta não é medição — é a escuta**, e ela é decisão do desenvolvedor.

## Proposta técnica

1. **Uma rota de geração de amostras**, versionada, que produz as mesmas N
   frases para uma lista de vozes com o tempo ao lado. É o instrumento que o
   briefing pediu, e ele torna a comparação repetível quando aparecer voz nova —
   mesma lógica da rota de medição do ADR-0047: instrumento no repositório,
   não script perdido.
2. **A troca em si é `tts_voice` no `.env`.** Uma linha. Se a escolha for outra
   voz `medium`, o card termina aqui e **não gera ADR** — é escolha local e
   reversível, que o `README.md` dos ADRs manda explicitamente **não** registrar.
3. **Se a escolha for `high`, ADR é obrigatório** — critério 3 (afeta custo,
   aqui em latência) e critério 6 (contraria o alvo de 2,4 s da fase). Ele teria
   de trazer o p50 remedido no aparelho, não a projeção. **Não escrevo esse ADR
   agora**: ele depende de uma escolha que ainda não foi feita.
4. **Sotaque e voz por aluno ficam fora**, e o motivo é de produto, não técnico:
   o briefing já identificou que "quem escolhe? é preferência de conta? muda no
   meio da sessão?" são perguntas em aberto. Voz por aluno também **quebra a
   premissa de modelo residente** (ADR-0025) — o worker mantém uma voz na
   memória, não seis.

## Refinamento obrigatório — cache e limites

**Cache:** a voz fica **residente no worker** (ADR-0025) e é carregada na
subida. TTL: a vida do processo. Invalidação: mudança de `tts_voice`, que exige
reinício — e isso é desejável, não limitação: trocar voz no meio de uma sessão
mudaria o professor de identidade no meio da conversa.

**Endpoint:** a rota de amostras é **ferramenta de desenvolvimento**, e por isso
precisa de decisão explícita: ou fica atrás do mesmo gate da rota de medição do
ADR-0047, ou não existe em produção. Não pode ser endpoint aberto que sintetiza
áudio arbitrário sob demanda — isso é CPU do worker à disposição de qualquer um.

**Dependência externa:** nenhuma em runtime. O Piper **não baixa nada** (é a
propriedade que o fez ganhar do Kokoro no ADR-0032): as vozes são arquivos que
alguém buscou antes, e o adapter falha **na subida** dizendo qual falta.
Baixar voz nova é passo manual documentado.

## Escopo

- **In:** a rota/script de amostras versionado; a escuta comparada com a decisão
  registrada; a troca de `tts_voice` se houver troca; o p50 remedido **se** a
  escolha custar latência; o passo de download documentado.
- **Out:** trocar o **motor** (exigiria ADR substituindo o 0032, com as mesmas
  medições que ele fez — e não há evidência que o justifique). **Voz por aluno é
  o CARD-048** — este card escolhe UMA voz, e apenas registra qual porta ele
  deixa aberta. Sotaques. APIs pagas de TTS (colidem com o ADR-0010). Clonagem
  de voz.

## Critérios de aceite

- **Dado** a lista de vozes candidatas, **quando** a rota é executada, **então**
  ela produz as mesmas frases por voz com o tempo de geração ao lado, num só
  comando.
- **Dado** as amostras, **quando** o desenvolvedor as ouve em sequência,
  **então** a escolha fica **registrada no card com o motivo** — inclusive se o
  motivo for "nenhuma é melhor o bastante para pagar", que é resultado válido.
- **Dado** a voz escolhida, **quando** o worker sobe, **então** o log nomeia a
  voz em uso — a configuração efetiva é visível, como o `apiBaseUrl` do
  CARD-037 ensinou.
- **Dado** uma voz `high` escolhida, **quando** o card fecha, **então** existe
  ADR **e** o p50 remedido no aparelho, não a projeção de +563 ms.
- **Dado** uma voz inexistente em `tts_voice`, **quando** o worker sobe,
  **então** ele falha na subida dizendo qual arquivo falta (comportamento atual,
  e há teste que o preserva).

## Riscos

- **A escuta pode não resolver nada.** É o desfecho mais provável e mais
  incômodo: se nenhuma voz do Piper satisfizer, a conversa vira substituição de
  motor — e aí o ADR-0032 exige as mesmas medições (latência, RTF, tamanho,
  custo) e o ADR-0010 barra API paga. **Esse é assunto de outro card**, e o
  gatilho para abri-lo é este card terminar em "nenhuma serve".
- **Escolher `high` sem remedir.** A projeção de +563 ms é aritmética sobre a
  frase única; o aparelho tem contenção que a bancada não tem.
- **Viés de novidade na escuta.** Ouvir a atual por último a favorece. A rota
  deve embaralhar, ou o desenvolvedor deve ouvir sem saber qual é qual.
- **Escolher voz de falante único sem perceber o custo futuro.** Não é risco de
  implementação, é de decisão: encarece o CARD-048 depois, quando já for tarde
  para trocar a identidade do professor sem estranhar o aluno.

## Objetivo de aprendizado

Entender **RTF (real-time factor) como unidade de orçamento**, e por que ele é o
número certo aqui e a latência absoluta não: RTF 0,028 contra 0,177 diz que a
voz `high` consome 18% do tempo que ela produz, contra 3% — e é isso, não os
0,645 s da frase medida, que prevê o comportamento em sentenças de qualquer
tamanho. É a diferença entre medir um caso e medir uma taxa.

## Execução (2026-09-13, loop autônomo) — BLOQUEADO, escuta humana

**Não implementado.** O próprio card é explícito sobre o que falta: *"o que
falta não é medição — é a escuta, e ela é decisão do desenvolvedor"*. Preferência
de naturalidade de voz é o exemplo textual de "preferência subjetiva de UX" que
`docs/prompt-loop-autonomo-backlog.md` lista como o tipo de decisão que o loop
autônomo **não** deve tomar por adivinhação — não há como eu ouvir áudio e
julgar qual voz soa menos robótica.

**O instrumento do proposta técnica item 1 já existe** —
`backend/benchmarks/tts_audicao.py` — e é o MESMO script que decidiu Kokoro vs.
Piper no ADR-0032 (`docs/medicao-latencia.md:477-479`): roda contra o adapter de
produção, toca cada voz de `voices/` em sequência e deixa os WAVs em `/tmp` para
comparação lado a lado. Ele já cobre a maior parte do que este card pediria
construir; não recriei um segundo script equivalente.

**O que verifiquei, sem decidir nada de subjetivo:**

- Hoje só `en_US-lessac-medium` (atual) e `en_US-amy-medium` estão baixadas em
  `backend/voices/` — as candidatas `high` e femininas da segunda rodada
  (`hfc_female`, `ljspeech`, `cori`, `libritts`) medidas em 2026-09-09/10 não
  estão no repositório nem em `backend/voices/`, só as amostras de áudio
  citadas em `~/Desktop/voicecoach-vozes-femininas/` (máquina do
  desenvolvedor, fora deste ambiente).
- `tts_voice = "en_US-lessac-medium"` continua o default em `config.py:366` —
  nenhuma troca foi feita, porque nenhuma escolha foi feita.

**Risco do próprio card que fica registrado, não resolvido:** o script atual
toca as vozes em ordem alfabética fixa (`sorted(...)`), sem embaralhar — o
risco de "viés de novidade" que a seção Riscos deste card nomeia continua
presente. Não mudei isso especulativamente: não sei se o desenvolvedor prefere
embaralhar, ouvir contrabalanceado, ou já tem outro hábito de escuta às cegas
— é pergunta do ponto de decisão, não algo para decidir sem ele.

**Seguindo para o próximo card da fila (CARD-043) sem tocar mais neste.**
