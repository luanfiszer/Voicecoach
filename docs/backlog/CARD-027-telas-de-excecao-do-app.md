# CARD-027 — As telas de exceção do app: o que o aluno vê quando algo não vai bem

- **ID:** CARD-027
- **Épico:** Fase 2 — Proteção de margem (fecha o lado cliente dela)
- **Plataforma:** mobile · **Esforço:** M · **Status:** backlog
- **Dependências:** CARD-015 (quota e kill switch), CARD-025 (varredura de
  travados), CARD-026 (desfecho de provedor indisponível) e os três cards de
  backend desta tela: **CARD-031** (sessão encerrada como desfecho tipado),
  **CARD-032** ("Descartar"), **CARD-033** (saldo e serviço pausado como
  leitura)

## Contexto

Três artboards estão desenhados desde 2026-08-17 e **nunca tiveram dono**:

| Artboard | Empurrado para "Out" por |
|---|---|
| **14** offline — *"Sua fala está guardada aqui"* | CARD-012 (*"offline real"* em Out) |
| **15** quota atingida — *"Por hoje é isso"* | CARD-015 (*"UI de cota restante"* em Out) |
| **16** pausado + timeout — *"Demorou mais que o normal"* | ninguém: é o **achado #6** da `reconciliacao-telas-dominio.md`, órfão desde 2026-08-18 |

Não são telas esquecidas: são telas adiadas três vezes, por três cards
diferentes, e o backlog nunca criou o card que as recebesse. Este é ele.

## Problema

**Todo caminho triste do produto termina numa tela que não existe.**

O backend já sabe (ou vai saber, nos cards de que este depende) dizer as quatro
coisas. O app não sabe mostrar nenhuma:

- **sem rede** — o `enviarTurn` falha e a fala é perdida. O CARD-012 entregou
  retry com backoff, **não** fila local: o áudio existe em `file://` e ninguém o
  guarda para depois;
- **cota estourada** — o POST volta com Problem Details e o app mostra "Algo deu
  errado", indistinguível de erro de verdade;
- **kill switch** — idem, e é o caso em que a mensagem honesta importa mais
  (*"desligamos o professor para não gastar além do previsto"*);
- **turn travado** — o app espera indefinidamente. O CARD-025 marca `failed` no
  servidor; ninguém decidiu o que o app faz com isso, nem o que **"Descartar"**
  significa.

## Proposta técnica

- **Um overlay, quatro conteúdos.** As quatro telas têm a mesma forma (cartão
  sobre a conversa, título + explicação + até dois botões) e o mesmo insumo: um
  desfecho que veio do servidor **ou** a ausência dele. Um componente, quatro
  usos — não quatro componentes.
- **O Problem Details vira o discriminador.** O ADR-0040 já garante `type` como
  URN estável; o cliente casa sobre ele, nunca sobre a mensagem. É o que separa
  "cota" de "kill switch" de "erro de verdade" sem parsear texto.
- **Fila local para o offline (artboard 14).** A gravação sobrevive ao
  fechamento do app e sobe sozinha quando a conexão voltar, **reusando a mesma
  `Idempotency-Key`** — o servidor já responde `replayed: true` e não duplica
  (provado no CARD-012).
- **A decisão pendente sobre "Descartar" mudou de casa:** ela é do
  **[CARD-032](CARD-032-descartar-turn-travado.md)**, que decide e implementa o
  lado servidor. Fica aqui o registro do que estava em jogo: Três
  leituras, e elas divergem no servidor: (a) só some da tela — o turn `failed`
  fica no histórico; (b) o app pede para o servidor apagar; (c) nunca chegou a
  existir turn (caso offline) e é só apagar o arquivo local. Provavelmente
  **(a) e (c)**, e a diferença entre elas é onde a fala estava quando o aluno
  desistiu. **Não implementar antes do ok.**

> **Vira ADR se (b) for escolhido** — critério 2 (o contrato ganha uma ação
> destrutiva sobre um recurso) e critério 4 (dado do aluno sendo apagado por
> pedido dele: é o começo do direito de exclusão, que o CARD-017 trata do outro
> lado).

## Escopo

- **In:** o componente de overlay; os quatro conteúdos; a fila local de envio
  com persistência entre aberturas do app; o casamento por URN de Problem
  Details; o desfecho de "Descartar" implementado conforme a decisão.
- **Out:** *"Avisar quando voltar"* do artboard 16 — é **push**, cortado pela
  visão §F com gatilho escrito (revisão espaçada). O botão não entra, e o card
  registra por quê; a UI de saldo de cota **antes** de estourar (artboard 12, é
  a tela de perfil e depende da auth da Fase 3); retry automático de turn
  travado (o ADR-0037 proíbe depois de entrega parcial).

## Critérios de aceite

- **Dado** o app em modo avião, **quando** o aluno grava e solta, **então** a
  fala aparece como pendente, sobrevive a fechar e reabrir o app, e sobe sozinha
  quando a rede volta — **sem** criar um segundo turn.
- **Dado** um POST que volta com a URN de cota, **então** o aluno vê a tela de
  cota (não "algo deu errado"), e **continua conseguindo ler** os turns
  anteriores da sessão.
- **Dado** um POST que volta com a URN de kill switch, **então** a mensagem é a
  do orçamento, distinta da de cota.
- **Dado** um turn que passou do prazo sem evento, **então** o aluno vê a tela de
  timeout com as duas ações, e a gravação **não** foi perdida.
- **Dado** "Descartar", **então** acontece exatamente o que foi decidido — com
  teste, e com o estado do servidor verificado se a decisão o envolver.

## Riscos

- **Fila local é mais cara do que parece.** Persistir arquivo + metadados,
  sobreviver a reinício, não subir duas vezes, não crescer sem limite. É a maior
  parte do esforço do card e o candidato natural a virar card próprio se
  estourar — e nesse caso o corte é **offline sai, as outras três ficam**, não o
  contrário.
- **Dependência tripla.** Três cards precedem este. Se algum atrasar, a parte
  correspondente vira mock — e mock de tela de erro tem o hábito de sobreviver
  até produção. Se for mockar, escreva o gatilho de remoção.
- **Testar offline no Simulador não prova nada** sobre o aparelho, e o aparelho
  físico está bloqueado pelo ADR-0048. Declare o que ficou por provar.

## Objetivo de aprendizado

Persistência local no Expo — `expo-file-system` para o áudio e o que guarda os
metadados (`AsyncStorage`? SQLite?), com a pergunta que decide: o que sobrevive
a um *force quit*, e o que sobrevive a um *update do app*. Não há equivalente
direto em .NET: o mais próximo é `IsolatedStorage`, e a analogia quebra porque
aqui o sistema operacional pode apagar o diretório de cache sem avisar.
