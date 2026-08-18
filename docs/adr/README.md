# Architecture Decision Records (ADRs)

Registro imutável das decisões arquiteturais deste projeto, com alternativas
consideradas e trade-offs explícitos.

## Quando um ADR é OBRIGATÓRIO

Escreva um ADR sempre que a decisão:

1. **Introduz ou remove uma dependência externa** — biblioteca, serviço, provider
   de IA, banco, fila. (Ex.: escolher SQLAlchemy, trocar de modelo Claude.)
2. **Define ou altera uma fronteira** — camadas, portas/adaptadores, contrato
   de API, formato de dados persistidos.
3. **Afeta custo recorrente** — modelo de LLM, estratégia de cache, storage.
4. **Afeta segurança ou privacidade** — autenticação, exposição de mídia,
   validação de webhook, retenção de dados de usuário.
5. **Seria difícil de reverter** — se desfazer custa mais que uma sessão de
   trabalho, a decisão merece registro.
6. **Contraria uma convenção estabelecida** — exceções à regra são decisões.

## Quando NÃO escrever ADR

- Escolhas locais e reversíveis (nome de função, estrutura interna de um módulo).
- Correções de bug sem mudança de design → isso vai para `docs/learnings/`.
- Detalhes de implementação que a skill de arquitetura já cobre.

## Regras

- Numeração sequencial: `0001-titulo-kebab-case.md`, `0002-...`.
- Use o template `0000-template.md`.
- ADR aceito **não é editado** para mudar a decisão: escreva um novo ADR que o
  substitui e atualize o status do antigo para "substituído por ADR-XXXX".
- Mínimo de duas alternativas reais consideradas, com o motivo da rejeição.
- Um ADR sem seção "Consequências negativas" preenchida está incompleto.

## Índice

| ADR | Título | Status |
|---|---|---|
| [0001](0001-descontinuar-whatsapp-em-favor-de-app-proprio.md) | Descontinuar WhatsApp/Twilio em favor de app mobile próprio + web companion | aceito |
| [0002](0002-stack-de-cliente-expo-mais-web-separada.md) | Stack de cliente: Expo/RN (mobile) + web separada (Vite) em monorepo | aceito |
| [0003](0003-interacao-v1-turn-based-preparada-para-v2-realtime.md) | Interação: V1 turn-based, desenhado para V2 realtime | aceito |
| [0004](0004-persistencia-postgres-sqlalchemy-alembic.md) | Persistência: PostgreSQL + SQLAlchemy 2.0 (async) + Alembic | aceito |
| [0005](0005-fila-e-worker-arq-sobre-redis.md) | Fila e worker: arq sobre Redis | aceito |
| [0006](0006-storage-de-midia-s3-url-assinada.md) | Storage de mídia: S3-compatível (MinIO) com URL assinada e expiração | aceito |
| [0007](0007-autenticacao-jwt-refresh-rotativo.md) | Autenticação: e-mail verificado, JWT curto + refresh rotativo | aceito (ajustado por 0010) |
| [0008](0008-contrato-api-versionamento-e-tipos-gerados.md) | Contrato de API: REST /v1 aditivo + tipos TS gerados do OpenAPI | aceito |
| [0009](0009-estrategia-de-modelos-de-ia.md) | Modelos de IA: forte para pedagogia, barato para auxiliares, via config | aceito (ajustado por 0010) |
| [0010](0010-politica-de-custo-projeto-pessoal.md) | Política de custo: infra a dinheiro zero, gasto restrito à IA com teto mensal | aceito |
| [0011](0011-stt-e-tts-locais-como-default.md) | STT e TTS locais como default de desenvolvimento; APIs por config | aceito |
| [0012](0012-regra-de-camada-como-contrato-executavel.md) | Regra de camada como contrato executável (import-linter) | aceito |
| [0013](0013-configuracao-tipada-fora-das-camadas.md) | Configuração tipada com pydantic-settings, fora das camadas e proibida no núcleo | aceito |
| [0014](0014-health-check-liveness-readiness.md) | Health check: liveness separado de readiness, com clientes nativos e sem porta | aceito |
| [0015](0015-quality-gates-tres-aneis.md) | Quality gates em três anéis: agente, pre-commit e CI | aceito (item 3 ajustado por 0019) |
| [0016](0016-ciclo-de-vida-do-turn-estado-grosso-e-etapa-derivada.md) | Ciclo de vida do Turn: estado grosso persistido, etapa derivada dos artefatos | aceito |
| [0017](0017-erro-de-dominio-e-excecao-result-fica-para-o-caso-de-uso.md) | Invariante de domínio violada é exceção; `Result` fica para o caso de uso | aceito |
| [0018](0018-teste-de-adapter-contra-postgres-real-com-testcontainers.md) | Teste de adapter contra Postgres real, com testcontainers | aceito |
| [0019](0019-limiar-global-de-cobertura-com-folga-agora-que-o-nucleo-morde.md) | Limiar global de cobertura com folga, agora que o anel do núcleo morde | aceito |
