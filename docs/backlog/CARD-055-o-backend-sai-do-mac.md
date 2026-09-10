# CARD-055 — O backend sai do Mac: servidor, domínio, TLS e o primeiro deploy

- **ID:** CARD-055
- **Épico:** Lançamento na App Store (bloqueante de V1.0 — N1 do corte)
- **Esforço:** M — **e ele só é M porque o CARD-056 tirou metade dele**
- **Status:** backlog
- **Dependências:** CARD-024 (Dockerfile do worker), ADR-0060, ADR-0025

## Contexto

Bloqueante do lançamento e o de maior incógnita técnica de todos. A decisão está
no **ADR-0060**: VPS Linux barato, `mlx` fora de produção, e o alvo de latência
redefinido para **p50 < 4,5 s no aparelho contra o servidor real**.

Este card é a primeira vez que este projeto tem um ambiente que alguém precisa
**operar**, e não apenas rodar.

## Problema

Levantado ao ler o `docker-compose.yml` em 2026-09-10, e é maior do que "falta
um servidor":

1. **O compose só tem infra** — `postgres`, `redis`, `minio`, `jaeger`. A **API e
   o worker rodam como processos do host**, à mão, no terminal.
2. **Nenhum dos dois tem `Dockerfile`.** O CARD-024 cobre o do worker (com os
   modelos dentro da imagem, que é o pedaço difícil por causa do peso). **A API
   não tem card nenhum** — e é este.
3. Não há domínio, não há TLS, não há segredo que não seja um `.env` local, e
   as migrations são aplicadas por você, na sua máquina, quando lembra.
4. O `S3_PUBLIC_ENDPOINT_URL` que o CARD-037 precisou existe só no `.env` não
   versionado — e o ADR-0045 diz que quem assina a URL de mídia é o host
   **alcançável pelo leitor**. Com o servidor na internet, isso muda de valor e
   precisa estar certo, ou o áudio não toca (foi exatamente o sintoma 5 do
   CARD-037).

## Proposta técnica

1. **`Dockerfile` da API**, irmão do que o CARD-024 faz para o worker. Eles
   compartilham o código e **não** compartilham a imagem: a do worker carrega
   ~700 MB de modelos (Whisper + a voz do Piper); a da API não precisa de
   nenhum. Enfiar as duas numa imagem só faria o deploy da API arrastar os pesos.
2. **Compose de produção separado do de desenvolvimento.** Não é o mesmo arquivo
   com variáveis: o de dev expõe portas e tem o Jaeger; o de produção não expõe
   Postgres nem Redis para fora, e a mídia deixa de ser MinIO com credencial de
   brinquedo.
3. **Domínio e TLS**, com certificado renovado sozinho. O nome precisa ser
   estável **antes** do CARD-053, porque a URL da API fica gravada no build de
   release e mudá-la custa uma revisão nova da Apple.
4. **Segredos fora do repositório e fora do `.env` de dev** — chave do
   Anthropic, credenciais do storage, segredo de assinatura do JWT (CARD-049).
   Como eles chegam ao servidor é decisão deste card, e a resposta mais simples
   que funciona é preferível à mais sofisticada.
5. **Migrations aplicadas no deploy**, não à mão. Alembic já está no projeto
   (ADR-0004); o que falta é o momento em que ele roda — e a ordem entre "aplicar
   migration" e "subir o código novo" é onde deploys quebram.
6. **A readiness já sabe distinguir "subiu" de "pronto"** (ADR-0025), e ela é o
   instrumento certo: o worker só aceita job depois de carregar os modelos. Num
   servidor pequeno essa carga é mais lenta que no seu Mac, e isso vai aparecer.
7. **A medição no fim é entregável, não bônus.** O ADR-0060 estimou +0,5 a
   +1,5 s e disse que é estimativa. Este card produz o número.

## Refinamento obrigatório — cache e limites

**Cache:** os modelos residentes (ADR-0025) passam a viver num servidor com
memória escassa. Whisper `small` multilíngue + a voz do Piper + Postgres + Redis
num VPS de 2 GB **pode não caber** — e essa conta precisa ser feita **antes** de
escolher o plano, não depois do primeiro OOM. TTL: a vida do processo.
Invalidação: reinício.

