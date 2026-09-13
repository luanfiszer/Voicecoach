"""STT local na GPU do Apple Silicon com ``mlx-whisper``.

Duas vezes mais rápido que o ``faster-whisper`` no ``small`` (0,59 s contra
1,18 s) e — o que a tabela não mostra — **libera a CPU**, que no worker disputa
com o TTS (ADR-0025). Em troca, só existe em Mac ARM.

Consequência de desenho: a biblioteca é extra opcional e o import é **tardio**.
Ver ``load_mlx_whisper`` para o porquê.

A língua é configurável (ADR-0055). **Verificado em
``mlx_whisper/transcribe.py``** (não suposto): ``language=None`` só dispara
``model.detect_language()`` de verdade quando o modelo é multilíngue — num
modelo ``.en``, a biblioteca força ``"en"`` mesmo recebendo ``None``. É por
isso que a troca de modelo (ADR-0055 item 1) e a de idioma são o mesmo commit:
configurável **sem** o modelo multilíngue não detectaria nada.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

from voicecoach.adapters.stt.audio import decode, duration_seconds
from voicecoach.application.ports.speech_to_text import (
    AudioInput,
    Segment,
    SttError,
    Transcript,
)

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


class _TranscribeFn(Protocol):
    """A função ``mlx_whisper.transcribe``, descrita pelo que usamos dela.

    ``verbose=None`` silencia a barra de progresso: em worker, ela iria para o
    log a cada turno sem informar nada. ``language`` não é parâmetro nomeado
    na assinatura real (vai por ``**decode_options``), mas descrevê-lo aqui é
    o que faz o `mypy` conferir a chamada — mesmo motivo do `_Engine` do outro
    adapter.
    """

    def __call__(
        self,
        audio: NDArray[np.float32],
        /,
        *,
        path_or_hf_repo: str,
        language: str | None,
        verbose: bool | None,
    ) -> dict[str, object]: ...


class MlxWhisperSpeechToText:
    """Implementa ``SpeechToText`` sobre ``mlx_whisper.transcribe``.

    Guarda a **função**, não um modelo: no ``mlx-whisper`` não existe objeto de
    modelo a construir — os pesos são carregados e cacheados por repositório
    dentro da própria biblioteca. Por isso a paridade com o outro adapter é de
    interface, não de mecânica.
    """

    def __init__(
        self, transcribe_fn: _TranscribeFn, model_repo: str, language: str | None
    ) -> None:
        self._transcribe_fn = transcribe_fn
        self._model_repo = model_repo
        self._language = language

    async def transcribe(self, audio: AudioInput) -> Transcript:
        """Mesma fronteira do outro adapter, conta de GIL diferente.

        Também vai para o executor, mas **não presuma simetria**: aqui o
        trabalho pesado vai para a GPU, então o que a thread segura é sobretudo
        a espera. No ``faster-whisper`` o ganho depende de o CTranslate2 soltar
        o GIL durante o cálculo; aqui a pergunta nem é a mesma.
        """
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._transcribe_sync, audio)
        except Exception as exc:
            # `except Exception` amplo, e justificado: ao contrário do `boto3`
            # (que tem `ClientError`/`BotoCoreError` como raízes), nem o
            # `faster-whisper` nem o `mlx-whisper` publicam uma família de
            # exceções. O que sai daqui é `RuntimeError` do CTranslate2, erro do
            # PyAV ao decodificar, `OSError` de pesos corrompidos ou qualquer
            # coisa do MLX. Listar as que conhecemos hoje deixaria as demais
            # escaparem para `application` como tipo de biblioteca — que é
            # exatamente o que a porta existe para impedir.
            message = f"transcrição falhou: {exc}"
            raise SttError(message) from exc

    def _transcribe_sync(self, audio: AudioInput) -> Transcript:
        samples = decode(audio)
        # Passamos AMOSTRAS, nunca um caminho de arquivo. Com um caminho, o
        # `mlx_whisper` chama `load_audio()`, que dispara o binário `ffmpeg` via
        # subprocesso — ausente na máquina de desenvolvimento e dependência de
        # sistema que ninguém pediu (ADR-0029). O benchmark original nunca
        # exercitou esse caminho porque já lia o WAV com `soundfile`.
        saida = self._transcribe_fn(
            samples,
            path_or_hf_repo=self._model_repo,
            language=self._language,
            verbose=None,
        )
        # `saida["segments"]` já é uma LISTA de dicts (não um generator como no
        # faster-whisper) — a biblioteca a materializou inteira antes de
        # devolver. Iterar mais de uma vez aqui não repete trabalho de CPU.
        segments_brutos = saida.get("segments", [])
        if not isinstance(segments_brutos, list):
            segments_brutos = []
        segments: list[Segment] = []
        logprob_x_duracao = 0.0
        duracao_total = 0.0
        no_speech = 0.0
        for bruto in segments_brutos:
            # A forma do dict é a do `mlx-whisper` (verificado em
            # transcribe.py), não input de usuário — o `assert` documenta a
            # suposição em vez de silenciá-la com `cast`.
            assert isinstance(bruto, dict)
            start = float(bruto["start"])
            end = float(bruto["end"])
            duracao = end - start
            segments.append(
                Segment(
                    start_seconds=start,
                    end_seconds=end,
                    text=str(bruto["text"]).strip(),
                )
            )
            logprob_x_duracao += float(bruto["avg_logprob"]) * duracao
            duracao_total += duracao
            no_speech = max(no_speech, float(bruto["no_speech_prob"]))

        confidence = logprob_x_duracao / duracao_total if duracao_total > 0 else 0.0
        return Transcript(
            text=str(saida["text"]).strip(),
            language=str(saida["language"]),
            duration_seconds=duration_seconds(samples),
            confidence=confidence,
            no_speech=no_speech,
            segments=tuple(segments),
        )


def load_mlx_whisper(
    model_repo: str, language: str | None = None
) -> MlxWhisperSpeechToText:
    """Importa a biblioteca e devolve o adapter — nesta ordem, e só aqui.

    **O import é tardio de propósito** (ADR-0027, item 4). ``import
    mlx_whisper`` no topo do módulo quebraria qualquer máquina x86 que apenas
    *importasse* este arquivo, mesmo sem nunca usá-lo — e importar é o que um
    coletor de testes ou uma ferramenta de análise faz o tempo todo.

    Não há paralelo direto em C#: lá o assembly é resolvido pelo runtime na
    primeira chamada e a referência é declarada no build. Em Python o ``import``
    é uma **instrução executável**, que roda onde estiver escrita — então mover
    a instrução para dentro da função move o momento da falha.

    A falha continua existindo; ela só passa a acontecer em quem realmente pediu
    o adapter, com a plataforma já verificada pelo ``factory``.
    """
    import mlx_whisper

    transcribe_fn: _TranscribeFn = mlx_whisper.transcribe
    return MlxWhisperSpeechToText(transcribe_fn, model_repo, language)
