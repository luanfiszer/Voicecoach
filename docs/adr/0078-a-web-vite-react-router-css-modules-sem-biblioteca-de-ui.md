# ADR-0078 — A web: Vite, React Router e CSS Modules, sem biblioteca de UI

- **Status:** aceito
- **Data:** 2026-10-01
- **Relacionado:** ADR-0001 (web companion), ADR-0002 (stack de cliente), ADR-0008 (contrato), ADR-0043 (Biome), ADR-0061 (Vitest sobre lógica extraída), ADR-0077 (sessão da web), CARD-064
- **Critérios de obrigatoriedade:** **1 — dependências externas** (`vite`, `@vitejs/plugin-react`, `react-router`, `react-dom`; o script do Google Identity Services) e **5 — difícil de reverter** (roteamento e estilo são o esqueleto que o redesign vai herdar).

## Contexto

O ADR-0002 fixou "Vite + React + TypeScript" para a web e deixou o resto em
aberto. O desenvolvedor pediu (2026-10-01) as telas análogas às do mobile, no
mesmo estilo, sabendo que **haverá investimento futuro em UX/UI**. A decisão
de estilo, portanto, tem de baratear o redesign, não antecipá-lo.

## Decisão

1. **Versões alinhadas ao monorepo:** React **19.2.3** (o mesmo do mobile),
   TypeScript ~6.0.3, e **`vite` ~7.3.6** — a mesma que o `vitest` da raiz já
   usava. Tentou-se `vite` 8.3.2: o pnpm exigiu uma exceção na política de
   idade mínima de release (versão de horas) e passou a resolver dois `vite`
   no repo. Recusado: uma versão madura e única. `@vitejs/plugin-react` ~5.2
   (a 6.x exige `vite` 8).
2. **`react-router` 8, modo declarativo** (`BrowserRouter` + `Routes`). As
   telas de auth ganham URL (`/entrar`, `/criar-conta`…) — no mobile elas são
   estado local (CARD-050), mas na web o botão Voltar e os links de e-mail
   precisam de URL. O estado da sessão decide o que aparece (`SoLogado`,
   `SoDeslogado`), não a rota pedida.
3. **CSS Modules + variáveis CSS, sem biblioteca de componentes.** Os tokens
   do mobile viram `theme/tokens.css` (tema escuro por
   `prefers-color-scheme`); cada componente tem seu `.module.css`. Nenhuma
   dependência de estilo — o Vite já suporta os dois.
4. **Sem gerenciador de estado nem de requisições** (Redux, TanStack Query):
   os hooks seguem o desenho do mobile (`useHistorico` com `AbortController`).
5. **Google Identity Services por `<script>`**, sem pacote npm (ver ADR-0077 e
   o docstring de `BotaoGoogle.tsx`: só o botão do próprio Google entrega
   `id_token`).
6. **Os textos do produto são copiados do mobile, não importados**
   (`rotulosDoHistorico.ts`, `rotulosDeConfiguracoes.ts`, `mensagensDeErro`),
   com os testes copiados junto — ADR-0002 proíbe compartilhar UI.

## Alternativas consideradas

### A — Tailwind CSS
- **Prós:** velocidade de escrita; ecossistema enorme.
- **Por que foi rejeitada (por ora):** as classes utilitárias ficam espalhadas
  pelo JSX, e o redesign futuro teria de reescrever cada tela. Com tokens +
  CSS Modules, o redesign troca `tokens.css` e os `.module.css`. **Gatilho para
  reabrir:** a equipe de UX/UI entregar um design system pensado em Tailwind.

### B — Biblioteca de componentes (MUI, Mantine, shadcn/ui)
- **Por que foi rejeitada:** impõe a identidade visual dela sobre a do
  produto, e é exatamente a decisão que o investimento de UX/UI vai tomar.

### C — TanStack Router
- **Prós:** rotas tipadas de ponta a ponta.
- **Por que foi rejeitada:** para sete rotas, o ganho não paga a curva; o
  React Router é o padrão que o mercado (e a entrevista) cobra.

### D — TanStack Query
- **Por que foi rejeitada (por ora):** três leituras simples (histórico, cota,
  sessão) não justificam cache de servidor. **Gatilho:** a fase 2 (conversa)
  ou telas que leiam o mesmo dado em vários lugares.

## Consequências

- A web roda na mesma origem da API (proxy do Vite; reverse proxy em
  produção — ADR-0077, CARD-055).
- Os textos duplicados podem divergir do mobile. Mitigação: os testes de
  texto foram copiados junto. **Gatilho para um pacote compartilhado de
  textos:** um terceiro cliente ou uma divergência real.
- O `pnpm-lock.yaml` re-chaveou as dependências do mobile com `react-dom` como
  peer (nenhuma versão mudou); `tsc` e testes do mobile verdes depois disso.
