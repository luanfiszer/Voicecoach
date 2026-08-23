"""Porta de transcrição de áudio (ADR-0011, ADR-0027, ADR-0029).

Declarada como ``Protocol``, igual às portas de repositório: tipagem
**estrutural**. Um adapter satisfaz esta porta por ter o método com a
assinatura certa — não herda nada e não se registra em lugar nenhum. Em teste
isso significa que um fake é uma classe comum, sem framework de mock.

**O que trafega aqui é o contrato desta camada, e ele é deliberadamente
pobre** (ADR-0029). Nenhum tipo de biblioteca atravessa a porta:

- ``numpy.ndarray`` seria o mais natural (é o que os dois adapters consomem
  internamente) e é exatamente o que não pode passar: amarraria ``application``
  ao formato interno do adapter. O contrato do import-linter proíbe ``numpy``
  aqui justamente por isso;
- um **caminho de arquivo** também não serve, e por um motivo mais concreto:
  ``mlx_whisper.transcribe()`` só aceita caminho delegando para o binário
  ``ffmpeg`` no PATH, que a máquina de desenvolvimento não tem. Caminho na
  porta transformaria o `ffmpeg` em dependência de sistema do produto inteiro.

Sobra **bytes codificados** — que é, convenientemente, exatamente o que o
storage devolve. Decodificar é responsabilidade do adapter, e custa 6 ms num
turno de 20 s em AAC (medição §3.5): 0,3% do orçamento de 1,8 s.

O V2 (streaming, ADR-0003) acrescenta ``stream_transcribe`` **por extensão** —
esta assinatura não muda.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SttError(RuntimeError):
    """A transcrição não produziu texto utilizável.

    Chegou no CARD-009 e não no CARD-006 porque só agora existe alguém que a
    captura: o caso de uso, que precisa marcar o turn como ``failed`` com um
    motivo em vez de deixar a exceção da biblioteca escapar. É a mesma regra do
    ADR-0031, item 5 — **onde o erro mora é consequência de quem precisa
    capturá-lo** —, e por isso ele mora na porta, e não junto do
    ``SttProviderUnavailableError``, que é erro de subida e ninguém captura.

    Herda de ``RuntimeError`` e não de ``DomainError`` (ADR-0017): motor de
    transcrição que falha é infraestrutura, não invariante de negócio violada.
    """


@dataclass(frozen=True, slots=True)
class AudioInput:
    """Áudio como ele chega do storage: bytes de um arquivo, ainda codificado.

    Um único campo, e de propósito. A tentação é carregar junto um
    ``content_type`` vindo do upload, mas o decodificador identifica o
    container lendo os próprios bytes — o campo seria uma dica que ninguém usa
    e que pode mentir quando o cliente mandar o rótulo errado.

    ``frozen=True`` + ``slots=True``: imutável e sem ``__dict__``, como o resto
    dos value objects do projeto.
    """

    data: bytes


@dataclass(frozen=True, slots=True)
class Transcript:
    """O que o STT devolve — texto, e o mínimo em volta dele que alguém usa.

    ``duration_seconds`` não é enfeite: a cota do aluno é medida em **minutos
    de áudio por dia** (``daily_audio_minutes_per_student``), e esta é a única
    etapa do pipeline que conhece a duração real do que foi falado. Deixá-la de
    fora obrigaria a decodificar o áudio uma segunda vez só para contar.
    """

    text: str
    language: str
    duration_seconds: float


class SpeechToText(Protocol):
    """Transcreve a fala do aluno.

    ``async`` porque quem chama é o worker, que é assíncrono. Os adapters locais
    são **CPU-bound** e por isso empurram o trabalho para um executor — a porta
    não sabe nem se importa se a implementação é local, remota ou um fake.

    Falha do motor atravessa como ``SttError``: o que não pode atravessar é uma
    exceção do ``faster-whisper`` ou do ``mlx-whisper``, porque quem a captura
    está em ``application`` e não pode importar nenhuma das duas.
    """

    async def transcribe(self, audio: AudioInput) -> Transcript: ...
