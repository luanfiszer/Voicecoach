# CARD-053 — Conta Apple, build de release e o caminho até a revisão

- **ID:** CARD-053
- **Épico:** Lançamento na App Store (bloqueante de V1.0 — N6 do corte)
- **Esforço:** M — **com prazo que não depende de você**
- **Status:** backlog
- **Dependências:** CARD-051, CARD-052, ADR-0054, ADR-0048

## Contexto

O CARD-037 pôs o app no iPhone com um **dev build assinado por Apple ID
gratuito**, e registrou a conta dos 7 dias: *"instalado em 2026-09-09, expira em
2026-09-16. Depois disso o app deixa de abrir, sem mensagem."*

Publicar é outro caminho inteiro. A Parte E da visão já o previa e o adiou, com
gatilho escrito — e o gatilho disparou. Ela também já mandava o que este card
faz de mais útil: **absorver o prazo de revisão no plano**.

## Problema

Hoje não há conta paga, não há build de release, não há App Store Connect, não
há ícone nem screenshots, e ninguém nunca passou por uma revisão da Apple. Cada
um desses é pequeno; juntos são a diferença entre "funciona no meu iPhone" e
"existe na loja".

E há um problema **de calendário**, não de engenharia: a revisão reprova, você
corrige, reenvia, espera de novo. Planejar como se fosse uma etapa de uma
tentativa é o erro clássico.

## Proposta técnica

1. **Apple Developer Program**, US$ 99/ano. Isto **contradiz o ADR-0010**
   (infra a dinheiro zero) e depende do ADR sucessor dele, que também é
   pré-requisito do card de deploy. Não é decisão deste card, mas ele não anda
   sem ela.
2. **Dados bancários e fiscais no App Store Connect.** Cobrar exige os
   contratos pagos aceitos e a conta bancária configurada — burocracia com prazo
   próprio, e ela **bloqueia a venda mesmo com o app aprovado**. Começar cedo.
3. **Build de release, não dev build.** Assinatura de distribuição, provisioning
   próprio, `Release` de verdade (sem o bundler embutido). O ADR-0054 vale para
   o **ambiente de desenvolvimento** — o release resolve o `apiBaseUrl` de outro
   jeito, e isso é trabalho deste card: **a URL da API passa a ser de
   compilação**, apontando para o servidor real, não derivada do bundler.
4. **Identidade visual mínima:** ícone em todos os tamanhos, splash, nome,
   subtítulo, palavras-chave, descrição e **screenshots nos tamanhos exigidos**
   — que precisam ser tiradas de um app que já esteja bonito.
5. **A conta de teste para o revisor.** O revisor precisa entrar. Um app com
   cadastro e assinatura **tem** de vir com credenciais de demonstração nas
   notas da revisão, e com a assinatura acessível a ele — omitir isso é motivo
   de reprovação comum e evitável.
6. **Passar pela lista de reprovações prováveis antes de enviar**, e ela é
   conhecida: permissão de microfone negada tratada com elegância (a pendência
   herdada do CARD-011, ainda **não verificada**), telas de exceção (CARD-027),
   delete de conta (CARD-051), política acessível (CARD-052), IAP correto e
   restauração de compra funcionando.

## Refinamento obrigatório — cache e limites

**Cache:** não se aplica.

**Endpoint:** nenhum. Mas o card **fixa a URL da API do build de release**, e
essa é uma decisão de fronteira: uma vez publicada, mudá-la exige uma versão
nova na loja e a revisão de novo. O servidor precisa de nome estável **antes**
deste card — é dependência real do card de deploy.

**Dependência externa:** a Apple, e ela é a única deste projeto cujo tempo de
resposta você não controla e não pode retentar à vontade. **Timeout:** não
existe. **Idempotente:** reenviar build é normal e esperado. **Desfecho quando
reprova:** corrigir e reenviar — e o plano tem de caber **duas ou três**
tentativas sem virar crise.

## Escopo

- **In:** conta paga; contratos e dados fiscais; certificados e provisioning de
  distribuição; build de release com a URL da API de produção; ícone, splash e
  screenshots; ficha da loja; rótulos ligados (CARD-052); conta de demonstração
  e notas para o revisor; a verificação da pendência de permissão do CARD-011; o
  envio.
- **Out:** Google Play — decisão de escopo ainda não tomada, e o corte assumiu
  iOS primeiro. TestFlight como etapa formal (pode ser usado no caminho, mas não
  é entrega). EAS Update / OTA — a Parte E já o adiou, e ele só faz sentido
  depois de existir distribuição. Marketing.

## Critérios de aceite

- **Dado** o build de release instalado num aparelho limpo, **quando** aberto,
  **então** ele fala com o servidor de produção — e **não** com nenhum endereço
  de LAN, túnel ou `localhost`. É a regressão mais provável, e o CARD-037 já
  ensinou que o endereço errado é silencioso até o áudio não tocar.
- **Dado** o app instalado a partir do build de release, **quando** o
  certificado de desenvolvimento expira, **então** nada acontece — build de loja
  não tem a validade de 7 dias do CARD-037.
- **Dado** as notas da revisão, **quando** lidas, **então** há credenciais de
  demonstração válidas e instruções para exercitar a assinatura.
- **Dado** o app enviado, **quando** a revisão responde, **então** o resultado é
  registrado no card — **inclusive a reprovação, com o motivo literal**. É o
  princípio do ADR-0048: número honesto vale mais que número bom, e o motivo da
  reprovação é o dado mais útil que este card pode produzir.
- **Dado** a permissão de microfone negada duas vezes, **quando** o aluno volta
  ao app, **então** o caminho para os Ajustes funciona — fechando a pendência
  aberta desde o CARD-011.

## Riscos

- **A revisão reprova, e o motivo pode ser qualquer um.** É o risco de
  calendário, e a mitigação é planejar múltiplas tentativas.
- **A URL da API fica gravada no build.** Errar significa versão nova e revisão
  nova. Merece conferência dupla.
- **Cobrar exige a burocracia fiscal aprovada**, que tem prazo próprio e
  independente do técnico. Começar por ela é contraintuitivo e correto.
- **Screenshots exigem um app apresentável**, o que amarra este card ao estado
  visual do produto — se as telas de exceção (CARD-027) e a UI de correções
  (CARD-016) não estiverem prontas, não há o que fotografar.

## Objetivo de aprendizado

Entender **o que muda entre um dev build e um build de release em Expo/RN** — e
por que a diferença não é uma flag: o dev build carrega o JavaScript de um
bundler na rede (foi por isso que o CARD-037 teve de recompilar quando o IP
mudou), e o release **embarca o bundle**. É a diferença entre um binário que
depende do seu Mac estar ligado e um que não depende de nada — e ela explica,
retroativamente, metade dos problemas que o CARD-037 encontrou.
