"""Contrato HTTP do Turn — e a **única** definição do que é um trecho.

**O requisito que dá forma a este arquivo** está no ADR-0026, seção de
consequências negativas: *"o payload do evento e o do ``GET /v1/turns/{id}``
descrevem a mesma coisa de duas formas. Devem sair do mesmo schema pydantic, ou
divergem."*

Por isso ``ChunkPayload`` aparece **duas vezes** aqui: como item de
``TurnResponse.chunks`` e como corpo do evento SSE ``chunk``. Não é
reaproveitamento oportunista — é a garantia. Duas classes com os mesmos quatro
campos passariam em todos os testes de hoje e divergiriam no primeiro campo que
alguém acrescentasse a uma só. Um teste compara as duas usagens justamente
porque a garantia é por construção e a construção pode ser desfeita sem querer.

**A projeção não recalcula nada** (ADR-0028): ``stage`` e ``delivered_partially``
são lidos de ``turn.stage`` e ``turn.delivered_partially``. Nenhum ``if`` sobre
artefato mora neste módulo — refazer a tabela do ADR-0023 aqui daria ao servidor
duas implementações da mesma regra, que é o defeito que o ADR-0028 nomeia.

**Evolução aditiva** (ADR-0008): ``chunks`` é campo novo e opcional na prática —
um cliente antigo que o ignore continua correto, vê ``stage == "speaking"`` e
espera ``completed`` para tocar ``reply_audio_url``.
"""

from __future__ import annotations

# Importados em runtime, não sob TYPE_CHECKING: o pydantic RESOLVE as anotações
# ao construir o modelo, e um nome que só existe para o type checker faz a classe
# nascer inválida (ver a mesma nota em `api/dependencies.py`).
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from voicecoach.domain.turn import Turn, TurnAudioChunk, TurnStage, TurnStatus


class ChunkPayload(BaseModel):
    """Um trecho tocável da resposta — no GET e no evento ``chunk``.

    ``url`` é uma URL **pré-assinada e de vida curta** (ADR-0024): ela é montada
    no momento da entrega, com TTL de ``media_url_ttl``. Não é endereço estável e
    não deve ser guardada pelo cliente além do playback do turn.
    """

    index: int = Field(description="0-based e denso; é a ordem de playback.")
    url: str = Field(description="URL assinada, válida por media_url_ttl.")
    duration_seconds: float
    text: str = Field(description="A frase que gerou este trecho.")

    @classmethod
    def de_chunk(cls, chunk: TurnAudioChunk, url: str) -> ChunkPayload:
        """Projeta o trecho persistido. Usado pelo ``GET``."""
        return cls(
            index=chunk.index,
            url=url,
            duration_seconds=chunk.duration_seconds,
            text=chunk.text,
        )


class TurnResponse(BaseModel):
    """``GET /v1/turns/{id}`` — completo e verdadeiro (ADR-0026, item 4).

    Este é o **contrato de recuo**: um cliente que nunca abra o stream tem de
    conseguir levar um turn até o fim só com esta rota. É por isso que ela
    devolve tudo, e não um resumo.
    """

    id: UUID
    session_id: UUID
    status: TurnStatus = Field(description="Estado grosso; não cresce (ADR-0008).")
    stage: TurnStage = Field(description="Etapa exibida, DERIVADA (ADR-0023/0028).")
    created_at: datetime
    transcript: str | None = None
    reply_text: str | None = None
    reply_audio_url: str | None = Field(
        default=None,
        description="Áudio inteiro concatenado, assinado. Nulo antes de completar "
        "— ou depois de a retenção expirar (ADR-0024).",
    )
    delivered_partially: bool = Field(
        description="Falhou DEPOIS de o aluno já ter ouvido algo (ADR-0023)."
    )
    failure_reason: str | None = None
    chunks: list[ChunkPayload] = Field(
        default_factory=list, description="Campo ADITIVO (ADR-0008)."
    )

    @classmethod
    def de_turn(
        cls,
        turn: Turn,
        *,
        chunk_urls: list[str],
        reply_audio_url: str | None,
    ) -> TurnResponse:
        """Projeta a entidade. As URLs vêm prontas porque assinar é ``await``.

        Assinar é HMAC local (ADR-0024) — microssegundos —, mas passa por
        executor no adapter S3 (ADR-0034), então é uma corrotina. Um
        ``@computed_field`` do pydantic não pode ser async; por isso a rota
        assina e passa, em vez de o schema resolver sozinho.
        """
        return cls(
            id=turn.id,
            session_id=turn.session_id,
            status=turn.status,
            # Projeção pura: `turn.stage` é @property do domínio (ADR-0028).
            stage=turn.stage,
            created_at=turn.created_at,
            transcript=turn.transcript,
            reply_text=turn.reply_text,
            reply_audio_url=reply_audio_url,
            delivered_partially=turn.delivered_partially,
            failure_reason=turn.failure_reason,
            chunks=[
                ChunkPayload.de_chunk(chunk, url)
                for chunk, url in zip(turn.audio_chunks, chunk_urls, strict=True)
            ],
        )


class TurnAcceptedResponse(BaseModel):
    """``202`` do ``POST`` — o turn está aceito e a caminho."""

    turn_id: UUID
    replayed: bool = Field(
        description="true quando a Idempotency-Key já tinha sido usada: "
        "nenhum turn novo foi criado e nada é reprocessado."
    )


class SessionResponse(BaseModel):
    """``POST /v1/sessions`` — o mínimo para o cliente ter onde falar."""

    id: UUID
    student_id: UUID
    started_at: datetime
    is_active: bool


# --- payloads dos eventos SSE (ADR-0026, item 1) --------------------------
#
# `chunk` NÃO tem classe própria: ele é `ChunkPayload`, o mesmo do GET. É a
# negativa do ADR-0026 aplicada onde ela morde.


class TranscribedPayload(BaseModel):
    """Evento ``transcribed``."""

    transcript: str


class FeedbackPayload(BaseModel):
    """Evento ``feedback``.

    **O único evento que a retomada não reconstrói**, porque correção só é
    persistida no CARD-013 (ADR-0035). Um cliente que reconecte depois de ele ter
    passado o verá no histórico, mais tarde — não neste stream.
    """

    has_mistakes: bool
    original: str
    corrected: str
    tip: str


class CompletedPayload(BaseModel):
    """Evento ``completed``. Carrega a URL do áudio inteiro, já assinada."""

    reply_audio_url: str


class FailedPayload(BaseModel):
    """Evento ``failed`` — inclusive depois de entrega parcial (ADR-0023)."""

    reason: str
    delivered_partially: bool
