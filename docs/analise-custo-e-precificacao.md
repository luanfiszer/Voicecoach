# Análise de custo unitário e precificação

- **Data:** 2026-08-19
- **Origem:** sessão de medição de latência (o custo apareceu como consequência
  da decomposição do pipeline, não como objetivo da sessão)
- **Status:** análise — **nenhuma decisão de produto foi tomada aqui**

---

## 0. A premissa que sustenta este documento — NÃO CONFIRMADA

> ⚠️ **Este documento inteiro depende de uma premissa que contradiz o objetivo
> declarado do projeto.** Registrada como não confirmada pela regra de
> [LEARNING-0002](learnings/0002-diagnostico-sem-confirmar-premissas-de-escopo.md).

O `CLAUDE.md` declara o objetivo como *"meu aprendizado real de Python/React"* e
*"defensável em entrevista técnica"*; o [ADR-0010](adr/0010-politica-de-custo-projeto-pessoal.md)
chama isto de **projeto pessoal** com infra a custo zero. Uma busca no
repositório inteiro por `assinatura`, `monetiz`, `cobran`, `precifica`, `receita`
e `plano pago` não encontrou **nenhum** registro de intenção comercial — todas as
ocorrências de "assinatura" são assinatura de função ou de URL pré-assinada.

Portanto: **cobrar por este produto é premissa nova.** Se ela for adotada, o
documento de visão muda, não apenas um card. Enquanto não for confirmada, os
números abaixo são exercício de viabilidade, não plano.

---

## 1. A estrutura de custo tem duas naturezas

Confundir as duas foi o que tornou a primeira conta desta sessão ilegível.

| Natureza | O que é | Escala com |
|---|---|---|
| **Fixo** | caixa de infra, conta Apple, domínio | **nada** — é o mesmo com 1 ou 50 usuários, até a capacidade acabar |
| **Variável** | tokens do LLM | **turns**, e turns escalam com usuários |
| **Percentual** | comissão de loja, gateway de pagamento | receita |

A consequência prática é contraintuitiva: **a infra é irrelevante quase
imediatamente.** Já com 10 usuários ela é ~12% do total; com 100, ~1,4%.
Otimizar servidor é ruído; o custo é governado por tokens e por comissão.

---

## 2. De onde vem o custo de um turn

> **Corrigido em 2026-08-27 (CARD-014).** A tabela original desta seção era
> **estimativa**, e errava nas duas direções. O número abaixo é medido, das 6
> execuções reais de `benchmarks/results/llm_prompt_v1_vs_v2.json`. O que
> tornou a correção possível foi o `UsageEvent` ([ADR-0051](adr/0051-usage-event-fora-do-agregado-com-custo-congelado-na-escrita.md)),
> que passou a gravar o `usage` que o pipeline vinha descartando desde o
> CARD-007.

Modo dev do ADR-0010 (STT e TTS locais, `claude-haiku-4-5` a US$ 1/MTok de
entrada e US$ 5/MTok de saída), **turn sem histórico de conversa**, prompt v2:

| Componente | Tokens (medido) | Custo | Fatia |
|---|---|---|---|
| Entrada — system prompt + schema da tool + a fala do aluno | **1.488** | US$ 0,001488 | **56%** |
| Saída — `spoken_reply` + `translation_pt` + `corrections[]` | **238** | US$ 0,001190 | **44%** |
| STT local (`faster-whisper` / `mlx-whisper`) | — | US$ 0 | 0% |
| TTS local (Piper) | — | US$ 0 | 0% |
| **Total** | | **US$ 0,002678** | |

**100% do custo variável continua sendo o LLM.** O que mudou foi tudo o resto:

| A estimativa dizia | O medido diz | Erro |
|---|---|---|
| system prompt ~700 tokens | o prefixo sem histórico é **1.488** | **2,1x para baixo** |
| total ~US$ 0,004/turn | **US$ 0,002678** | **~49% para cima** |
| "meio a meio" entrada/saída | **56% / 44%** | a composição inverteu |
| saída ~400 tokens | **238** | 1,7x para cima |

Duas leituras que a correção obriga:

- **a projeção de custo era pessimista, não otimista.** Corrigir a base
  (§3) já dividia o custo por três; corrigir o custo unitário o reduz mais 33%.
  Nada aqui piora a margem;
