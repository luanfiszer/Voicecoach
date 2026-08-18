# ADR-0013 — Configuração tipada com pydantic-settings, fora das camadas e proibida no núcleo

- **Status:** aceito
- **Data:** 2026-08-18
- **Complementa:** ADR-0012 (regra de camada como contrato executável), visão §D
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **2 — define ou altera
  uma fronteira** (cria um módulo fora das cinco camadas e a regra que o cerca).

## Contexto

O protótipo lia configuração com `os.getenv` mais um helper `_required()`
(`english_teacher_bot/config.py`): o valor chega como `str` ou explode, e cada
consumidor converte na mão (`int(os.getenv("MAX_AUDIO_MB", "2"))`). Funciona,
mas não há tipo, faixa válida, nem lugar único onde a forma da configuração
esteja declarada.

O CARD-002 precisa da configuração antes de qualquer outra coisa: o health
check só sabe onde procurar Postgres, Redis e MinIO se alguém lhe disser. Isso
força duas perguntas que a visão §D não responde:

1. **Onde esse módulo mora**, já que ele não é `domain`, nem `application`, nem
   `adapters`, nem entrypoint.
2. **Quem pode lê-lo.** A visão diz que `domain` só importa a stdlib e que
   `application` não conhece framework — mas `voicecoach.config` não é
   framework nem camada, então nenhuma regra existente o alcança.

## Decisão

1. **`pydantic-settings` como mecanismo**, com uma classe `Settings(BaseSettings)`
   em `voicecoach/config.py`. Tipos declarados uma vez; a validação acontece na
   construção da instância.
2. **O módulo mora no topo do pacote, fora das cinco camadas.** Configuração é
   detalhe de composição — quem a lê é quem monta o processo.
3. **`domain` e `application` não podem importar `voicecoach.config`**,
   verificado por um contrato `forbidden` novo no import-linter. Eles recebem os
   valores de que precisam por parâmetro. Só `api`, `worker` e `adapters` leem
   configuração.
4. **A instância é preguiçosa e memoizada** (`get_settings()` com
   `@lru_cache`), consumida em `create_app()`. A aplicação é servida por
   factory (`uvicorn ... --factory`): configuração inválida derruba o boot,
   não o import do módulo.
5. **Uma única variável é obrigatória: `ANTHROPIC_API_KEY`.** Endereços de
   infraestrutura (`DATABASE_URL`, `REDIS_URL`, `S3_*`) têm default apontando
   para o `docker-compose.yml` deste repositório.
6. **Dinheiro é `Decimal`**, nunca `float` (`DAILY_BUDGET_USD`,
   `MONTHLY_BUDGET_USD`).

### Por que só a chave da Anthropic é obrigatória

O default de infraestrutura não pode estar errado: ele descreve o Compose
versionado ao lado, no mesmo repositório. Já um segredo de provedor externo não
tem default correto possível — qualquer valor inventado é uma falha adiada para
a primeira chamada paga. Falta de default é o que preserva o fail-fast do
`_required()` do protótipo, agora com mensagem do pydantic nomeando o campo.

## Alternativas consideradas

### Alternativa A — Manter `os.getenv` + helper `_required()`
- O que é: portar o `config.py` do protótipo, trocando os nomes das variáveis.
- Por que foi rejeitada: sem tipo declarado, cada consumidor converte na mão e
  cada conversão é uma chance de divergir (`"10"` vira `int` num lugar e fica
  `str` em outro); sem faixa válida, `MONTHLY_BUDGET_USD=-5` passa; e a forma da
  configuração não existe em lugar nenhum — só no conjunto das chamadas
  espalhadas. O custo da alternativa tipada é uma dependência que **já estava no
  `pyproject.toml` desde o CARD-001**.

### Alternativa B — `voicecoach.config` dentro de `adapters/`
- O que é: colocar o módulo numa camada existente, para o contrato de `layers`
  já cobri-lo sem contrato novo.
- Por que foi rejeitada: `adapters` é a camada que implementa portas; config não
  implementa nenhuma. Pior, `api` passaria a ler configuração *através* de
  `adapters`, o que faz a composition root depender da camada que ela deveria
  compor. Economiza cinco linhas de TOML ao preço de uma mentira no mapa de
  camadas.

### Alternativa C — Módulo no topo, sem contrato que o proteja
- O que é: `voicecoach/config.py` e disciplina.
- Por que foi rejeitada: é exatamente o buraco que o ADR-0012 existe para
  fechar. Um módulo fora das camadas é invisível para o contrato de `layers` —
  `domain` poderia importá-lo e o lint continuaria verde. E a violação seria
  grave: via `config`, o `domain` alcançaria `pydantic` transitivamente,
  derrubando a pureza que o ADR-0012 decidiu. Verificado empiricamente no
  CARD-002 (violação injetada e revertida): com o contrato, o import-linter
  aponta os dois saltos — `voicecoach.domain -> voicecoach.config (l.16)` e
  `voicecoach.config -> pydantic (l.18)`.

### Alternativa D — Instanciar `Settings()` no topo do módulo
- O que é: `settings = Settings()` como variável de módulo, importada por quem
  precisar.
- Por que foi rejeitada: torna a validação um efeito colateral do *import*.
  Qualquer `import voicecoach.config` sem `.env` presente explode — inclusive a
  coleta dos testes, uma ferramenta de documentação ou um script que só quisesse
  ler o módulo. O fail-fast é desejável no **boot**, não no import; a factory dá
  o mesmo momento de falha sem o dano colateral.

## Consequências

**Positivas**
- Uma declaração única e tipada de toda a configuração do produto, com faixas
  válidas (`gt=0`) e imutabilidade (`frozen=True`).
- O núcleo (`domain`, `application`) permanece testável sem ambiente: recebe
  valores, não os busca.
- A obrigatoriedade da chave da Anthropic é verificável por teste, sem subir
  processo (`Settings(_env_file=None)` levanta `ValidationError`).
- `_env_file=None` nos testes isola o resultado do `.env` da máquina.

**Negativas — o preço aceito**
- Mais um contrato de import-linter para manter, e ele é do tipo que **não se
  atualiza sozinho**: mesmo elo fraco já registrado no ADR-0012.
- Passar valores por parâmetro para `application` é mais verboso que injetar um
  objeto de configuração. É o preço de um núcleo que não sabe o que é uma
  variável de ambiente. **Gatilho para reavaliar:** se um caso de uso precisar
  de mais de três valores de configuração, o certo é criar um objeto de política
  em `application` (definido lá, preenchido na composição), não afrouxar o
  contrato.
- `Settings()` sem argumentos não passa em type checker estrito — os campos são
  preenchidos pelo pydantic em runtime. Custa um `# type: ignore[call-arg]`
  documentado; revisitar no CARD-003 quando mypy entrar (o plugin do pydantic
  pode dispensá-lo).
- O `.env` mora na raiz (o Compose o lê sozinho) mas o backend roda de
  `backend/`, então `env_file` carrega dois caminhos candidatos. É um detalhe
  de layout de monorepo, não de arquitetura.

**Equivalente mental .NET:** `IOptions<T>` com `ValidateOnStart()`. A diferença
que não tem paralelo: em .NET a configuração é injetada em qualquer camada sem
constrangimento; aqui a decisão é deliberadamente mais estrita — o núcleo não
recebe `IOptions`, recebe valores.
