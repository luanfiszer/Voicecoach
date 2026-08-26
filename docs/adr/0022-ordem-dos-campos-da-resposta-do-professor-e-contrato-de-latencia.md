# ADR-0022 — A ordem dos campos da resposta do professor é contrato de latência, não estilo

- **Status:** aceito — **a REGRA continua valendo; a lista de campos que ela ordena foi trocada pelo [ADR-0049](0049-correction-e-entidade-persistida-e-os-campos-texto-viram-derivacao.md)** (2026-08-26): `spoken_reply` segue primeiro, e o último passou a ser `corrections` (o mais caro de gerar) em vez de `translation_pt` (o mais descartável)
- **Data:** 2026-08-19
- **Relacionado:** ADR-0003 (costura 4 — pipeline componível), ADR-0009 (modelos),
  CARD-007 (adapter do professor)
- **Consome:** [`docs/analise-caminho-para-1-2s.md`](../analise-caminho-para-1-2s.md)

## Contexto

O alvo do produto passou a ser **primeiro áudio em ~1,4 s** (de 3,74 s medidos
hoje). O mecanismo é a **cascata**: o LLM responde em streaming, o parse extrai
`spoken_reply` frase a frase, e cada frase segue para o TTS enquanto o resto
ainda está sendo gerado.

O schema atual do protótipo (`english_teacher_bot/teacher.py`) emite nesta ordem:

```
has_mistakes → original → corrected → tip → spoken_reply → translation_pt
```

`spoken_reply` é o **quinto** campo. Como a geração é sequencial, a cascata só
começa depois que o modelo produziu os quatro campos anteriores — que podem somar
100–200 tokens. A **taxa de geração medida é de ~130 tok/s**
([medição §5.1](../medicao-latencia.md)), então esses campos custam **0,8–1,5 s de
espera antes da primeira palavra falada**.

O prompt do professor está **congelado** até existir o eval (Fase 4), por decisão
do desenvolvedor, para não trocar qualidade pedagógica por métrica sem baseline.
A pergunta que se colocou foi se a *ordem dos campos* cai dentro desse
congelamento. **O desenvolvedor decidiu que não cai, e aprovou a reordenação**
(2026-08-19).

## Decisão

**`spoken_reply` é o primeiro campo da resposta do professor, e a ordem dos
campos é um contrato de latência — não uma escolha de legibilidade.**

```
spoken_reply → has_mistakes → original → corrected → tip → translation_pt
```

1. **`spoken_reply` primeiro.** É o único campo que alimenta o TTS, e portanto o
   único no caminho crítico até o aluno ouvir alguma coisa.
2. **`translation_pt` permanece por último.** É o campo mais descartado
   (diagnóstico §1: usado só quando o aluno pede "traduzir") e o mais barato de
   se perder se uma geração for cortada.
3. **O congelamento do prompt continua valendo para todo o resto** — instruções,
   tom, regras pedagógicas, tamanho da resposta. Esta decisão abre uma exceção
   estreita e explícita: **ordem de campos não é conteúdo pedagógico.**
4. **A ordem é verificada por teste**, não confiada à revisão humana. O CARD-007
   assere que `spoken_reply` é a primeira chave do objeto retornado.
5. **Mudar a ordem depois exige ADR novo.** Não é refatoração.

### O risco técnico que esta decisão não resolve

Ordem de chaves num JSON gerado por LLM é **aderência a prompt, não garantia**.
Dependendo de como o CARD-007 resolver a saída estruturada, o provedor pode
reordenar as chaves ou emitir o objeto de forma que a ordem não se preserve no
streaming.

**O CARD-007 tem de verificar isso empiricamente antes de fechar o desenho.** Se
a ordem não for confiável, a decisão não muda — muda o mecanismo, e as saídas
são: um segundo campo/chamada dedicado à fala, ou uma resposta em duas partes.
Registrar aqui para que a verificação não seja esquecida.

## Alternativas consideradas

### Alternativa A — Manter a ordem e aceitar a espera

- **O que é:** cascata começando depois dos quatro campos anteriores.
- **Por que foi rejeitada:** custa 0,8–1,5 s do orçamento de 1,4 s — ou seja,
  consome entre metade e a totalidade do alvo, para não mexer numa linha que não
  tem conteúdo pedagógico. É o pior câmbio disponível na mesa.

### Alternativa B — Duas chamadas paralelas ao LLM

- **O que é:** uma chamada curta que produz só a fala (vai direto ao TTS) e outra
  que produz as correções (vira texto na tela).
- **Por que foi rejeitada por ora:** corta o caminho crítico de forma ainda mais
  agressiva, mas **dobra os tokens de entrada** (system prompt e histórico
  reenviados) num produto cujo custo é 100% LLM, e cria o risco de as duas saídas
  discordarem — a correção citando uma fala que o outro ramo não produziu. Fica
  registrada como saída caso o risco técnico acima se confirme.

### Alternativa C — Esperar o eval (Fase 4) para mexer em qualquer coisa do prompt

- **O que é:** manter o congelamento absoluto.
- **Por que foi rejeitada:** o congelamento existe para proteger **qualidade
  pedagógica** de ser trocada por métrica sem baseline. Ordem de serialização não
  afeta o que o professor diz nem como corrige — proteger isso é aplicar a regra
  onde ela não tem função, ao custo do alvo inteiro do produto.

## Consequências

**Positivas**

- Desbloqueia a cascata e, com ela, o alvo de ~1,4 s.
- Recupera 0,8–1,5 s pelo custo de reordenar campos num arquivo.
- O campo mais descartável (`translation_pt`) fica no fim, onde um corte de
  geração dói menos.

**Negativas — o preço aceito**

- **Uma restrição não-óbvia sobre um arquivo que parece livre.** O prompt do
  professor passa a ter uma linha que **não pode ser movida por legibilidade**.
  É exatamente o tipo de regra que se perde: quem editar o prompt daqui a três
  meses não tem motivo para suspeitar que a ordem importa. O teste do item 4 é o
  que impede — e sem ele esta decisão erode sozinha.
- **Modo de falha silencioso.** Reordenar não quebra nada: as respostas continuam
  corretas, os testes de conteúdo passam, e só a latência sobe. É a mesma classe
  de bug do prompt caching (ADR-0021), e pela mesma razão precisa de verificação
  executável em vez de disciplina escrita.
- **Abre uma exceção num congelamento.** Exceção registrada e estreita, mas a
  próxima virá com este ADR como precedente. A linha que fica: **conteúdo e
  tamanho seguem congelados; forma de serialização não.**
- **Uma incerteza técnica em aberto** (risco acima) que só o CARD-007 fecha.

**Equivalente mental .NET:** é a ordem dos campos importar num contrato
serializado — como depender de `[JsonPropertyOrder]` para que um consumidor que lê
em streaming consiga agir antes de o payload terminar. Funciona, é legítimo, e é
frágil pelo mesmo motivo: nada no tipo denuncia quem reordenou.
