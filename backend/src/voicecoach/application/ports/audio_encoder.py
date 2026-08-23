"""Porta de compressão do áudio antes de gravar (ADR-0024, ADR-0033).

**Por que esta porta existe, quando `concat` não precisou de uma.** As duas
operações acontecem no mesmo caso de uso e parecem irmãs, mas só uma delas é
aritmética: `concat` junta amostras com `b"".join` e não conhece biblioteca
nenhuma, então mora em `application` como função livre. Comprimir é o oposto —
precisa de um codec, e o codec do projeto é o PyAV (`adapters/tts/encoding.py`,
que já vinha com o `faster-whisper`).

Verificado nesta sessão, importando `to_aac` direto do caso de uso: dois
contratos reprovam de uma vez — `layers`, pela seta que sobe, e o `forbidden` de
`application`, que alcança `av` **pela cadeia indireta** (`use_case → encoding →
av`, com a rota impressa no relatório). Logo, ou a compressão vira porta, ou ela
não acontece no caso de uso — e não comprimir custa 816 KB por resposta em vez
de ~136 KB, na rede móvel do aluno.

**`async` pela mesma razão que STT e TTS são** (Q11, ADR-0034): codificar é
CPU-bound e o adapter empurra para um executor. A porta não sabe e não se
importa; o que ela garante é que o chamador pode `await` sem congelar o event
loop enquanto o próximo trecho é sintetizado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from voicecoach.application.ports.text_to_speech import SynthesizedAudio


class AudioEncodingError(RuntimeError):
    """O codec não produziu áudio utilizável.

    Mora na porta como o `TtsError` e o `LlmError` (ADR-0031, item 5): quem
    captura é o caso de uso, e `application` não pode importar `adapters`.
    """


@dataclass(frozen=True, slots=True)
class EncodedAudio:
    """Áudio comprimido, com as duas coisas de que quem grava precisa.

    `content_type` porque quem baixa é o player do aluno, direto do storage, por
    URL assinada: sem o cabeçalho certo ele recebe `application/octet-stream` e
    pode se recusar a tocar (docstring de `MediaStorage.put`).

    `extension` porque a chave do ADR-0024 a carrega (`reply/000.aac`), e o
    esquema de chaves é contrato. As duas saem do mesmo lugar — o codec —
    justamente para que não possam divergir: gravar `.aac` com `audio/mpeg` é o
    tipo de erro que só aparece no aparelho de alguém.
    """

    data: bytes
    content_type: str
    extension: str


class AudioEncoder(Protocol):
    """Comprime PCM cru no formato que vai para o storage."""

    async def encode(self, audio: SynthesizedAudio) -> EncodedAudio: ...
