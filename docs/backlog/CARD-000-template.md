# CARD-000 — [Título curto e acionável]

- **ID:** CARD-000
- **Épico:** [fase/tema do roadmap a que pertence]
- **Esforço:** P | M | G *(deve caber em uma sessão de trabalho — se for G, quebre antes de começar)*
- **Status:** backlog | em andamento | bloqueado | concluído
- **Dependências:** [CARD-XXX, ADR-XXXX ou "nenhuma"]

## Contexto

Por que este card existe agora. Que estado do sistema ou decisão anterior
o motivou.

Se o card corrige algo que já existe, **classifique o débito** — os dois pedem
remédios diferentes e confundi-los faz refatorar o que devia ser reescrito:

- **Débito de negócio** — a regra estava errada ou mudou. O código pode estar
  impecável. A correção é de requisito, e **não conta como dívida técnica**.
- **Débito técnico** — a regra está certa, a implementação envelheceu.

E antes de melhorar qualquer trecho: **este código ainda é usado?** Se foi
substituído, é código morto — a ação é remover, não polir.

## Problema

O que está errado, faltando ou em risco. Concreto, com evidência
(arquivo:linha quando aplicável).

## Proposta técnica

Como resolver. Bibliotecas envolvidas e por quê. Se houver decisão
arquitetural embutida, referencie (ou crie) o ADR.

## Refinamento obrigatório — cache e limites

> Duas perguntas que se respondem **antes** de escrever código, não depois.
> Origem: guia arquitetural externo §05. Se o card não toca nenhum dos dois
> temas, escreva "não se aplica" — a ausência de resposta é que não vale.

**Se houver cache:**

1. **TTL** — por quanto tempo este dado pode ficar guardado antes de estar velho?
2. **Gatilho de invalidação** — que evento o torna inválido e força a atualização?

Sem as duas respostas, o cache **não é implementado ainda**. Dado errado servido
rápido é pior que dado certo servido devagar.

**Se o card cria ou muda um endpoint:**

3. **Política de limite** — qual o teto, por qual chave (conta, IP, plano), e em
   que camada (infraestrutura protege a máquina; aplicação protege a lógica).
   Endpoint **autenticado também precisa** — usuário logado abusa, de propósito
   ou por bug no cliente. O número inicial é estimativa declarada, recalibrada
   por métrica.

**Se o card fala com uma dependência externa:**

4. **Timeout, retry e desfecho** — qual o teto de tempo de parede, a operação é
   idempotente (*o que acontece se rodar duas vezes?*), e o que o aluno vê
   quando o outro lado está fora. Política declarada aqui, implementada como o
   CARD-026 estabeleceu — nunca requisição crua.

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
