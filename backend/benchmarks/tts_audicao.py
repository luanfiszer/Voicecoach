"""Ouvir o TTS com o texto que você quiser — o instrumento do julgamento humano.

A §9 da medição fecha os eixos cronometráveis (carga, RTF, empacotamento) e
declara explicitamente o que ela NÃO decide: **qualidade percebida**. Este script
existe para essa parte, que é a única do desempate Kokoro vs Piper que não é
automatizável — e que continua em aberto no ADR-0032.

Roda no venv do PROJETO (como o `llm_primeira_sentenca.py`), não no dos
benchmarks: ele exercita o adapter de produção, então o número e o som que você
ouve são os do produto, não os de uma reimplementação.

    cd backend
    uv run python benchmarks/tts_audicao.py
    uv run python benchmarks/tts_audicao.py "texto que você quiser ouvir"

Toca cada voz encontrada em `voices/` em sequência e deixa os WAVs em /tmp para
comparação lado a lado depois.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import wave
from pathlib import Path

from voicecoach.adapters.tts.piper_adapter import load_piper

VOICES_DIR = Path(__file__).resolve().parents[1] / "voices"

# Uma correção pedagógica de verdade, que é o que o produto mais fala: tem nome
# próprio, contraste de formas erradas/certas e uma pergunta no fim. Texto
# genérico esconde justamente onde a prosódia de um TTS local falha.
PADRAO = (
    "That's a great point! I noticed you said 'I have went to the store'. "
    "The correct form is 'I have gone'. It's one of those irregular verbs "
    "that trips everyone up. Could you try saying that sentence again?"
)


async def main() -> None:
    texto = sys.argv[1] if len(sys.argv) > 1 else PADRAO
    vozes = sorted(p.stem for p in VOICES_DIR.glob("*.onnx"))
    if not vozes:
        print(f"nenhuma voz em {VOICES_DIR} — ver backend/README.md")
        raise SystemExit(1)

    print(f'texto: "{texto}"\n')
    for nome in vozes:
        tts = load_piper(VOICES_DIR, nome)
        audio = await tts.synthesize(texto)

        destino = Path(f"/tmp/audicao_{nome}.wav")
        with wave.open(str(destino), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(audio.sample_rate)
            w.writeframes(audio.pcm)

        print(f"{nome:24s} {audio.duration_seconds:5.2f}s  -> {destino}")
        # `afplay` no macOS; noutros SOs, abra os WAVs à mão.
        subprocess.run(["afplay", str(destino)], check=False)


if __name__ == "__main__":
    asyncio.run(main())
