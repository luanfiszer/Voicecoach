# Prompt — loop autônomo sobre o backlog do Voicecoach

> Gerado em 2026-09-13, para colar em uma sessão nova do Claude Code (ou usar
> como argumento da skill `/loop`, sem intervalo, deixando o modelo se
> autopacing). Este arquivo é o prompt em si — copie tudo a partir da linha
> "## Papel" para a sessão nova.

## Papel

Você vai codar o backlog do Voicecoach **sozinho**, card a card, até não
conseguir mais continuar (contexto ou orçamento de tokens esgotando). Para
cada card: implementar, testar, documentar, commitar, abrir PR, **mergear
sem esperar aprovação humana**, e seguir imediatamente para o próximo. O
desenvolvedor não vai responder perguntas durante este loop — ele revisa tudo
depois, de uma vez. Isso é uma autorização explícita dele, registrada nesta
sessão de 2026-09-13.

**O que NÃO muda:** todos os gates técnicos, a Definition of Done, a
obrigação de ADR quando o critério bater, e as regras de arquitetura do
`CLAUDE.md`. O que muda é só a `regra do explicador` (seção abaixo) e a
autorização de merge sem pausa.

## Antes de tudo: leia isto, uma vez, no início do loop

1. `CLAUDE.md` inteiro.
2. `docs/backlog/README.md` inteiro — é o mapa de prioridade e dependências.
3. `docs/visao-produto-e-arquitetura-alvo.md`, especialmente a Parte F
   (anti-overengineering).
4. `docs/adr/README.md` — critério de quando ADR é obrigatório.
5. `docs/learnings/` inteiro — são os erros já cometidos neste projeto.
6. A skill `voicecoach-arquitetura` (backend) e `voicecoach-cliente`
   (mobile/web), conforme o card tocar uma ou outra.

Não precisa reler tudo a cada card — releia o card específico, os ADRs que
ele cita, e a skill de arquitetura relevante.

## Como escolher o próximo card

> **Atualizado em 2026-09-13 (segunda revisão, à noite), depois da primeira
> sessão de teste em aparelho físico.** O texto abaixo substitui a versão
> anterior desta seção inteira. **Antes de confiar nesta lista, releia
> `docs/backlog/README.md` de novo** — ele é a fonte de verdade; esta seção é
> só um atalho para não rederivar o estado do zero.

**O que mudou desde a revisão anterior:** o desenvolvedor testou o app pela
primeira vez num iPhone físico (dev build, `pnpm run ios:device`). Isso
revelou e corrigiu um bug real (microfone cortado a partir da 2ª gravação —
[LEARNING-0008]; ver `docs/backlog/CARD-035-controles-do-player-sobre-a-fila-de-trechos.md`,
seção "Desbloqueio"), e gerou dois cards novos por observação de uso real:
**CARD-058** (UI do botão `traduzir`) e **CARD-059** (aba de Configurações).
**CARD-035** também deixou de estar bloqueado — o motivo do bloqueio (falta
de aparelho físico com áudio real) não existe mais.

Nesta ordem:

1. **CARD-058 primeiro** — UI do botão `traduzir`. Sem áudio, sem dependência
   de aparelho físico, sem ambiguidade de produto (o endpoint do CARD-036 já
   define o contrato). É o card mais seguro e mais barato da fila agora.
2. **CARD-059 depois** — aba de Configurações. Também sem áudio nem aparelho
   físico. **Implemente só as seções 2 (limite de gravação, leitura) e 3
   (sobre/versão) se o CARD-035 ainda não tiver rodado** — a seção 1
   (preferências de reprodução) não tem o que controlar antes dele existir;
   não invente o toggle antes do valor.
3. **CARD-035 — reavalie a disponibilidade de aparelho físico no INÍCIO da
   sessão, antes de assumir que dá para rodar.** `xcrun devicectl list
   devices` diz se algum iPhone está pareado e `tunnelState: connected` (foi
   assim que a sessão de 2026-09-13 confirmou); sem isso, o card volta a ter
   a mesma limitação de antes (sem microfone, sem ouvido) e a decisão correta
   é **não reabri-lo às cegas** — documente que o aparelho não estava
   disponível nesta sessão e siga para o próximo item da lista, sem tocar no
   código. **Se o aparelho estiver disponível**, esta sessão de teste ensinou
   um caminho de verificação que não depende de ouvido: baixar o `.m4a`/`.wav`
   real do MinIO via `boto3` e inspecionar com `afinfo` (macOS nativo,
   embutido — não precisa instalar nada), consultar `audio_duration`/
   `transcript` direto no Postgres, e usar os mesmos deep links sem toque
   (`xcrun devicectl device process launch ... --payload-url
   "voicecoach://rota"`) que a rota `/medicao` já usa. Isso cobre boa parte
   dos critérios objetivos (`0.75×` valendo para trechos futuros, `repetir`
   sem nova requisição de rede, nenhum player tocando ao sair da tela); só o
   "scrub sem silêncio audível" continua sendo, literalmente, uma asserção de
   ouvido — declare-o como dívida se ninguém puder confirmar.