**Endpoint:** nenhum novo. Mas **toda a API deixa de estar numa LAN**, e é a
primeira vez. O que antes era protegido por "só quem está na minha rede" passa a
ser protegido por autenticação (CARD-049) e limites (CARD-054) — **e este card
não pode ir ao ar sem eles**. Enquanto não forem, o servidor fica fechado.

**Dependência externa:** o provedor de VPS. **Timeout/retry** não se aplicam; o
que se aplica é o desfecho quando ele cai — e é o **CARD-056**. **Idempotente:**
o deploy tem de ser: rodar duas vezes não pode duplicar nada nem perder dados. A
migration aplicada duas vezes é um não-evento com Alembic; o resto precisa ser
verificado.

## Escopo

- **In:** `Dockerfile` da API; compose de produção; provisionamento do VPS;
  domínio e TLS; segredos; migrations no deploy; `S3_PUBLIC_ENDPOINT_URL` correto
  para o mundo; smoke test ponta a ponta (um turn real contra o servidor); e a
  **medição do p50 do aparelho contra produção**, registrada mesmo se for ruim.
- **Out:** backup, restore e observabilidade alcançável — **CARD-056**, e ele
  não é opcional, só é depois. CI que faz deploy sozinho (fazer à mão primeiro;
  automatizar o que ainda não se entende é como se automatiza um erro). Escala
  horizontal, load balancer, réplica.

## Critérios de aceite

- **Dado** o servidor provisionado, **quando** o deploy roda, **então** API e
  worker sobem em container, e a readiness do worker só fica verde depois dos
  modelos carregados.
- **Dado** o app apontando para o domínio de produção, **quando** um turn é
  gravado no iPhone, **então** ele completa e **o áudio toca** — que é o critério
  que o CARD-037 provou ser o mais fácil de quebrar por configuração de host.
- **Dado** cinco turns consecutivos, **quando** medidos, **então** o p50 está
  registrado no card com o número real. **Se ele estourar os 4,5 s do ADR-0060,
  o número entra assim mesmo** e a conversa passa a ser sobre o alvo, não sobre
  o registro (ADR-0048).
- **Dado** o STT em produção, **quando** o log de subida é lido, **então** ele
  nomeia `faster-whisper` — provando que a assimetria do ADR-0060 item 2 é
  visível e não suposta.
- **Dado** o deploy executado duas vezes seguidas, **quando** o segundo termina,
  **então** o sistema está íntegro e nenhum dado foi perdido.
- **Dado** o Postgres e o Redis, **quando** varridos da internet, **então** não
  respondem — só a API responde, e só em TLS.

## Riscos

- **O VPS pode não caber os modelos.** É o risco número um e o mais barato de
  eliminar: fazer a conta de memória **antes** de contratar. Plano B é um plano
  maior, o que muda a conta de custo do ADR-0060.
- **A latência pode ser pior que a estimativa.** +1,5 s era o palpite pessimista;
  um VPS ruim pode entregar mais. Plano B, em ordem: um plano com CPU melhor;
  reduzir o modelo de STT (`base` multilíngue, remedindo); e, no limite,
  reabrir a Alternativa C do ADR-0060.
- **Este card não pode ir ao ar sem auth e limites.** Uma API pública sem
  CARD-049 e CARD-054 é a chave do seu cartão de crédito na internet. Está no
  refinamento, e vale repetir aqui.
- **O primeiro deploy sempre demora mais do que parece**, e este é o primeiro de
  um projeto que nunca teve nenhum.

## Objetivo de aprendizado

Entender **por que a imagem do worker e a da API não podem ser a mesma** neste
projeto, e o que isso ensina sobre camadas de imagem: elas compartilham o mesmo
código-fonte e divergem em ~700 MB de artefato: o `Dockerfile` deixa de ser
"empacotar o app" e vira uma decisão sobre **o que precisa estar presente para o
processo estar pronto** — que é o mesmo assunto do ADR-0025, visto do outro
lado. Em .NET o paralelo é publicar um worker service e uma API do mesmo
solution; a diferença aqui é que o modelo de IA é um asset pesado que muda a
resposta.
