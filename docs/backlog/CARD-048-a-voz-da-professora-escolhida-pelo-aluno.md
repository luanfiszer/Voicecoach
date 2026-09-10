# CARD-048 — A voz da professora, escolhida pelo aluno *(catalogado, não bloqueia o V1)*

- **ID:** CARD-048
- **Épico:** Qualidade da conversa (briefing 2026-09-09, ponto 1 — item 3)
- **Esforço:** M *(estimativa que depende inteiramente do CARD-044 — ver Contexto)*
- **Status:** backlog — **catalogado para depois do MVP**, por decisão do
  desenvolvedor em 2026-09-10: *"estou focado em publicar um bom MVP, e existem
  coisas que não impedem a V1 — essa é uma delas"*
- **Dependências:** CARD-044 (**e o resultado dele muda o tamanho deste card**)

## Contexto

Na escuta comparada do CARD-044, o desenvolvedor gostou do `ryan-high` mas quer
uma professora **feminina e menos artificial** — e perguntou quanto custaria
deixar o **aluno** escolher a voz.

A resposta honesta é: **depende de uma decisão que o CARD-044 vai tomar antes**,
e é por isso que este card existe agora em vez de depois. Medido em 2026-09-10:

| Se o CARD-044 escolher… | então este card é… |
|---|---|
| uma voz de **falante único** (`ljspeech-high`, `cori-high`, `lessac-high`, `ryan-high`) | **caro** — cada voz é um `.onnx` de 63–137 MB, e o worker mantém os modelos **residentes** (ADR-0025). Seis vozes = seis modelos na memória, ou carga de ~0,5 s no meio do turno |
| `en_US-libritts-high` (**904 falantes num arquivo só**, 137 MB) | **quase de graça no motor** — trocar de voz é passar `speaker_id: int` para o `synthesize`. Um modelo residente, uma coluna a mais no aluno |

Ou seja: **a decisão do CARD-044 compra ou encarece esta feature**, e ela vai
ser tomada por qualidade de som, que é o critério certo. Este card só garante
que o custo do outro lado esteja escrito quando a escolha for feita.

O catálogo do Piper tem outros multi-falantes se `libritts-high` não agradar:
`en_US-libritts_r-medium` (904), `en_GB-vctk-medium` (109, britânicas),
`en_US-l2arctic-medium` (24), `en_GB-aru-medium` (12).

## Problema

A voz é global e fixa em `tts_voice`. Não há como o aluno escolher, nem como
ouvir antes de escolher — e "voz da professora" é das poucas preferências que um
produto de conversa por áudio tem de tratar como identidade, não como
configuração escondida.

## Proposta técnica

**Nada implementado; o desenho está esboçado para a sessão que pegar o card.**

1. **Um catálogo curado, não os 904.** O produto oferece **de 4 a 6 vozes
   escolhidas por escuta**, com nome de pessoa — não "speaker 217". Expor o
   catálogo inteiro é despejar uma decisão de curadoria no aluno.
2. `Student` ganha a voz escolhida; `None` significa a voz padrão. Mesma regra
   do CARD-045: **ausência é o caso normal**, sem default inventado.
3. A voz atravessa até o adapter de TTS como parâmetro da síntese. **A porta do
   ADR-0033 não muda** — o que trafega continua sendo PCM com a taxa junto; o
   que muda é quem escolhe o timbre antes.
4. **A prévia é o problema de verdade**, e não o armazenamento. Sintetizar sob
   demanda para o aluno ouvir é **CPU do worker à disposição de quem apertar o
   botão** — e o worker é o mesmo que atende os turns. A saída provável é
   **amostras pré-geradas e servidas como mídia estática**, não síntese ao vivo.
5. Trocar de voz **no meio de uma sessão** é decisão de produto em aberto. O
   professor mudar de identidade entre dois turns da mesma conversa é estranho;
   o mais provável é aplicar na sessão seguinte.

## Refinamento obrigatório — cache e limites

**Cache:** o modelo residente (ADR-0025). Com multi-falante, **um** modelo
serve todas as vozes — que é o argumento inteiro deste card. Com falante único,
seria preciso decidir um teto de modelos residentes e uma política de despejo,
e aí o cache passa a ter TTL (vida do processo) e invalidação (troca de
configuração) que hoje são triviais e deixariam de ser.

**Endpoint:** listar o catálogo (leitura, barata) e gravar a escolha junto do
perfil do CARD-045. **A prévia não é endpoint de síntese** — ver item 4. Teto:
o do perfil.

**Dependência externa:** nenhuma em runtime — o Piper não baixa nada (ADR-0032).
Baixar o modelo multi-falante é passo de provisionamento, e o adapter já falha
na subida dizendo qual arquivo falta.

## Escopo

- **In (quando entrar):** o catálogo curado; a voz no `Student`; a voz chegando
  ao TTS; as amostras pré-geradas; a tela de escolha.
- **Out:** sotaques como feature separada — com multi-falante, "sotaque" é só
  outra entrada do catálogo (`en_GB-vctk` para britânicas), e não merece
  mecanismo próprio. Clonagem de voz. Outros idiomas. Voz mudando no meio da
  sessão, até haver decisão.

## Critérios de aceite

- **Dado** um aluno sem voz escolhida, **quando** um turn é sintetizado,
  **então** usa a voz padrão — sem regressão para quem não escolheu.
- **Dado** um aluno com voz escolhida, **quando** um turn é sintetizado,
  **então** sai naquela voz, **e o worker não carrega modelo nenhum durante o
  turno** — verificado pelo tempo de síntese, que não pode ter o degrau de
  ~0,5 s da carga.
- **Dado** a tela de escolha, **quando** o aluno ouve uma prévia, **então** o
  áudio vem de mídia pré-gerada, e nenhuma síntese é disparada pelo toque.
- **Dado** o catálogo, **quando** lido, **então** tem nomes de pessoa, não ids.

## Riscos

- **O risco real é de ordem, não de implementação:** o CARD-044 escolher uma voz
  de falante único e este card nascer caro. Mitigação: está escrito nos dois.
- **Curadoria de 904 vozes é trabalho de escuta**, não de código, e é o que de
  fato consome a sessão. Triar por F0 (como feito em 2026-09-10) reduz o
  conjunto, mas não decide qual soa como professora.
- **`high` custa 6,5x** independente de quem fale (RTF 0,12–0,15 medido em todas
  as candidatas). Este card **não** muda esse trade-off — ele é do CARD-044.

## Objetivo de aprendizado

Entender por que **um modelo multi-falante é uma decisão de arquitetura
disfarçada de escolha de asset**: o `speaker_id` transforma "carregar outro
modelo" em "passar um inteiro", e isso muda o que cabe no worker residente do
ADR-0025. Em .NET o paralelo mais próximo é escolher entre N instâncias de um
serviço caro e uma instância parametrizada — com a diferença de que aqui o custo
não é objeto, é **memória de processo em ONNX Runtime**, e o gargalo aparece na
readiness, não no GC.
