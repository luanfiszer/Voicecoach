# ADR-0024 — Mídia por trecho: chave, URL assinada junto do evento e retenção assimétrica

- **Status:** aceito
- **Data:** 2026-08-19
- **Substitui:** [ADR-0006](0006-storage-de-midia-s3-url-assinada.md)
- **Relacionado:** ADR-0023 (trechos como artefatos), ADR-0026 (transporte),
  CARD-008, CARD-017
- **Critérios de obrigatoriedade:** **2 — altera uma fronteira** (esquema de
  chaves e contrato de download) e **4 — afeta privacidade** (exposição de
  mídia e retenção de voz).

## Contexto

O ADR-0006 decidiu S3-compatível (MinIO local) com **URL pré-assinada de TTL
curto** e chave por usuário — e essas duas decisões continuam de pé. O que ele
não podia prever é que **o áudio da resposta deixaria de ser um objeto**.

Com a cascata (ADR-0023), um turn produz de 3 a 6 trechos em vez de um arquivo.
Isso reabre três pontos que o ADR-0006 tratou como triviais:

1. **A chave** — `{student_id}/{session_id}/{turn_id}/reply.mp3` não comporta
   ordem nem multiplicidade.
2. **Quem pede a URL.** No ADR-0006 o cliente fazia `GET /v1/turns/{id}` e
   recebia uma URL. Com trechos, esse desenho custaria **um roundtrip por
   frase** — dentro de um orçamento de 1,8 s, é o tipo de custo que anula o
   ganho que a cascata comprou.
3. **A retenção.** Trecho e áudio inteiro carregam o mesmo conteúdo. Guardar os
   dois por 90 dias é pagar duas vezes por bytes de voz — e voz é dado pessoal
   (visão §E).

## Decisão

**Cada trecho é um objeto próprio, com chave ordenável; a URL assinada viaja
junto do evento que anuncia o trecho; e a retenção do trecho é curta porque o
áudio inteiro é a cópia de longo prazo.**

1. **Esquema de chaves** (namespace por usuário, como o ADR-0006 já mandava):

   ```
   {student_id}/{session_id}/{turn_id}/input.{ext}
   {student_id}/{session_id}/{turn_id}/reply/{index:03d}.{ext}
   {student_id}/{session_id}/{turn_id}/reply/full.{ext}
   ```

   `{index:03d}` é zero-padded **de propósito**: a ordem lexicográfica do
   storage passa a coincidir com a ordem de playback, o que faz `list_objects`
   por prefixo devolver os trechos já ordenados e mantém o `delete_prefix` do
   CARD-017 funcionando sem mudança.
2. **A URL assinada é emitida pelo servidor e entregue junto do evento do
   trecho** (ADR-0026), nunca pedida pelo cliente trecho a trecho. Assinar é
   HMAC local — custa microssegundos e economiza um roundtrip por frase.
3. **TTL da URL de trecho é curto (minutos)** e **maior que o tempo esperado de
   playback do turn inteiro** — uma URL que expira enquanto o aluno ainda ouve é
   um bug de produto disfarçado de segurança. O valor fica em `Settings`.
4. **Retenção assimétrica**, em lifecycle do bucket:

   | Objeto | TTL default | Por quê |
   |---|---|---|
   | `input.*` | 7 dias | reprocessamento e debug (herdado do ADR-0006) |
   | `reply/{index}.*` | **1 dia** | redundante assim que `full` existe |
   | `reply/full.*` | 90 dias | é o que o histórico reproduz |

5. **Degradação honesta continua sendo regra** (CARD-017): trecho expirado com
   `full` presente ⇒ o cliente toca o inteiro. Ambos expirados ⇒ o turn responde
   com áudio indisponível, texto e correções preservados. Nunca 500.
6. **O que o ADR-0006 decidiu e continua valendo sem alteração:** API S3 como
   contrato atrás da porta `MediaStorage`, MinIO no Compose, bucket privado,
   proibição de URL eterna, delete por prefixo no delete de conta.

## Alternativas consideradas

### Alternativa A — Um objeto só, reescrito a cada trecho (append)

- **O que é:** manter `reply.mp3` e ir acrescentando bytes.
- **Por que foi rejeitada:** S3 não tem append; seria `PUT` completo a cada
  frase, com tráfego quadrático, e um cliente que baixasse no meio pegaria um
  arquivo truncado sem saber. O protocolo escolhido no ADR-0006 não suporta a
  ideia, e trocar o protocolo por causa disso custaria mais que a tabela de
  trechos.

### Alternativa B — Trechos servidos pela própria API (bytes passando pelo backend)

- **O que é:** `GET /v1/turns/{id}/chunks/{index}` devolvendo o áudio.
- **Por que foi rejeitada:** tira o backend de fora do caminho dos bytes — o
  ganho que o ADR-0006 listou como positivo — e coloca banda e CPU de streaming
  no processo que precisa estar livre para atender o próximo turn. Fica
  registrada como saída caso um provedor de storage sem URL assinada entre em
  cena.

### Alternativa C — Não gravar o áudio inteiro (só os trechos)

- **O que é:** o histórico toca a sequência de trechos.
- **Por que foi rejeitada:** obriga todo consumidor futuro (histórico no mobile,
  web companion, export LGPD) a saber remontar a sequência, e transforma cada
  reprodução antiga em N downloads. Um arquivo por turn é a forma que o resto do
  produto já sabe consumir.

## Consequências

**Positivas**

- Nenhum roundtrip extra no caminho crítico: o trecho chega já assinado.
- A retenção assimétrica reduz o custo de bytes **e** a exposição de voz — o
  trecho, que é a cópia mais numerosa, é o que some primeiro.
- `delete_prefix` e as lifecycle rules do CARD-017 continuam valendo sem
  reescrita, porque tudo segue sob o mesmo prefixo de turn.

**Negativas — o preço aceito**

- **N objetos por turn em vez de 1.** Mais chamadas de `PUT`, mais linhas de
  lifecycle, e um bucket com contagem de objetos que cresce ~5× mais rápido.
- **Duas cópias do mesmo áudio convivendo por um dia** — desperdício deliberado,
  em troca de compatibilidade de contrato e de histórico simples.
- **Uma URL assinada pode expirar durante a escuta** se o TTL for mal escolhido.
  O ADR fixa a regra ("maior que o playback"), mas o valor errado só aparece em
  uso real — é risco de configuração, e o CARD-012 tem de exercitá-lo.
- **MinIO ≠ S3 em lifecycle** (nota herdada do ADR-0006), agora com mais regras
  para divergir.

**Equivalente mental .NET:** continua Azure Blob + SAS, mas o blob virou um
*virtual directory* com blocos numerados e política de expiração diferente por
nível de prefixo.
