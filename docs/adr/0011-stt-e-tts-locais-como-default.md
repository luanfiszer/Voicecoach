# ADR-0011 — STT e TTS locais como default de desenvolvimento; APIs pagas por configuração

- **Status:** aceito — **o candidato de TTS foi revisto pelo [ADR-0032](0032-piper-substitui-o-kokoro-como-motor-de-voz.md)** (2026-08-23): o Kokoro era escolha provisória, sem medição; medido, perdeu para o Piper em todos os eixos cronometrados
- **Data:** 2026-08-17
- **Relacionado:** ADR-0010 (política de custo), ADR-0003 (portas de STT/TTS)

## Contexto

O pipeline paga três IAs por turn: STT (Whisper API, ~US$ 0,006/min), LLM e
TTS (~US$ 0,005/turn). A política de custo (ADR-0010) pede gasto restrito ao
Claude. As portas `SpeechToText` e `TextToSpeech` (ADR-0003) já foram
desenhadas para trocar provider sem tocar domínio — esta é a primeira
cobrança desse investimento. Hardware disponível: Mac Apple Silicon, capaz de
rodar Whisper local com folga para uso pessoal.

## Decisão

1. **STT default: `faster-whisper` local** (reimplementação CTranslate2 do
   Whisper; modelo `small`/`medium` — inglês de aprendiz é o caso fácil do
   Whisper). Alternativa Mac-otimizada a avaliar na implementação:
   `mlx-whisper`. Custo: **US$ 0**.
2. **TTS default de desenvolvimento: local** — candidato principal
   **Kokoro** (qualidade alta para o tamanho, roda em CPU), fallback Piper.
   Custo: **US$ 0**.
3. **APIs pagas viram adapters alternativos, ativados por config**
   (`STT_PROVIDER`, `TTS_PROVIDER`): OpenAI Whisper API e OpenAI TTS
   permanecem implementados para o modo qualidade e para comparação no eval.
4. **A porta não muda.** `SpeechToText.transcribe()` e
   `TextToSpeech.synthesize()` têm as mesmas assinaturas para adapter local e
   remoto; a escolha é composição na inicialização (DI), invisível para
   application/domain.
5. O **eval harness (P5) compara os adapters** (WER do STT local vs API;
   qualidade percebida do TTS) — a promoção de um default é decisão medida,
   não estética.

## Alternativas consideradas

### Alternativa A — Manter tudo em API paga (status quo do P2)
- O que é: Whisper API + OpenAI TTS sempre.
- Por que foi rejeitada como default: ~US$ 0,011/turn de custo evitável e
  uma conta de provedor a mais, contra a prioridade recém-declarada. E o
  loop de desenvolvimento fica refém de rede/rate limit para cada teste
  manual. Permanece como modo qualidade por config.

### Alternativa B — Whisper original (openai/whisper) em vez de faster-whisper
- O que é: a implementação PyTorch de referência.
- Por que foi rejeitada: 3–5× mais lenta e mais pesada em memória que a
  CTranslate2 para o mesmo modelo, sem ganho de qualidade — pior no único
  critério em que diferem.

### Alternativa C — TTS local também em produção/modo qualidade
- O que é: nunca pagar TTS.
- Por que foi rejeitada como decisão *agora*: a voz do professor é parte da
  experiência pedagógica (naturalidade, prosódia para dicas de pronúncia);
  vozes locais são boas mas não comprovadamente suficientes para este uso.
  Decisão adiada para quando o eval (P5) permitir comparação honesta —
  exatamente o mesmo tratamento dado ao LLM local no ADR-0010.

## Consequências

**Positivas**: custo de STT+TTS em desenvolvimento = zero; uma única conta
paga (Anthropic); desenvolvimento offline-friendly (só o LLM exige rede);
o eval ganha um caso de uso real (comparar adapters); primeira validação
prática da arquitetura de portas.

**Negativas — o preço aceito**: dois modelos locais para baixar/gerir
(disco e RAM da máquina); latência de STT local depende do hardware (ok no
Apple Silicon; documentar requisito); qualidade do TTS local inferior à API
— aceitável em dev, medida antes de qualquer promoção; adapters locais são
código nosso a manter (dois arquivos pequenos atrás de portas estáveis).

**Equivalente mental .NET:** emulador local no lugar do serviço pago em
desenvolvimento (Azurite no lugar do Blob real) — mesma interface, custo
zero no inner loop, serviço real atrás de configuração.
