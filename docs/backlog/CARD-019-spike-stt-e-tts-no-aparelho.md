# CARD-019 — Spike: STT e TTS no aparelho do aluno (avaliação, sem compromisso de adoção)

- **ID:** CARD-019 · **Épico:** Fase 2 — Proteção de margem
- **Plataforma:** mobile/IA · **Esforço:** P · **Status:** backlog
- **Dependências:** CARD-012 (a fatia vertical precisa estar medida antes)

## Contexto

A alavanca **I** da [análise de custo §11](../analise-custo-e-precificacao.md):
rodar STT e TTS **no aparelho** zeraria o compute de servidor e o tráfego de
áudio nos dois sentidos, deixando só o LLM como custo. A medição desta semana
dá o argumento: `mlx-whisper small.en` transcreve 17,6 s de áudio em **0,59 s**
num M4 usando a GPU, e o chip de um iPhone recente é da mesma família.

A rejeição registrada em §11 foi: *"esvazia a prioridade nº 1 declarada do
projeto"* — o aprendizado de backend. **Esse argumento expirou com a virada de
eixo**, e o desenvolvedor pediu (2026-08-19) que a alavanca fosse avaliada.

## Por que agora

**Agora significa depois do CARD-012, e isso é deliberado.** A regra de
desempate manda não atrasar a latência nem a fatia vertical; e sem o número
ponta a ponta do CARD-012 não há baseline contra o qual comparar. Antes disso, o
spike compararia contra uma estimativa.

## Problema

A economia é grande e a decisão é cara de reverter. Hoje ela está registrada
como palpite: *"o TTS do sistema operacional é gratuito e instantâneo"* — não
medido, e qualidade de voz é exatamente onde este produto não pode piorar.

## Proposta técnica — é um spike, o entregável é conhecimento

Timebox de **uma sessão**. Mede, no aparelho físico:

1. **STT on-device**: latência e qualidade de transcrição de fala de aprendiz
   (com sotaque e hesitação — o insumo que a medição §3.4 diz faltar).
2. **TTS do sistema** (iOS `AVSpeechSynthesizer` / Android TTS): latência até o
   primeiro áudio e **qualidade percebida contra o Kokoro/Piper**, na mesma
   frase. É o critério que decide, não a latência.
3. **O que sobra de arquitetura**: se STT e TTS saem do worker, o que resta lá
   dentro é a chamada ao LLM — e a cascata muda de lugar, não some. Descrever o
   desenho resultante em meia página **é parte do entregável**.
4. **O custo escondido**: tamanho do app, primeiro download de modelo no
   aparelho, aparelhos antigos, e o fato de o backend perder a transcrição
   como dado confiável (o cliente passa a poder mentir).

## Escopo

- **In:** medição no aparelho, comparação de qualidade, desenho resultante,
  recomendação escrita.
- **Out:** **qualquer implementação de produção.** Se a recomendação for adotar,
  isso vira ADR (contraria ADR-0003 e ADR-0011 — critério 6) e cards próprios.

## Critérios de aceite

- **Dado** a mesma frase, **então** existe tabela comparando latência e
  qualidade percebida entre TTS do sistema e TTS local do servidor.
- **Dado** fala de aprendiz real, **então** existe a primeira medida honesta de
  qualidade de STT do projeto — que a medição §3.4 registrou como pendência 1.
- **Dado** o fim do timebox, **então** há recomendação escrita com um veredito
  entre três: adotar (com ADR), adiar com gatilho novo, ou descartar.

## Riscos

Spike vira implementação disfarçada. Mitigação: timebox e a proibição explícita
de código de produção acima. E o resultado pode ser "não vale" — o que também é
entrega: fecha uma alavanca que hoje fica voltando à mesa.

## Objetivo de aprendizado

O limite entre o que o Expo entrega e o que exige módulo nativo — e como se
mede qualidade de voz sem cair em preferência estética.
