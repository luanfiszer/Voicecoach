# ADR-0068 — Provedor de e-mail transacional: Resend, com console como default de custo zero

- **Status:** aceito
- **Data:** 2026-09-13
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **1 — introduz uma
  dependência externa** (um serviço de terceiro, envio de e-mail
  transacional); **3 — afeta custo recorrente** (o ADR-0010 restringia gasto
  externo ao Claude; este ADR abre uma segunda categoria); **4 — afeta
  segurança/privacidade** (o link de confirmação de e-mail é a porta de
  entrada da conta).
- **Relacionado:** ADR-0007 (decisão original de auth, que já previa
  "verificação de e-mail obrigatória" sem escolher provedor), ADR-0010
  (política de custo), ADR-0027 (fallback silencioso entre adapters é
  proibido — o mesmo padrão se aplica aqui), CARD-049

## Contexto

O ADR-0007 desenhou e-mail+senha com verificação obrigatória antes do
primeiro turn, mas deixou o provedor de e-mail sem escolher — item explícito
do CARD-049 ("um provedor de e-mail transacional entra no projeto, e isso é
ADR obrigatório"). Sem essa escolha, o cadastro não tem como confirmar que o
endereço existe.

**A restrição que mais pesa: este é um projeto de aprendizado a custo zero
(ADR-0010), sem domínio próprio ainda** — o backend só saiu do Mac
recentemente, e a URL pública estável (CARD-055) não existe. Qualquer
provedor escolhido hoje vai operar em modo "sandbox" até esse card entregar
um domínio verificado.

## Decisão

**1. Resend como provedor pago-quando-usado, com free tier permanente
(3.000 e-mails/mês, 100/dia) sem cartão de crédito.** API REST simples (um
`POST` com `from`/`to`/`html`), sem exigir um SDK — `httpx`, já presente no
projeto, basta.

**2. Um adapter de console é o DEFAULT, não o Resend.** `EMAIL_PROVIDER`
(config) escolhe entre `console` (escreve o link no log — zero custo, zero
conta de terceiro, funciona hoje) e `resend`. A escolha é explícita e uma
configuração incompatível **levanta na subida** (`EMAIL_PROVIDER=resend` sem
`RESEND_API_KEY`) — nunca cai para o console em silêncio, mesmo princípio do
ADR-0027 item 3 para o adapter de STT.

**3. Limitação aceita e documentada, não escondida: sem domínio verificado,
o remetente sandbox (`onboarding@resend.dev`) só entrega para o e-mail da
PRÓPRIA conta Resend** — não para um aluno qualquer. Isto significa que o
fluxo de confirmação de e-mail **não pode ser testado ponta a ponta com um
destinatário arbitrário** até o CARD-055 (domínio) existir. O mecanismo
(geração de token, hash, expiração, endpoint de confirmação) está
implementado e testado inteiramente sem depender disso — é só o "clique
funciona de qualquer caixa de entrada" que fica bloqueado.

**4. Nenhuma credencial real entra neste commit.** `RESEND_API_KEY` não
existe no `.env` desta sessão (loop autônomo, CLAUDE.md: "não lide com
segredo real") — o adapter Resend está implementado e testado com
`httpx.MockTransport` (sem rede), mas nunca foi exercitado contra a API real.
**Pendente de revisão humana:** criar a conta Resend, gerar a chave, decidir
se/quando verificar um domínio.

## Alternativas consideradas

### Alternativa A — SendGrid

Free tier histórico (100/dia), mas a Twilio (dona do SendGrid) vem
restringindo cadastros novos sem cartão e sem verificação de negócio — fricção
alta para um projeto pessoal. SDK mais pesado. Rejeitada por fricção de
cadastro, não por preço.

### Alternativa B — AWS SES

Custo por e-mail menor que qualquer um dos dois (fração de centavo), mas
**começa em sandbox que só permite enviar para endereços verificados
manualmente um a um** — pior que o sandbox do Resend, que ao menos permite o
e-mail da própria conta sem verificação extra. Exigiria abrir uma conta AWS
só para isto, mais uma superfície de configuração (IAM, região) para um
volume de e-mail que hoje é zero.

### Alternativa C — Brevo (ex-Sendinblue)

Free tier maior em volume (300/dia, permanente), mas SDK e API mais
verbosos, e a documentação de sandbox é menos clara sobre o que exatamente
funciona sem domínio verificado. Ficou em segundo lugar — sem gatilho
concreto para reabrir, é troca de gosto, não de capacidade.

### Alternativa D — nunca integrar um provedor real; console para sempre

Custo zero literal, para sempre. Rejeitada: o card exige que a conta
**exista e o reenvio funcione** mesmo quando o e-mail falha — sem provedor
real, o produto nunca teria como confirmar conta nenhuma fora do
desenvolvedor lendo o próprio log, o que não é um app público.

## Consequências

- **Positivas:** cadastro por e-mail (ADR-0007) deixa de ser uma promessa
  sem mecanismo; o custo zero do ADR-0010 é preservado em desenvolvimento
  (console) sem bloquear o caminho para produção (Resend); nenhuma
  dependência nova de biblioteca — `httpx` já estava no projeto.
- **Negativas:** o remetente sandbox limita quem recebe e-mail de verdade
  até existir domínio (CARD-055) — dívida explícita, não escondida. O
  adapter Resend nunca foi testado contra a API real nesta sessão (sem
  chave). Um segundo provedor no catálogo (se o Resend mudar de política)
  exigiria um adapter novo — a porta `EmailSender` já existe para isso, mas
  o trabalho não é zero.
- **Pendente de revisão humana:** criar a conta Resend e gerar
  `RESEND_API_KEY`; decidir se o e-mail de verificação já vale a pena
  configurar com um domínio próprio antes do CARD-055, ou esperar o deploy.
- **Equivalente mental .NET:** a porta `IEmailSender` do ASP.NET Identity —
  o framework define a interface, quem registra o `SmtpClient`/provider real
  no `Program.cs` é a composition root; aqui é a mesma forma, com um
  `ConsoleEmailSender` como o `NullEmailSender` que muitos templates do
  ASP.NET usam em desenvolvimento.