- **a alavanca mudou de lado.** Com o v2, a **entrada** passou a ser a metade
  maior — e entrada é a metade que o prompt caching atacaria. Ver §9.

O v1, medido no mesmo benchmark, era **US$ 0,002542** (48,9% entrada / 51,1%
saída): o v2 ficou ~5% mais caro por turn e trocou saída por entrada.

### A distância até o limiar de caching (ADR-0021)

O [ADR-0021](adr/0021-prompt-caching-adiado-o-limiar-medido-nao-e-alcancado.md)
adiou o prompt caching porque o limiar medido do Haiku 4.5 é **4.096 tokens** e a
conversa não chegava lá. O número atualizado:

| Cenário | Entrada | % do limiar |
|---|---|---|
| v1, sem histórico (base do ADR-0021) | 1.242 | 30% |
| **v2, sem histórico (medido)** | **1.488** | **36%** |
| v2 + os 6 turns de histórico do worker (`HISTORY_TURNS`) — derivado, não medido | ~2.400 | ~58% |

**O gatilho continua não atingido, e agora isso é dado gravado em vez de
memória:** cada `usage_events` traz `llm_cache_creation_tokens` e
`llm_cache_read_tokens` com **zero como valor**. O dia em que um deles deixar de
ser zero — ou em que a entrada cruzar 4.096 por motivo pedagógico — é o dia de
reabrir o ADR-0021, e a consulta que responde isso agora existe.

> A linha com histórico é **derivada** do "~150 tokens por troca" do próprio
> ADR-0021, não medida. Medi-la custa ~3 execuções reais (~US$ 0,01) e ficou de
> fora do CARD-014 por não ser critério de aceite dele.

---

## 3. A suposição de volume estava projetando o perfil errado

O ADR-0010 projeta custo sobre *"uso pessoal: ~30 turns/dia"*. Esse é o perfil de
**um desenvolvedor testando o próprio app**, não o de um aluno. Como o número foi
escrito num ADR e reusado depois como se fosse dado de produto, ele passou a
inflar toda projeção derivada.

| Perfil | Turns/mês | Custo/mês (US$ 0,004/turn) |
|---|---|---|
| Desenvolvedor testando (base atual do ADR-0010) | 900 | US$ 3,60 |
| Aluno engajado — 15 turns, 5×/semana | ~300 | **US$ 1,20** |
| Aluno casual — 15 turns, 2×/semana | ~120 | **US$ 0,48** |

**Corrigir só a base de projeção divide o custo por três**, sem tocar em código.
O número do ADR-0010 não está errado para o que ele mede (o custo *do
desenvolvedor*); está errado como base de projeção de produto.

---

## 4. Dois custos que faltavam na conta

| Custo | Valor | Natureza |
|---|---|---|
| **Comissão de loja** (App Store / Google Play) | **15%** abaixo de US$ 1M/ano, **30%** acima | % da receita |
| Gateway de pagamento na web (Pix/cartão) | ~4% | % da receita |
| Conta Apple Developer | US$ 99/ano | fixo |
| Google Play | US$ 25 (único) | fixo |

**A comissão da loja é da ordem de 4× o custo de IA por usuário.** Escolher o
canal de cobrança pesa mais na margem do que qualquer otimização de token.

---

## 5. Margem por cenário de uso

Premissas: preço de **R$ 29,90/mês**, câmbio **R$ 5,50/US$**, 100 assinantes,
custo de IA otimizado **com o pacote que sobrou** (~US$ 0,0031/turn — ver §9),
venda **dentro do app** (comissão de 15%).

| | Casual (120 turns) | Engajado (300 turns) | Pesado (900 turns) |
|---|---|---|---|
| Receita bruta | R$ 29,90 | R$ 29,90 | R$ 29,90 |
| − Comissão de loja (15%) | −R$ 4,49 | −R$ 4,49 | −R$ 4,49 |
| − IA | −R$ 2,05 | −R$ 5,12 | −R$ 15,35 |
| − Infra rateada | −R$ 0,28 | −R$ 0,28 | −R$ 0,28 |
| **Margem** | **R$ 23,08 (77%)** | **R$ 20,01 (67%)** | **R$ 9,78 (33%)** |
| **Múltiplo sobre custo** | **4,4×** | **3,0×** | **1,49×** |

**Leitura:** a meta de 3× é batida no casual (4,4×) e fica **no fio da navalha no
engajado (3,0×)**; no perfil pesado despenca para **1,49×**. Um usuário fazendo ~3.000 turns/mês dá prejuízo
líquido.

