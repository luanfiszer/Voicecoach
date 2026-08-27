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
| [0005](0005-fila-e-worker-arq-sobre-redis.md) | Fila e worker: arq sobre Redis | aceito (complementado por 0025; instalado e custeado pelo 0038) |
| [0006](0006-storage-de-midia-s3-url-assinada.md) | Storage de mídia: S3-compatível (MinIO) com URL assinada e expiração | **substituído por ADR-0024** |
| [0007](0007-autenticacao-jwt-refresh-rotativo.md) | Autenticação: e-mail verificado, JWT curto + refresh rotativo | aceito (ajustado por 0010) |
| [0008](0008-contrato-api-versionamento-e-tipos-gerados.md) | Contrato de API: REST /v1 aditivo + tipos TS gerados do OpenAPI | aceito |
| [0009](0009-estrategia-de-modelos-de-ia.md) | Modelos de IA: forte para pedagogia, barato para auxiliares, via config | aceito (ajustado por 0010) |
| [0010](0010-politica-de-custo-projeto-pessoal.md) | Política de custo: infra a dinheiro zero, gasto restrito à IA com teto mensal | aceito (base de projeção revista por [`analise-custo-e-precificacao.md`](../analise-custo-e-precificacao.md) §3) |
| [0011](0011-stt-e-tts-locais-como-default.md) | STT e TTS locais como default de desenvolvimento; APIs por config | aceito (complementado por 0027) |
| [0012](0012-regra-de-camada-como-contrato-executavel.md) | Regra de camada como contrato executável (import-linter) | aceito |
| [0013](0013-configuracao-tipada-fora-das-camadas.md) | Configuração tipada com pydantic-settings, fora das camadas e proibida no núcleo | aceito |
| [0014](0014-health-check-liveness-readiness.md) | Health check: liveness separado de readiness, com clientes nativos e sem porta | aceito (estendido por 0025) |
| [0015](0015-quality-gates-tres-aneis.md) | Quality gates em três anéis: agente, pre-commit e CI | aceito (item 3 ajustado por 0019) |
| [0016](0016-ciclo-de-vida-do-turn-estado-grosso-e-etapa-derivada.md) | Ciclo de vida do Turn: estado grosso persistido, etapa derivada dos artefatos | **substituído por ADR-0023** |
| [0017](0017-erro-de-dominio-e-excecao-result-fica-para-o-caso-de-uso.md) | Invariante de domínio violada é exceção; `Result` fica para o caso de uso | aceito (o TBD do item 3 foi **fechado pelo 0039**; a borda prometida no item 2 é o **0040**) |
| [0018](0018-teste-de-adapter-contra-postgres-real-com-testcontainers.md) | Teste de adapter contra Postgres real, com testcontainers | aceito |
| [0019](0019-limiar-global-de-cobertura-com-folga-agora-que-o-nucleo-morde.md) | Limiar global de cobertura com folga, agora que o anel do núcleo morde | aceito |
| [0020](0020-prompt-caching-no-adapter-do-professor.md) | Prompt caching no adapter do professor, com o prompt tratado como prefixo estável | **substituído por ADR-0021** |
| [0021](0021-prompt-caching-adiado-o-limiar-medido-nao-e-alcancado.md) | Prompt caching adiado: o limiar medido (4.096 tok) não é alcançado por uma conversa real | aceito (o instrumento do item 3 existe desde o **0051**; distância medida: 36% do limiar) |
| [0022](0022-ordem-dos-campos-da-resposta-do-professor-e-contrato-de-latencia.md) | A ordem dos campos da resposta do professor é contrato de latência, não estilo | aceito (risco técnico fechado por 0030) |
| [0023](0023-ciclo-de-vida-do-turn-com-entrega-em-cascata.md) | Ciclo de vida do Turn com entrega em cascata: o áudio vira uma sequência de trechos | aceito (substitui 0016; a forma da cascata está no 0037) |
| [0024](0024-midia-por-trecho-chave-url-assinada-e-retencao-assimetrica.md) | Mídia por trecho: chave, URL assinada junto do evento e retenção assimétrica | aceito (substitui 0006; porta estendida com `get` pelo 0036) |
| [0025](0025-modelos-residentes-no-worker-e-readiness-que-distingue-pronto.md) | Modelos de IA residentes no worker, e um readiness que distingue "subiu" de "pronto" | aceito (implementado no CARD-009; dívida do item 7 fechada — ver 0038) |
| [0026](0026-entrega-progressiva-por-sse-com-polling-como-contrato-de-recuo.md) | Entrega progressiva do turn por SSE, com o polling preservado como contrato de recuo | aceito (canal worker→API definido no 0035) |
| [0027](0027-adapter-duplo-de-stt-com-default-resolvido-pela-plataforma.md) | Adapter duplo de STT (`mlx-whisper` e `faster-whisper`), com default resolvido pela plataforma | aceito (complementado por 0029) |
| [0028](0028-derivacao-da-etapa-do-turn-mora-no-dominio.md) | A derivação da etapa do Turn mora no domínio, não na borda | aceito (revoga o §4 do 0016) |
| [0029](0029-o-que-atravessa-a-porta-de-stt-sao-bytes-codificados.md) | O que atravessa a porta de STT são bytes codificados; decodificar é do adapter | aceito (complementa 0027) |
| [0030](0030-saida-estruturada-em-streaming-por-tool-use-com-deltas-granulares.md) | Saída estruturada em streaming por tool use com deltas granulares | aceito (fecha o risco em aberto do 0022) |
| [0031](0031-o-que-atravessa-a-porta-do-professor-e-um-fluxo-de-eventos.md) | O que atravessa a porta do professor é um fluxo de eventos, não um objeto | aceito (complementa 0023 e 0026) |
| [0032](0032-piper-substitui-o-kokoro-como-motor-de-voz.md) | Piper substitui o Kokoro como motor de voz local | aceito (revê a escolha provisória do 0011; encolhe o número do 0025) |
| [0033](0033-o-que-atravessa-a-porta-de-tts-e-pcm-com-a-taxa-junto.md) | O que atravessa a porta de TTS é PCM cru com a taxa junto | aceito (complementa 0029) |
| [0034](0034-adapter-s3-sincrono-em-executor-e-retencao-por-tag.md) | Adapter S3 síncrono num executor, e retenção por tag em vez de prefixo | aceito (complementa 0024; fecha a dívida do 0014) |
| [0035](0035-canal-worker-api-por-pubsub-com-o-banco-como-fonte-da-verdade.md) | O canal worker→API é pub/sub, e o banco é a fonte da verdade | aceito (complementa 0026) |
| [0036](0036-o-primeiro-consumidor-revela-o-que-faltava-nas-portas.md) | O primeiro consumidor revela o que faltava nas portas (`get`, `AudioEncoder`, `SttError`, `list_by_session`, `UnitOfWork`) | aceito (estende 0024/0029/0031/0004) |
| [0037](0037-a-cascata-e-uma-fila-interna-com-um-consumidor-so.md) | A cascata é uma fila interna com um consumidor só, não uma task por sentença | aceito (complementa 0023 e 0031) |
| [0038](0038-arq-entra-e-rebaixa-o-redis.md) | O `arq` entra e rebaixa o `redis` de 8.1 para 5.3 | aceito (executa o 0005) |
| [0039](0039-result-minimo-para-desfecho-esperado-de-caso-de-uso.md) | `Result` mínimo próprio para o desfecho esperado de um caso de uso | aceito (fecha o TBD do 0017) |
| [0040](0040-formato-de-erro-da-api-problem-details.md) | O formato de erro da API é Problem Details (RFC 9457), num handler só | aceito (implementa 0008 item 5 e 0017 item 2) |
| [0041](0041-id-estruturado-do-evento-sse-e-retomada-derivada-do-banco.md) | O `id` do evento SSE é estruturado, e a retomada é derivada do banco | aceito (completa 0026 e 0035) |
| [0042](0042-idempotencia-do-post-por-coluna-no-postgres.md) | A idempotência do `POST` mora numa coluna do Postgres, não no Redis | aceito |
| [0043](0043-quality-gates-do-cliente-typescript-com-biome.md) | Os quality gates do cliente: `tsc --strict` e Biome, nos mesmos três anéis | aceito (estende 0015 ao cliente; torna verificável o 0008) |
| [0044](0044-dependencias-de-arranque-do-app-expo-e-convivencia-com-pnpm.md) | As dependências de arranque do app Expo, e a convivência do Metro com o pnpm | aceito (executa 0002; dispensa o polyfill previsto no 0026) |
| [0045](0045-o-host-que-assina-a-url-e-o-do-leitor-nao-o-do-servidor.md) | O host que assina a URL de mídia é o do **leitor**, não o do servidor | aceito (completa 0024) |
| [0046](0046-a-forma-do-client-typescript-e-o-contrato-do-sse-no-openapi.md) | A forma do client TypeScript, e os eventos do SSE entrando no contrato | aceito (completa 0008; torna verdadeira a promessa dele para o stream) |
| [0047](0047-fila-de-playback-com-um-player-por-trecho-e-a-rota-de-medicao.md) | Fila de playback com um player por trecho, e a rota de medição como instrumento | aceito |
| [0048](0048-o-expo-go-da-loja-ficou-para-tras-e-o-aparelho-fisico-vira-divida.md) | O Expo Go da App Store ficou 3 SDKs para trás, e o aparelho físico vira dívida declarada | aceito (ajusta premissa do 0002) |
| [0049](0049-correction-e-entidade-persistida-e-os-campos-texto-viram-derivacao.md) | `Correction` é entidade persistida, e os quatro campos texto do `/v1` viram derivação | aceito (complementa 0008/0022/0028/0031) |
| [0050](0050-o-feedback-volta-na-retomada-e-o-buraco-do-adr-0041-fecha.md) | O `feedback` volta na retomada, e o buraco do ADR-0041 fecha | aceito (completa 0041; depende do 0049) |
| [0051](0051-usage-event-fora-do-agregado-com-custo-congelado-na-escrita.md) | `UsageEvent` fora do agregado, com o custo congelado na escrita | aceito (executa o item 3 do 0021; instrumenta o 0010) |

## ADRs pendentes de decisão de produto

Identificados na reconstrução do backlog (2026-08-19) e **não escritos** porque
dependem de escolha do desenvolvedor, não de análise:

| Tema | Critério | O que trava |
|---|---|---|
| **Canal de cobrança e provedor de pagamento** (loja vs. web) | 1 e 3 | CARD-021; vale 11–26 pontos de margem |
| ~~**Unidade da cota** (minutos falados vs. turns)~~ | 2 (afeta o domínio) | **DECIDIDO em 2026-08-27: cobrar e comunicar em minutos, limitar em ambos** — um teto de turns/dia dimensionado para só morder no comportamento patológico. O ADR é escrito na execução do CARD-015; até lá esta linha registra a decisão, não a substitui |
| **Sucessor do ADR-0010** (política de custo sob receita) | 3 | depende dos dois acima |
