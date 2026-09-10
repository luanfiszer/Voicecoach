# CARD-056 — Quando o servidor cair: backup, restore testado e log alcançável

- **ID:** CARD-056
- **Épico:** Lançamento na App Store (bloqueante de V1.0 — N1 do corte)
- **Esforço:** M
- **Status:** backlog
- **Dependências:** CARD-055, ADR-0060

## Contexto

A outra metade do N1, separada porque o CARD-055 já era grande — e porque **esta
metade é a que costuma ser adiada até deixar de ser possível fazer**.

O ADR-0060 nomeia a consequência: *"a partir daqui existe um estado de produção
que não pode ser recriado apagando uma pasta"*. A partir do CARD-049, esse
estado inclui **conta, senha em hash e voz de gente de verdade**; a partir do
CARD-051, inclui uma promessa legal sobre o que foi apagado.

## Problema

Depois do CARD-055, o produto está no ar e **não há resposta para nenhuma destas
perguntas**:

1. O VPS morre. Quanto do banco se perde?
2. Um aluno diz "o app não funciona". Como você lê o log? Hoje o `structlog` sai
   no terminal do processo, e o terminal está no servidor.
3. Uma migration corre errado em produção. Como se volta?
4. O disco enche de mídia. Como se percebe **antes** de o produto parar?

Nenhuma delas é hipotética num serviço pago.

## Proposta técnica

1. **Backup do Postgres, automático e fora do servidor.** No mesmo disco não é
   backup — é uma cópia que morre junto. Periodicidade e retenção são decisão
   deste card, e a pergunta que as define é *"quanto de conversa eu aceito
   perder?"*.
2. **Restore testado, e é o item que dá valor a todos os outros.** Backup nunca
   restaurado é um arquivo com nome bonito. O critério de aceite exige o restore
   **executado**, não configurado.
3. **Log alcançável sem SSH no meio da noite.** O `structlog` já produz JSON
   estruturado (visão, Observabilidade); falta ele ir para algum lugar que
   sobreviva ao container reiniciar e que dê para pesquisar por `turn_id`.
4. **O Jaeger do compose de dev não vai para produção assim.** OpenTelemetry
   está previsto na visão e o span do worker já carrega `turn_id` e
   `student_id`. A decisão aqui é entre manter tracing em produção (custo de
   memória num VPS pequeno) ou ficar só com log estruturado na V1.0 — e a
   resposta honesta provavelmente é a segunda, com gatilho escrito.
5. **Alarme mínimo, não observabilidade completa.** A Parte F da visão corta
   Prometheus+Grafana com o gatilho *"tráfego real"*. O que **não** dá para
   cortar: saber que o serviço caiu, que o disco encheu, ou que o kill switch
   disparou (CARD-015). Três avisos, não um dashboard.
6. **Runbook de uma página**, no repositório: como derrubar, subir, ver log,
   restaurar, e como reverter uma migration. Escrito antes de precisar, porque
   quem precisa está nervoso.

## Refinamento obrigatório — cache e limites

**Cache:** não se aplica.

**Endpoint:** nenhum novo no produto. Se o log ou as métricas ficarem atrás de
uma rota, ela **não** é pública e **não** mora em `/v1` — e o `/health` que já
existe (ADR-0014) continua sendo o único endpoint operacional aberto, com
liveness separado de readiness.

**Dependência externa:** o destino do backup (object storage fora do VPS) e,
se houver, o destino do log. **Timeout/retry:** backup que falha tem de **avisar
alto** — backup silenciosamente quebrado é pior que backup ausente, porque
produz confiança falsa. **Idempotente:** restaurar duas vezes o mesmo dump deve
dar o mesmo resultado. **Desfecho quando o destino está fora:** o produto
continua funcionando (backup não está no caminho do turno) e o alarme dispara.

## Escopo

- **In:** backup automático fora do servidor; **um restore executado de
  verdade**; log estruturado persistido e pesquisável; os três alarmes; a
  decisão sobre tracing em produção; o runbook.
- **Out:** alta disponibilidade, réplica, failover — não há SLA (a Parte F já
  cortou multi-provider com esse argumento). Prometheus/Grafana, com o gatilho
  já escrito. Retenção de log de longo prazo.

## Critérios de aceite

- **Dado** o backup configurado, **quando** um dia se passa, **então** existe um
  dump fora do VPS, e sua idade é verificável sem SSH.
- **Dado** um dump, **quando** restaurado num banco vazio, **então** um aluno de
  teste consegue entrar e ver o histórico dele. **Este critério exige o restore
  ter acontecido**, e é o único do card que não pode ser cumprido por
  configuração.
- **Dado** um turn que falhou em produção, **quando** procurado pelo `turn_id`,
  **então** o log daquele turn aparece — sem entrar no servidor.
- **Dado** o serviço fora do ar por 5 minutos, **quando** o tempo passa,
  **então** você é avisado, por um canal que você lê.
- **Dado** o disco a 90%, **quando** o limiar é cruzado, **então** o aviso sai
  antes de o produto parar.
- **Dado** o runbook, **quando** seguido do zero, **então** ele funciona —
  testado uma vez, por você, sem consultar mais nada.

## Riscos

- **O restore é o item que se pula.** Ele é o único que dá sentido ao resto, e é
  o único que dá trabalho. Está como critério de aceite explícito por isso.
- **Backup com dado pessoal é dado pessoal.** Ele precisa entrar no inventário do
  CARD-052 e obedecer ao delete do CARD-051 — uma conta excluída que ressuscita
  num restore é uma violação, não um detalhe. **Este é o acoplamento mais fácil
  de esquecer dos dois cards.**
- **Alarme demais vira alarme nenhum.** Três, não trinta.
- **Um VPS pequeno pode não ter fôlego para tracing** e degradar o produto ao
  tentar observá-lo.

## Objetivo de aprendizado

Entender a diferença entre **log, métrica e trace** decidindo, com restrição
real de memória, qual deles cortar — e por que a resposta num serviço de um
usuário é diferente da de um serviço com tráfego. É o assunto que em .NET viria
pronto pelo Application Insights, com a conta escondida: aqui a conta é sua, o
VPS tem 2 GB, e a escolha aparece.
