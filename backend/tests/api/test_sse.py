"""O stream SSE: entrega ao vivo, retomada, fechamento e o schema único.

Estes testes exercitam a rota de verdade (`httpx` + `ASGITransport`), com o
`sse-starlette` serializando o fio. O que é fake são as portas.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import MutableMapping
from datetime import timedelta
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from fakes_api import AGORA, Fakes, turn_pronto
from voicecoach.api.schemas.turns import ChunkPayload, TurnResponse
from voicecoach.application.ports.turn_events import (
    ChunkReady,
    Completed,
    Failed,
    FeedbackAvailable,
)
from voicecoach.config import Settings
from voicecoach.domain.correction import Correction, CorrectionType, Severity

PRAZO = 5.0


async def ler_eventos(
    client: AsyncClient, url: str, *, headers: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Lê o stream inteiro até ele fechar e devolve os eventos já desmontados.

    O SSE separa eventos por **linha em branco** e cada evento é um bloco de
    linhas ``campo: valor`` — é o formato que o `sse-starlette` existe para não
    errarmos à mão.
    """
    eventos: list[dict[str, Any]] = []
    atual: dict[str, Any] = {}
    async with client.stream("GET", url, headers=headers) as resposta:
        assert resposta.status_code == 200
        assert resposta.headers["content-type"].startswith("text/event-stream")
        async for linha in resposta.aiter_lines():
            if not linha.strip():
                if atual:
                    eventos.append(atual)
                    atual = {}
                continue
            campo, _, valor = linha.partition(":")
            valor = valor.lstrip()
            if campo == "data":
                atual["data"] = json.loads(valor)
            elif campo in {"id", "event"}:
                atual[campo] = valor
    return eventos


async def test_o_stream_entrega_o_historico_e_depois_o_que_chega_ao_vivo(
    client: AsyncClient, fakes: Fakes
) -> None:
    turn = turn_pronto(fakes, trechos=1, transcript="hi there")

    async def worker() -> None:
        # Espera o stream abrir e assinar antes de publicar.
        while fakes.canal.assinantes(turn.id) == 0:
            await asyncio.sleep(0)
        await fakes.canal.publish(
            turn.id,
            ChunkReady(
                index=1,
                storage_key="reply/001.aac",
                duration_seconds=1.5,
                text="frase 1",
            ),
        )
        await fakes.canal.publish(
            turn.id,
            FeedbackAvailable(
                corrections=(
                    Correction(
                        index=0,
                        type=CorrectionType.GRAMMAR,
                        original_excerpt="I has a dog",
                        corrected_form="I have a dog",
                        explanation="have, com I",
                        severity=Severity.MODERATE,
                    ),
                )
            ),
        )
        await fakes.canal.publish(turn.id, Completed(reply_audio_key="reply/full.aac"))

    tarefa = asyncio.create_task(worker())
    eventos = await asyncio.wait_for(
        ler_eventos(client, f"/v1/turns/{turn.id}/events"), timeout=PRAZO
    )
    await tarefa

    assert [e["event"] for e in eventos] == [
        "transcribed",
        "chunk",
        "chunk",
        "feedback",
        "completed",
    ]
    # Os cinco nomes do ADR-0026, e o `id:` de cada um (a base da retomada).
    assert [e["id"] for e in eventos] == [
        "transcribed",
        "chunk:0",
        "chunk:1",
        "feedback",
        "completed",
    ]
    # A URL assinada viaja DENTRO do evento (ADR-0024): zero roundtrip.
    assert eventos[1]["data"]["url"].startswith("https://storage.test/")
    assert eventos[4]["data"]["reply_audio_url"].startswith("https://storage.test/")


async def test_reconectar_com_last_event_id_do_segundo_trecho_recebe_do_terceiro(
    client: AsyncClient, fakes: Fakes
) -> None:
    """Critério de aceite: sem repetir e sem pular.

    E o que acontece com o ``feedback`` está escrito: ele **não** volta, porque
    não é reconstituível do banco até o CARD-013 (ADR-0035). O aluno o vê no
    histórico, depois — nunca neste stream.
    """
    turn = turn_pronto(fakes, trechos=4, transcript="hi there")
    turn.fail("parou depois de 4", AGORA)

    eventos = await asyncio.wait_for(
        ler_eventos(
            client,
            f"/v1/turns/{turn.id}/events",
            headers={"Last-Event-ID": "chunk:1"},
        ),
        timeout=PRAZO,
    )

    assert [e["id"] for e in eventos] == ["chunk:2", "chunk:3", "failed"]
    assert all(e["event"] != "feedback" for e in eventos)


