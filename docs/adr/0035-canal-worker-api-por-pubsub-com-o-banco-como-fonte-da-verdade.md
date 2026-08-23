# ADR-0035 — O canal worker→API é pub/sub, e o banco é a fonte da verdade

- **Status:** aceito
- **Data:** 2026-08-23
- **Complementa:** [ADR-0026](0026-entrega-progressiva-por-sse-com-polling-como-contrato-de-recuo.md)
  (SSE e os nomes dos eventos), [ADR-0023](0023-ciclo-de-vida-do-turn-com-entrega-em-cascata.md)
  (trechos persistidos), [ADR-0024](0024-midia-por-trecho-chave-url-assinada-e-retencao-assimetrica.md)
  (chave e URL assinada)
- **Critérios de obrigatoriedade:** **2 — define uma fronteira** (é o contrato
  entre dois processos, e o formato do que trafega entre eles).

## Contexto

O ADR-0026 fixou os cinco eventos que o cliente recebe por SSE (`transcribed`,
`chunk`, `feedback`, `completed`, `failed`) e exigiu **retomada por
`Last-Event-ID`**. O que ele não decidiu foi **como o worker conta isso à API** —
e os dois processos não se importam (ADR-0012), então precisam de um canal.

Quando o CARD-009 foi planejado, a leitura mais fiel ao que os ADRs escreveram
parecia ser "canal nenhum": o ADR-0023 já persiste os trechos, o ADR-0026 diz
que a retomada é *"a partir dos trechos persistidos"*, e a visão §F corta o que
não tem pergunta a responder. O SSE leria do banco.

**A implementação desmentiu essa leitura, e o motivo é concreto:** o evento
`feedback` carrega `{has_mistakes, original, corrected, tip}`, e **nada disso é
persistido hoje** — a tabela de correções é do CARD-013. Um canal que só
"acorde" um leitor que busca tudo no banco simplesmente não consegue entregar um
dos cinco eventos do contrato.

## Decisão

**O worker publica os eventos num canal Redis de pub/sub, um por turn, com o
payload completo. O canal é o caminho rápido; a fonte da verdade continua sendo
o banco.**

1. **Canal por turn:** `voicecoach:turn:{turn_id}`. Um canal global obrigaria
   cada conexão SSE aberta a receber e descartar os eventos de todos os outros
   alunos; por turn, é um `SUBSCRIBE` e nenhum filtro. Não há o que limpar: o
   canal deixa de existir quando o último assinante sai.
2. **A divisão de papéis é a decisão, não o transporte.** O canal entrega
   latência; o banco entrega durabilidade. Perder uma publicação custa alguns
   segundos ao aluno (o cliente cai no polling do ADR-0026, item 4) e **nunca**
   custa dado.
3. **A retomada por `Last-Event-ID` lê do banco**, não do canal — exatamente
   como o ADR-0026 item 3 escreveu.
4. **O que viaja no canal é a `storage_key`, não a URL assinada.** A URL viaja
   no evento **SSE**, que é outro evento, montado pela API no momento da
   entrega. Assinar no worker produziria URLs cujo TTL começou a contar na
   publicação, já envelhecidas quando um cliente reconectasse; e a retomada, que
   lê do banco, só tem a chave para oferecer. Uma origem, um caminho de
   assinatura.
5. **JSON, não `pickle`.** Ao contrário do payload do job na fila, este conteúdo
   é reencaminhado para um `text/event-stream`, que é texto por definição — e o
   formato do fio deixa de depender da versão de Python dos dois lados.
6. **Os nomes do fio são traduzidos explicitamente**, numa tabela com
   `assert_never`, e não derivados do nome da classe. Os cinco nomes são
   contrato de API (ADR-0026): renomear uma dataclass não pode mudar o que o
   cliente recebe.
7. **Falha ao publicar não derruba o turn.** É a única exceção capturada e
   descartada em todo o pipeline, e é consequência direta do item 2.

