"""``POST`` e ``GET`` de Turn — o contrato que se sustenta sem o SSE.

O ADR-0026 item 4 é explícito: *"o SSE é uma otimização de latência sobre um
contrato que se sustenta sem ele"*, e a seção de consequências registra o preço —
**dois caminhos de entrega precisam ambos ser testados, ou o recuo apodrece.**
Este arquivo é a metade do polling.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import get_args
from uuid import uuid4

import pytest
from httpx import AsyncClient

from fakes_api import AGORA, TURN_ID, Fakes, turn_pronto, wav_de
from voicecoach.api.schemas.problem import CONTENT_TYPE
from voicecoach.api.schemas.turns import (
    CorrectionPayload,
    FeedbackPayload,
    TurnResponse,
)
from voicecoach.config import Settings
from voicecoach.domain.correction import Correction, CorrectionType, Severity
from voicecoach.domain.session import Session
from voicecoach.domain.turn import RejectionReason
from voicecoach.domain.usage import UsageEvent

CHAVE = {"Idempotency-Key": "chave-do-cliente-0001"}


def upload(segundos: float = 2.0) -> dict[str, tuple[str, bytes, str]]:
    return {"audio": ("fala.wav", wav_de(segundos), "audio/wav")}


# --- POST -------------------------------------------------------------------


async def test_post_aceita_com_202_grava_o_audio_e_enfileira(
    client: AsyncClient, fakes: Fakes
) -> None:
    resposta = await client.post(
        f"/v1/sessions/{fakes.sessao.id}/turns", files=upload(), headers=CHAVE
    )

    assert resposta.status_code == 202
    assert resposta.json() == {"turn_id": str(TURN_ID), "replayed": False}
    assert fakes.enfileirados == [TURN_ID]

    turn = fakes.turns.turns[TURN_ID]
    # A duração foi MEDIDA do arquivo, não declarada pelo cliente.
    assert turn.audio_duration == pytest.approx(
        timedelta(seconds=2), abs=timedelta(milliseconds=50)
    )
    assert turn.input_audio_ref.endswith("/input.wav")
    assert turn.input_audio_ref in fakes.storage.objetos


async def test_a_mesma_chave_duas_vezes_devolve_o_mesmo_turn_e_um_so_no_banco(
    client: AsyncClient, fakes: Fakes
) -> None:
    """Critério de aceite do card, ponta a ponta pela rota."""
    url = f"/v1/sessions/{fakes.sessao.id}/turns"

    primeira = await client.post(url, files=upload(), headers=CHAVE)
    segunda = await client.post(url, files=upload(), headers=CHAVE)

    assert primeira.status_code == segunda.status_code == 202
    assert segunda.json() == {"turn_id": str(TURN_ID), "replayed": True}
    assert len(fakes.turns.turns) == 1


async def test_sem_o_cabecalho_de_idempotencia_e_422_em_problem_details(
    client: AsyncClient, fakes: Fakes
) -> None:
    """O cabeçalho é obrigatório de propósito.

    Gerar uma chave quando o cliente esquece faria o esquecimento virar um turno
    extra processado e pago, em silêncio.
    """
    resposta = await client.post(
        f"/v1/sessions/{fakes.sessao.id}/turns", files=upload()
    )

    assert resposta.status_code == 422
    assert resposta.headers["content-type"].startswith(CONTENT_TYPE)
    assert resposta.json()["type"] == "urn:voicecoach:problem:validation"


async def test_upload_que_nao_e_audio_valido_e_422_em_problem_details(
    client: AsyncClient, fakes: Fakes
) -> None:
    """Critério de aceite: "upload sem áudio válido ⇒ 422 em Problem Details"."""
    resposta = await client.post(
        f"/v1/sessions/{fakes.sessao.id}/turns",
        files={"audio": ("fala.wav", b"isto nao e audio", "audio/wav")},
        headers=CHAVE,
    )

    corpo = resposta.json()
    assert resposta.status_code == 422
    assert resposta.headers["content-type"].startswith(CONTENT_TYPE)
    assert corpo["title"] == "Áudio inválido"
    assert fakes.turns.turns == {}
    assert fakes.storage.objetos == {}


async def test_formato_nao_suportado_e_415(client: AsyncClient, fakes: Fakes) -> None:
    resposta = await client.post(
        f"/v1/sessions/{fakes.sessao.id}/turns",
        files={"audio": ("nota.txt", b"oi", "text/plain")},
        headers=CHAVE,
    )

    corpo = resposta.json()
    assert resposta.status_code == 415
    assert corpo["type"] == "urn:voicecoach:problem:unsupported-audio-type"
    # A extensão da RFC 9457 diz ao cliente o que fazer, em vez de só recusar.
    assert "audio/wav" in corpo["accepted"]


async def test_audio_longo_demais_e_413(
    client: AsyncClient, fakes: Fakes, settings: Settings
) -> None:
    limite = settings.max_turn_audio_duration.total_seconds()

    resposta = await client.post(
        f"/v1/sessions/{fakes.sessao.id}/turns",
        files=upload(limite + 5),
        headers=CHAVE,
    )

    assert resposta.status_code == 413
    assert resposta.json()["max_duration_seconds"] == limite


async def test_sessao_inexistente_e_404_com_o_id_no_corpo(
    client: AsyncClient,
) -> None:
    ausente = uuid4()

    resposta = await client.post(
        f"/v1/sessions/{ausente}/turns", files=upload(), headers=CHAVE
    )

    corpo = resposta.json()
    assert resposta.status_code == 404
    assert corpo["type"] == "urn:voicecoach:problem:session-not-found"
    assert corpo["session_id"] == str(ausente)


async def test_sessao_encerrada_e_409_com_urn_propria(
    client: AsyncClient, fakes: Fakes
) -> None:
    """RF3 (CARD-031): distinto de ``invalid-state`` — o app precisa dizer "sua
    fala não entrou porque a sessão fechou", não "algo deu errado".

    A requisição está bem formada — é o **estado** que não permite. É o caso real
    da fala gravada offline que chega depois de a sessão ter sido encerrada.
    """
    fakes.sessao.end(AGORA + timedelta(hours=1))

    resposta = await client.post(
        f"/v1/sessions/{fakes.sessao.id}/turns", files=upload(), headers=CHAVE
    )

    corpo = resposta.json()
    assert resposta.status_code == 409
    assert corpo["type"] == "urn:voicecoach:problem:session-ended"
    assert corpo["session_id"] == str(fakes.sessao.id)


async def test_cota_diaria_excedida_e_429_com_reset_at(
    client: AsyncClient, fakes: Fakes
) -> None:
    """ADR-0063 (CARD-015): a cota é por student, verificada antes de criar o turn."""
    for _ in range(1000):
        fakes.usage_events.eventos[uuid4()] = UsageEvent(
            turn_id=uuid4(),
            student_id=fakes.sessao.student_id,
            occurred_at=AGORA,
            llm_model="claude-haiku-4-5-20251001",
            llm_input_tokens=1,
            llm_cache_creation_tokens=0,
            llm_cache_read_tokens=0,
            llm_output_tokens=1,
            stt_audio_duration=timedelta(seconds=1),
            stt_provider="faster_whisper",
            stt_confidence=-0.1,
            stt_no_speech=0.0,
            tts_chars=1,
            tts_provider="piper",
            estimated_cost_usd=Decimal("0.001"),
        )

    resposta = await client.post(
        f"/v1/sessions/{fakes.sessao.id}/turns", files=upload(), headers=CHAVE
    )

    corpo = resposta.json()
    assert resposta.status_code == 429
    assert corpo["type"] == "urn:voicecoach:problem:daily-quota-exceeded"
    assert "reset_at" in corpo
    assert fakes.turns.turns == {}


async def test_orcamento_do_servico_excedido_e_503(
    client: AsyncClient, fakes: Fakes
) -> None:
    fakes.budget.excedido = True

    resposta = await client.post(
        f"/v1/sessions/{fakes.sessao.id}/turns", files=upload(), headers=CHAVE
    )

    corpo = resposta.json()
    assert resposta.status_code == 503
    assert corpo["type"] == "urn:voicecoach:problem:service-budget-exceeded"
    assert fakes.turns.turns == {}


async def test_rate_limit_excedido_e_429_antes_de_ler_o_audio(
    client: AsyncClient, fakes: Fakes
) -> None:
    """A dependência da rota nega antes do corpo — nenhum turn, nenhum objeto."""
    fakes.rate_limiter.permitido = False

    resposta = await client.post(
        f"/v1/sessions/{fakes.sessao.id}/turns", files=upload(), headers=CHAVE
    )

    corpo = resposta.json()
    assert resposta.status_code == 429
    assert corpo["type"] == "urn:voicecoach:problem:rate-limited"
    assert fakes.turns.turns == {}
    assert fakes.storage.objetos == {}


# --- GET: o contrato de recuo ----------------------------------------------


async def test_get_projeta_a_etapa_do_dominio_sem_recalcular(
    client: AsyncClient, fakes: Fakes
) -> None:
    """ADR-0028: a borda lê ``turn.stage``; nenhum ``if`` sobre artefato aqui."""
    turn = turn_pronto(fakes, trechos=1, transcript="hi there")

    corpo = (await client.get(f"/v1/turns/{turn.id}")).json()

    assert corpo["status"] == "processing"
    # Com trecho gravado, a etapa é `speaking` MESMO com `reply_text` nulo — é a
    # inversão que a cascata trouxe (ADR-0023, item 4).
    assert corpo["stage"] == "speaking"
    assert corpo["reply_text"] is None
    assert corpo["delivered_partially"] is False


async def test_get_de_turn_recusado_mostra_o_motivo_nao_uma_falha(
    client: AsyncClient, fakes: Fakes
) -> None:
    """CARD-040: `nao_entendido` é `status == completed`, não `failed`."""
    turn = turn_pronto(fakes, transcript="")
    turn.reject(RejectionReason.NO_SPEECH, AGORA)

    corpo = (await client.get(f"/v1/turns/{turn.id}")).json()

    assert corpo["status"] == "completed"
    assert corpo["stage"] == "not_understood"
    assert corpo["rejection_reason"] == "no_speech"
    assert corpo["failure_reason"] is None
    assert corpo["reply_audio_url"] is None


async def test_um_cliente_que_so_faz_polling_leva_o_turn_ate_o_fim(
    client: AsyncClient, fakes: Fakes
) -> None:
    """**O teste do recuo.** Sem tocar no SSE (ADR-0026, item 4).

    É o único que impede o contrato de recuo de virar ficção — e o card manda
    não cortá-lo mesmo se a sessão estourar.
    """
    turn = turn_pronto(fakes, trechos=2, transcript="hi there")

    # 1ª leitura: o professor ainda está falando.
    primeira = (await client.get(f"/v1/turns/{turn.id}")).json()
    assert primeira["stage"] == "speaking"
    assert primeira["reply_audio_url"] is None
    assert [c["index"] for c in primeira["chunks"]] == [0, 1]

    # O worker fecha o turn.
    turn.attach_reply("Hi there. How are you?", AGORA)
    turn.attach_reply_audio("full.aac", AGORA)
    turn.complete(AGORA)

    # 2ª leitura: tudo pronto, com o áudio INTEIRO assinado.
    segunda = (await client.get(f"/v1/turns/{turn.id}")).json()
    assert segunda["status"] == "completed"
    assert segunda["stage"] == "completed"
    assert segunda["reply_audio_url"].startswith("https://storage.test/full.aac")
    assert segunda["transcript"] == "hi there"
    assert len(segunda["chunks"]) == 2


async def test_turn_que_falhou_depois_de_dois_trechos_continua_listando_os_dois(
    client: AsyncClient, fakes: Fakes
) -> None:
    """Critério de aceite: falhar não apaga o que o aluno já ouviu (ADR-0023)."""
    turn = turn_pronto(fakes, trechos=2, transcript="hi")
    turn.fail("o TTS caiu", AGORA)

    corpo = (await client.get(f"/v1/turns/{turn.id}")).json()

    assert corpo["status"] == "failed"
    assert corpo["delivered_partially"] is True
    assert corpo["failure_reason"] == "o TTS caiu"
    assert len(corpo["chunks"]) == 2


async def test_as_urls_dos_trechos_sao_assinadas_e_com_ttl(
    client: AsyncClient, fakes: Fakes
) -> None:
    """A URL viaja pronta (ADR-0024): zero roundtrip por frase."""
    turn = turn_pronto(fakes, trechos=1, transcript="hi")

    trecho = (await client.get(f"/v1/turns/{turn.id}")).json()["chunks"][0]

    assert trecho["url"].startswith("https://storage.test/")
    assert "expires=900" in trecho["url"]  # media_url_ttl = 15 min
    assert trecho["text"] == "frase 0"


async def test_turn_inexistente_e_404_em_problem_details(
    client: AsyncClient,
) -> None:
    resposta = await client.get(f"/v1/turns/{uuid4()}")

    assert resposta.status_code == 404
    assert resposta.headers["content-type"].startswith(CONTENT_TYPE)
    assert resposta.json()["type"] == "urn:voicecoach:problem:turn-not-found"


# --- POST /v1/sessions ------------------------------------------------------


async def test_criar_sessao_devolve_uma_sessao_ativa(
    client: AsyncClient, fakes: Fakes
) -> None:
    corpo = (await client.post("/v1/sessions")).json()

    assert corpo["is_active"] is True
    assert corpo["student_id"] == "00000000-0000-0000-0000-000000000001"
    assert corpo["id"] in {str(s) for s in fakes.sessions.sessions}


# --- corrections no contrato /v1 (CARD-013) --------------------------------


CORRECOES = (
    Correction(
        index=0,
        type=CorrectionType.VOCABULARY,
        original_excerpt="very stressful",
        corrected_form="quite stressful",
        explanation="'quite' soa mais natural aqui.",
        severity=Severity.MINOR,
    ),
    Correction(
        index=1,
        type=CorrectionType.WORD_ORDER,
        original_excerpt="always I go",
        corrected_form="I always go",
        explanation="O advérbio vem depois do sujeito.",
        severity=Severity.MAJOR,
    ),
)


async def test_o_get_devolve_as_correcoes_tipadas(
    client: AsyncClient, fakes: Fakes
) -> None:
    """Critério de aceite do CARD-013 na borda: 2 correções ⇒ 2 no payload."""
    turn = turn_pronto(fakes, trechos=1, transcript="hi")
    turn.attach_reply("Nice.", AGORA)
    turn.attach_corrections(CORRECOES)

    corpo = (await client.get(f"/v1/turns/{turn.id}")).json()

    assert [c["index"] for c in corpo["corrections"]] == [0, 1]
    assert corpo["corrections"][1]["type"] == "word_order"
    assert corpo["corrections"][1]["severity"] == "major"
    assert corpo["corrections"][0]["original_excerpt"] == "very stressful"


async def test_os_quatro_campos_velhos_continuam_no_contrato_e_saem_da_primeira(
    client: AsyncClient, fakes: Fakes
) -> None:
    """ADR-0008: proibido remover ou renomear campo dentro de ``/v1``.

    O que muda no CARD-013 é a ORIGEM dos quatro, não a existência deles: o
    modelo parou de gerá-los e eles passaram a ser derivados de
    ``corrections[0]``. Um cliente antigo não percebe diferença — que é
    literalmente o que a política aditiva promete.
    """
    turn = turn_pronto(fakes, trechos=1, transcript="hi")
    turn.attach_reply("Nice.", AGORA)
    turn.attach_corrections(CORRECOES)

    payload = FeedbackPayload.de_correcoes(turn.corrections).model_dump()

    assert payload["has_mistakes"] is True
    assert payload["original"] == "very stressful"
    assert payload["corrected"] == "quite stressful"
    assert payload["tip"] == "'quite' soa mais natural aqui."
    assert len(payload["corrections"]) == 2


def test_o_get_e_o_evento_usam_a_mesma_classe_de_correcao() -> None:
    """A garantia do ADR-0026 estendida a ``corrections`` (CARD-013).

    Duas classes com os mesmos seis campos passariam em todos os testes de hoje
    e divergiriam no primeiro campo que alguém acrescentasse a uma só. Este teste
    existe porque a garantia é por construção — e construção se desfaz sem
    querer.
    """
    do_get = get_args(TurnResponse.model_fields["corrections"].annotation)
    do_evento = get_args(FeedbackPayload.model_fields["corrections"].annotation)

    # `is`, e não `==`: duas classes pydantic com os mesmos seis campos são
    # diferentes mas comparariam iguais em quase todo teste. O que se quer
    # afirmar é que existe UMA classe, não duas equivalentes.
    assert do_get[0] is CorrectionPayload
    assert do_evento[0] is CorrectionPayload


async def test_turn_sem_erro_nenhum_devolve_corrections_vazio(
    client: AsyncClient, fakes: Fakes
) -> None:
    """Lista vazia é o desfecho ESPERADO, não ausência de dado."""
    turn = turn_pronto(fakes, trechos=1, transcript="hi")
    turn.attach_reply("Nice.", AGORA)
    turn.attach_corrections([])

    corpo = (await client.get(f"/v1/turns/{turn.id}")).json()

    assert corpo["corrections"] == []


# --- POST /v1/sessions/{id}/end (CARD-031) ---------------------------------


async def test_encerrar_sessao_devolve_o_resumo(
    client: AsyncClient, fakes: Fakes
) -> None:
    turn = turn_pronto(fakes, trechos=1, transcript="hi")
    turn.attach_reply("Nice.", AGORA)
    turn.attach_corrections(CORRECOES)

    resposta = await client.post(f"/v1/sessions/{fakes.sessao.id}/end")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["turns"] == 1
    assert corpo["spoken_seconds"] == pytest.approx(2.0)
    assert corpo["corrections_by_type"] == {"vocabulary": 1, "word_order": 1}
    assert fakes.sessions.sessions[fakes.sessao.id].ended_at is not None


async def test_encerrar_sessao_sem_turn_nenhum_devolve_resumo_vazio(
    client: AsyncClient, fakes: Fakes
) -> None:
    resposta = await client.post(f"/v1/sessions/{fakes.sessao.id}/end")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo == {"turns": 0, "spoken_seconds": 0.0, "corrections_by_type": {}}


async def test_encerrar_sessao_duas_vezes_e_idempotente(
    client: AsyncClient, fakes: Fakes
) -> None:
    """RF2: a segunda chamada devolve o mesmo resumo, não erro."""
    url = f"/v1/sessions/{fakes.sessao.id}/end"

    primeira = await client.post(url)
    segunda = await client.post(url)

    assert primeira.status_code == segunda.status_code == 200
    assert primeira.json() == segunda.json()


async def test_encerrar_sessao_inexistente_e_404(client: AsyncClient) -> None:
    ausente = uuid4()

    resposta = await client.post(f"/v1/sessions/{ausente}/end")

    corpo = resposta.json()
    assert resposta.status_code == 404
    assert corpo["type"] == "urn:voicecoach:problem:session-not-found"
    assert corpo["session_id"] == str(ausente)


# --- POST /v1/turns/{id}/discard (CARD-032) --------------------------------


async def test_descartar_turn_processando_devolve_204(
    client: AsyncClient, fakes: Fakes
) -> None:
    turn = turn_pronto(fakes, trechos=1, transcript="hi")

    resposta = await client.post(f"/v1/turns/{turn.id}/discard")

    assert resposta.status_code == 204
    assert fakes.turns.turns[turn.id].discarded_at is not None


async def test_descartar_nao_apaga_nada_o_get_continua_completo(
    client: AsyncClient, fakes: Fakes
) -> None:
    """RF1/RF3/RF4: o turn continua no histórico, com tudo que já tinha."""
    turn = turn_pronto(fakes, trechos=1, transcript="hi")

    await client.post(f"/v1/turns/{turn.id}/discard")
    corpo = (await client.get(f"/v1/turns/{turn.id}")).json()

    assert corpo["transcript"] == "hi"
    assert len(corpo["chunks"]) == 1
    assert corpo["discarded_at"] is not None


async def test_descartar_duas_vezes_e_204_as_duas(
    client: AsyncClient, fakes: Fakes
) -> None:
    turn = turn_pronto(fakes, trechos=1, transcript="hi")
    url = f"/v1/turns/{turn.id}/discard"

    primeira = await client.post(url)
    segunda = await client.post(url)

    assert primeira.status_code == segunda.status_code == 204


async def test_descartar_turn_completo_e_409(client: AsyncClient, fakes: Fakes) -> None:
    turn = turn_pronto(fakes, trechos=1, transcript="hi")
    turn.attach_reply("Nice.", AGORA)
    turn.attach_reply_audio("dev/resposta.mp3", AGORA)
    turn.complete(AGORA)

    resposta = await client.post(f"/v1/turns/{turn.id}/discard")

    corpo = resposta.json()
    assert resposta.status_code == 409
    assert corpo["type"] == "urn:voicecoach:problem:turn-already-completed"
    assert fakes.turns.turns[turn.id].discarded_at is None


async def test_descartar_turn_inexistente_e_404(client: AsyncClient) -> None:
    resposta = await client.post(f"/v1/turns/{uuid4()}/discard")

    assert resposta.status_code == 404
    assert resposta.json()["type"] == "urn:voicecoach:problem:turn-not-found"


async def test_descartar_turn_de_outro_aluno_e_404_como_inexistente(
    client: AsyncClient, fakes: Fakes
) -> None:
    """RNF2: mesmo 404 de um id que não existe — sem oráculo de posse."""

    outro_aluno = uuid4()
    outra_sessao = Session(id=uuid4(), student_id=outro_aluno, started_at=AGORA)
    fakes.sessions.sessions[outra_sessao.id] = outra_sessao
    turn = turn_pronto(fakes, trechos=1, transcript="hi")
    turn.session_id = outra_sessao.id

    resposta = await client.post(f"/v1/turns/{turn.id}/discard")

    assert resposta.status_code == 404
    assert resposta.json()["type"] == "urn:voicecoach:problem:turn-not-found"
    assert fakes.turns.turns[turn.id].discarded_at is None
