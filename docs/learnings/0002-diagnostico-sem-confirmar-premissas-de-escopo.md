# LEARNING-0002 — Diagnóstico produzido sobre premissa de escopo não confirmada

- **Data:** 2026-08-17
- **Card/sessão relacionado:** sessão P1 (diagnóstico arquitetural) → revisada em P1.5

## Sintoma

O diagnóstico arquitetural (commit b70b5e2) tratou o WhatsApp/Twilio como canal
permanente do produto: 4 achados (F1, F2, F4, F11), 2 itens do checklist e
parte do veredito foram construídos sobre essa premissa. Dias depois, a decisão
de descontinuar o canal (ADR-0001) tornou esses achados obsoletos e exigiu uma
sessão inteira de revisão (P1.5).

## Causa raiz

A premissa "o canal atual é produto ou andaime?" nunca foi perguntada nem
declarada — foi **assumida silenciosamente** a partir do estado do código.
Diagnóstico técnico herda o escopo de produto vigente; se o escopo está em
aberto na cabeça do desenvolvedor e ninguém pergunta, o artefato nasce com
data de validade desconhecida. Não foi erro de análise: cada achado estava
correto **dentro da premissa errada**.

## Como descobri

O desenvolvedor trouxe a mudança de escopo já redigida (novo bloco ESCOPO DO
CANAL no documento do harness), com P1.5 criado especificamente para propagar
a correção — evidência de que o retrabalho foi percebido como evitável.

## Como evitar

Antes de qualquer sessão de análise ou planejamento (diagnóstico, arquitetura
alvo, roadmap), listar explicitamente as premissas de escopo de produto das
quais as conclusões vão depender — em especial **o que do sistema atual é
permanente vs. andaime** — e pedir confirmação do desenvolvedor antes de
produzir o artefato. Uma pergunta de 30 segundos ("o WhatsApp fica ou é
andaime?") teria poupado a sessão de revisão.

## Regra criada no CLAUDE.md

> **Premissas de escopo antes de análise:** toda sessão de análise ou
> planejamento (diagnóstico, arquitetura, roadmap) começa declarando as
> premissas de escopo de produto das quais as conclusões dependem — em
> especial o que é permanente vs. andaime no sistema atual — e as confirma
> com o desenvolvedor antes de produzir o artefato. Premissa não confirmada
> é anotada como tal no próprio artefato.

Adicionada à seção "Regras de trabalho" do CLAUDE.md.
