# Referência — o *porquê* das regras do cliente

Complemento de [SKILL.md](SKILL.md). Aqui mora o raciocínio, o trade-off aceito
e o **gatilho** que reabre cada decisão. A skill diz *o quê*; este arquivo diz
*por quê* e *até quando*.

## Como esta skill não mente

Ela nasceu no CARD-011 — **de propósito depois** do primeiro código de cliente.
A irmã (`voicecoach-arquitetura`) registrou o motivo no CARD-004: *"regra
escrita antes de existir tela é letra morta"*. Toda regra aqui foi conferida
contra código que roda, não contra intenção.

Três consequências práticas:

1. **Nenhuma regra sem ADR de origem.** Se você não consegue citar a fonte, ela
   não devia estar na skill.
2. **Divergência entre skill e código não se resolve afrouxando a skill.** Ou o
   código está errado, ou falta ADR novo (mesmo princípio do ADR-0012).
3. **A skill cresce por postmortem**, não por antecipação — com linha no log
   no fim deste arquivo.

## Por que o cliente tem skill separada do backend

Não é organização: é que **as regras não se transferem**. O backend tem cinco
camadas com um contrato executável (`import-linter`) que reprova a seta errada.
O cliente **não tem equivalente** — nada impede um componente de importar
qualquer coisa, e o Metro empacota feliz. As fronteiras do cliente
(`apps/*` não é importado por `packages/*`; o app fala com o backend só pelo
`api-client`) são hoje **prosa em README**, não gate.

> **Dívida declarada:** essa fronteira não tem verificação automática. *Gatilho
> para criar uma:* quando `packages/` tiver algo além de tipos gerados, ou
> quando a web existir e a tentação de compartilhar componente aparecer.

## As fronteiras, e o que cada uma protege

### `packages/api-client` — conhece HTTP e o contrato, não conhece produto

Zero regra de negócio, zero UI, zero estado de tela. Existe porque duplicar
tipos entre mobile e web **garante** drift — a classe de bug que só aparece em
runtime, no aparelho de alguém (ADR-0008, Alternativa A).

O `schema.d.ts` é **commitado de propósito**: é o que faz uma mudança de
contrato virar **diff revisável** no PR. O CI compara o gerado com o commitado
(job `openapi`) — mas quem prova que o *app* ainda casa com ele é o
`tsc --noEmit` do job `mobile` (ADR-0043). São dois gates diferentes, e o
segundo só existe desde o CARD-011.

### Mobile e web não compartilham UI (ADR-0002)

A Alternativa A do ADR-0002 (`react-native-web` cobrindo tudo) foi rejeitada
com **dado observado**, não com argumento: o monorepo da empresa do
desenvolvedor faz exatamente isso, e paga com três pacotes só para conciliar
aparência (`ui`, `ui-override`, `ui-tokens`), arquivos `.web.tsx`/`.native.tsx`
espalhados e um `CLAUDE.md` de 24 KB em que seções inteiras são *quirks* de
plataforma.

*Gatilho para reabrir:* sobreposição de telas grande o bastante para que manter
duas UIs custe mais que conciliar duas plataformas. Hoje a sobreposição é
pequena **por decisão de produto** (visão §A).

## Por que a permissão é estado da plataforma

É a diferença mais cara entre React web e React Native nesta base.

Na web, permissão é uma promessa que você pede e o browser resolve; se o usuário
negar, você pede de novo. **No iOS, não.** O sistema mostra o diálogo **uma vez**
por instalação. Depois disso, `requestRecordingPermissionsAsync()` retorna
negado **na hora**, sem UI nenhuma — do ponto de vista do código é indistinguível
de uma negação instantânea do usuário. Um app que só conheça
`concedida`/`negada` fica preso num botão que não faz nada.

Por isso:

- **consulte** (`getRecordingPermissionsAsync`) antes de **pedir**, e só peça
  quando o aluno tiver tocado em algo — pedir no arranque gasta a única chance;
- traduza `granted` + `canAskAgain` para os **três** estados;
- o terceiro tem tela pronta no design (artboard 13) e **é o item que o CARD-011
  manda nunca cortar**.

E ela **sobrevive ao processo**: o usuário pode revogá-la nos Ajustes com o app
em background. Guardar "já tenho permissão" em estado é guardar uma verdade com
data de validade desconhecida.

## Por que o limite de duração é do produto, e não do componente

