# docs/design — o design do app mobile

| Arquivo | O que é |
|---|---|
| `Design.pdf` | o entregável original do Claude Design (8 páginas, artboards em imagem) |
| `prompt-claude-design-mobile.md` | o prompt que o gerou, em 2026-08-17 |
| `artboards/` | as mesmas telas extraídas do PDF em PNG, **legíveis por qualquer sessão sem ferramenta externa** |
| `briefing-produto-para-design-2026-08-27.html` | **o briefing entregue à designer** — regras de negócio, fluxos e o que é lei × o que está em aberto |
| `briefing-produto-para-design-2026-08-27.pdf` | o mesmo, em PDF, para circular por e-mail |

Os PNGs foram extraídos do próprio PDF (mesmas imagens, sem reprocessamento). O
PDF não tem texto extraível — são páginas de imagem —, e a extração existe porque
ler o design **é pré-requisito** para implementar tela, e depender de `poppler`
instalado na máquina torna isso opcional na prática.

## Índice dos artboards

| # | Arquivo | Conteúdo |
|---|---|---|
| 01 | `01-conversa-light-idle.png` | tela de conversa, **light**, estado idle — "Toque para falar" |
| 02 | `02-conversa-dark-idle.png` | a mesma, **dark** |
| 03 | `03-estado-transcrevendo.png` | "Transcrevendo sua fala…" · *Passo 1 de 3* |
| 04 | `04-estado-professor-pensando.png` | "O professor está pensando…" · *Passo 2 de 3* |
| 05 | `05-estado-texto-primeiro-audio-a-caminho.png` | "Áudio a caminho… / Você já pode ler; o áudio toca sozinho quando chegar" |
| 06 | `06-estado-audio-pronto-player.png` | player com scrub, `0.75×`, `traduzir`, `repetir` |
| 07 | `07-card-de-correcao-anatomia.png` | o card de correção anatomizado, com as 5 regras de tom |
| 08 | `08-correcoes-uma-tres-e-sem-erro.png` | 1 correção · 3 empilhadas · o estado "sem erro" |
| 09 | `09-resumo-pos-sessao.png` | "Você falou inglês por 8 minutos hoje" + correções por tipo |
| 10 | `10-historico.png` | lista de sessões, com "áudio expirado — transcrição permanece" |
| 11 | `11-login-registro-com-convite.png` | e-mail + senha + código de convite, com erro inline |
| 12 | `12-perfil-nivel-e-quota.png` | faixa CEFR, quota do dia, autoplay, tema |
| 13 | `13-overlay-permissao-de-microfone.png` | "Precisamos do microfone" → Abrir Ajustes / Agora não |
| 14 | `14-overlay-offline-fala-guardada.png` | "Sua fala está guardada aqui" |
| 15 | `15-overlay-quota-atingida.png` | "Por hoje é isso — 20 min falados" |
| 16 | `16-overlay-pausado-e-timeout.png` | "As aulas estão pausadas" (orçamento) e "Demorou mais que o normal" |
| 17 | `17-style-guide.png` | **paleta com os hex, tipografia e controles** |

## O style guide, em texto (do artboard 17)

| Papel | Light | Dark |
|---|---|---|
| fundo | `#F7F5F2` | `#121211` |
| superfície | `#FFFFFF` | `#1A1918` |
| tinta | `#171614` | `#F2F0EC` |
| secundário | `#6E6A62` | — |
| acento | `#B44B31` | `#E4795C` |

**Tipografia: Instrument Sans.** Display 30/600 (títulos de tela) · Correção
19/600 (forma correta) · Corpo 16.5/400 (resposta do professor) · Apoio 13.5/400
(explicação, microcopy) · Rótulo 9.5/600 com tracking .16em.

