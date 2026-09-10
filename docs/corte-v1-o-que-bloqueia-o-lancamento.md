# Corte da V1.0 — o que bloqueia o lançamento e o que não

- **Data:** 2026-09-10
- **Origem:** pedido do desenvolvedor de separar o backlog em "impeditivo para a
  V1.0" e "pode esperar", para publicar o MVP o quanto antes.

## Premissas de escopo — confirmadas nesta sessão

Elas mudam a lista inteira, e por isso foram perguntadas antes (LEARNING-0002):

1. **Distribuição: App Store pública.** Qualquer pessoa baixa. Não é dev build,
   não é TestFlight.
2. **A V1.0 cobra**, desde o lançamento.
3. Não confirmado, e **assumido**: **iOS primeiro, Android depois.** "App Store"
   é da Apple; o Google Play tem exigências próprias (e US$ 25 únicos, contra
   US$ 99/ano). Se Android for junto, este corte cresce — diga, e eu remarco.
4. Não confirmado, e **assumido**: o núcleo pedagógico continua no servidor
   (ADR-0011). A alavanca de rodar STT/TTS no aparelho tem gatilho escrito
   (`analise-custo-e-precificacao.md` §11) que é *"existirem usuários pagantes
   reais"* — e este alvo o dispara. **Não estou puxando esse gatilho aqui**; ele
   é decisão sua, e mudaria a economia inteira do produto.

## O que este alvo contradiz no repositório

Três decisões aceitas **passam a ser falsas**. Nenhuma é impedimento — mas
nenhuma pode ser contornada em silêncio: ADR aceito não se edita, se substitui.

| Decisão hoje | O que o alvo exige | Como resolver |
|---|---|---|
| **ADR-0010** — infra a dinheiro zero, gasto restrito à IA | Servidor sempre no ar, conta Apple US$ 99/ano, e-mail transacional | ADR novo, o **sucessor do 0010 sob receita** — já listado como pendente em `adr/README.md` |
| **Visão, Parte E** — "build local; loja adiada", com gatilho *"produto com usuários reais além do autor"* | O gatilho disparou | Atualizar a Parte E, com a data e o motivo |
| **CARD-038** — túnel escolhido **no lugar de deploy** em 2026-09-09 | O túnel não sustenta app de loja | O 038 é **substituído** pelo card de deploy. O `INVITE_CODE` dele morre junto: app público não é por convite |

E um quarto, que não é contradição mas cobrança: o **ADR pendente de canal de
cobrança** (`adr/README.md`, "ADRs pendentes de decisão de produto") deixa de ser
uma escolha. Ver a seção seguinte.

## O que a App Store impõe, e que o backlog não tem

**Esta é a parte que mais surpreende, e é o motivo de este documento existir:
sete trabalhos bloqueantes não tinham card nenhum.**

> **Atualização de 2026-09-10:** os cinco que não dependiam de decisão viraram
> card — **N3 → CARD-049 + CARD-050** (auth era **G**, e o template manda quebrar),
> **N4 → CARD-051**, **N5 → CARD-052**, **N6 → CARD-053**, **N7 → CARD-054**.
> **Atualização 2 (2026-09-10, mesmo dia):** os dois últimos fecharam.
> **N1 → ADR-0060 + CARD-055 + CARD-056** (decidido: VPS Linux barato).
> **N2 → não virou card novo**: ele já era o **CARD-021**, que foi atualizado —
> a pesquisa virou o primeiro entregável dele, por decisão de decidir o canal
> depois de pesquisar. **Nenhum dos sete segue sem dono.**

