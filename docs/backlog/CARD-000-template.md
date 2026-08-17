# CARD-000 — [Título curto e acionável]

- **ID:** CARD-000
- **Épico:** [fase/tema do roadmap a que pertence]
- **Esforço:** P | M | G *(deve caber em uma sessão de trabalho — se for G, quebre antes de começar)*
- **Status:** backlog | em andamento | bloqueado | concluído
- **Dependências:** [CARD-XXX, ADR-XXXX ou "nenhuma"]

## Contexto

Por que este card existe agora. Que estado do sistema ou decisão anterior
o motivou.

## Problema

O que está errado, faltando ou em risco. Concreto, com evidência
(arquivo:linha quando aplicável).

## Proposta técnica

Como resolver. Bibliotecas envolvidas e por quê. Se houver decisão
arquitetural embutida, referencie (ou crie) o ADR.

## Escopo

- **In:** o que este card entrega
- **Out:** o que explicitamente NÃO entra (e onde entra, se souber)

## Critérios de aceite

> Formato Dado/Quando/Então. Verificáveis por teste automatizado sempre
> que possível.

- **Dado** [estado inicial], **quando** [ação], **então** [resultado observável]
- ...

## Riscos

O que pode dar errado ao implementar, e o plano B.

## Objetivo de aprendizado

> Obrigatório e específico.
> Ruim: "aprender SQLAlchemy".
> Bom: "entender a diferença entre session scope e unit of work no
> SQLAlchemy 2.0 e por que difere do DbContext".

O que EU vou aprender de Python/React ao executar este card.
