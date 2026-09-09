# CARD-038 — O backend sai da LAN por túnel, e ganha porteiro antes de sair

- **ID:** CARD-038
- **Épico:** Fase 2 — Proteção de margem
- **Plataforma:** backend/infra · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-037 (o app precisa existir no aparelho antes de valer a
  pena alcançá-lo de fora), [ADR-0010](../adr/0010-politica-de-custo-projeto-pessoal.md)

## Contexto

O CARD-037 põe o app num iPhone, mas amarrado ao Wi-Fi de casa: o `apiBaseUrl`
aponta para o IP do Mac na LAN. Testar o produto **na rua** — que é onde uma
aula de conversação de fato acontece — exige que o backend seja alcançável pela
internet.

Em 2026-09-09 o desenvolvedor pediu "uma esteira de deploy". A análise das
alternativas mostrou que **deploy de verdade sai caro em três frentes ao mesmo
tempo**, e a decisão foi o túnel:

| | Túnel (escolhido) | Deploy em servidor |
|---|---|---|
| Custo | **R$ 0** — preserva o ADR-0010 | ~US$ 10–15/mês, **exige ADR novo** |
| STT | **MLX segue** (`factory.py:33`: *"a única plataforma onde o `mlx` existe"*) | cai para `faster_whisper`; **a latência medida deixa de valer** |
| RAM | a do Mac | Whisper small + Piper residentes **não cabem** em free tier (Fly 256 MB, Render 512 MB) |
| Preço a pagar | **só funciona com o Mac ligado** | funciona sem o Mac |

O túnel entrega quase tudo que o deploy entregaria **para o objetivo atual, que
é validar o MVP**, por zero e numa fração do trabalho. Quando o objetivo virar
"outras pessoas usam sem eu ligar o Mac", aí sim é deploy — e é outro card, com
ADR de custo.

## Problema

**Expor a API na internet sem porteiro é publicar um endpoint que gasta Claude
por conta do cartão do desenvolvedor.** Hoje não há autenticação: o
`POST /v1/sessions` cria sessão para qualquer um, e o
`POST /v1/sessions/{id}/turns` dispara STT + LLM + TTS sem perguntar quem é.

Na LAN isso é irrelevante. Atrás de uma URL pública, é o cenário que o CARD-015
descreve — *"vender risco ilimitado por preço fixo"* — só que sem nem vender.

O ADR-0010 item 5 **já decidiu o remédio** e ele ainda não foi implementado:
cadastro por `INVITE_CODE`, escolhido justamente para eliminar a superfície de
abuso sem exigir auth completa nem provedor de e-mail no MVP.

## Proposta técnica

Duas peças, uma dependente da outra.

**1. O porteiro, primeiro.** Um segredo compartilhado exigido em toda rota de
`/v1`, vindo da config tipada (`pydantic-settings`, ADR-0013) — nunca hardcoded.
Rejeição em **Problem Details** (ADR-0040), como todo erro da API, com `401` e
um `type` próprio. O app o envia em cabeçalho, guardado no armazenamento seguro
do dispositivo.

> **Isto não é autenticação e o card não deve fingir que é.** Não há conta, não
> há usuário, não há sessão de login: é um segredo único que separa "eu" de "a
> internet". Contas de verdade continuam sendo a Fase 3 (ADR-0007). O nome no
> código deve dizer isso.

**2. O túnel.** `cloudflared` (Cloudflare Tunnel) — gratuito, HTTPS com
certificado válido, e com URL estável no plano nomeado. Alternativa: `ngrok`,
que o protótipo do `english_teacher_bot/` já usava, com URL que muda a cada
reinício no free tier.

> ### Decisão arquitetural embutida — **ADR obrigatório antes da implementação**
>
> Critério **4 de `docs/adr/README.md` — afeta segurança ou privacidade**, e
> critério **1** (introduz dependência externa: o provedor de túnel). Expor à
> internet um backend desenhado para rodar em `localhost` é exatamente a
> mudança de superfície que o critério 4 existe para registrar. O ADR precisa
> decidir: `cloudflared` vs. `ngrok`; onde o segredo mora no cliente; e o que
> **não** fica exposto (o MinIO assina URLs — ver risco abaixo).

## Refinamento obrigatório — cache e limites

