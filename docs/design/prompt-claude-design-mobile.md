# Prompt para Claude Design — Voicecoach Mobile

> Gerado na sessão pós-P3 (2026-08-17). Cole o bloco abaixo no Claude Design.
> Fonte dos requisitos: visão §A/§D, cards 011/012/016, ADRs 0002/0003/0010.

---

Crie o design de um app mobile (iOS e Android, React Native/Expo) chamado
**Voicecoach**: um tutor pessoal de inglês por conversa de áudio para
brasileiros. O aluno fala inglês no microfone, o professor (IA) responde em
áudio com correções estruturadas. A interface é em português (pt-BR); o
conteúdo de aprendizado é em inglês.

## Conceito do produto

Não é um chat de texto com botão de áudio — é um app **voice-first**: a ação
central da experiência é falar. Cada resposta do professor pode vir com
correções tipadas (gramática, vocabulário, preposição, ordem de palavras),
que são o valor pedagógico do produto. O aluno acumula progresso (nível CEFR
estimado como faixa, ex. "A2–B1", e contagem de correções por tipo).

## Telas a desenhar (artboards separados, com variações de estado)

### 1. Tela de conversa (a tela principal — 80% do tempo de uso)
- Botão de gravação grande, central-inferior, alcançável com uma mão — é o
  herói da interface.
- Lista da conversa da sessão atual acima: turnos do aluno (transcrição da
  fala) e respostas do professor (player de áudio + texto da resposta).
- **Estados do botão/tela (desenhar todos):**
  a. idle (pronto para gravar)
  b. gravando (indicador de nível de áudio + tempo decorrido + limite de
     duração visível; parar/descartar)
  c. gravação concluída (ouvir o que gravei / regravar / enviar)
  d. enviando
  e. "transcrevendo…" (~2–4s)
  f. "professor pensando…" (~3–4s)
  g. **resposta em texto chega primeiro** (~5–6s após envio): transcrição +
     correções aparecem enquanto o áudio ainda é sintetizado — indicar
     sutilmente que o áudio está a caminho
  h. áudio pronto (~10–15s): player em destaque, autoplay opcional
- A progressão e→f→g→h deve parecer viva e curta — microcopy honesta e
  motion sutil, nunca spinner genérico parado.
- Ação secundária por resposta: "traduzir" (mostra tradução pt-BR sob
  demanda, recolhível).
- Indicador discreto de quota restante do dia (ex.: "12 min restantes hoje").

### 2. Card de correção (componente-chave, dentro da conversa)
- Aparece **somente quando há erro** (sem erro = só a resposta em áudio,
  natural).
- Anatomia: trecho original riscado → forma correta em destaque → explicação
  curta em inglês simples → badge do tipo de erro (grammar / vocabulary /
  preposition / word order / other) e severidade (sutil, não alarmante).
- Tom visual: encorajador, nunca punitivo — correção como presente, não
  como nota vermelha.
- Desenhar variação com 1 correção e com 2–3 correções no mesmo turno.

### 3. Resumo pós-sessão
- Ao encerrar: duração da sessão, nº de turnos, correções por tipo
  (visualização simples), destaque de 1 acerto ("hoje você usou o past
  perfect corretamente").
- CTA: encerrar / revisar correções.

### 4. Histórico (resumido)
- Lista de sessões passadas: data, duração, nº de correções, acesso à
  conversa. (A análise profunda vive no app web — aqui é consulta rápida.)

### 5. Login / registro
- E-mail + senha + **código de convite** (produto é fechado por convite).
- Estados de erro inline (convite inválido, credenciais erradas).

### 6. Perfil / configurações (mínima)
- Nível CEFR estimado como faixa com explicação honesta ("estimativa, não
  certificação"); quota diária; sair.

### 7. Estados de sistema (desenhar como componentes/overlays)
- Permissão de microfone negada (com caminho para configurações)
- Sem conexão / falha de envio (retry visível)
- Quota diária atingida ("volte amanhã" — honesto e leve, com horário)
- Serviço pausado por orçamento (mensagem honesta, sem jargão)
- Áudio antigo expirado no histórico (transcrição permanece, áudio
  indisponível)
- Timeout de processamento (tentar de novo)

## Requisitos não funcionais que moldam o design

- **Latência real**: texto da resposta em ~5–6s, áudio em ~10–15s. Os
  estados de espera são parte central do design — a espera deve parecer
  progresso, não travamento.
- **Uso com uma mão e com fones**: controles principais na metade inferior;
  o app deve funcionar bem sem olhar (prática ao caminhar).
- **Acessibilidade**: alvos de toque ≥ 44pt, contraste AA, suporte a
  dynamic type sem quebrar o layout.
- **Light e dark mode** (desenhar a tela de conversa nos dois).
- **Safe areas** iOS/Android; componentes viáveis em React Native (nada de
  efeitos que só existem em SwiftUI).

## Direção visual — minimalista e moderno

- Base neutra (off-white / near-black no dark) + **uma única cor de acento**
  usada com intenção (botão de gravar, estados ativos, acertos).
- Tipografia como protagonista: hierarquia forte, generosa, uma família só
  (ex. Inter ou similar); o texto em inglês corrigido merece tratamento
  tipográfico cuidadoso (riscado/destaque legíveis, não poluídos).
- Muito espaço em branco; poucos elementos por tela; nada de gradientes
  chamativos, sombras pesadas ou gamificação visual (sem confete, sem
  mascote).
- Ícones de linha, consistentes e mínimos.
- Motion sutil e funcional: a onda de áudio ao gravar e a transição
  texto→áudio da resposta são os dois únicos momentos de animação expressiva.
- Sensação-alvo em uma frase: **calma, focada e adulta — um tutor
  particular, não um jogo de aprender inglês.**

## Entregáveis

- Artboards mobile (390×844) para as telas 1–6, com as variações de estado
  da tela 1 (mínimo: idle, gravando, professor pensando, resposta em texto,
  áudio pronto) e os estados da seção 7 como overlays/componentes.
- Tela de conversa em light e dark.
- Mini style guide num artboard: paleta, tipografia, botões, o card de
  correção anatomizado.
