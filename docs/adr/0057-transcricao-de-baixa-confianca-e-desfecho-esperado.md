# ADR-0057 — Transcrição de baixa confiança é desfecho esperado, não erro

- **Status:** aceito
- **Data:** 2026-09-09
- **Critério de obrigatoriedade** (`docs/adr/README.md`): **2 — define ou altera
  uma fronteira** (o contrato de `/v1` ganha um desfecho novo de turn, e o
  cliente precisa saber renderizá-lo). Executa o mecanismo do ADR-0039.
- **Depende de:** ADR-0055, ADR-0056

## Contexto

O briefing de 2026-09-09 registrou o pedido em palavras do desenvolvedor:
*"entender o que foi dito em qualquer idioma e, quando não entender, **não
deduzir**"*.

A primeira metade é o ADR-0055. Esta é a segunda, e ela é necessária **mesmo
depois** da troca de modelo: um modelo multilíngue não elimina fala inaudível,
gravação de silêncio, microfone abafado ou o aluno tossindo. O que ele elimina é
a alucinação **por incapacidade estrutural** do modelo; sobra a alucinação por
insumo ruim, que é a que todo Whisper tem.

Hoje o produto **não tem como recusar**. Qualquer texto que saia do STT vira
prompt do professor, que responde a ele com toda a confiança do mundo. Foi
exatamente esse o sintoma relatado: o professor respondendo a algo que o aluno
não disse.

**A medição diz que o sinal para recusar já existe e é limpo** (ADR-0056):

| situação medida | `avg_logprob` |
|---|---|
| alucinação sobre fala em português | **−5,938** · **−4,139** · **−1,124** |
| transcrição correta em inglês | −0,143 · −0,131 · −0,317 · −0,206 · −0,173 |

Há mais de uma ordem de grandeza de folga entre os dois grupos. Um limiar em
qualquer lugar entre −1,1 e −0,4 separa os casos medidos.

**A decisão de produto foi tomada em 2026-09-09:** confiança baixa produz um
desfecho explícito — *"não entendi, pode repetir?"* — **sem gastar LLM nem
TTS**. A alternativa considerada (responder mesmo assim, avisando o professor da
dúvida) foi recusada pelo desenvolvedor.

## Decisão

**Uma transcrição abaixo do limiar encerra o turn num desfecho próprio,
`nao_entendido`, produzido como `Err` do `Result` (ADR-0039) — não como
exceção, não como `failed`.**

1. **A pergunta que classifica**, na formulação do CLAUDE.md, é *"quem chamou
   tem um bug?"*. Não tem: o aluno falou baixo. Logo, não é exceção
   (ADR-0017) e não é `SttError` — é **desfecho esperado de caso de uso**, que é
   literalmente para o que o ADR-0039 foi escrito. É o segundo consumidor real
   do `Result`, e o primeiro que nasce de uma observação de uso.
2. **O turn termina, e termina sem resposta.** Ele não é `failed` — não houve
   falha de infraestrutura, e marcá-lo assim contaminaria a varredura de turns
   travados (CARD-025) e a taxa de erro. Ele é um turn concluído cujo desfecho é
   "não entendi". A forma exata do estado é trabalho do CARD-040, e o ADR-0028
   manda que a derivação more no domínio.
3. **O corte acontece antes do professor.** É o que dá o efeito colateral bom:
   um turn recusado custa **US$ 0** de LLM e de TTS, contra os US$ 0,002678 de
   um turn completo (CARD-014). Recusar é a única operação do produto que
   economiza dinheiro ao melhorar a experiência.
4. **Dois limiares, não um**, ambos configuração e ambos com o número medido no
   comentário:
   - `stt_min_confidence: float = -1.0` sobre o `confidence` do ADR-0056;
   - `stt_max_no_speech: float = 0.6` sobre o `no_speech`, que pega o caso
     diferente de "não havia fala nenhuma" (gravação vazia, botão tocado sem
     querer). Os dois casos merecem mensagens diferentes ao aluno, e por isso
     não são o mesmo campo.
5. **O limiar é declaradamente uma estimativa.** −1,0 fica entre o pior acerto
   medido (−0,32) e a melhor alucinação medida (−1,12), com folga dos dois
   lados. Ele **será recalibrado** com fala real — e o instrumento para isso é o
   próprio produto: o CARD-040 registra `confidence` no `UsageEvent`, de modo
   que a distribuição real apareça em vez de ser adivinhada.

## Alternativas consideradas

### Alternativa A — responder assim mesmo, com a dúvida no prompt

Passar a confiança ao professor e deixá-lo pedir confirmação com naturalidade
(*"did you say…?"*). É mais suave e nunca deixa o aluno sem resposta.
**Apresentada ao desenvolvedor em 2026-09-09 e rejeitada por ele**: gasta o turn
inteiro para tratar um caso em que não se sabe o que foi dito, e o professor
inevitavelmente ancoraria na transcrição errada ao formular a pergunta — que é o
sintoma que este ADR existe para matar. Fica registrada como o caminho a
reconsiderar se a taxa de recusa medida incomodar na prática.

### Alternativa B — `SttError`, reaproveitando o que já existe

`SttError` já atravessa a porta e já é capturado pelo caso de uso, que marca o
turn como `failed`. Seria a mudança de menor esforço. Rejeitada porque **mente
sobre a natureza do evento**: transcrição de baixa confiança não é o motor
falhando — o motor funcionou perfeitamente e produziu um resultado ruim. Tratar
os dois como o mesmo tipo apagaria a distinção justamente nas métricas onde ela
importa (um exige investigação de infra, o outro é o aluno falando baixo) e
mostraria ao aluno uma tela de erro onde cabe um convite a repetir.

### Alternativa C — deixar como está

A opção honesta de sempre. Rejeitada porque é exatamente o sintoma relatado no
primeiro uso real, e porque o custo de manter é pagar LLM e TTS para responder a
ruído.

## Consequências

- **Positivas:** o professor para de responder ao que não foi dito. Turn
  recusado é grátis. O `Result` ganha um segundo caso de uso real, o que é
  aprendizado do padrão sob pressão de produto e não de exercício. O aluno
  recebe uma instrução acionável em vez de um não-sequitur.
- **Negativas:** **falso positivo é pior que o sintoma que estamos curando** —
  recusar fala boa é insultuoso de um jeito que responder errado não é, e o
  limiar é uma estimativa de vozes sintéticas. É o risco central desta decisão,
  e a mitigação é o número em configuração, a distribuição real registrada e a
  disposição de afrouxar. Um desfecho novo é superfície nova: contrato de API,
  evento de SSE, estado no cliente e tela — o CARD-027 (telas de exceção) ganha
  um caso, e ele **não é uma tela de erro**. E o produto passa a poder terminar
  um turn sem áudio nenhum, que é um caminho que o app até hoje nunca exercitou.
- **Equivalente mental .NET:** é a diferença entre `throw new ValidationException`
  e devolver um `Result.Fail("não entendi")` — com a distinção que o CLAUDE.md
  já fixou: exceção é para quem chamou ter um bug, e aqui ninguém tem.