| # | O que é | Por que é bloqueante | Esforço |
|---|---|---|---|
| **N1** | **Deploy do backend** — servidor sempre no ar | ✅ **Decidido em 2026-09-10: VPS Linux barato** (ADR-0060, cards 055 e 056). O custo foi remedido com a configuração que o CARD-039 vai deixar (multilíngue + detecção): o STT sai de **0,25 s** no `mlx` para **0,97 s** no `faster-whisper` em CPU — e isso num núcleo M4 ocioso, não num VPS. **O alvo de 2,4 s morreu**; o novo é p50 < 4,5 s, e o número real sai do CARD-055 | **G** + ADR |
| **N2** | **Canal de cobrança** — ~~e isso não é escolha~~ | ⚠️ **Corrigido em 2026-09-10:** a afirmação original desta linha estava errada. A regra exige IAP para a compra feita **dentro** do app — mas **vender só na web continua permitido** (o app apenas *consome* a assinatura). O que não se pode é divulgar a compra externa dentro do app, o que é problema de **conversão**, não de legalidade. **A escolha continua real e continua valendo os 11–26 pontos de margem.** Ver o CARD-021, atualizado | **G** |
| **N3** | **Contas e auth de verdade** | Hoje é a linha "a detalhar" do backlog. Cobrar exige saber quem é quem. O ADR-0007 já desenhou; faltam os cards | **G** — quebrar |
| **N4** | **Delete de conta dentro do app** | Guideline 5.1.1(v): app que cria conta **tem de** oferecer exclusão no próprio app. É motivo de rejeição direta. Toca retenção de áudio (CARD-017) e LGPD | **M** |
| **N5** | **Política de privacidade, termos e App Privacy labels** | A visão já dizia *"não adia"* (Parte E) porque processamos voz. App Store Connect exige URL de política, os rótulos de privacidade preenchidos e uma URL de suporte | **M** — e parte não é engenharia |
| **N6** | **Conta Apple Developer e o caminho até a revisão** | US$ 99/ano, build de release (não dev build), ícones, screenshots, App Store Connect, dados bancários e fiscais, e **a revisão em si** — que reprova e devolve. Absorver o prazo no plano, como a Parte E já mandava | **M** + calendário |
| **N7** | **Proteção de custo contra conta criada por qualquer um** | Hoje a defesa é allowlist/convite. Público + pagante muda a superfície: rate limit por IP no cadastro, e-mail verificado, e o kill switch valendo de verdade. Parte disso é o CARD-015; a parte de cadastro não tem card | **M** |

## Os cards existentes, classificados

### Bloqueantes — sem eles não há V1.0 na loja

| Card | Por quê |
|---|---|
| **024** Dockerfile do worker | Pré-requisito do N1. Sem imagem, não há deploy |
| **042** Regravar cala o professor | **P, e é o mais barato da lista.** App pago em que o professor fala por cima do aluno é reprovação de review e nota 1 |
| **039** STT ouve qualquer idioma | O público é brasileiro aprendendo inglês: ele **vai** falar português. Hoje o produto alucina — é o defeito mais visível que existe |
| **040** "Não entendi, pode repetir?" | Responder ao que não foi dito é o sintoma que sobra depois do 039. E é a única mudança do lote que **reduz** custo, o que importa quando o custo é seu |
| **015** Quotas + kill switch | Já marcado "bloqueante comercial". Público + pagante sem teto é conta aberta |
| **033** Saldo de cota e estado do serviço | O aluno tem de **ver** a cota que o 015 impõe. P |
| **017** Retenção de áudio: lifecycle e delete | LGPD e pré-requisito do N4. Voz é dado pessoal |
| **027** Telas de exceção: offline, quota, pausado, timeout | O review **testa** modo avião. Sem isso, reprova |
| **016** UI de correções + resumo de sessão | **Aqui você está cobrando pelo produto da visão**, e ele é *"conversa → correção → acúmulo → progresso visível"*. As `Correction` já são persistidas (013) e **não aparecem em lugar nenhum**. Cobrar por conversa sem isso é vender menos do que o produto é |
| **029 + 030** Histórico de sessões | Mesmo argumento. Sem histórico, não há "progresso", e progresso é metade do que justifica a assinatura |
| **031** Ciclo de vida da sessão na borda | Sem sessão que encerra, o histórico do 029 não tem unidade |
| **034** Encerramento automático por inatividade | P, e sem ele nenhuma sessão fecha sozinha — o histórico enche de sessões abertas |
| **020** Planos, assinatura e entitlements | Cobrança |
| **021** Canal de cobrança e provedor | Cobrança. **Desbloqueado pelo N2**: é IAP |
| **022** Webhooks de pagamento e reconciliação | Com IAP, são as App Store Server Notifications. Sem reconciliação, assinatura cancelada continua valendo |
| **023** Gate de entitlement no POST de turn | Sem ele, não pagante usa igual |
| **011** (pendência) Permissão de microfone negada permanentemente | Herdada do CARD-011 e ainda **não verificada**. O review nega a permissão de propósito |

**17 cards existentes + 7 trabalhos sem card.**

### Não bloqueantes — melhoram o produto, não impedem o lançamento

