# packages/api-client — contrato tipado do backend

**Os tipos existem a partir do CARD-010**, com as primeiras rotas `/v1`.

## O que mora aqui

Duas coisas, e nada além delas (ADR-0008):

1. **`src/schema.d.ts`** — tipos gerados do OpenAPI que o FastAPI expõe.
   **Gerados, não escritos à mão.** O arquivo é commitado de propósito: é o que
   faz uma mudança de contrato aparecer como **diff revisável** no PR.
2. **Client HTTP fino** — baseURL, envio do token, retry, `Idempotency-Key`.
   *(Ainda não existe; entra com o CARD-012, quando houver quem o consuma.)*

## Como regenerar

De dentro de `backend/`, gere o schema; da raiz, gere os tipos:

```bash
cd backend
uv run python -c "
import json, pathlib
from voicecoach.api.app import create_app
pathlib.Path('openapi.json').write_text(json.dumps(create_app().openapi(), indent=2) + '\n')
"
cd ..
pnpm --filter @voicecoach/api-client run generate
```

**O CI compara o resultado com o que está commitado** e reprova se divergirem
(job `contrato OpenAPI e tipos TypeScript`). Esquecer de regenerar é build
vermelho, não erro de runtime no aparelho de alguém.

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
