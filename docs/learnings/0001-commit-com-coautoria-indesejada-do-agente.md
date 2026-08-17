# LEARNING-0001 — Commit foi pushado com trailer "Co-Authored-By: Claude" indesejado

- **Data:** 2026-08-17
- **Card/sessão relacionado:** Sessão de bootstrap do harness de engenharia (commit `2f70e8a`)

## Sintoma

O commit `2f70e8a` ("Bootstrap engineering harness (P0): CLAUDE.md, ADR/backlog/learnings
templates, slash commands") foi criado com autor correto (`luanfiszer
<luanbfiszer@gmail.com>`), mas com o seguinte trailer na mensagem:

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
```

O commit já estava pushado em `origin/develop` quando o desenvolvedor apontou
o erro, junto de uma segunda reclamação relacionada (`.claude` versionado —
investigado e considerado correto/intencional, sem ação necessária).

## Causa raiz

O agente segue, por padrão de sistema, a instrução de sempre assinar commits
que ele cria com um trailer `Co-Authored-By: Claude ...`. Esse comportamento
não foi desativado nem questionado no início do projeto porque o CLAUDE.md
não continha nenhuma regra sobre autoria de commits neste repositório — ou
seja, faltou uma premissa explícita de que este projeto quer autoria
exclusivamente humana. Sem essa regra, o agente aplicou seu default global,
que diverge da expectativa do desenvolvedor.

## Como descobri

1. `git log --format='%h %an <%ae> %s'` — confirmou que o *autor* já estava
   correto, descartando a hipótese óbvia.
2. `git log -1 --format='%B' <hash>` — mostrou o corpo completo da mensagem e
   revelou o trailer `Co-Authored-By`, a causa real do segundo ponto
   reclamado pelo usuário.
3. `git rev-parse <branch> origin/<branch>` — confirmou que o commit já
   estava pushado, o que definiu a correção necessária (amend + force-push
   em vez de só um novo commit).

## Como evitar

Antes de criar qualquer commit neste repositório, o agente deve saber que
este projeto não quer o trailer `Co-Authored-By: Claude`. Isso só é garantido
com uma regra explícita no CLAUDE.md, já que é o arquivo lido no início de
toda sessão.

## Regra criada no CLAUDE.md

Adicionada uma nova seção **"Convenções de commit"** ao CLAUDE.md:

> ## Convenções de commit
>
> - Commits neste repositório **NUNCA** devem incluir o trailer
>   `Co-Authored-By: Claude` (ou qualquer variação com nome de modelo). A
>   autoria é exclusivamente do desenvolvedor humano, mesmo quando o agente
>   redige a mensagem ou parte do código.
