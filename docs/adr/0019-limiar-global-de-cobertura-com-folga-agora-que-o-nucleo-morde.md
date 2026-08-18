# ADR-0019 — Limiar global de cobertura com folga, agora que o anel do núcleo morde

- **Status:** aceito
- **Data:** 2026-08-18
- **Relação:** ajusta o item 3 da decisão do
  [ADR-0015](0015-quality-gates-tres-aneis.md) (o ADR-0015 permanece válido em
  todo o resto)

## Contexto

O ADR-0015 fixou dois anéis de cobertura e **rejeitou explicitamente** a
alternativa E ("`--cov-fail-under` com folga"), com o argumento de que um limiar
abaixo do valor real *"permite que a cobertura caia sem quebrar nada — é um gate
que autoriza a regressão que deveria impedir"*.

O CARD-005 mudou o cenário que sustentava esse argumento. Quando o ADR-0015 foi
escrito, **o segundo anel media zero statement** — `domain` e `application`
estavam vazios, e o comando passava com 100% de nada. Na prática existia **um**
anel: o global. Travá-lo no valor real era a única proteção que havia.

Hoje o segundo anel mede **114 statements reais** do núcleo, com 100% de
cobertura, e é ele que guarda a lógica cara de errar. O anel global passou a
medir majoritariamente borda e composição — `api/dependencies.py`, `config.py`,
entrypoints — onde a cobertura oscila por motivos que não são regressão de
qualidade (um provider novo de `Depends`, um ramo de erro de infraestrutura).

Com o global travado em 89,27%, qualquer arquivo novo de borda quebra o CI antes
de existir teste para ele, e o efeito prático é ruído: o gate passa a ser
contornado ou o número, baixado às pressas — as duas coisas piores que a folga.

## Decisão

**Travar o anel global em 80%** (real hoje: 89,27%), mantendo o anel do núcleo
(`domain` + `application`) em **90%, sem folga**.

A regra "sem folga inventada" do ADR-0015 **continua valendo onde importa** — ela
migra do anel global para o anel do núcleo, que é onde agora existe algo a
proteger.

Gatilho de revisão: se o global cair **abaixo de 80%** em algum card, isso deixa
de ser oscilação de borda e vira sinal de que código sem teste está entrando em
volume — o limiar sobe de novo, ou o card explica por escrito o que aconteceu.

## Alternativas consideradas

### Alternativa A — Manter o global travado no valor real (89,27%), como o ADR-0015 manda

- **A favor:** coerência com a decisão anterior; nenhuma regressão passa
  despercebida, nem na borda.
- **Por que foi rejeitada:** o valor real do anel global agora sobe e desce por
  causa de arquivos de composição, não de regra de negócio. Um gate que acende
  vermelho por motivo que o time considera irrelevante é um gate que ensina a
  contornar gate — e o ADR-0015 já se preocupava com `--no-verify`. O
  desenvolvedor avaliou o custo de atrito como maior que o benefício, e a
  proteção que ele comprava passou a ser redundante com o anel do núcleo.

### Alternativa B — Abandonar o anel global e ficar só com o do núcleo

- **A favor:** um número só, no lugar que importa; nenhum ruído.
- **Por que foi rejeitada:** o anel global é o que impede a borda de virar terra
  sem teste nenhum — rotas, adapters e handlers precisam de **alguma** régua. 80%
  ainda reprova um card que adicione um módulo inteiro sem teste; zero régua não
  reprova nada.

### Alternativa C — Excluir a borda da medição global em vez de baixar o limiar

- **O que é:** manter 89% e tirar `api/`, `config.py` e entrypoints do cálculo.
- **Por que foi rejeitada:** troca um número honesto por um número maquiado — a
  cobertura passaria a descrever um subconjunto escolhido para parecer bom, e a
  parte excluída ficaria sem régua nenhuma (que é a Alternativa B, disfarçada).

## Consequências

**Positivas**

- O gate que oscila deixa de gerar ruído; o gate que protege regra de negócio
  continua rígido, e agora com conteúdo real para proteger.
- O princípio do ADR-0015 (limiar não é teto, e regressão tem que quebrar algo)
  sobrevive onde tem efeito.

**Negativas — o preço aceito**

- Existe agora uma **folga de ~9 pontos** no anel global: a cobertura de borda
  pode cair de 89% para 80% sem que nada acuse. É exatamente o risco que o
  ADR-0015 nomeou, aceito conscientemente em troca de menos atrito.
- O número vira uma decisão de gosto que precisará ser revisitada; sem o gatilho
  escrito acima, ele tenderia a só descer.
- Duas decisões sobre o mesmo assunto em ADRs diferentes: quem ler o ADR-0015
  isolado terá a informação desatualizada. Mitigado pelo ponteiro no cabeçalho
  deste ADR e pela linha no índice.
