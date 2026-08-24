"""``POST`` e ``GET`` de Turn — o contrato que se sustenta sem o SSE.

O ADR-0026 item 4 é explícito: *"o SSE é uma otimização de latência sobre um
contrato que se sustenta sem ele"*, e a seção de consequências registra o preço —
**dois caminhos de entrega precisam ambos ser testados, ou o recuo apodrece.**
Este arquivo é a metade do polling.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from fakes_api import AGORA, TURN_ID, Fakes, turn_pronto, wav_de
from voicecoach.api.schemas.problem import CONTENT_TYPE
from voicecoach.config import Settings

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


async def test_sessao_encerrada_e_409(client: AsyncClient, fakes: Fakes) -> None:
    """Invariante de domínio traduzida na borda (ADR-0017), e o 409 é o certo.

    A requisição está bem formada — é o **estado** que não permite. É o caso real
    da fala gravada offline que chega depois de a sessão ter sido encerrada.
    """
    fakes.sessao.end(AGORA + timedelta(hours=1))

    resposta = await client.post(
        f"/v1/sessions/{fakes.sessao.id}/turns", files=upload(), headers=CHAVE
    )

    assert resposta.status_code == 409
    assert resposta.json()["type"] == "urn:voicecoach:problem:invalid-state"


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
