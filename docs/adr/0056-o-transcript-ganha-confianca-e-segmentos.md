# ADR-0056 — O `Transcript` ganha confiança e segmentos: o que o STT já produz para de ser jogado fora

- **Status:** aceito
- **Data:** 2026-09-09
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **2 — define ou altera
  uma fronteira.** `Transcript` é o contrato de saída da porta de STT; mudá-lo
  muda o que `application` pode saber sobre a fala do aluno, e obriga os dois
  adapters e todos os fakes de teste.

## Contexto

O `Transcript` de hoje tem três campos: `text`, `language`, `duration_seconds`.
Cada um deles nasceu por necessidade concreta e documentada — o
`duration_seconds`, por exemplo, existe porque a cota é em minutos e esta é a
única etapa que conhece a duração real.

O que a investigação de 2026-09-09 mostrou é que **o Whisper já devolve muito
mais, e o adapter descarta tudo na saída**. Executado sobre
`benchmarks/inputs/curto.wav`, o que a biblioteca entrega por segmento:

```
{'start': 0.0,  'end': 2.36,  'avg_logprob': -0.205, 'no_speech_prob': 0.002, 'compression_ratio': 1.46}  ' Wow, that sounds like an amazing project.'
{'start': 2.62, 'end': 4.2,   …}   ' My day has been great too.'
{'start': 4.38, 'end': 5.32,  …}   ' Thanks for asking.'
{'start': 5.78, 'end': 11.34, …}   ' So you created a WhatsApp chatbot that helps you…'
```

Isso custa **zero**: já foi calculado, já está na memória, e a linha
`Transcript(text=…, language=…, duration_seconds=…)` o deixa cair no chão.

Dois dos cinco apontamentos do briefing dependem exatamente destes campos:

- **o ponto 3** ("não deduzir") precisa de uma medida de confiança. O
  `avg_logprob` separa os dois mundos com folga: **−1,12 a −5,94** nas
  alucinações medidas, **−0,13 a −0,32** nas transcrições corretas;
- **o ponto 4** ("o professor não percebe entonação") tem, no item 2 do
  briefing, o caminho barato: *"usar os segmentos que o Whisper já devolve — ele
  dá tempos por segmento, e daí saem pausa e ritmo de graça"*. Os `start`/`end`
  acima **são** esse dado.

Portanto: **a porta é o gargalo comum de dois dos cinco pontos.** Alargá-la uma
vez é mais barato — e mais honesto com o ADR-0036, que já ensinou que é o
primeiro consumidor quem revela o que faltava na porta.

## Decisão

**O `Transcript` passa a carregar a confiança da transcrição e os limites de
tempo dos segmentos**, além dos três campos atuais:

```python
@dataclass(frozen=True, slots=True)
class Segment:
    start_seconds: float
    end_seconds: float
    text: str

@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    language: str
    duration_seconds: float
    confidence: float          # média de `avg_logprob`, ponderada por duração
    no_speech: float           # maior `no_speech_prob` entre os segmentos
    segments: tuple[Segment, ...]
```

Quatro regras que a decisão carrega:

1. **Nenhum tipo de biblioteca atravessa.** `Segment` é um value object do
   projeto, não o segmento do `faster-whisper` nem o `dict` do `mlx-whisper`. É
   a mesma regra do ADR-0029, aplicada agora à saída: o contrato do
   import-linter continua proibindo `numpy` em `application`, e passa a valer o
   mesmo para qualquer forma de segmento vinda dos motores.
2. **`confidence` é normalizado pelos adapters, não pelo caso de uso.** Os dois
   motores expõem `avg_logprob` por segmento; a média ponderada por duração é
   feita no adapter, porque é ele quem conhece o formato. `application` recebe
   um número e não sabe de onde veio — que é o ponto da porta.
3. **`segments` entra vazio quando o motor não os der.** Um fake de teste que
   devolva `segments=()` continua satisfazendo a porta, e nenhum consumidor pode
   presumir que a tupla tem elementos.
4. **A escala do `confidence` é log-probabilidade, e isso é declarado.** Não é
   0–1, não é porcentagem, e o número é sempre negativo. Convertê-lo para
   "0 a 100%" seria inventar uma calibração que não existe — o limiar do
   ADR-0057 opera na escala crua, com o número medido junto.

## Alternativas consideradas

### Alternativa A — devolver o `dict` bruto do motor num campo `raw`

Um `raw: Mapping[str, object]` carregaria tudo sem decidir nada agora.
Rejeitada: é o tipo de biblioteca atravessando a porta com disfarce. Quem
consumisse teria de conhecer o formato do `mlx-whisper` **ou** o do
`faster-whisper`, e os dois diferem — a porta deixaria de esconder qual motor
está rodando, que é exatamente o que ela existe para fazer (ADR-0027).

### Alternativa B — uma porta separada, `ProsodyAnalyzer`

Deixar `Transcript` como está e criar uma segunda porta para as características
acústicas. Rejeitada por custo desproporcional: seria uma porta nova, um adapter
novo e uma segunda decodificação do mesmo áudio para extrair dado que a primeira
passagem **já calculou**. O gatilho para ela existir é o item 1 do ponto 4 do
briefing (pitch, energia, taxa de fala) — que exige biblioteca nova e ainda não
tem pergunta de produto respondida. Enquanto o dado for subproduto do Whisper,
ele pertence ao `Transcript`.

### Alternativa C — só `confidence`, sem `segments`

Atender ao ponto 3 e adiar o ponto 4. Rejeitada porque o custo marginal dos
segmentos é literalmente uma compreensão de tupla no adapter, e a alternativa
obrigaria a mexer na mesma porta duas vezes — com dois ADRs, duas migrações dos
fakes e duas passagens pelos gates. **Os segmentos entram agora e ficam sem
consumidor de propósito**; o ponto 4 continua sem card (ver o "não fazer" da
investigação), e é a Parte F da visão que decide quando ele ganha um.

## Consequências

- **Positivas:** o desfecho "não entendi" (ADR-0057) passa a ser possível sem
  tocar em adapter de novo. Pausa e ritmo ficam disponíveis no dia em que
  houver pergunta pedagógica que os use, sem trabalho adicional de infra. O
  `no_speech` dá, de graça, a detecção de "gravou silêncio" — que hoje vira uma
  resposta do professor a nada.
- **Negativas:** **toda implementação da porta muda**, incluindo os fakes dos
  testes de `application` — é o preço recorrente de tipagem estrutural sem
  classe base. Três campos novos que hoje **ninguém consome** (`segments`
  inteiro) contrariam o instinto YAGNI; a defesa é que o custo de produzi-los é
  zero e o de voltar ao adapter é uma sessão. `confidence` numa escala pouco
  intuitiva vai exigir cuidado em toda leitura futura — o comentário na porta
  precisa dizê-lo, não o commit.
- **Equivalente mental .NET:** é alargar um `record` de retorno que atravessa
  uma interface de infraestrutura — com a diferença de que aqui não há
  implementação padrão nem `virtual` para amortecer: `Protocol` é estrutural, e
  quem não tiver o campo simplesmente deixa de satisfazer o tipo, com o `mypy`
  acusando em todos os pontos de uma vez.
