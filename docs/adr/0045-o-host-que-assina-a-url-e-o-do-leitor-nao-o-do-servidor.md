# ADR-0045 — O host que assina a URL de mídia é o do **leitor**, não o do servidor

- **Status:** aceito
- **Data:** 2026-08-25
- **Completa:** [ADR-0024](0024-midia-por-trecho-chave-url-assinada-e-retencao-assimetrica.md)
  (item 2: *"a URL assinada é emitida pelo servidor e entregue junto do evento"*,
  sem dizer **com que host**) e
  [ADR-0006](0006-storage-de-midia-s3-url-assinada.md) (S3 + URL pré-assinada)
- **Critérios de obrigatoriedade** (`docs/adr/README.md`): **2 — altera uma
  fronteira** (acrescenta campo a `Settings` e muda o endereço que a API entrega
  ao cliente) e **4 — afeta privacidade** (é o endereço por onde a voz do aluno
  trafega, e ele passa a ser configurável por ambiente).

## Contexto

O ADR-0024 decidiu que a URL assinada do trecho **viaja junto do evento**, para
não gastar um roundtrip por frase dentro de um orçamento de 1,8 s. Ele tratou o
endereço como detalhe: assinar é HMAC local, e a URL "é o que o storage devolve".

O CARD-012 é o primeiro card em que **um aparelho físico** baixa esse trecho, e
o detalhe deixou de ser detalhe. O `backend/config.py` tinha um campo só —
`s3_endpoint_url = "http://localhost:9000"` — usado ao mesmo tempo para duas
coisas que só coincidem por acidente de ambiente:

1. **para onde o worker e a API mandam as requisições** ao MinIO;
2. **com que host as URLs entregues ao cliente são assinadas**.

No Simulador as duas coincidem, porque ele compartilha a rede do Mac. **Num
telefone, `localhost` é o próprio telefone** — o download falha, e o sintoma que
chega ao desenvolvedor é *"o playback não funciona"*, não *"a URL está errada"*.

E o remendo óbvio não existe. Medido nesta sessão, contra o MinIO do compose:

```
A) assinada para localhost, pedida em localhost      → HTTP 200
B) MESMA assinatura, host trocado para 127.0.0.1     → 403 SignatureDoesNotMatch
C) assinada JÁ para 127.0.0.1, pedida em 127.0.0.1   → HTTP 200
```

A causa está escrita na própria query string: **`X-Amz-SignedHeaders=host`**. No
SigV4 o *canonical request* inclui os cabeçalhos assinados **com os seus
valores**; trocar o `Host` depois de assinar produz outro hash. **Não há conserto
do lado do cliente** — reescrever a URL no app é matematicamente impossível de
funcionar.

## Decisão

**A configuração passa a distinguir o endpoint com que o backend FALA com o
storage do endpoint com que ele ASSINA as URLs entregues ao cliente. Quando os
dois diferem, o adapter carrega dois clientes S3: um que faz IO e um que só
assina.**

1. **`Settings.s3_public_endpoint_url: str | None = None`.** `None` significa
   "mesmo host", e é o default — Simulador, CI e testes seguem inalterados.
   A resolução mora numa propriedade única, `s3_signing_endpoint_url`, e não num
   segundo campo com o mesmo literal: dois defaults iguais saem de sincronia no
   dia em que alguém mudar um só.
2. **`S3MediaStorage(client, bucket, signer=None)`**, com `signer` caindo para
   `client`. `presigned_get_url` — e **só** ele — usa o `signer`. `put`, `get` e
   `delete_prefix` continuam no cliente de IO.
3. **O segundo cliente nunca abre conexão.** Assinar é cálculo local; ele existe
   para carregar uma string de host diferente, e nada mais.
4. **Um objeto gravado por um cliente é lido pela URL assinada pelo outro**,
   porque quem identifica o objeto é `(bucket, key)` — `endpoint_url` é para onde
   a requisição **vai**, e a URL assinada descreve a requisição que o **leitor**
   fará. Isso está no teste, não na confiança.
