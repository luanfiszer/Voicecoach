# packages/api-client — contrato tipado do backend

**Ainda vazio.** A geração de tipos entra junto com os primeiros endpoints; o
CARD-001 só reserva o lugar e declara a fronteira.

## O que mora aqui

Duas coisas, e nada além delas (ADR-0008):

1. **Tipos gerados do OpenAPI** que o FastAPI expõe. Gerados, não escritos à
   mão — o OpenAPI do backend é a fonte da verdade.
2. **Client HTTP fino**: baseURL, envio do token, retry, `Idempotency-Key`.

## Regra de fronteira

> **Este pacote não conhece produto.** Ele conhece HTTP e o contrato.

- Zero regra de negócio, zero componente de UI, zero estado de tela.
- Não importa de `apps/*` — é consumido pelos dois apps, não o contrário.
- Tipo editado à mão aqui é bug esperando acontecer: se o backend mudou,
  regenere. O ganho do monorepo é justamente que mudança de API quebra os
  clientes **em build**, não em runtime.

## Por que existe

Duplicar tipos em dois repositórios garante drift de contrato — a classe de bug
que tipos gerados eliminam. É a justificativa do monorepo no ADR-0002.