async def test_last_event_id_invalido_e_400_em_problem_details(
    client: AsyncClient, fakes: Fakes
) -> None:
    turn = turn_pronto(fakes, transcript="hi")

    resposta = await client.get(
        f"/v1/turns/{turn.id}/events", headers={"Last-Event-ID": "inventado"}
    )

    assert resposta.status_code == 400
    assert resposta.json()["type"] == "urn:voicecoach:problem:invalid-event-id"


async def test_turn_que_falha_depois_de_dois_trechos_emite_failed_parcial(
    client: AsyncClient, fakes: Fakes
) -> None:
    """Critério de aceite: ``failed`` com ``delivered_partially: true``.

    É o que muda a tela: "a conexão caiu, o que você ouviu está aqui" em vez de
    "não deu, tente de novo" (ADR-0023).
    """
    turn = turn_pronto(fakes, trechos=2, transcript="hi")

    async def worker() -> None:
        while fakes.canal.assinantes(turn.id) == 0:
            await asyncio.sleep(0)
        turn.fail("o TTS caiu no terceiro trecho", AGORA)
        await fakes.canal.publish(
            turn.id,
            Failed(reason="o TTS caiu no terceiro trecho", delivered_partially=True),
        )

    tarefa = asyncio.create_task(worker())
    eventos = await asyncio.wait_for(
        ler_eventos(client, f"/v1/turns/{turn.id}/events"), timeout=PRAZO
    )
    await tarefa

    assert [e["id"] for e in eventos] == ["transcribed", "chunk:0", "chunk:1", "failed"]
    assert eventos[-1]["data"] == {
        "reason": "o TTS caiu no terceiro trecho",
        "delivered_partially": True,
    }

    # E o GET continua listando os dois trechos — o recuo não perde nada.
    corpo = (await client.get(f"/v1/turns/{turn.id}")).json()
    assert len(corpo["chunks"]) == 2


async def test_o_stream_fecha_no_terminal_e_devolve_a_assinatura(
    client: AsyncClient, fakes: Fakes
) -> None:
    """Stream aberto para sempre é conexão vazando (ADR-0026, item 5)."""
    turn = turn_pronto(fakes, trechos=1, transcript="hi")
    turn.attach_reply("x", AGORA)
    turn.attach_reply_audio("reply/full.aac", AGORA)
    turn.complete(AGORA)

    await asyncio.wait_for(
        ler_eventos(client, f"/v1/turns/{turn.id}/events"), timeout=PRAZO
    )

    assert fakes.canal.assinantes(turn.id) == 0


async def test_o_stream_fecha_quando_o_cliente_desconecta(
    app: FastAPI, fakes: Fakes
) -> None:
    """O outro fechamento, e o que o ``sse-starlette`` está aqui para fazer.

    O aluno fecha o app no meio do turn. Sem alguém observando o
    ``http.disconnect``, a corrotina do stream continuaria viva segurando a
    assinatura até o prazo de 60 s — multiplicado por todo mundo que fechou o
    app.

    **Este teste fala ASGI direto, e não pelo ``httpx``, e a razão é uma
    armadilha que custou uma execução para aparecer.** O ``ASGITransport`` do
    httpx **não emite ``http.disconnect``**: sair do ``async with`` do
    ``client.stream`` não conta ao servidor que alguém foi embora. Escrito com o
    client, este teste passava — em **60 s**, porque quem fechava o stream era o
    prazo, não a desconexão. Um teste verde provando o contrário do que diz é
    pior que teste nenhum, e o card pede este item "com teste, não com
    confiança".

    Aqui o ``receive`` devolve ``http.disconnect`` assim que o segundo evento
    sai, que é exatamente o que um servidor real entrega.
    """
    turn = turn_pronto(fakes, trechos=1, transcript="hi there")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": f"/v1/turns/{turn.id}/events",
        "raw_path": b"",
        "query_string": b"",
        "headers": [],
        "client": ("test", 1),
        "server": ("test", 80),
        "root_path": "",
    }
    desconectou = asyncio.Event()

    async def receive() -> MutableMapping[str, str]:
        await desconectou.wait()
        return {"type": "http.disconnect"}

    corpos = 0

    async def send(message: MutableMapping[str, Any]) -> None:
        nonlocal corpos
        if message["type"] == "http.response.body" and message.get("body"):
            corpos += 1
            if corpos == 2:  # o aluno some depois do segundo evento
                desconectou.set()

    # Prazo do teste MUITO menor que o `sse_timeout` de 60 s: se o fechamento
    # dependesse do prazo, este `wait_for` estouraria em vez de passar.
    await asyncio.wait_for(app(scope, receive, send), timeout=5)

    assert corpos == 2
    assert fakes.canal.assinantes(turn.id) == 0


