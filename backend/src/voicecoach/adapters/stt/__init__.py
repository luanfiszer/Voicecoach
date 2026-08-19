"""Adapters de transcrição — as implementações da porta ``SpeechToText``.

Dois adapters locais para a mesma porta (ADR-0027), porque o mais rápido não
roda em todo lugar:

- ``mlx_whisper_adapter`` — GPU do Apple Silicon, 0,59 s no ``small.en``. Só
  existe em Mac ARM, e por isso a biblioteca é **extra opcional** com import
  tardio;
- ``faster_whisper_adapter`` — CPU, 1,18 s no mesmo modelo. Roda em qualquer
  lugar, e é o único caminho que o CI consegue exercitar.

A escolha entre eles é do ``factory``, no boot, e **nunca** por job: latência
que varia sem que ninguém saiba por quê é o oposto do que um alvo medido exige.
"""
