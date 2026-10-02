# CARD-066 — O mobile mostra quando o professor recusa a fala

- **ID:** CARD-066
- **Épico:** Qualidade da conversa
- **Esforço:** P
- **Status:** backlog
- **Dependências:** CARD-040 (o desfecho `rejected`), CARD-065 (onde a lacuna foi achada)

## Contexto

Achado no CARD-065 (2026-10-02): desde o CARD-040 o servidor encerra o turn
com o evento `rejected` (`no_speech`, `not_english`, `low_confidence`) quando
não chama o professor. O cliente TypeScript **ignorava** esse evento
(tolerância a evento desconhecido, ADR-0008), e o `useTurno` do mobile não lê
`rejection_reason` no polling. Resultado: o aluno fala português (ou nada) e o
app **não diz por quê** — só a transcrição aparece.

O `api-client` já reconhece o `rejected` desde o CARD-065, e a web já mostra o
convite a repetir.

## Critérios de aceite

- **Dado** uma fala em português, **quando** o turn termina, **então** o
  mobile mostra *"Isso não pareceu inglês. Pode repetir em inglês?"* — o mesmo
  texto da web.
- **Dado** o recuo por polling, **então** `rejection_reason` produz a mesma
  tela que o evento.

## Objetivo de aprendizado

União discriminada que cresce: o `switch` do mobile compila sem tratar o caso
novo porque não é exaustivo — e o que faria o `tsc` cobrar é um `assertNever`.