| Card | Por que pode esperar |
|---|---|
| **041** O aluno falou português, o professor trata isso | O 039 já mata a alucinação. Isto é refinamento pedagógico — e é o card que eu **mais recomendo** entre os não-bloqueantes |
| **044** A voz do professor por escuta | Esforço P e a medição já foi feita. Não impede lançar; muda muito a percepção. **Ver a ressalva abaixo** |
| **043** Cancelar o turn no servidor | O 042 resolve a experiência. Isto economiza US$ 0,0027/abandono e prepara o V2 |
| **045** Nível declarado no onboarding | Não impede. Mas é o tipo de coisa que faz a assinatura parecer valer — decida com o olho na proposta de valor, não na engenharia |
| **046** `CefrAssessment` estimado | G, e a primeira entrega é um ADR |
| **047** Mini-teste inicial | Já mapeado sem data |
| **048** Voz escolhida pelo aluno | Já catalogado. **Mas ver a ressalva** |
| **028** Estados do turno redesenhados | Polimento de design |
| **035** Controles do player (0,75×, repetir, scrub) | Bom para aprendizado, não impeditivo |
| **036** Tradução sob demanda | Feature isolada |
| **032** Descartar turn travado | Já marcado "pode morrer no plano" |
| **019** Spike STT/TTS no aparelho | Spike sem compromisso — **mas ele é a alavanca do §11 da análise de custo**, e com usuários pagantes ele muda de natureza: deixa de ser curiosidade e vira estudo de margem |
| **038** Túnel + `INVITE_CODE` | **Substituído pelo N1.** App público não é por convite |
| **037** (pendências) p50 e gap no aparelho | Dívida de medição |
| — Eval harness da IA (P5) | Não impede. Mas publicar um professor de inglês pago sem baseline de qualidade é risco assumido, não risco ausente |
| — Web companion | Fase 6. **Nota:** a `analise-custo-e-precificacao.md` §10 via nele o canal de receita a ~4% em vez dos 15–30% da loja. Com o N2, essa alavanca fica para depois |

> **Ressalva sobre 044 e 048, e é a única ordem que eu inverteria:** o 044 é
> esforço P, você já ouviu as amostras, e ele **decide o custo do 048** (voz
> única × `libritts-high` multi-falante). Fazê-lo agora é barato; refazê-lo
> depois de publicar significa **mudar a voz da professora de um app que já
> tem usuários** — que é trocar a identidade do produto no meio do caminho.
> Não é bloqueante. É a coisa mais barata da lista que fica cara se adiar.

## A ordem que eu sugiro

Cada anel só começa quando o anterior fecha, porque cada um depende do outro.

1. **Anel do produto conversável** (o que já está quase pronto):
   `042 → 039 → 040 → 044` — três dos quatro são P/M e atacam o que o uso real
   reclamou. Ao fim dele, o app é bom.
2. **Anel do produto vendável:** `016 → 031 → 034 → 029 → 030` — as correções e
   o progresso aparecem. Ao fim dele, há o que cobrar.
3. **Anel de quem é o usuário:** `N3 (auth) → N4 (delete) → N7 (abuso no
   cadastro)`.
4. **Anel do dinheiro:** `015 → 033 → 020 → N2/021 → 022 → 023`.
5. **Anel de existir fora do seu Mac:** `024 → N1 (deploy + ADR)` — pode correr
   em paralelo com o 3 e o 4, e **quanto antes começar, melhor**: é o único com
   incógnita técnica de verdade (a queda do MLX).
6. **Anel da loja:** `017 → N5 → N6 → 027 → 011 (pendência)` — e o N6 tem prazo
   de revisão que não depende de você.

## O corte, se precisar caber

A regra do backlog é *"se algo tiver que ceder para caber, cede escopo — nunca
latência"*. Onde eu cederia, em ordem:

1. **Android.** Uma loja só, primeiro.
2. **029 + 030 (histórico).** É o corte que mais dói e o mais defensável: dá
   para lançar com correções visíveis (016) e sem lista de sessões, se a
   proposta de valor da V1.0 for "converse e seja corrigido" em vez de
   "acompanhe seu progresso". **Mas isso é decisão sua de produto, não minha** —
   e reduz o que a assinatura entrega.
3. **A cobrança na V1.0.** Vale dizer em voz alta: **lançar grátis com cota tira
   os cards 020–023 e o N2 do caminho crítico** — quatro cards, um deles G, mais
   toda a reconciliação de assinatura. É de longe o maior corte disponível, e
   nada impede cobrar na 1.1. Você já respondeu que quer cobrar na 1.0; registro
   a alternativa porque o custo dela é grande e o caminho de volta é barato.

## O que este documento NÃO faz

- **Não cria o N1 nem o N2.** Os outros cinco viraram os cards 049–054 em
  2026-09-10. Estes dois precisam de decisão sua antes: o N1 exige um ADR que
  escolha entre latência (Apple Silicon) e custo/disponibilidade (Linux barato),
  e o N2 fixa os 15–30% da loja.
- **Não estima prazo.** Nenhum número de semanas sairia de medição, e este
  repositório não registra estimativa que não mediu.
- **Não substitui o ADR-0010 nem atualiza a Parte E da visão.** As duas coisas
  são obrigatórias antes de a primeira linha de deploy ser escrita.
