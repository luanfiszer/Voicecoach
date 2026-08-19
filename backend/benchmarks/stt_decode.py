"""Custo de DECODIFICAR o áudio antes do STT — a etapa que os outros tiram de fora.

Os benchmarks de STT (`stt_faster_whisper.py`, `stt_mlx.py`) leem o WAV com
`soundfile` **fora** da medição, de propósito: a pergunta deles é quanto custa
transcrever. O adapter real não tem esse luxo. Ele recebe do storage os bytes
que o celular gravou — AAC ou Opus, não PCM — e alguém tem que decodificar.

Este script responde quanto isso custa, porque a resposta decide um item de
desenho: se a decodificação fosse cara, valeria empurrá-la para o cliente
(mandar PCM) ou para um processo separado. Ela não é — e o número está aqui
para que a próxima pessoa não precise reabrir a discussão de memória.

O que este benchmark NÃO mede: baixar o objeto do storage. Estes tempos
pressupõem os bytes já em memória, e o download é uma linha maior e separada
(CARD-009).
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from _common import INPUT_DIR, SAMPLE_RATE, cronometra, grava, resume
from faster_whisper.audio import decode_audio

# `decode_audio` do faster-whisper é um wrapper fino sobre o PyAV: abre o
# container, converte para mono e reamostra. É a MESMA função que o adapter usa
# nos dois caminhos (faster-whisper e mlx), então medi-la aqui mede o adapter.
REPETICOES = 11

# Ordem deliberada: do que não comprime ao que comprime mais. O eixo que explica
# o tempo é o trabalho do decoder, não o tamanho do arquivo — e a tabela só
# mostra isso quando as duas colunas aparecem lado a lado.
EXTENSOES = ("wav", "m4a", "opus")


def mede(caminho: Path) -> dict[str, Any]:
    # Lê o arquivo ANTES de cronometrar: o disco não é o que se está medindo.
    dados = caminho.read_bytes()

    def uma_vez() -> int:
        # `BytesIO` embrulha os bytes num objeto que se comporta como arquivo —
        # é o que o adapter faz, porque o áudio chega do storage como bytes e
        # nunca toca o disco. Sem paralelo exato em C#; o mais próximo é um
        # `MemoryStream` passado onde se esperava um `FileStream`.
        return len(decode_audio(io.BytesIO(dados), sampling_rate=SAMPLE_RATE))

    tempos, amostras = cronometra(uma_vez, REPETICOES)
    duracao = amostras / SAMPLE_RATE
    return {
        "arquivo": caminho.name,
        "formato": caminho.suffix.lstrip("."),
        "bytes": caminho.stat().st_size,
        **resume(tempos, duracao),
        "duracao_audio_s": round(duracao, 2),
    }


def main() -> None:
    resultados: list[dict[str, Any]] = []
    for nome in ("curto", "longo"):
        for extensao in EXTENSOES:
            caminho = INPUT_DIR / f"{nome}.{extensao}"
            if not caminho.exists():
                # Insumo faltando é aviso, não erro: os comprimidos só existem
                # depois de rodar `make_inputs.py` com a versão que os gera.
                print(f"(sem {caminho.name} — rode make_inputs.py)", flush=True)
                continue
            r = mede(caminho)
            resultados.append(r)
            print(
                f"{r['arquivo']:12s} {r['duracao_audio_s']:6.2f}s "
                f"{r['bytes'] / 1024:8.0f} KB  p50={r['p50_s'] * 1000:7.1f} ms",
                flush=True,
            )

    if resultados:
        print(f"\nresultados em {grava('stt_decode', resultados)}")


if __name__ == "__main__":
    main()
