# ADR-0055 — O STT ouve qualquer idioma: modelo multilíngue e detecção, em vez de língua fixa

- **Status:** aceito
- **Data:** 2026-09-09
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **6 — contraria uma
  convenção estabelecida.** O ADR-0027, item 7, **bloqueou explicitamente** a
  escolha de modelo de STT "até existir insumo com voz real de aprendiz", e os
  dois adapters carregam `LANGUAGE = "en"` como constante de módulo, com o
  comentário "não é autodetecção — o aluno fala inglês por definição".
  Este ADR desfaz as duas coisas, e por isso precisa existir.

## Contexto

O primeiro uso do produto em aparelho físico (CARD-037) produziu cinco
apontamentos, registrados em `docs/briefing-qualidade-da-conversa-2026-09-09.md`.
O terceiro deles: *"o STT entende errado — e 'deduz' inglês quando falo
português"*.

A causa foi **medida, não suposta**, na sessão de investigação de 2026-09-09.
Insumo: três falas sintéticas (`say -v Luciana` para português, `say -v
Samantha` para inglês) mais os quatro insumos já usados em
`docs/medicao-latencia.md`. Motor: `mlx-whisper`, que é o default nesta máquina.

**Fala em português, no `small.en` de hoje, duas execuções do mesmo áudio:**

```
pt1.aiff  ->  'Comment SHARE Tooth imitate'                             avg_logprob=-5.938
pt1.aiff  ->  'And if you like this video, please like and subscribe.'  avg_logprob=-1.124
pt2.aiff  ->  '....'                                                    avg_logprob=-4.139
en1.aiff  ->  'Yesterday I go to the market to buy some bread, …'       avg_logprob=-0.143
```

Não é só errado: é **não determinístico**, e a segunda saída é a alucinação
clássica de legenda de YouTube — o modelo devolvendo o que viu no treino quando
o áudio não se parece com nada que ele saiba transcrever. **É o comportamento
esperado de uma variante *English-only*, não um defeito dela.**

**A comparação que decide, com três execuções por par e mediana:**

| insumo | `small.en` (hoje) | `small` multi + `language="en"` | `small` multi + detecção |
|---|---|---|---|
| pt1 (4,1 s, português) | 1,72 s — lixo | **0,28 s** — `"I don't know how to say this in English, can you help me?"` | **0,46 s** — `pt`, texto correto em português |
| en1 (4,4 s) | 0,29 s | 0,30 s | 0,47 s |
| amazing-project (2,3 s) | 0,25 s | 0,25 s | 0,43 s |
| curto (19,1 s) | 0,60 s | 0,60 s | 0,78 s |
| longo (63,7 s) | 2,21 s | 2,24 s | 2,32 s |

Dois números mandam nesta decisão:

1. **Trocar `small.en` por `small` multilíngue com a língua fixa custa ZERO.**
   Cinco insumos, diferença dentro do ruído de medição. A intuição de que "o
   modelo multilíngue é mais pesado" está errada nesta faixa: o `.en` e o multi
   têm o mesmo tamanho de rede; o que muda é o vocabulário do decoder.
2. **Detectar o idioma custa +0,17 s, fixo.** É uma janela de 30 s a mais no
   encoder, e por isso **não cresce com a duração da fala**: +0,18 s no insumo
   de 4 s, +0,18 s no de 19 s, +0,11 s no de 64 s. O comentário do
   `faster_whisper_adapter.py` que dizia "detectar custa uma janela a mais"
   estava certo — faltava o número.

**O que a investigação derrubou do briefing:** ele atribuía parte do erro ao
`beam_size=1` do CARD-006. Isso é **falso para o que foi observado**:
`BEAM_SIZE` só existe no `faster_whisper_adapter.py`, e o Mac do desenvolvedor
roda o `mlx`, que nunca passou esse parâmetro. O `beam_size` continua sendo um
trade-off legítimo do outro adapter e segue **não remedido** — mas não explica
nada do que o aparelho mostrou.

## Decisão

**O modelo de STT passa a ser multilíngue, e o idioma passa a ser detectado, não
fixado.** Em detalhe:

1. Os defaults mudam para as variantes multilíngues:
   `stt_model_mlx = "mlx-community/whisper-small-mlx"` e
   `stt_model_faster_whisper = "small"`. O tamanho (`small`) **não muda** — a
   evidência justifica trocar a variante, não subir de porte.
