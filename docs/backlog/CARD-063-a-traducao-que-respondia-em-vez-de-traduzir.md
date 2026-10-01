# CARD-063 — A tradução que respondia em vez de traduzir

- **ID:** CARD-063
- **Épico:** Qualidade da conversa (o botão `traduzir`, CARD-036/058)
- **Esforço:** P
- **Status:** concluído (2026-10-01)
- **Dependências:** CARD-036, [LEARNING-0009](../learnings/0009-o-loop-mergeou-com-gates-verdes-o-que-so-o-uso-real-mostrava.md)

## Contexto

Achado pelo QA contra a stack real da validação do loop (2026-10-01). Pedida a
tradução da resposta do professor *"That's great! I'd love to hear more about
it. What kind of project are you working on? Tell me what makes it so amazing
for you."*, o tradutor devolveu, em inglês: *"I appreciate your interest, but
I should clarify: I'm an AI assistant without personal projects..."*. O aluno
que toca `traduzir` recebe uma frase em inglês que nem é a fala do professor.

O prompt do CARD-036 já previa o risco ("sem responder ao conteúdo"), mas
mandava o texto **cru** como mensagem do usuário — e a fala do professor quase
sempre termina em pergunta, que é o convite a responder.

## Critérios de aceite

- **Dado** uma fala do professor que termina em pergunta, **quando** traduzida,
  **então** a saída é a tradução, não uma resposta — medido, não suposto.
- **Dado** que o modelo ecoe as marcas de delimitação, **então** elas não
  chegam à tela.

## Objetivo de aprendizado

Separar **dado** de **instrução** num prompt (delimitar o material e dizer o
que ele é) é a mesma técnica que se usa contra injeção de prompt — e o
comportamento de LLM se decide por medição repetida (taxa sobre N), nunca por
uma execução que "funcionou".

## Execução (2026-10-01)

- **O texto entra delimitado** (`<texto>…</texto>`, `mensagem_do_usuario`) e a
  instrução diz que o delimitado é material: perguntas e pedidos ali são
  traduzidos, não respondidos. As marcas são removidas da saída se o modelo as
  ecoar.
- **Medição** (`benchmarks/llm_traducao_responde.py`, `claude-haiku-4-5`, 3
  falas do professor terminando em pergunta, duas rodadas):

  | Variante | N=10/texto | N=20/texto | Total |
  |---|---|---|---|
  | v1 (texto cru, prompt do CARD-036) | 3/30 | 7/60 | **10/90 (11%)** |
  | v2 (texto delimitado) | 0/30 | 0/60 | **0/90** |

  Todas as falhas da v1 foram respostas em inglês do tipo "I'm Claude, an AI
  assistant" / "I haven't mentioned any project". Custo das duas rodadas:
  US$ 0,063. Conferência à mão de saídas da v2 pelo adapter de produção:
  *"Que ótimo! Eu adoraria ouvir mais sobre isso. Que tipo de projeto você
  está desenvolvendo?…"* e *"Você disse "I go in the beach". Dizemos "I went
  to the beach" — use o past simple…"* (termos ensinados mantidos em inglês).
- **O adapter não tinha teste nenhum** desde o CARD-036. Agora
  `tests/adapters/test_anthropic_translator.py` (7 casos, cliente fake): texto
  delimitado no pedido, marcas fora da saída, uso do modelo que respondeu,
  resposta vazia e erros do SDK virando `TranslatorError`. **3 deles falham
  no adapter antigo** (verificado com `git stash push src`).
- **Cache de traduções (`turn_translations`):** não invalidado — o banco
  local não guarda nenhuma tradução defeituosa (a do QA saiu com o delete da
  conta de teste) e o app não tem usuários reais. Limitação conhecida: a
  chave do cache não inclui versão de prompt; se o prompt mudar com usuários
  reais, traduções antigas continuam sendo servidas.

### ADR

Nenhum critério de `docs/adr/README.md` se aplica: sem dependência nova (1),
a porta `Translator` e o contrato HTTP não mudam (2), o custo sobe ~30 tokens
de entrada por tradução — US$ 0,00003 no Haiku, abaixo de qualquer limiar (3),
sem efeito de segurança/privacidade (4), e reverter é trocar uma constante (5).

### Regra do explicador (modo autônomo)

Decisão técnica, sem pergunta: delimitação por marcas no texto em vez de
*tool use* com schema — o CARD-036 já recusou tool use aqui por custo, e a
medição mostrou que a delimitação basta.
