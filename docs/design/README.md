# docs/design — o design do app mobile

| Arquivo | O que é |
|---|---|
| `Design.pdf` | o entregável original do Claude Design (8 páginas, artboards em imagem) |
| `prompt-claude-design-mobile.md` | o prompt que o gerou, em 2026-08-17 |
| `artboards/` | as mesmas telas extraídas do PDF em PNG, **legíveis por qualquer sessão sem ferramenta externa** |

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

## Varredura de 2026-08-27 — quem é dono de cada artboard

Cruzamento dos 17 artboards com o backlog. **Cinco não tinham dono nenhum**, e o
padrão é que cada card de cliente empurrou a metade de exceção para "Out" sem
que ninguém a recolhesse.

| # | Dono |
|---|---|
| 01, 02 | CARD-011 — **implementado**. O chip *"12 min hoje"* do cabeçalho é backend do **CARD-033** |
| 03, 04, 05 | **CARD-028** — decide o que sobrevive à cascata (ver aviso acima) |
| 06 | **CARD-028** (o que a tela mostra) + **CARD-035** (`0.75×`, `repetir`, scrub sobre a fila) + **CARD-036** (o endpoint do `traduzir`) |
| 07, 08 | CARD-016 |
| 09 | CARD-016 (tela) + **CARD-031** (o "Encerrar" e o resumo, no servidor) + Fase 6 (completo) |
| 10 | **CARD-029** (tela) + **CARD-030** (`GET /v1/sessions` agregado e a mídia expirada) |
| 11 | Fase 3 (auth) — sem card ainda, e é o correto |
| 12 | Fase 3 (auth) — sem card de tela ainda. O saldo de cota é o **CARD-033** |
| 13 | CARD-011 — **implementado** |
| 14, 15, 16 | **CARD-027** (telas). Backend: **CARD-031** (fala atrasada em sessão encerrada), **CARD-032** ("Descartar"), **CARD-033** (quota e serviço pausado) |
| 17 | `apps/mobile/src/theme/tokens.ts` — **implementado** |

**O que o design NÃO cobre e o produto precisa** (entra pelo CARD-028): a tela de
*"áudio tocando, feedback a caminho"* — o estado central da cascata, e o único
sem desenho. O artboard 05 descreve o inverso dele.

**Toda tela tem os dois lados.** A varredura criou três cards de tela (027, 028,
029), quatro de backend (030–033) e mais três depois que as decisões de produto
foram fechadas em 2026-08-27 (034, 035, 036). A regra que os separa: o card de tela decide
o que o aluno **vê**; o card de backend decide a **regra de negócio, o contrato
e a consulta** que sustentam aquilo — e nasce antes.

**O que está desenhado e foi recusado:** *"Avisar quando voltar"* (artboard 16) é
push, cortado pela visão §F com gatilho escrito. Está em "Out" do CARD-027.