Isto não é argumento contra cobrar — é a demonstração de que o
**[CARD-015](backlog/CARD-015-quotas-e-kill-switch.md) (quotas + kill switch) é
bloqueante de lançamento comercial**, não só técnico. Sem cota, a margem é
definida pelo usuário mais entusiasmado da base.

---

## 6. Âncoras de mercado

| Produto | Modelo | Preço |
|---|---|---|
| **Praktika** — conversa com IA (concorrente direto) | assinatura | **~US$ 8/mês (~R$ 44)** |
| Cambly — conversa com humano | assinatura por horas/semana | US$ 40–350/mês |
| Preply — aula com professor humano | por aula | a partir de R$ 16 / 50 min |

O teto da categoria de conversa com IA é ~R$ 40–45/mês. O argumento de
diferenciação disponível é a **correção pedagógica estruturada** (o JSON de
`corrected` + `tip` que o protótipo já produz), não preço.

Com margem de 77% no casual e 33% no pesado, um preço único provavelmente é
subótimo: dois planos (leve ~R$ 19,90 com cota menor; completo ~R$ 39,90)
separam melhor os perfis e o plano caro ainda fica abaixo da Praktika.

---

## 7. Cobrança por turn vs. assinatura

**Assinatura com cota.** Cobrança por turn cria "ansiedade de taxímetro": o aluno
fala menos para gastar menos, que é exatamente o oposto do comportamento que o
produto precisa induzir. A cota protege a margem sem punir o uso.

---

## 8. Achado: a unidade da cota diverge do driver de custo

O domínio **já** escolheu a unidade da cota. Em
`backend/src/voicecoach/domain/turn.py`, o campo `audio_duration` está
documentado como *"o insumo da quota em **minutos falados** (CARD-015)"*.

O problema: **com STT e TTS locais, o custo é dominado pelo número de chamadas ao
LLM, não pelos minutos falados.** O system prompt e o histórico dominam a entrada
e são reenviados por chamada, independentemente do tamanho da fala.

A [medição §5.1](medicao-latencia.md) quantificou o resíduo: uma fala longa
produz resposta maior (145 → 388 tokens de saída), então um turn longo custa
~1,7× um turn curto — mas **não 5×, que seria o necessário para a cota em minutos
ser justa**:

| Aluno | Minutos falados | Turns | Custo/turn | **Custo total** |
|---|---|---|---|---|
| A — 100 turns de 6 s | 10 min | 100 | US$ 0,00183 | **US$ 0,183** |
| B — 20 turns de 30 s | 10 min | 20 | US$ 0,00304 | US$ 0,061 |

Uma cota em minutos trata A e B como iguais, e **A custa 3× mais**.

