# ADR-0075 — A retenção do bucket é aplicada por comando e verificada no boot do worker

- **Status:** aceito
- **Data:** 2026-10-01
- **Relacionado:** ADR-0024 (retenção assimétrica), ADR-0027 (incompatível falha no boot), ADR-0034 (tag de retenção), ADR-0069 (delete de conta), CARD-017, CARD-052, CARD-055
- **Critérios de obrigatoriedade:** **4 — privacidade** (retenção de dado de usuário) e **2 — contrato** (o que `GET /v1/turns/{id}` devolve depois do prazo).

## Contexto

As três regras de lifecycle do ADR-0024 foram escritas e testadas no
CARD-008 (`apply_lifecycle`), mas **nenhum código de produção as chamava**.
Verificado em 2026-10-01 no bucket local: `mc ilm rule ls` →
*"The lifecycle configuration does not exist"*. A voz dos alunos estava sendo
guardada para sempre — o modo de falha que o ADR-0034 nomeou ("não daria
erro, só faria voz de aluno viver para sempre"), por outro caminho.

E `GET /v1/turns/{id}` assinava URL de objeto já expirado: o contrato
prometia `reply_audio_url: null` depois da retenção, e entregava um 404 no
player.

## Decisão

1. **Aplicar é comando de operador:** `uv run voicecoach-storage-setup`
   (idempotente; lê de volta o que aplicou). Configurar o bucket é
   administração, como criá-lo (CARD-008) — não roda no caminho de request.
2. **O worker verifica no boot** (`ensure_lifecycle`), **antes** da chave de
   readiness: sem as regras, ou com TTLs diferentes de `Settings`, ele não
   sobe e a mensagem diz o comando. Esquecer o setup vira erro visível, não
   silêncio.
3. **A API degrada por previsão, sem bater no bucket:** depois de
   `created_at + retenção`, trechos saem de `chunks` (o cliente cai no
   `reply_audio_url`) e, depois do prazo do inteiro, `reply_audio_url` é
   `null`. Mesma previsão conservadora do `ListSessions` ("não conte com ele").
4. **A matriz de retenção** mora em `docs/retencao-de-dados.md`, citando o
   mecanismo de cada linha — fonte do CARD-052.

## Alternativas consideradas

### A — Aplicar no boot (do worker ou da API), automaticamente
- **Prós:** impossível esquecer.
- **Por que foi rejeitada:** daria à credencial do produto permissão de
  administrar o bucket, que o CARD-008 recusou explicitamente para criar o
  bucket. Verificar exige só leitura da configuração.

### B — Regras no `docker-compose.yml` (`mc ilm rule add` no `createbuckets`)
- **Por que foi rejeitada:** duplicaria os TTLs fora de `Settings` — duas
  fontes de verdade para a única política que é obrigação legal (motivo já
  escrito no `lifecycle.py`). E não existe compose em produção.

### C — `HEAD` no objeto antes de assinar
- **Prós:** resposta exata, não previsão.
- **Por que foi rejeitada:** N chamadas de rede por GET, contra o "assinar é
  HMAC local" do ADR-0024; e o objeto que ainda existe na janela de graça do
  lifecycle é dado que a política diz que já não deveria contar.

### D — Anular `url` do trecho vencido em vez de removê-lo da lista
- **Por que foi rejeitada:** `ChunkPayload.url` não é anulável no contrato;
  torná-lo anulável quebraria os tipos gerados do cliente (ADR-0008).

## Consequências

- Todo ambiente novo (dev, CI que suba o worker, o deploy do CARD-055) precisa
  rodar o setup uma vez — documentado no `backend/README.md`.
- O SSE de um turn antigo ainda reenvia trechos do histórico sem esta
  previsão; aceito porque o SSE é para o turn ao vivo (ADR-0026). Gatilho:
  algum cliente passar a reabrir o stream de turn com mais de um dia.
- **Decisão autônoma (loop, 2026-10-01):** remover trechos vencidos da lista
  em vez de mudar o contrato → **PENDENTE DE REVISÃO HUMANA**.
