# ADR-0008 — Contrato de API: REST /v1, evolução aditiva, tipos TypeScript gerados do OpenAPI

- **Status:** aceito
- **Data:** 2026-08-17

## Contexto

Dois clientes TypeScript (mobile e web) consomem o backend Python. Restrição
dura do mobile: **usuário com app desatualizado não atualiza quando queremos**
— uma versão velha do contrato fica viva no mundo por meses. Precisamos de:
contrato único como fonte de verdade, tipos compartilhados sem duplicação, e
política de mudança que não quebre apps antigos.

## Decisão

1. **REST JSON sob `/v1`**, documentado pelo **OpenAPI que o FastAPI gera**
   dos schemas pydantic — o contrato é código, não documento paralelo.
2. **Política de evolução aditiva**: permitido adicionar campo opcional,
   endpoint ou enum novo (clientes toleram o desconhecido); **proibido**
   remover/renomear campo, mudar tipo ou semântica dentro de `/v1`. Breaking
   change ⇒ `/v2` convivendo com `/v1` + janela de sunset.
3. `GET /v1/meta` retorna `min_supported_app_version`; o app compara e força
   atualização apenas em último caso (kill switch de contrato).
4. **Tipos gerados**: `openapi-typescript` gera tipos puros no pacote
   `packages/api-client` do monorepo, junto de um client `fetch` fino tipado.
   **A geração roda no CI**: diff nos tipos gerados torna toda mudança de
   contrato visível e revisável; quebra de compilação dos clientes acusa
   breaking change antes do runtime.
5. Erros no formato **Problem Details (RFC 9457)** via exception handlers.

## Alternativas consideradas

### Alternativa A — Tipos escritos à mão nos clientes
- O que é: interfaces TS mantidas manualmente espelhando a API.
- Por que foi rejeitada: drift silencioso garantido (a classe de bug só
  aparece em runtime no device); duplicação entre mobile e web; o custo da
  geração automática é um passo de build.

### Alternativa B — Gerador pesado (orval / openapi-generator / Kiota)
- O que é: gerar client completo (hooks react-query, classes, mocks).
- Por que foi rejeitada: código gerado volumoso e opinativo cedo demais —
  esconde o fetch/estado que o desenvolvedor quer aprender no React. Gatilho
  para reavaliar (provável: orval): quando a escrita manual de hooks de dados
  virar repetição mecânica comprovada.

### Alternativa C — GraphQL
- O que é: schema GraphQL como contrato, codegen nos dois lados.
- Por que foi rejeitada: dois clientes com necessidades próximas não têm o
  problema de shape que GraphQL resolve; adiciona runtime e vocabulário
  novos num projeto que já carrega Python+RN+web. Já cortado na visão §F.

### Alternativa D — Versionamento por header (media type) em vez de path
- O que é: `Accept: application/vnd.voicecoach.v2+json`.
- Por que foi rejeitada: mais elegante em tese, menos visível e mais
  propenso a erro em clientes móveis e ferramentas; `/v1` no path é
  inequívoco em log, cache e debugging. Trade-off estético aceito.

## Consequências

**Positivas**: contrato único versionado com o código; mudança de API vira
diff revisável no CI e erro de compilação nos clientes; política aditiva dá
liberdade de evoluir sem coordenação de release com apps na rua.

**Negativas — o preço aceito**: a política aditiva acumula campos legados
dentro de `/v1` (limpeza só em major); manter `/v1`+`/v2` simultâneos quando
houver breaking custa manutenção dupla temporária; o passo de geração entra
no caminho do build dos clientes.

**Equivalente mental .NET:** Swashbuckle gerando OpenAPI + NSwag/Kiota
gerando clients — com a disciplina de compatibilidade que se usa em APIs
públicas (add-only), imposta pela loja em vez do cliente enterprise.
