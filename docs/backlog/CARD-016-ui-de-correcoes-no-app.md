# CARD-016 — UI de correções estruturadas + resumo mínimo de sessão no app

- **ID:** CARD-016 · **Épico:** Fase 2 — Domínio pedagógico
- **Plataforma:** mobile · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-012, CARD-013

## Contexto

Diagnóstico §7.4: formatar feedback no servidor era decisão de canal; agora
o cliente renderiza dados estruturados. É o momento em que o app deixa de
mostrar texto e passa a mostrar **pedagogia**.

## Problema

As Corrections persistem mas o aluno não as vê; o valor do produto está
invisível.

## Proposta técnica

- Componente de card de correção: original riscado, forma correta em
  destaque, explicação, badge de tipo e severidade — renderização por
  dados, mantendo o espírito do card do protótipo ("You said / Better way /
  Tip") sem markdown de canal.
- Regra de produto preservada: sem correções ⇒ sem card (resposta só em
  áudio, natural — decisão do protótipo que o diagnóstico §5 mandou manter).
- Lista da conversa na tela (turns da sessão atual com áudio + correções).
- Resumo mínimo ao encerrar: contagem de correções por tipo da sessão
  (fundação do resumo pós-sessão completo da Fase 6).
- Botão "traduzir" por resposta chamando a tradução on-demand (se o endpoint
  já existir; senão, entra no escopo aqui — decisão na sessão).

## Escopo

- **In:** o acima. **Out:** histórico entre sessões — **revisto em 2026-08-27**:
  a consulta rápida de 30 dias volta para o app no [CARD-029](CARD-029-historico-de-sessoes-no-app.md)
  (o artboard 10 sempre a desenhou no mobile, com a análise completa na web); o
  que continua em Out aqui é a análise completa; CEFR (Fase 6); polimento visual
  além do legível.

## Critérios de aceite

- **Dado** um turn com 2 correções, **então** os 2 cards aparecem com tipo,
  original, correção e explicação.
- **Dado** um turn sem erros, **então** nenhum card aparece e o áudio toca
  normalmente.
- **Dado** o fim da sessão, **então** vejo o total de correções por tipo.

## Riscos

Primeira UI de dados em RN — tentação de componentizar demais cedo; começar
concreto, extrair componente na segunda repetição.

## Objetivo de aprendizado

Renderização de listas no RN (FlatList vs map, keys, performance básica) e
composição de componentes com TypeScript estrito sobre os tipos gerados —
o contrato do backend dirigindo a UI.

## Ajuste da reconstrução (2026-08-19)

**Mantido**, com um ajuste de ordem de apresentação: com a cascata, o áudio
começa **antes** do feedback estar pronto (ADR-0022 pôs `spoken_reply` primeiro).
A tela não pode assumir que texto e áudio chegam juntos — o card de correção
entra na tela enquanto o professor ainda fala.


## Ajuste da varredura do design (2026-08-27)

Dois recortes, nenhum aumento de escopo:

- **Os estados que esta tela usa são decididos no [CARD-028](CARD-028-estados-do-turno-redesenhados-contra-a-cascata.md)**,
  que roda antes. Este card renderiza pedagogia **sobre** uma máquina de estados
  já reconciliada com a cascata — não a inventa de passagem.
- **O botão `traduzir`** do artboard 06 continua aqui, mas a decisão sobre as
  outras três affordances do player (scrub, `0.75×`, `repetir`) é do CARD-028.
