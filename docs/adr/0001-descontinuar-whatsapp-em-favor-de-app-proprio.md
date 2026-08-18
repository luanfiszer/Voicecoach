# ADR-0001 — Descontinuar WhatsApp/Twilio em favor de app mobile próprio + web companion

- **Status:** aceito
- **Data:** 2026-08-17

## Contexto

O protótipo nasceu sobre o WhatsApp via Twilio Sandbox por três razões válidas
à época: custo zero de distribuição (o aluno já tem WhatsApp), zero código de
cliente (Twilio entrega captura e playback de áudio de graça) e time-to-first-demo
de horas. Era o andaime certo para validar o núcleo pedagógico
(STT → LLM → TTS com correções estruturadas).

O andaime deixou de servir quando os objetivos do projeto se firmaram:

1. **Aprendizado de React/React Native é objetivo de primeira classe** — e o
   WhatsApp não tem frontend a construir.
2. **O produto imaginado (sessões, progresso, revisão espaçada, relatórios)
   não cabe num thread de mensagens** — exige UI própria.
3. **O canal impõe tetos técnicos**: interação estritamente turn-based, resposta
   como MP3 completo por URL pública, webhook público como superfície de ataque
   (F1/F2 do diagnóstico), identidade = número de telefone, limites do Sandbox.
4. **Dependência de plataforma**: políticas do WhatsApp Business e preços do
   Twilio são variáveis fora do nosso controle no caminho crítico do produto.

## Decisão

Descontinuar o WhatsApp/Twilio como canal. O produto passa a ser:

- **App mobile (iOS e Android)** — carro-chefe; onde a conversa por áudio acontece.
- **App web** — companion: progresso, histórico, correções acumuladas, erros
  recorrentes, onboarding, gestão de conta.
- **Backend Python** — API própria consumida pelos dois clientes.

O protótipo WhatsApp permanece no repositório como referência executável do
núcleo pedagógico até a paridade, mas não recebe investimento (nem os patches
de segurança F1/F2 — a mitigação é não expô-lo via ngrok).

## Alternativas consideradas

### Alternativa A — Manter WhatsApp como canal único
- O que é: evoluir o produto inteiro dentro do WhatsApp (persistência, nível
  CEFR, relatórios via mensagens formatadas).
- Por que foi rejeitada: mata o objetivo de aprendizado React/React Native
  (metade da prioridade declarada do projeto); relatório de progresso e revisão
  espaçada viram texto corrido num chat — UX inadequada ao produto; mantém as
  superfícies de ataque e os tetos do canal; portfolio resultante não demonstra
  frontend.

### Alternativa B — Manter WhatsApp como canal adicional ao lado do app
- O que é: app mobile/web como principal, WhatsApp como segundo adapter de
  entrada permanente.
- Por que foi rejeitada: dobra a superfície de manutenção (webhook público,
  assinatura Twilio, idempotência por MessageSid, allowlist — tudo continua
  existindo em paralelo ao stack de auth do app) para um canal que não é o foco;
  duas identidades de usuário (telefone vs conta) precisariam de vinculação —
  complexidade real sem usuário real que a justifique. Gatilho para reabrir:
  demanda comprovada de usuários que não instalariam o app.

### Alternativa C — Descontinuar (escolhida)
- Corte limpo do canal; ver Decisão.

## Consequências

**Positivas**
- O currículo de aprendizado passa a cobrir o stack completo declarado
  (Python + React/React Native).
- Some a superfície de ataque do webhook público e toda a lógica de canal
  Twilio (~40% do código atual, ver diagnóstico § Revisão pós-mudança de escopo).
- Controle total da UX: sessões explícitas, playback com controle, UI de
  correções estruturadas em vez de markdown de WhatsApp.
- Identidade real de usuário (conta) em vez de número de telefone.

**Negativas — o preço aceito**
- **Perdemos distribuição sem atrito.** O aluno tinha o canal instalado;
  agora precisa achar, baixar e instalar um app. Para um produto de portfólio
  o custo é aceitável; para um negócio seria a decisão mais cara deste documento.
- **Ganhamos ciclo de publicação em loja**: contas de desenvolvedor pagas
  (Apple ~US$ 99/ano, Google US$ 25), revisão com prazo fora do nosso controle,
  política de privacidade obrigatória (processamos voz — implicação de LGPD).
- **Responsabilidades que eram do Twilio passam a ser nossas**: captura e
  playback de áudio, permissões de microfone, upload com retry, comportamento
  offline, push notifications, entrega em dois sistemas operacionais.
- **Proteção de custo fica mais difícil**: a allowlist por número era uma
  proteção binária eficaz; cadastro aberto exige quotas por conta, verificação
  de e-mail, limites para contas novas e alertas de gasto **antes** de qualquer
  lançamento.
- Tempo até a primeira demo do novo stack é maior — aceito explicitamente,
  velocidade não é prioridade.

**Equivalente mental .NET:** trocar um BFF acoplado a um canal de terceiros
por uma API própria multi-cliente — o domínio não muda, os adapters de borda
sim.
