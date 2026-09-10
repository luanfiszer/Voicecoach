# ADR-0060 — O backend sai do Mac para um VPS Linux, e a latência paga a conta

- **Status:** aceito
- **Data:** 2026-09-10
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **3 — afeta custo
  recorrente** (o primeiro gasto de infra do projeto) e **5 — seria difícil de
  reverter** (um app publicado grava o endereço do servidor no binário).
- **Ajusta:** ADR-0010 (a parte de infra), Parte E da visão
- **Substitui, na prática:** a escolha do CARD-038

## Contexto

A V1.0 vai para a App Store pública e vai cobrar (decisões de 2026-09-10). Um
app de loja não pode depender do laptop do desenvolvedor estar aberto — e é
exatamente aí que o backend roda hoje.

Isso não é descuido: foi **escolha deliberada de ontem**. O CARD-038 preferiu um
túnel a um deploy com o argumento de que *"mantém o MLX e a latência medida (o
servidor Linux cairia para `faster_whisper`)"*. O argumento estava certo. O que
mudou foi o alvo, não o argumento.

**A conta que a decisão custa, medida em 2026-09-10** (`faster-whisper`,
`float32`, `beam_size=1`, CPU **deste Mac** — que é rápido):

| insumo | `mlx` (hoje, GPU Apple) | `faster-whisper` CPU, língua fixa | `faster-whisper` CPU, **com detecção** |
|---|---|---|---|
| 2,3 s de áudio | **0,25 s** | 0,66 s | **0,97 s** |
| 19,1 s de áudio | **0,60 s** | 1,36 s | **1,79 s** |

A coluna da direita é a que vale, porque o CARD-039 liga a detecção de idioma.
**Sair do Apple Silicon custa ~+0,5 s no melhor caso.** E o melhor caso não é o
caso: a medição rodou num núcleo M4 ocioso, enquanto num VPS típico o STT
disputa dois núcleos com o TTS, a API, o Postgres e o Redis. **A estimativa
honesta é +1 a +1,5 s**, e ela é estimativa — o número real só existe depois do
CARD-055.

O p50 medido no aparelho é **3.037 ms** (CARD-037). O alvo da fase era 2.400 ms
e já não era atingido. Depois desta decisão, **o alvo de 2,4 s está morto para a
V1.0**, e fingir o contrário seria a única coisa pior que perdê-lo.

## Decisão

**O backend passa a rodar num VPS Linux barato (US$ 5–20/mês), e o `mlx-whisper`
deixa de existir em produção.**

1. **O ADR-0027 não é contrariado — ele é exercido.** Ele decidiu adapter duplo
   com *"default resolvido pela plataforma"*, e em Linux a plataforma resolve
   para `faster-whisper`. O desenho previa este dia; o que ele não previa era o
   custo em latência ser cobrado do produto e não do desenvolvedor.
2. **O `mlx` continua sendo o default de desenvolvimento** no Mac. Isso cria uma
   assimetria nova e perigosa — dev mais rápido que produção — e ela precisa ser
   **visível**, não descoberta: o log de subida já nomeia o provider, e o CARD-055
   passa a exigir a medição no servidor real, não no laptop.
3. **A infra deixa de ser gratuita**, o que ajusta o ADR-0010. Ele continua
   valendo no que importa (teto mensal, kill switch, gasto de IA sob controle),
   mas a frase *"infra a dinheiro zero"* deixa de ser verdade. **O sucessor
   completo do ADR-0010 não é este ADR** — ele depende da decisão de canal de
   cobrança, que segue em aberto (CARD-021), e continua listado como pendente.
4. **O alvo de latência da V1.0 é redefinido honestamente:** *o aluno começa a
   ouvir a resposta em menos de 4,5 s no p50, medido no aparelho contra o
   servidor de produção*. É pior que o de hoje, e é o número que a decisão
   comprou. Ele volta a apertar por três caminhos já conhecidos e nenhum deles
   entra agora: o CARD-019 (STT/TTS no aparelho), um servidor com GPU, ou a
   alavanca §11 da análise de custo.
5. **Um servidor implica coisas que este projeto nunca teve:** nome de domínio,
   TLS, segredos fora do `.env` de desenvolvimento, migrations aplicadas por
   alguém que não é você no terminal, e backup de um Postgres que passa a conter
   dado de gente de verdade. É o CARD-055 e o CARD-056.

## Alternativas consideradas

### Alternativa A — o Mac como servidor

Manter o `mlx` e o p50 de ~3,2 s por custo marginal ~zero. **Foi a escolha de
ontem** (CARD-038) e continuaria sendo defensável para um beta fechado.

Rejeitada pela disponibilidade, não pela latência: um app na App Store
dependendo de energia elétrica residencial, internet doméstica e de um IP que o
DHCP troca — **o que aconteceu ao vivo durante o CARD-037** — não é um produto,
é uma demonstração. E o modo de falha é o pior possível: o app fica fora do ar
para quem pagou, sem que ninguém perceba.

### Alternativa B — VPS com GPU

Manteria a velocidade sem depender de casa. Rejeitada por custo: US$ 100+/mês
contra US$ 5–20, com um punhado de usuários. A `analise-custo-e-precificacao.md`
projeta margem por usuário na casa de poucos reais — uma conta dessas a consome
inteira e transforma cada assinante novo em prejuízo menor, não em lucro.
**Gatilho para reabrir:** volume que dilua o custo fixo, ou latência provando ser
o motivo de cancelamento.

### Alternativa C — STT e TTS no aparelho

A alavanca do §11 da análise de custo, cujo gatilho escrito é *"existirem
usuários pagantes reais"* — e este lançamento o dispara. Zeraria o compute de
servidor **e** a latência de rede do áudio, dando o melhor dos dois mundos.

Rejeitada **por ora, e não por mérito**: contraria o ADR-0011 de frente, exige o
CARD-019 (spike) virando projeto, e reescreve o pipeline no momento em que o
objetivo é publicar. Fica registrada como **a melhoria de maior alavancagem do
produto** — ela ataca custo e latência ao mesmo tempo, que é raro.

## Consequências

- **Positivas:** o produto existe independentemente do seu Mac. Deploy,
  segredos, TLS e backup entram no repertório — e são conteúdo de entrevista que
  o projeto ainda não tinha. O `faster-whisper`, que era o caminho só do CI,
  passa a ser o caminho **real**, e para de ser código exercitado por educação.
- **Negativas:** **+0,5 a +1,5 s no p50**, num produto de conversa onde a
  latência é a experiência. O primeiro gasto recorrente de infra. Uma
  assimetria dev/produção que vai esconder regressões (o que é rápido no seu Mac
  pode não ser no servidor) e que só a medição no servidor real desfaz. E o
  `mlx`, que o ADR-0027 mediu e o CARD-038 protegeu, vira **código que só roda
  na máquina do desenvolvedor** — com o risco de apodrecer sem ninguém notar.
- **Equivalente mental .NET:** é a primeira vez que este projeto sai do
  `F5 local` para um ambiente que alguém precisa operar. A diferença que morde
  não é o Docker — é que a partir daqui existe um estado de produção que não
  pode ser recriado apagando uma pasta.