- **Minutos falados** é a unidade que o **aluno** entende ("você tem 60 minutos
  de conversa este mês").
- **Turns** é a unidade que o **caixa** entende.

Hoje só a primeira está modelada. Decidir isto é escopo do **CARD-015** — este
documento apenas registra que as duas divergem e que a divergência medida é de 3×.

---

## 9. Alavancas de custo, com impacto em qualidade

| # | Alavanca | Economia estimada | Perde qualidade? | Status |
|---|---|---|---|---|
| **A** | ~~**Prompt caching**~~ | **0% no uso real** | — | ❌ **derrubada pela medição**: o limiar do Haiku é **4.096 tokens** e uma conversa deste produto não o alcança. Ver [ADR-0021](adr/0021-prompt-caching-adiado-o-limiar-medido-nao-e-alcancado.md) e [medição §5.2](medicao-latencia.md) |
| **B** | Tirar `translation_pt` da resposta padrão (gerar sob demanda) | ~17% do total, + ganho de latência | Nenhuma pedagógica — é feature de UI | 🔒 **congelado** até o eval (Fase 4) |
| **C** | Teto de histórico enviado (janela deslizante) | 10–20% da entrada | Sim, se apertar demais — o professor perde contexto | proposto, sem dono |
| **D** | Portão barato: não chamar o LLM para `yes`/`ok`/ruído | 5–10% | Nenhuma, com limiar conservador | proposto, sem dono |
| **E** | LLM local (custo de token zero) | 100% do variável | **Alto risco** — é o núcleo pedagógico | 🔒 gatilho: eval com baseline (ADR-0010) |
| **F** | Batch API (50% de desconto) | 50% | — | ❌ **descartada**: assíncrona com horas de latência; mata o produto |
| **G** | Modelo mais barato que Haiku | — | ❌ Haiku 4.5 já é o degrau mais barato da Anthropic | inexistente |
| **H** | **Vender pela web** em vez de dentro do app | **~11 pontos de margem** (15% → 4%) | Nenhuma | proposto — ver §10 |
| **I** | **STT + TTS no aparelho do aluno** | zera compute de servidor e o tráfego de áudio | Nenhuma de custo; risco de qualidade de voz | 🔒 gatilho: usuários pagantes reais — ver §11 |

Pacote sem perda de qualidade, **agora sem A** (**B + D**): **US$ 0,004 → ~US$ 0,0031/turn.**

> A queda da alavanca A **encarece** a projeção em ~55% frente ao que este
> documento estimava na primeira versão, e é o motivo de a tabela da §5 ter sido
> refeita. Custo projetado sobre alavanca não medida é o erro que a medição
> acabou de cobrar.

---

## 10. A alavanca de canal (H)

O [ADR-0002](adr/0002-stack-de-cliente-expo-mais-web-separada.md) já prevê um app
web companion. Se a assinatura for vendida **lá** (Pix/cartão, ~4%) em vez de
dentro do app (15–30%), recuperam-se **~R$ 3,30/usuário/mês** — quase o custo
inteiro de IA de um aluno engajado.

Consequência de desenho: o companion web deixa de ser "tela de progresso" e vira
**o canal de receita**. Isso muda a prioridade dele no roadmap e é decisão
arquitetural (critério 3 do [ADR README](adr/README.md)) — **não tomada aqui.**

> Restrição a verificar antes de decidir: as regras da App Store limitam
> divulgar cobrança externa dentro do app. É pesquisa a fazer, não suposição a
> carregar.

## 11. A alavanca que muda a conta inteira, e por que ela está parada (I)

A [medição desta sessão](medicao-latencia.md) mostrou `mlx-whisper` transcrevendo
17,6 s de áudio em **0,20 s** (modelo `base.en`) num M4. O chip de um iPhone recente é da mesma
família, e o TTS do sistema operacional é gratuito e instantâneo. Rodar STT e TTS
**no aparelho** zeraria o compute de servidor e o tráfego de áudio nos dois
sentidos, deixando só o LLM como custo.

**Por que não entra agora:** contraria o [ADR-0003](adr/0003-interacao-v1-turn-based-preparada-para-v2-realtime.md)
e o [ADR-0011](adr/0011-stt-e-tts-locais-como-default.md) de frente, e — mais
importante — **esvazia a prioridade nº 1 declarada do projeto**. Tirar STT e TTS
do backend remove exatamente as portas, os adapters e o pipeline de worker que os
CARDs 006–009 existem para ensinar. É a decisão certa para uma startup e a errada
para este projeto hoje.

**Gatilho:** existirem usuários pagantes reais — momento em que a economia deixa
de ser hipotética e o aprendizado de backend já terá acontecido.

---

## 12. O que precisa de decisão do desenvolvedor

1. **Monetizar é premissa nova** (§0) e contradiz o objetivo declarado no
   `CLAUDE.md`. Adotá-la muda o documento de visão.
2. **Canal de cobrança** (§10): vale 11–26 pontos de margem. ADR pelo critério 3.
3. **Unidade da cota** (§8): o domínio apostou em minutos; a economia aponta
   turns. Escopo do CARD-015.
4. **Levantar ou manter o congelamento de B** — `translation_pt` mexe no arquivo
   do prompt, mas não na pedagogia. Só o desenvolvedor decide de que lado da
   linha isso cai.

## Propostas de ajuste no backlog — NÃO aplicadas

> Por instrução explícita da sessão, o backlog **não foi editado**. As linhas
> abaixo são propostas aguardando OK.

- **CARD-007** — implementar o prompt caching do ADR-0020 e assertar
  `cache_read_input_tokens > 0` em teste.
- **CARD-015** — decidir a unidade da cota à luz de §8; tratar o kill switch como
  bloqueante de lançamento comercial, não só técnico.
- **ADR-0010** — anotar no índice que a base de projeção foi revista por este
  documento (§3), no mesmo padrão de "ajustado por" já usado nos ADRs 0007, 0009
  e 0015.
