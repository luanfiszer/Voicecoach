# ADR-0038 — O `arq` entra e rebaixa o `redis` de 8.1 para 5.3

- **Status:** aceito
- **Data:** 2026-08-23
- **Complementa:** [ADR-0005](0005-fila-e-worker-arq-sobre-redis.md) (a escolha
  do arq), [ADR-0025](0025-modelos-residentes-no-worker-e-readiness-que-distingue-pronto.md)
  (o que o worker precisa da biblioteca), [ADR-0015](0015-quality-gates-tres-aneis.md)
  (o gate de tipos)
- **Critérios de obrigatoriedade:** **1 — introduz uma dependência externa**, e a
  introdução **remove** a versão de outra que já estava no projeto.

## Contexto

O ADR-0005 escolheu `arq` sobre Redis em 2026-08-17, sem instalá-lo — o CARD-009
é quem finalmente traz a biblioteca. A instalação não é neutra:

```
+ arq==0.28.0
+ hiredis==3.4.1
+ pyjwt==2.13.0
- redis==8.1.0
+ redis==5.3.1
```

O `arq` 0.28 fixa `redis>=4.2,<6`, e o `redis` está no projeto **desde o
CARD-002**, usado pelo `check_redis` do readiness (ADR-0014). Rebaixar uma
dependência existente por causa de uma nova é decisão, não detalhe de resolução.

**O custo apareceu no gate, não na leitura do changelog.** Com o `redis` 5.3.1 o
`mypy --strict` reprovou uma linha que passava limpa na 8.1.0:

```
src/voicecoach/adapters/health.py:88: error: Call to untyped function "from_url" in typed context  [no-untyped-call]
```

Verificado: na 5.3.1 o `from_url` não tem tipo de retorno anotado; na 8.x tem.
O `strict` reprova chamada a função não tipada, e essa é a única regressão — a
API consumida (`from_url`, `ping`, `publish`, `set`, `exists`, `delete`,
`aclose`) é a mesma nas duas majors, e a suíte inteira passa.

## Decisão

**Aceitar o rebaixamento, e pagá-lo com um `type: ignore` pontual e datado em vez
de afrouxar o gate ou trocar a biblioteca de fila.**

1. **`arq>=0.28` entra** nas dependências base, com o motivo escrito no
   `pyproject.toml`: é a única biblioteca da lista curta que oferece o que o
   ADR-0025 exige — um `on_startup` **async** que popula um `ctx` compartilhado
   por toda task e que bloqueia o consumo de job até retornar.
2. **`arq` e `hiredis` entram nas listas `forbidden` de `domain` e de
   `application` no mesmo commit.** `hiredis` está junto pela lição da Q8: é o
   parser em C que o `arq` arrasta, e a lista não enxerga o que ninguém digitou.
3. **O rebaixamento do `redis` é aceito** e o `# type: ignore[no-untyped-call]`
   fica numa linha só, com o código do erro, o motivo e o **gatilho para
   remover**: o `arq` passar a aceitar `redis>=6`.
4. **`function_name` explícito, não `__qualname__`.** A task é registrada com
   `func(process_turn, name=PROCESS_TURN_TASK)`; sem isso o nome na fila
   dependeria do caminho do módulo, e renomear o arquivo quebraria os jobs já
   enfileirados.
5. **A configuração entra por `run_worker(..., redis_settings=...)`, numa função
   `run()`,** e não como atributo de classe. Um `redis_settings =
   RedisSettings.from_dsn(get_settings().redis_url)` no corpo da classe seria
   avaliado no **import** do módulo, e `get_settings()` valida o `.env` — importar
   o worker passaria a exigir configuração completa, inclusive na coleta dos
   testes. É a armadilha que o `get_settings()` preguiçoso do CARD-002 existe
   para evitar.

## Alternativas consideradas

### Alternativa A — Fixar `redis>=8` e escolher outra biblioteca de fila

- **O que é:** manter a versão nova do cliente e trocar `arq` por Dramatiq,
  Celery ou uma implementação própria sobre Streams.
- **Por que foi rejeitada:** reabriria o ADR-0005 por causa de **uma anotação de
  tipo ausente**. Celery é síncrono na raiz (o worker inteiro é async), Dramatiq
  não tem contexto de processo async equivalente ao `ctx` — e sem `ctx`
  compartilhado o ADR-0025 não tem onde morar, o que custaria ~1 s por turno.
  Trocar um `type: ignore` de uma linha por um segundo modelo de execução é
  desproporcional.

### Alternativa B — Afrouxar o `mypy` para o módulo `redis`

- **O que é:** um `[[tool.mypy.overrides]]` com `ignore_missing_imports` ou
  `disallow_untyped_calls = false` para `redis.*`, como já existe para `asyncpg`,
  `faster_whisper` e `boto3`.
- **Por que foi rejeitada:** os overrides existentes são para bibliotecas que
  **não publicam `py.typed`** — o mypy não tem o que ler. O `redis` publica: ele é
  tipado, só tem *uma* função sem retorno anotado nesta versão. Um override de
  módulo cegaria o type checker para todo o resto do `redis`, inclusive o
  `publish` do canal de eventos do ADR-0035, para silenciar um caso conhecido. O
  ignore de uma linha é mais estreito e tem gatilho.

### Alternativa C — Não usar o cliente `redis` diretamente; ir só pelo `ArqRedis`

- **O que é:** o `arq` expõe um `ArqRedis` que herda de `redis.asyncio.Redis`;
  usá-lo em todo lugar evitaria a chamada a `from_url`.
- **Por que foi rejeitada:** a API não tem nem deve ter um pool de fila. O
  `check_redis` é da borda e existe desde o CARD-002, antes de existir worker;
  amarrá-lo ao cliente da fila faria o readiness da API depender da biblioteca de
  background job — uma seta de acoplamento nova para não escrever um comentário.

## Consequências

**Positivas**

- A fila do ADR-0005 finalmente existe, com o ciclo de vida que o ADR-0025 pede,
  e o `worker/` deixa de ser um diretório com um `__init__.py` depois de quatro
  cards.
- A regressão de tipo ficou **visível e datada**, num lugar só, em vez de
  dissolvida num override de módulo.
- O par de contratos do `lint-imports` foi exercitado com o par completo (`arq`
  fora da lista → 3 kept/1 broken; dentro → 2 kept/2 broken), reconfirmando a
  lição da Q8.

**Negativas — o preço aceito**

- **Uma major a menos no `redis`.** Correção de segurança que só saia na 6.x+
  exigiria esperar o `arq` ou fixar manualmente — e o `arq` não é uma biblioteca
  de atualização rápida.
- **Duas dependências transitivas novas** (`hiredis`, `pyjwt`) que ninguém pediu.
  O `pyjwt` em particular entra num projeto que ainda vai escolher sua própria
  estratégia de token (ADR-0007) e pode confundir quem ler a árvore.
- **Um `type: ignore` a mais para lembrar de remover.** O gatilho está escrito,
  mas nada o verifica: ele vai sobreviver ao dia em que deixar de ser necessário,
  como todos os outros — o `warn_unused_ignores` do mypy strict é o que
  eventualmente o denuncia.
- **O nome da task vira contrato de deploy.** Mudar `PROCESS_TURN_TASK` com jobs
  em voo faz o worker novo ignorar o que o antigo enfileirou.
