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
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from voicecoach.domain.correction import (
    Correction,
    CorrectionType,
    Severity,
    legacy_summary,
)
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


class CorrectionPayload(BaseModel):
    """Uma correção tipada — no ``GET`` e no evento ``feedback``.

    Mesma garantia do ``ChunkPayload`` e pela mesma razão (ADR-0026): o payload
    do evento e o do ``GET`` descrevem a mesma coisa, então **saem do mesmo
    schema** ou divergem no primeiro campo que alguém acrescentar a um só.

    ``index`` viaja porque ele não é detalhe de armazenamento: é a **ordem
    pedagógica**, e é o contrato que diz ao cliente qual correção destacar
    quando só couber uma na tela (CARD-016).
    """

    index: int = Field(description="0-based e denso; é a ordem pedagógica.")
    type: CorrectionType
    original_excerpt: str = Field(description="Trecho verbatim da fala do aluno.")
    corrected_form: str
    explanation: str
    severity: Severity = Field(
        description="Escala fechada. O rótulo em pt-BR é do cliente, não daqui."
    )

    @classmethod
    def de_correcao(cls, correction: Correction) -> CorrectionPayload:
        return cls(
            index=correction.index,
            type=correction.type,
            original_excerpt=correction.original_excerpt,
            corrected_form=correction.corrected_form,
            explanation=correction.explanation,
            severity=correction.severity,
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
    corrections: list[CorrectionPayload] = Field(
        default_factory=list,
        description="Correções tipadas e persistidas (CARD-013). Campo ADITIVO.",
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
            corrections=[CorrectionPayload.de_correcao(c) for c in turn.corrections],
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
    """Evento ``feedback`` — agora reconstruído na retomada (CARD-013).

    Era **o único evento que a retomada não reconstruía**, porque correção não
    era persistida (ADR-0035, ADR-0041 item 5). Com ``turn.corrections`` no
    banco, o gatilho que aquele ADR deixou escrito disparou e ele volta como
    qualquer outro.

    **Os quatro campos velhos continuam aqui, e continuam obrigatórios**
    (ADR-0008: proibido remover ou renomear dentro de ``/v1`` — a restrição dura
    é o app na loja que não atualiza quando queremos). O que mudou é de onde
    saem: eles são **derivados** de ``corrections`` por ``legacy_summary``, e não
    mais gerados pelo modelo. Quando morrem: no ``/v2``, ou antes, quando o app
    mínimo suportado já ler ``corrections[]``.
    """

    has_mistakes: bool = Field(description="LEGADO — derivado de corrections.")
    original: str = Field(description="LEGADO — corrections[0].original_excerpt.")
    corrected: str = Field(description="LEGADO — corrections[0].corrected_form.")
    tip: str = Field(description="LEGADO — corrections[0].explanation.")
    corrections: list[CorrectionPayload] = Field(
        default_factory=list,
        description="Correções tipadas (CARD-013). Campo ADITIVO.",
    )

    @classmethod
    def de_correcoes(cls, corrections: Sequence[Correction]) -> FeedbackPayload:
        """Monta as duas metades do payload a partir de uma origem só.

        Os campos velhos NÃO são recalculados aqui: ``legacy_summary`` mora no
        domínio, e a borda apenas projeta (ADR-0028). Um ``[0]`` escrito neste
        arquivo daria ao servidor duas implementações da mesma regra — uma para
        o evento ao vivo e outra para a retomada —, que é exatamente o defeito
        que aquele ADR nomeia.
        """
        legado = legacy_summary(corrections)
        return cls(
            has_mistakes=legado.has_mistakes,
            original=legado.original,
            corrected=legado.corrected,
            tip=legado.tip,
            corrections=[CorrectionPayload.de_correcao(c) for c in corrections],
        )


class CompletedPayload(BaseModel):
    """Evento ``completed``. Carrega a URL do áudio inteiro, já assinada."""

    reply_audio_url: str


class FailedPayload(BaseModel):
    """Evento ``failed`` — inclusive depois de entrega parcial (ADR-0023)."""

    reason: str
    delivered_partially: bool


class TurnEventPayloads(BaseModel):
    """**Não é resposta de rota nenhuma.** Existe para o OpenAPI enxergar o SSE.

    O ADR-0008 promete que mudança de contrato quebra o cliente **em build**. Essa
    promessa era **falsa para quatro dos cinco eventos**: a rota do stream devolve
    ``EventSourceResponse``, que não é modelo pydantic, então os payloads nunca
    chegavam ao OpenAPI — e portanto nunca chegavam aos tipos gerados. Só
    ``ChunkPayload`` escapava, por carona em ``TurnResponse.chunks``.

    Descoberto no CARD-012, ao escrever o primeiro consumidor. Este envelope é a
    correção mínima: declarado no ``responses`` da rota, ele arrasta os cinco para
    ``components.schemas``. Um campo renomeado em qualquer evento passa a virar
    ``error TS2339`` no app, que é o ponto inteiro do ADR-0008.

    Os nomes dos campos são os cinco nomes de evento do ADR-0026 — de propósito:
    quem ler o tipo gerado descobre o mapa ``event: → payload`` sem sair dele.
    """

    transcribed: TranscribedPayload
    chunk: ChunkPayload
    feedback: FeedbackPayload
    completed: CompletedPayload
    failed: FailedPayload