5. **A regra de operação, escrita para a próxima sessão:** em aparelho físico,
   `S3_PUBLIC_ENDPOINT_URL` e `apiBaseUrl` do app precisam **ambos** apontar para
   um endereço que o telefone alcance. Apontar só um dos dois produz uma falha
   assimétrica difícil de ler: o turn processa, os eventos chegam, e nenhum
   áudio toca.

## Alternativas consideradas

### Alternativa A — Trocar `s3_endpoint_url` pelo IP da LAN

- **O que é:** um campo só, apontando para `http://192.168.x.x:9000`.
- **A favor:** zero código novo; é literalmente mudar uma string no `.env`.
- **Por que foi rejeitada:** faz o **worker** sair na rede para falar com um
  MinIO que está no mesmo host, trocando loopback por interface física no
  caminho crítico dos uploads de trecho — o oposto do que o orçamento de 1,8 s
  quer. E, pior, apaga a distinção: no dia em que o storage for S3 de verdade
  (endpoint público) com um cache interno na frente, não haverá onde expressar
  os dois consumidores. O valor também quebra a cada troca de IP do roteador,
  inclusive para quem só roda no Simulador.

### Alternativa B — A API serve os bytes do trecho (`GET /v1/turns/{id}/chunks/{i}`)

- **O que é:** o backend baixa do storage e repassa; o cliente nunca vê o MinIO.
- **A favor:** resolve host e ATS do iOS de uma vez, com um endereço só para
  tudo, e o bucket deixa de precisar ser alcançável de fora.
- **Por que foi rejeitada:** é a **Alternativa B do ADR-0024**, rejeitada lá com
  o argumento que continua valendo — põe banda e CPU de streaming no processo que
  precisa estar livre para atender o próximo turn, e desfaz o ganho de "o backend
  fora do caminho dos bytes" que o ADR-0006 listou como positivo. Fica registrada
  como a saída se um provedor sem URL assinada entrar em cena, ou se o ATS do iOS
  se mostrar intransponível em rede local.

### Alternativa C — Reescrever o host no cliente

- **O que é:** o app troca `localhost` pelo endereço certo ao receber a URL.
- **Por que foi rejeitada:** **não funciona**, e o ADR existe em parte para
  registrar isso com a medição junto (403 `SignatureDoesNotMatch`, acima). É a
  primeira ideia de quem topa com o problema, e custa uma sessão descobrir que
  ela é impossível em vez de difícil.

## Consequências

**Positivas**

- O modo de falha mais caro do card — *"o playback não funciona"* em aparelho
  físico — vira configuração explícita, com o motivo escrito ao lado do campo.
- O default `None` mantém Simulador, CI e a suíte inteira sem mudança: a decisão
  não cobra nada de quem não precisa dela.
- A distinção *"host de serviço" vs. "host de leitor"* passa a existir no
  vocabulário do projeto, e é a mesma que aparecerá em produção com CDN na
  frente do bucket.

**Negativas — o preço aceito**

- **Dois clientes boto3 no processo** quando a separação existe. São objetos
  baratos e um deles nunca faz IO, mas são duas coisas onde havia uma, e alguém
  vai perguntar por quê — daí o docstring.
- **Uma configuração a mais para errar**, e o erro é silencioso do lado do
  servidor: URLs assinadas com um host inalcançável são geradas com sucesso e só
  falham no aparelho. A mitigação é a regra de operação (item 5), não um check.
- **O ATS do iOS continua de pé.** Este ADR resolve a assinatura; tráfego HTTP em
  claro para IP de rede local pode ainda ser bloqueado pelo sistema. Se
  acontecer, é achado do CARD-012 e decisão própria — **não** motivo para dev
  build (ADR-0002).
- **Nada impede que os dois campos divirjam por engano** e apontem para storages
  diferentes. Não há validação cruzada; seria checagem de rede no boot, que o
  projeto não tem em lugar nenhum.

**Equivalente mental .NET:** é a diferença entre o `BlobServiceClient` que a
aplicação usa internamente e o **domínio do SAS** que você entrega ao cliente —
com CDN ou nome customizado na frente, os dois deixam de coincidir, e a
assinatura tem de ser emitida para o endereço que o cliente vai bater.