Origem: diagnóstico §7.4. O protótipo usava *"cap de 2 MB como proxy de
duração"* porque o servidor não conhecia a duração antes de baixar o arquivo. O
destino escrito é **"cliente mede e limita na captura; servidor valida ambos"**.

A metade do servidor existe desde o CARD-010: a borda decodifica o upload e
recusa acima de `max_turn_audio_duration` (120 s). Se o cliente não parar antes,
o aluno fala três minutos, espera o upload inteiro e recebe **413**. A folga
entre 90 e 120 é o custo de rede que se escolhe não desperdiçar.

E o critério de aceite é explícito: para sozinha **e informa**. Parar em
silêncio é meio requisito.

> **Por que reagir a `durationMillis` e não usar `setTimeout`:** o `setTimeout`
> mede o tempo do JavaScript. O relógio que importa é o do microfone, e quem o
> conhece é o objeto nativo do recorder — `useAudioRecorderState` faz polling
> dele. Um app em background, um GC longo ou uma interrupção de chamada
> dessincronizam os dois relógios.

## O transporte: o que o spike do CARD-011 mediu

O ADR-0026 previa que o cliente precisaria de `react-native-sse` (polyfill de
`EventSource` com headers) porque **o `EventSource` nativo não aceita
`Authorization`**. O spike mediu, dentro do Expo Go, contra o endpoint real:

| | `fetch` global (RN) | `expo/fetch` |
|---|---|---|
| turn processando ao vivo | `transcribed` +686 ms · `chunk 0` **+1653 ms** · `chunk 1` +2782 ms · `feedback` +2788 ms · `completed` +2867 ms — **5 leituras** | idem, testado no turn já pronto |
| turn já completo (replay) | 1 leitura | 2 leituras, +13 ms |

**Conclusão:** `fetch` entrega o stream progressivamente e aceita header — as
duas coisas que faltavam ao `EventSource`. Nenhuma dependência de transporte
entra. O `chunk 0` em 1,65 s bate com o 1,6 s medido no backend, o que também
confirma que o Expo Go não é o gargalo.

**A armadilha que custou uma execução do spike:** o `sse-starlette` termina
linha com **CRLF**, então o separador de eventos é `\r\n\r\n`. Um parser que
procure `\n\n` recebe o stream inteiro e **não reconhece evento nenhum** — sem
erro, sem exceção, parecendo "SSE não funciona no Expo Go". Normalize antes de
qualquer `split`.

*Gatilho para reabrir a escolha:* precisar de reconexão automática com
`Last-Event-ID` sem escrevê-la à mão — é o que o `EventSource` daria de graça.

## Por que o Expo Go é limite, e não etapa

ADR-0010: custo zero, sem conta paga, sem EAS. ADR-0002: Expo Go / build local.
ADR-0003: o V2 realtime é que exigirá módulo nativo, e ele tem gatilho próprio.

Portanto **"não funcionou no Expo Go" é um achado do card**, que vira ADR ou
dívida escrita — nunca um convite a sair para dev build no meio de uma sessão.
Sair para dev build muda o ciclo de desenvolvimento inteiro (build local, tempo
de iteração, instalação no aparelho) e é decisão do desenvolvedor.

## Design: seguir a direção, reconciliar a sequência

O design é de **2026-08-17**. A cascata (ADR-0022/0023) é de **2026-08-19**, e a
medição que colocou o primeiro trecho em 1,6 s veio depois. Três coisas nele
descrevem um produto que não existe mais — a tabela completa está em
`docs/design/README.md`.

A mais cara: o artboard 05 diz *"Você já pode ler; o áudio toca sozinho quando
chegar"*. **Hoje é o contrário** — o áudio vem primeiro, em trechos, e o texto
do feedback fecha depois. Uma tela montada na ordem desenhada precisa ser
refeita, não ajustada.

E há uma lacuna: **não existe artboard do estado "gravando"**, que é o coração
do CARD-011. O que existe para derivá-lo é o style guide (84 px, pulso,
quadrado). Derivar é permitido; inventar tela nova, não.

## Anti-overengineering — consulte antes de propor peça nova

Além da Parte F da visão, o ADR-0044 registra o que **não entrou** no cliente e
o gatilho de cada um: polyfill de SSE, state manager global, biblioteca de
animação, e a fonte `Instrument Sans` (adiada, não descartada).