2. `LANGUAGE` deixa de ser constante de módulo nos dois adapters e vira
   **configuração**, `stt_language: str | None = None`, onde `None` significa
   detectar. Um campo, não dois, porque aqui os dois motores falam a mesma
   língua de parâmetro — ao contrário do nome do modelo, que o ADR-0027 manteve
   em dois campos com razão.
3. **O idioma detectado é dado de produto, não log.** Ele atravessa a porta
   (ADR-0056) e chega ao professor (ADR-0059), porque a decisão de produto
   tomada em 2026-09-09 foi: *o aluno que fala português deve ser entendido e
   tratado pedagogicamente*, não silenciosamente traduzido.
4. O bloqueio do **ADR-0027 item 7 é levantado apenas para a variante**
   (`.en` → multilíngue). A escolha de **porte** (`small` → `medium`) continua
   bloqueada pelo mesmo item: não há insumo com voz real de aprendiz que a
   justifique, e ela custa latência de verdade.
5. **O orçamento de latência aceita os +0,17 s**, e o número entra no registro:
   o p50 medido no aparelho vai de 3.037 ms para ~3.210 ms (+5,7%). É o preço
   declarado da decisão de produto do item 3.

## Alternativas consideradas

### Alternativa A — multilíngue com `language="en"` fixo

Manter a língua fixa e apenas trocar a variante do modelo. **Custo zero de
latência**, e resolve inteiramente a alucinação: o multi diante do português
devolveu `"I don't know how to say this in English, can you help me?"` — inglês
fiel ao sentido, não lixo.

Rejeitada **por decisão de produto, não por técnica**. Ela apaga a informação de
que houve português: o professor recebe uma frase em inglês perfeita e responde
como se o aluno a tivesse dito. Um aluno iniciante que pediu ajuda em português
receberia de volta a ilusão de que falou inglês — que é o oposto de ensinar.
Fica registrada como **o recuo barato**: se os +0,17 s se mostrarem caros
demais, esta é a configuração para a qual voltar, e ela é uma linha de `.env`.

### Alternativa B — manter `small.en` e filtrar pela confiança

Não trocar nada e apenas recusar transcrições de baixa confiança (ADR-0057).
Rejeitada porque resolve metade errada do problema: o aluno em português nunca
seria **entendido**, apenas recusado, sempre. A confiança é a rede de segurança
para o que continua ruim depois da troca — não substituto dela.

### Alternativa C — subir para `medium` multilíngue

Rejeitada por falta de evidência **e** por custo. Não há medição de acerto com
voz real de aprendiz que a justifique (é exatamente o que o ADR-0027 item 7
exige), e o `medium` é ~3x o `small` em parâmetros, num orçamento onde o
pipeline do servidor já é 2,4 s dos 3,0 s. Gatilho para reabrir: um conjunto de
falas reais em que o `small` multilíngue erre de forma medida e repetida.

## Consequências

- **Positivas:** a alucinação em português desaparece pela raiz — o modelo passa
  a poder transcrever o que ouviu. O idioma detectado vira insumo pedagógico. O
  `.env` ganha um botão para voltar atrás sem recompilar nada.
- **Negativas:** **+0,17 s no caminho crítico**, num orçamento já estourado
  (3,04 s medidos contra alvo de 2,4 s). Os pesos multilíngues são um download
  novo (~500 MB no `small` do mlx) que toda máquina e todo container precisa
  buscar de novo — o worker que subir sem eles falha na readiness (ADR-0025), o
  que é o comportamento correto, mas é uma surpresa a mais no primeiro arranque.
  A detecção pode **errar** em fala curta ou ruidosa, e um "pt" falso positivo
  faria o professor tratar como português o que era inglês ruim — risco novo,
  que o ADR-0059 mitiga tratando o idioma como *dica*, nunca como comando.
- **A medição é de voz sintética.** Ela prova o mecanismo (o `.en` não consegue
  transcrever português; o multi consegue; o custo é conhecido) e **não** prova
  acerto sobre sotaque brasileiro real. É a mesma limitação declarada pelo
  ADR-0027, e ela permanece.
- **Equivalente mental .NET:** trocar de `en-US`-only para *culture-aware* num
  serviço de parsing — o custo não está no parser, está em ter de decidir a
  cultura antes, e em todo mundo abaixo passar a receber a cultura junto do
  valor.