**Equivalente mental .NET:** um `IDistributedEventBus` fire-and-forget na frente
de um repositório que já é durável — parecido com publicar uma notificação no
Redis para invalidar cache, onde perder a mensagem degrada mas não corrompe. O
contraste é com uma fila durável (RabbitMQ/outbox): aqui a entrega garantida é
deliberadamente **não** contratada, porque quem garante é a tabela.

## Alternativas consideradas

### Alternativa A — Redis Streams

- **O que é:** um stream por turn, com id por entrada (que mapearia
  naturalmente no `id:` do SSE) e leitura a partir de um ponto.
- **Por que foi rejeitada:** ela resolve retomada — que **já está resolvida**
  pelo banco, e resolvida melhor, porque o banco é o mesmo lugar de onde o
  `GET /v1/turns/{id}` (o contrato de recuo) responde. Em troca, cobra uma
  superfície inteira que não existe hoje: política de trimming (stream que
  ninguém apara cresce para sempre), decisão sobre consumer groups, e uma
  segunda fonte de verdade que pode divergir da tabela. É a peça que a visão §F
  corta por antecipação. **Gatilho para entrar:** a retomada precisar de algo
  que o banco não guarda **depois** de o CARD-013 persistir as correções — ou
  seja, se `feedback` continuar sendo o único evento não reconstituível.

### Alternativa B — Sem canal: o SSE lê do banco por polling interno

- **O que é:** o endpoint SSE consulta a tabela de tempos em tempos e emite o
  que for novo. Zero infraestrutura nova.
- **Por que foi rejeitada:** **não entrega o evento `feedback`**, que não é
  persistido até o CARD-013 — o contrato do ADR-0026 ficaria incompleto. E
  reintroduz, do lado de dentro, a latência de descoberta que o ADR-0026 existe
  para eliminar: o polling interno tem exatamente o mesmo problema do polling do
  cliente, só que escondido. Era a leitura preferida no planejamento desta
  sessão, e é registrada aqui como **descartada por evidência**, não por gosto.

### Alternativa C — Fila durável (outbox + RabbitMQ)

- **O que é:** garantir entrega de cada evento, com persistência do próprio
  evento.
- **Por que foi rejeitada:** a visão §F já cortou RabbitMQ, e o problema que
  uma outbox resolve — "o evento não pode se perder" — **não é o nosso**: o
  evento é derivável do estado, que já é durável. Pagar consistência transacional
  por uma notificação reconstituível é o exemplo de manual de overengineering.

## Consequências

**Positivas**

- O trecho chega ao cliente no instante em que existe, com uma conexão por turn
  em vez de N requisições.
- O canal pode cair inteiro sem que nenhum turn se perca — o pior caso é o
  produto ficar tão lento quanto o desenho original de polling.
- O worker continua sem conhecer HTTP: ele publica um evento de domínio, e quem
  o traduz para `text/event-stream` é a API.

**Negativas — o preço aceito**

- **Pub/sub é fire-and-forget.** Quem não está conectado no instante da
  publicação nunca recebe aquela mensagem. Aceitável só por causa do item 2 — e
  se algum dia um evento deixar de ser reconstituível do banco, esta decisão
  precisa ser reaberta.
- **O evento `feedback` não é retomável hoje.** Um cliente que reconecte no meio
  do turn perde o feedback **daquele** turn e o vê no histórico depois. Dívida
  explícita, com o CARD-013 como gatilho.
- **Duas representações do mesmo evento** (a dataclass interna e o payload do
  fio), com uma tabela de tradução no meio. É o preço de os nomes do fio serem
  contrato: elas podem divergir, e só o `assert_never` impede que a divergência
  seja silenciosa.
- **Mais uma coisa que a API precisa saber operar:** assinatura de canal,
  reconexão, e o cuidado de não segurar conexão de Redis por turn ocioso.
