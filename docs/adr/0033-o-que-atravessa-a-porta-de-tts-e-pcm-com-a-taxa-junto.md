# ADR-0033 — O que atravessa a porta de TTS é PCM cru com a taxa junto

- **Status:** aceito
- **Data:** 2026-08-23
- **Complementa:** [ADR-0029](0029-o-que-atravessa-a-porta-de-stt-sao-bytes-codificados.md)
  (o análogo na porta de STT, e a regra "nenhum tipo de biblioteca atravessa uma
  porta"), [ADR-0024](0024-midia-por-trecho-chave-url-assinada-e-retencao-assimetrica.md)
  (que exige o `reply/full` concatenado), ADR-0023, ADR-0012
- **Critérios de obrigatoriedade:** **2 — define uma fronteira** (o tipo que
  atravessa a porta `TextToSpeech`, e de que lado dela mora a compressão).

## Contexto

O CARD-008 propunha `synthesize(text) -> AudioData` e, três linhas abaixo, que a
concatenação do áudio inteiro seria *"barata e sem recodificação, porque o TTS
local devolve PCM"*. As duas frases não podem ser verdade ao mesmo tempo, e a
contradição é a decisão deste ADR:

- se `AudioData` carregasse `ndarray`, quebraria o ADR-0029 e o contrato do
  import-linter, que proíbe `numpy` em `application` **exatamente porque**
  `NDArray[np.float32]` é o tipo natural para áudio e passaria numa revisão;
- se carregasse áudio já comprimido, concatenar exigiria decodificar tudo de
  volta e comprimir de novo — e o "barato e sem recodificação" evaporaria.

Há ainda um fato que decide sozinho parte do desenho: **Kokoro sintetiza a
24.000 Hz e as vozes do Piper a 22.050 Hz**. A taxa de amostragem é propriedade
do *modelo*, não da porta.

## Decisão

**A porta `TextToSpeech` devolve `SynthesizedAudio(pcm: bytes, sample_rate:
int)` — PCM16 mono cru — e é chamada uma vez por sentença. Comprimir é
responsabilidade de quem grava.**

1. **`pcm` é `bytes`.** Não é tipo de biblioteca, concatena com `b"".join(...)`
   e é o que os dois motores já produzem nativamente (`audio_int16_bytes` no
   Piper). Nenhuma conversão de formato acontece nesta fronteira.
2. **`sample_rate` viaja junto, e não é metadado opcional.** PCM é uma lista de
   medidas sem cabeçalho: sem a taxa, nada nela diz a que velocidade tocar. É o
   `Encoding` de um `byte[]` de texto.
3. **`duration_seconds` é uma `@property` derivada**, nunca um campo. Guardada,
   ela sobreviveria a uma concatenação que muda o `pcm` — e o cliente agendaria
   o playback com o tempo do trecho antigo. É a mesma regra que mantém a etapa
   do `Turn` fora do banco (ADR-0023/0028).
4. **Juntar taxas diferentes levanta `SampleRateMismatchError`.** Este é o único
   modo de falha desta fronteira que **nenhum tipo pega**: o arquivo resultante é
   perfeitamente válido e toca com a velocidade errada em metade da resposta. O
   erro é audível para o aluno e invisível para o código; por isso vira exceção
   explícita.
5. **A compressão mora em `adapters/tts/encoding.py`**, sobre o **PyAV que já
   está no projeto** (veio com o `faster-whisper`, ADR-0029), em **AAC 64 kbps**
   — o mesmo formato que o app grava, tocável nativamente nos dois SOs.
6. **`concat` mora em `application`**, junto da porta: é aritmética sobre
   `bytes`, sem IO e sem biblioteca.

## Alternativas consideradas

### Alternativa A — A porta devolve áudio já comprimido (AAC/MP3)

- **O que é:** simetria total com a porta de STT — bytes entram, bytes saem — e
  o `sample_rate` escondido dentro do arquivo, que é auto-descritivo.
- **Por que foi rejeitada:** o `reply/full` do ADR-0024 deixa de ser barato.
  Juntar N trechos comprimidos exige decodificar todos, concatenar e comprimir
  outra vez: CPU no worker, no mesmo processo que precisa estar sintetizando a
  próxima frase, e uma **segunda passagem de perda** sobre conteúdo que já
  perdeu uma vez. A simetria com o STT é aparente: lá o produtor dos bytes é o
  celular do aluno, e o formato já vem dado; aqui o produtor é nosso, e escolher
  o formato cedo demais é que seria acoplamento.

### Alternativa B — A porta devolve `ndarray`

- **O que é:** o tipo que Kokoro e Piper realmente produzem por dentro.
- **Por que foi rejeitada:** `numpy` viraria dependência de `application`, contra
  o ADR-0012 e o ADR-0029. É o vazamento mais fácil de cometer sem querer nesta
  fronteira, e o contrato do import-linter já o vigia desde o CARD-006 —
  demonstrado: com `numpy` na lista, o import em `application` fica `BROKEN`.

### Alternativa C — Um objeto com PCM **e** o formato comprimido juntos

- **O que é:** o adapter devolveria os dois, e cada consumidor pegaria o que
  precisa.
- **Por que foi rejeitada:** paga a compressão de todo trecho **sempre**,
  inclusive quando o consumidor só quer concatenar, e dobra a memória por trecho.
  Pior: cria duas representações do mesmo áudio que podem divergir — a mesma
  classe de erro que o "não persistir o que se deriva" evita.

## Consequências

**Positivas**

- O `reply/full` é literalmente `b"".join(...)`: sem CPU de recodificação e sem
  perda adicional. Verificado ponta a ponta — 3 sentenças, 4,16 s de PCM
  concatenado, 179 KB → **33 KB** em AAC, e o arquivo decodifica de volta.
- A porta continua **pobre e estável**: texto entra, amostras saem. O V2
  (streaming intra-frase, ADR-0003) acrescenta método por extensão.
- Trocar de motor não mexe na porta: o Piper entrega 22.050 Hz e o Kokoro
  24.000 Hz, e a única coisa que muda é o número que viaja no campo.
- A compressão ficou **num lugar só**, testável sem motor de voz.

**Negativas — o preço aceito**

- **PCM ocupa memória.** 17 s de resposta são ~816 KB por turn vivos até o
  `full` ser gravado, contra ~136 KB em AAC. Irrelevante para uso pessoal, real
  com dezenas de turns simultâneos. **Gatilho:** mais de ~20 turns concorrentes
  por processo, ou respostas acima de 2 minutos.
- **A taxa de amostragem passa a ser responsabilidade de quem compõe.** O
  `SampleRateMismatchError` cobre o caso de juntar; ele não cobre alguém gravar
  um trecho a 22.050 Hz e outro a 24.000 Hz no mesmo turn sem concatenar —
  cenário que só existe com dois adapters ativos, hoje impossível.
- **O AAC acrescenta ~70 ms de *priming*** no início do fluxo (medido num áudio
  de 4,16 s). Está dentro da tolerância de ±100 ms do critério de aceite, é
  inaudível, e o teste verifica que a diferença **não cresce** com o tamanho — o
  que indicaria perda de quadros no fim (o `encode(None)` esquecido).
- **`bytes` não diz nada sobre si.** Um `bytes` de PCM e um `bytes` de AAC têm o
  mesmo tipo, e trocá-los numa chamada não é erro de compilação. A defesa é a
  validação no `__post_init__` (buffer ímpar não é PCM16) e o nome do campo.

**Equivalente mental .NET:** devolver `ReadOnlyMemory<byte>` + `SampleRate` em
vez de um `AudioFileStream` já codificado — o mesmo raciocínio de manter o dado
no formato mais barato de compor e adiar a serialização para a borda.