async def test_o_stream_fecha_sozinho_quando_o_turn_trava(
    client: AsyncClient, app: FastAPI, fakes: Fakes, settings: Settings
) -> None:
    """O prazo do ADR-0026 item 5, com o turn parado em ``processing``.

    Ninguém publica nada e o turn nunca fecha. O gerador tem de terminar
    sozinho — o ``EventSource`` do cliente reconecta com o ``Last-Event-ID`` e
    nada se perde, porque a retomada lê do banco.

    O prazo é encurtado só aqui: esperar 60 s reais num teste seria trocar uma
    conexão vazando por uma suíte inutilizável.
    """
    turn = turn_pronto(fakes, transcript="hi")
    app.state.settings = settings.model_copy(
        update={"sse_timeout": timedelta(seconds=0.1)}
    )

    eventos = await asyncio.wait_for(
        ler_eventos(client, f"/v1/turns/{turn.id}/events"), timeout=PRAZO
    )

    assert [e["id"] for e in eventos] == ["transcribed"]
    assert fakes.canal.assinantes(turn.id) == 0


# --- o schema único (a negativa do ADR-0026) --------------------------------


def test_o_trecho_do_get_e_o_do_evento_sao_a_mesma_classe() -> None:
    """*"Devem sair do mesmo schema pydantic, ou divergem"* — ADR-0026.

    Não basta terem os mesmos campos hoje: duas classes iguais passariam neste
    teste se ele comparasse campos, e divergiriam no primeiro campo que alguém
    acrescentasse a uma só. O que se verifica é a **identidade**.
    """
    tipo_no_get = TurnResponse.model_fields["chunks"].annotation

    assert tipo_no_get == list[ChunkPayload]
    assert ChunkPayload.model_fields.keys() == {
        "index",
        "url",
        "duration_seconds",
        "text",
    }


async def test_o_payload_do_evento_chunk_e_identico_ao_item_do_get(
    client: AsyncClient, fakes: Fakes
) -> None:
    """A prova de ponta a ponta: os dois caminhos produzem o mesmo objeto."""
    turn = turn_pronto(fakes, trechos=1, transcript="hi")
    turn.fail("parou", AGORA)

    eventos = await asyncio.wait_for(
        ler_eventos(client, f"/v1/turns/{turn.id}/events"), timeout=PRAZO
    )
    do_evento = next(e["data"] for e in eventos if e["event"] == "chunk")
    do_get = (await client.get(f"/v1/turns/{turn.id}")).json()["chunks"][0]

    assert do_evento == do_get


# --- o proxy que buferiza (o risco silencioso do card) ----------------------


async def test_o_stream_pede_para_ninguem_bufferizar(
    client: AsyncClient, fakes: Fakes
) -> None:
    """Proxy que buferiza ``text/event-stream`` mata a entrega **sem erro**.

    O produto fica exatamente tão lento quanto o polling que o SSE veio
    substituir, e nada acusa. Hoje o Compose deste repositório não tem proxy —
    os cabeçalhos vão mesmo assim, porque no dia em que um entrar ninguém vai
    lembrar disto.
    """
    turn = turn_pronto(fakes, transcript="hi")
    turn.fail("x", AGORA)

    async with client.stream("GET", f"/v1/turns/{turn.id}/events") as resposta:
        cabecalhos = dict(resposta.headers)
        async for _ in resposta.aiter_lines():
            pass

    assert cabecalhos["cache-control"] == "no-cache"
    assert cabecalhos["x-accel-buffering"] == "no"