**Controles:** alvo mínimo **48px**. Botão de gravar **84px** ("alcance do
polegar"); **pulso = gravando**, **quadrado = parar**.

## Duas coisas que este design **não** cobre, e é importante saber antes de abrir

1. **Não existe artboard do estado "gravando".** O prompt original pedia
   (estado `b`) e ele não foi entregue — e é justamente o coração do CARD-011.
   O que existe para derivá-lo é o style guide: 84px, pulso, quadrado para parar.
2. **A ordem de entrega desenhada está invertida em relação ao produto atual.**
   Ver a seção abaixo — é a divergência mais cara de não perceber.

## O design é de 2026-08-17. A cascata é de 2026-08-19.

O design foi desenhado **antes** dos ADRs 0022/0023/0026 e antes da medição que
mostrou o primeiro trecho de áudio em **1,6 s**. Três coisas nele descrevem um
produto que não existe mais:

| No design | No produto de hoje | Fonte |
|---|---|---|
| "resposta em texto chega primeiro (~5–6 s); áudio pronto em ~10–15 s" — artboard 05, *"Você já pode ler; o áudio toca sozinho quando chegar"* | **o áudio vem PRIMEIRO**, em 3–6 trechos, e o texto do feedback fecha **depois** do último trecho | ADR-0022, ADR-0023 |
| *"Passo 1 de 3 · você pode guardar o telefone, avisamos com som"* — artboard 03 | com 1,6 s até a primeira palavra, mandar o aluno guardar o telefone é errado | `medicao-latencia.md`, CARD-009 |
| um player só, com uma duração (`0:12`) — artboard 06 | 3–6 trechos tocados em sequência, com prefetch e gap < 150 ms | ADR-0023, CARD-012 |

E `reiniciar demo` / `a. idle` no rodapé do artboard 01 são **andaime de
apresentação**, não UI do produto — é a premissa P2 de
`docs/reconciliacao-telas-dominio.md`, registrada lá como **não confirmada**.

> **A regra, para qualquer sessão que use este design:** a direção visual
> (paleta, tipografia, tom, anatomia do card de correção) é para seguir. A
> **sequência de estados** é para reconciliar contra os ADRs — o design não
> perdeu validade, ele foi desenhado sob outro orçamento de latência.


## O briefing para a designer (2026-08-27)

O briefing é o documento entregue a quem vai cuidar de UI/UX. Ele **não repete**
este README: enquanto aqui está o histórico de como o design chegou onde chegou,
lá está o que o produto faz hoje, escrito do ponto de vista de quem usa — sem
`Turn`, `Session` nem `TurnStage`, com uma tabela de vocabulário amarrando os
dois lados.

O que ele carrega e vale conhecer antes de mexer em qualquer tela:

- **a cascata explicada como mecanismo**, com os tempos medidos, e o que ela
  **proíbe** na tela (nada de "aguarde", nada de barra de 3 passos, nada de
  duração total durante a reprodução);
- **cada regra marcada como Lei, Feito ou Aberto** — é a primeira pergunta de
  quem entra num produto existente ("o que eu posso mudar?"), respondida regra a
  regra em vez de em prosa;
- **as seis perguntas em aberto**, da mais cara para a mais barata, começando
  pela tela que não existe: professor falando enquanto o feedback ainda vem.

**Ele é derivado do código e das decisões registradas, não de memória — e é uma
foto, não um espelho.** Quando uma regra mudar aqui (um ADR novo, um card
fechando uma decisão), a foto envelhece e nada avisa. Daí a **data no nome**: uma
revisão nova é um arquivo novo, com a data do dia, e o anterior fica como
registro do que a designer recebeu naquele momento. Vale reler as seções de regra
ao fechar qualquer card das Fases 2 e 3.

O HTML e o PDF têm o mesmo conteúdo; o PDF é a versão de papel (A4, seção nova a
cada página, fontes embutidas) e o HTML é a versão que também está publicada como
página, onde a designer pode comentar.

Ele usa a paleta e a tipografia do próprio app (o artboard 17 e o
`theme/tokens.ts`), de propósito: a designer já abre o documento vendo a
linguagem visual com que vai trabalhar.