4. ~~CARD-057~~ — **concluído** (PR #34), imagem migrada para `quay.io/minio/minio`
   (ADR-0062). CI do backend está verde por causa disso.
5. ~~A ordem dos cinco pontos da qualidade da conversa~~ — **esgotada**:
   039, 040, 042 concluídos; **041 bloqueado** (contradiz o ADR-0057 revisado
   pelo 040 — precisa de decisão do desenvolvedor entre revogar o card ou
   reabrir o ADR); **044 bloqueado** (falta escuta comparada, subjetiva —
   mas agora com aparelho físico acessível, vale reconferir com o
   desenvolvedor se ele topa fazer a escuta comparada numa sessão dele);
   **043 adiado** (recuo do próprio ADR-0058, escopo maior que uma sessão);
   **045 bloqueado** (depende do 041, que está bloqueado, e de auth, que não
   existe). **046 e 047 não têm parte segura para o loop autônomo**: 046 exige
   escrever um ADR sem evidência (proibido pela própria régua do card), 047
   depende de 045/046.
6. ~~Cards de Fase 2/3 em `backlog`~~ — **esgotados além de 058/059/035**:
   015, 016, 028, 029, 030, 031, 032, 033, 034, 036, 027 concluídos. **019
   permanece bloqueado** (spike exige fala real de aprendiz e escuta
   comparada, não só aparelho — o gargalo aqui é subjetividade, não hardware).
   **017, 024, 038 despriorizados** (ver lista abaixo).
7. **Chegou a vez dos bloqueantes de V1.0 (CARD-049 em diante).** Releia a
   seção "Corte da V1.0" do README **e** `docs/corte-v1-o-que-bloqueia-o-lancamento.md`
   antes de tocar em qualquer um. **Recomendação forte: pare e peça
   confirmação explícita do desenvolvedor antes de abrir o CARD-049**
   (cadastro/login/JWT) — é o primeiro card que introduz autenticação real
   num backend que hoje não tem nenhuma, toca em segredo (chave de
   assinatura de token, provedor de e-mail — o card já assinala "ADR de
   provedor de e-mail" como dependência sem ADR nenhum ainda escrito), e é a
   fundação de que 050/051/054 dependem em cadeia. Errar aqui não é um card
   ruim isolado — é retrabalho em quatro cards. Isto não é uma regra nova do
   protocolo, é a "cautela redobrada" do item 4 original, tornada concreta
   agora que ele deixou de ser hipotético.
8. **Fase 4 (020/022/023 — planos, entitlements, webhook de pagamento)**
   também depende de auth (`015, auth` nas dependências do 020) e de decisão
   de provedor de pagamento — mesma cautela do item 7.

**NÃO toque nestes cards — despriorizados pelo desenvolvedor em 2026-09-13,
cada um com o motivo e o gatilho de retorno escrito no próprio arquivo:**
CARD-017, CARD-024, CARD-038, CARD-052, CARD-053, CARD-055, CARD-056. Releia
o card antes de assumir que o gatilho ainda não disparou — mas a leitura
honesta hoje é que nenhum disparou.

**Pule (não implemente, registre por que) qualquer card cujo primeiro
entregável seja um ADR que dependa de dado que não existe** — ex.: CARD-046
diz explicitamente "o ADR não foi escrito de propósito (sem evidência para
decidir janela e algoritmo)". Se não há como gerar essa evidência sozinho
(ex.: precisa de voz real de aprendiz, que só o desenvolvedor tem), registre
o card como bloqueado, explique o porquê, e siga para o próximo.

## O protocolo por card (adaptado de `/executa-card`, sem a pausa)

1. **Branch.** `git switch main && git pull --ff-only` (ou fast-forward
   local), depois `git switch -c card-NNN-<slug>`. Nunca commite em `main`.
2. **Leia o card e os ADRs que ele cita.** O que está em "Out" não entra.
3. **Declare premissas e plano por escrito, dentro do próprio card**, na
   seção de execução — mas **não espere aprovação**: registre e prossiga.
   Se uma premissa de produto for genuinamente ambígua (ver seção seguinte),
   resolva com a alternativa mais conservadora e diga isso explicitamente.
4. **Implemente.** Siga o estilo do código existente, a skill de
   arquitetura, e as regras de camada (`uv run lint-imports`). Nenhuma
   dependência nova sem justificar contra a Parte F da visão.
5. **Rode os gates, todos, sempre — nenhum é dispensável:**
   ```
   cd backend
   uv run ruff format --check src tests
   uv run ruff check src tests
   uv run mypy
   uv run lint-imports
   uv run pytest --cov --cov-fail-under=80
   uv run coverage report --include="*/domain/*,*/application/*" --fail-under=90
   ```
   Se algum gate falhar e você não conseguir corrigi-lo depois de um esforço
   razoável (não infinito — algumas tentativas focadas, não dezenas): **não
   invente workaround, não pule com `--no-verify`, não force o gate a
   passar**. Documente o bloqueio no card com a saída real do erro, deixe a
   branch como está (sem PR), e siga para o próximo card. Um card bloqueado
   não trava o loop inteiro.
6. **ADR quando o critério objetivo bater** — consulte
   `docs/adr/README.md` § "Quando um ADR é OBRIGATÓRIO" e **cite o critério**
   no card. Decisão só na seção de execução não conta como ADR.
7. **Atualize:** o card (status, execução, evidência colada — comando e
   saída real, nunca "deveria funcionar"), a tabela de
   `docs/backlog/README.md`, e `docs/perguntas-em-aberto.md` se alguma
   pergunta da fila tocar o card (ver seção seguinte).
8. **Commit.** Mensagem explica o porquê, não só o quê. **Nunca** inclua
   `Co-Authored-By: Claude` nem variação com nome de modelo — a autoria é do
   desenvolvedor, mesmo em modo autônomo.
9. **Push, PR, merge — sem pausa:**
   ```
   git push -u origin card-NNN-<slug>
   gh pr create --title "..." --body "..."
   uv run pytest ... # confirme local mais uma vez antes de mergear
   gh pr checks <PR> --watch   # espere o CI, se ele estiver verde para esse PR
   gh pr merge <PR> --merge    # merge commit, não squash — é o padrão do repo
   ```
   Se o CI remoto reprovar por algo que os gates locais não pegaram,
   trate como gate quebrado (item 5): não force o merge, documente, siga.
10. **Atualize `main` local** (`git switch main && git pull --ff-only`) e
    volte ao passo 1 com o próximo card.

## A regra do explicador, em modo autônomo

A regra original existe para o desenvolvedor aprender no ponto da decisão.
Sem ele para responder, ela vira **registro de decisão autônoma**, não
pergunta pendente:

- Quando o ponto de decisão é **técnico** (qual biblioteca, qual desenho
  dentro de uma camada, como nomear algo) — decida você mesmo, com a
  alternativa mais alinhada aos ADRs e à skill de arquitetura já existentes.
  Registre a escolha e o porquê no card, sem marcar como pendência.
- Quando o ponto de decisão é **de produto** (o card teria pedido a previsão
  ou a escolha do desenvolvedor) — escolha a alternativa **mais conservadora
  e mais reversível**, favorecendo o que já está documentado num ADR
  existente sobre o que exigiria um ADR novo sem evidência. Registre a
  decisão no card como:
  > **Decisão autônoma (loop sem desenvolvedor, <data>):** [a pergunta que
  > seria feita] → [a escolha] → [por que essa e não a alternativa] →
  > **PENDENTE DE REVISÃO HUMANA**.
- Nunca decida por adivinhação uma questão que exige dado que só existe fora
  do repositório (voz real de aprendiz, preferência subjetiva de UX, decisão
  jurídica/financeira). Nesses casos, pare aquele card específico, documente
  exatamente o que falta, e siga para o próximo.
- Nenhuma pergunta desta lista bloqueia o merge — ela só marca o que o
  desenvolvedor vai querer olhar primeiro na revisão.

## Onde o cuidado dobra

- **Nunca** delete dados, nunca rode migration `downgrade` contra um banco
  que não seja o de desenvolvimento local, nunca force-push.
- **Cards de auth/pagamento (049 em diante):** implemente com o mesmo rigor
  de sempre, mas não invente política de segurança nem lide com segredo real
  — se um card exigir uma chave de API ou conta de terceiro que não existe
  no `.env`, documente o bloqueio e siga.
- **Se o CI ficar vermelho em mais de um PR seguido por um motivo que não é
  o seu código** (infra externa, flakiness), não insista mais que uma
  segunda tentativa — documente e siga.

## Quando parar o loop inteiro

Quando você perceber que não tem mais orçamento de contexto/tokens para
completar mais um card com segurança (implementar + testar + documentar +
mergear), pare **entre cards**, nunca no meio de um. Antes de parar, escreva
um resumo consolidado em `docs/loop-autonomo-2026-09-13-resumo.md` (ou a data
real da execução) com:

- lista dos cards mergeados nesta sessão, com link do PR;
- lista dos cards bloqueados e por quê;
- todas as decisões autônomas tomadas, com o marcador "PENDENTE DE REVISÃO
  HUMANA" reunidas num lugar só, para o desenvolvedor revisar de uma vez;
- o próximo card na fila, para quem retomar saber por onde continuar.

## Lembretes finais

- `main` é protegida — todo trabalho em branch própria por card.
- Português nos comentários, nomes de domínio em inglês (o vocabulário já
  estabelecido: `Student`, `Session`, `Turn`, `Correction`, `UsageEvent`).
- Custo zero é requisito (ADR-0010) — nada que exija conta paga.
- Prefira a alternativa que **já está escrita em algum ADR** sobre inventar
  uma nova, mesmo em modo autônomo.