A régua é a mesma da irmã: **uma peça sem consumidor é uma peça sem gatilho.**
O `expo-router` entrou com uma tela só — decisão do desenvolvedor, contra a
recomendação — e está registrado como o preço pago desta sessão (ADR-0044 §3).

## Lacunas conhecidas — não invente

| Lacuna | Quem resolve |
|---|---|
| ~~Não há client HTTP em `packages/api-client`~~ | **resolvido no CARD-012** (ADR-0046) |
| ~~Não há upload, playback de trechos, nem consumo de SSE na tela~~ | **resolvido no CARD-012** |
| O **Problem Details** (ADR-0040) não está no OpenAPI, então o erro da API não é tipo gerado | ADR-0046 §6, com gatilho |
| A dedup e o recuo vivem no app, não no pacote — a web terá de reimplementá-los ou promovê-los | ADR-0046, gatilho: 1º card da web que consuma o stream |
| Não há autenticação; as rotas `/v1` estão abertas com `DEV_STUDENT_ID` | fase própria (ADR-0007) |
| Não há gate de teste automatizado no cliente | ADR-0043 item 6, com gatilho |
| Não há verificação automática da fronteira `apps/` ↔ `packages/` | ver §"Por que o cliente tem skill separada" |
| A fonte `Instrument Sans` não está carregada | dívida do CARD-011 |
| `apps/web` está vazio | fase própria |
| Comportamento do stream quando o token expirar | dívida registrada no ADR-0026 |

## Log de decisões desta skill

O que mudou aqui, quando e por quê. Alteração de regra sem linha nova nesta
tabela é alteração que ninguém vai conseguir auditar depois.

| Data | Mudança | Motivo |
|---|---|---|
| 2026-08-24 | Skill criada no CARD-011 | Herança escrita do CARD-004, adiada de propósito até existir código de cliente. Destila ADRs 0001–0003, 0007, 0008, 0010, 0023, 0024, 0026, 0043, 0044 e o style guide |
| 2026-08-24 | Regra nova: **`fetch` entrega SSE no Expo Go; nenhum polyfill entra** | Medido no spike do CARD-011 contra o endpoint real. O ADR-0026 previa `react-native-sse`; a medição dispensou a dependência |
| 2026-08-24 | Armadilha registrada: separador de evento SSE é `\r\n\r\n` | Não é hipótese: custou uma execução inteira do spike, com falha **silenciosa** (stream chegando, zero eventos reconhecidos) |
| 2026-08-24 | Regra nova: permissão tem **três** estados, e o terceiro tem tela | O ciclo do iOS não reapresenta o diálogo; sem o terceiro estado o app fica preso num botão inerte |
| 2026-08-24 | Regra nova: desligar `allowsRecording` ao parar de gravar | Comportamento do iOS: o modo de gravação joga o playback para o alto-falante do ouvido |
| 2026-08-24 | **Dívida declarada:** a fronteira `apps/` ↔ `packages/` não tem gate | O backend tem `import-linter`; o cliente não tem equivalente. Registrar a ausência é o que impede que ela passe por regra cumprida |
| 2026-08-25 | Regra nova: **upload é `Blob`, nunca `{uri, name, type}`** | CARD-012. Medido no Expo Go SDK 57 contra o endpoint real: as duas formas com `uri` dão `Unsupported FormDataPart implementation`; `Blob` dá 202. **Inverte o idioma que todo tutorial de RN ensina** (ADR-0046 §4) |
| 2026-08-25 | Regra nova: **não reescrever host de URL assinada** | CARD-012. `X-Amz-SignedHeaders=host` põe o `Host` no cálculo do SigV4; trocar depois dá 403 e não há conserto no cliente. Quem resolve é `S3_PUBLIC_ENDPOINT_URL` no servidor (ADR-0045) |
| 2026-08-25 | Regra nova: **o relógio da medição tem de ser mais fino que o critério** | CARD-012. A 1ª leva de 10 execuções mediu gap p50 de 594 ms com `updateInterval` no default de 500 ms — o número era a tick, não o produto (ADR-0047 §6) |
| 2026-08-25 | Regra nova: **os payloads do SSE são tipos gerados** | CARD-012. Quatro dos cinco estavam fora do OpenAPI, e a promessa do ADR-0008 era falsa justamente para o stream. Corrigido por envelope na rota (ADR-0046 §5) |

*Esta skill cresce pelos postmortems (`docs/learnings/`), não por antecipação.*
