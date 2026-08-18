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

- **In:** o acima. **Out:** histórico entre sessões (web, Fase 5); CEFR
  (Fase 6); polimento visual além do legível.

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