1. **TTL:** não se aplica.
2. **Gatilho de invalidação:** não se aplica.
3. **Política de limite — o ponto mais importante deste card.** O `INVITE_CODE`
   impede o desconhecido; **não impede o loop.** Um bug de retry no cliente com
   o segredo correto queima orçamento igual. Teto por **IP** na borda do túnel
   (protege a máquina) e teto de turns por janela na aplicação (protege a
   lógica). Número inicial é estimativa declarada: **30 turns/hora**, ~US$ 0,08
   pelo custo medido do ADR-0051, recalibrado por métrica. O teto de custo
   propriamente dito é o CARD-015 — este card entrega o teto **grosso**, e a
   dependência está declarada para que a ordem não se perca.
4. **Timeout, retry e desfecho:** o túnel vira um salto novo entre app e API —
   ele pode cair sozinho, com o Mac ligado e a API saudável. O app deve tratar
   isso como rede indisponível (comportamento já existente do CARD-012), e o
   desfecho precisa ser distinguível de "backend fora": o aluno vê que está sem
   conexão com o serviço, e o log diz que foi o túnel.

## Escopo

- **In:** `INVITE_CODE` na config tipada, exigido em `/v1` com `401` em Problem
  Details; envio e guarda do segredo no app; rate limit grosso por IP e por
  janela; túnel configurado com URL estável; `apiBaseUrl` do app apontando para
  ela; ADR da exposição; procedimento de subida documentado no `README`.
- **Out:** contas, login e auth de verdade (Fase 3, ADR-0007); quotas por aluno
  e kill switch de orçamento (**CARD-015**); deploy em servidor e Dockerfiles
  (**CARD-024** e um card de API ainda inexistente); CI/CD.

## Critérios de aceite

- **Dado** um `POST /v1/sessions` **sem** o cabeçalho do convite, **então** a
  resposta é `401` em Problem Details e **nenhuma** sessão é criada.
- **Dado** o cabeçalho com valor errado, **então** `401` — e a mensagem **não**
  revela se o segredo existe ou qual o formato esperado.
- **Dado** o cabeçalho correto, **então** o fluxo do CARD-010 segue idêntico:
  `202` com `turn_id`.
- **Dado** o teto de turns por janela estourado com segredo válido, **então**
  `429` em Problem Details, **antes** de qualquer chamada paga — verificável por
  teste que falha se o adapter de LLM for tocado.
- **Dado** o túnel no ar, **quando** o iPhone usa **rede móvel, fora do Wi-Fi de
  casa**, **então** um turn completa ponta a ponta com áudio audível.
- **Dado** o túnel no ar, **então** apenas a API está publicada — Postgres,
  Redis e o console do MinIO **não** respondem pela URL pública (verificado por
  requisição, não por inspeção de config).
- **Dado** os quality gates, **então** `uv run pytest --cov --cov-fail-under=80`
  e a cobertura do núcleo ≥ 90% seguem verdes.

## Riscos

- **As URLs de mídia são assinadas com o host do leitor** (ADR-0045). Com o
  túnel, o app baixa trechos de uma origem diferente da do servidor — se a
  assinatura sair com `localhost:9000`, **o áudio não toca no aparelho e o turn
  parece completar**. É o risco mais provável deste card, e o ADR-0045 é
  exatamente o lugar onde a resposta já foi pensada.
- **Segredo único não rotaciona.** Vazou, troca-se em dois lugares (config e
  app). Aceitável enquanto o público é uma pessoa; deixa de ser no beta.
- **Túnel gratuito cai** e o sintoma se confunde com "backend fora" — daí o
  desfecho distinguível ser critério de aceite.
- **`INVITE_CODE` dá falsa sensação de segurança.** Ele barra o desconhecido,
  não o loop; por isso o rate limit está no mesmo card, e não "depois".

## Objetivo de aprendizado

> Obrigatório e específico.

**Entender como uma dependência transversal se aplica a um grupo de rotas em
FastAPI sem virar `if` copiado em cada handler** — `Depends` em nível de
`APIRouter`, e por que isso não é o mesmo que um middleware ASGI. Especificamente:
que o middleware roda **antes** do roteamento (não sabe qual rota vai atender,
nem enxerga os parâmetros já validados) enquanto a dependência de router roda
**depois** (sabe, e participa da geração do OpenAPI, aparecendo no
`openapi.json` como requisito de segurança da rota).

O paralelo mental de C#: middleware ASGI é o pipeline do `Startup.Configure` —
posicional e cego à ação; a dependência de router é o `[Authorize]` aplicado ao
controller, que o Swagger enxerga. A diferença que **não** tem paralelo é a
dependência ser uma função comum cujo tipo de retorno o framework injeta — não
há atributo, não há reflexão sobre metadata, e o mesmo mecanismo serve para
autorização, conexão de banco e configuração.
