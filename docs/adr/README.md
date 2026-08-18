# Architecture Decision Records (ADRs)

Registro imutável das decisões arquiteturais deste projeto, com alternativas
consideradas e trade-offs explícitos.

## Quando um ADR é OBRIGATÓRIO

Escreva um ADR sempre que a decisão:

1. **Introduz ou remove uma dependência externa** — biblioteca, serviço, provider
   de IA, banco, fila. (Ex.: escolher SQLAlchemy, trocar de modelo Claude.)
2. **Define ou altera uma fronteira** — camadas, portas/adaptadores, contrato
   de API, formato de dados persistidos.
3. **Afeta custo recorrente** — modelo de LLM, estratégia de cache, storage.
4. **Afeta segurança ou privacidade** — autenticação, exposição de mídia,
   validação de webhook, retenção de dados de usuário.
5. **Seria difícil de reverter** — se desfazer custa mais que uma sessão de
   trabalho, a decisão merece registro.
6. **Contraria uma convenção estabelecida** — exceções à regra são decisões.

## Quando NÃO escrever ADR

- Escolhas locais e reversíveis (nome de função, estrutura interna de um módulo).
- Correções de bug sem mudança de design → isso vai para `docs/learnings/`.
- Detalhes de implementação que a skill de arquitetura já cobre.

## Regras

- Numeração sequencial: `0001-titulo-kebab-case.md`, `0002-...`.
- Use o template `0000-template.md`.
- ADR aceito **não é editado** para mudar a decisão: escreva um novo ADR que o
  substitui e atualize o status do antigo para "substituído por ADR-XXXX".
- Mínimo de duas alternativas reais consideradas, com o motivo da rejeição.
- Um ADR sem seção "Consequências negativas" preenchida está incompleto.

## Índice

| ADR | Título | Status |
|---|---|---|
| [0001](0001-descontinuar-whatsapp-em-favor-de-app-proprio.md) | Descontinuar WhatsApp/Twilio em favor de app mobile próprio + web companion | aceito |
