"""Porta de storage de mídia (ADR-0006, substituído pelo ADR-0024).

O contrato é a **API S3**, e o produto nunca fica no caminho dos bytes: o
cliente baixa o áudio direto do storage por **URL pré-assinada de TTL curto**.
É o que tira banda e CPU de streaming do processo que precisa estar livre para
atender o próximo turn.

As chaves não são construídas aqui — vêm prontas de ``domain/media_keys.py``,
onde moram as duas regras de produto que elas carregam (ordem lexicográfica =
ordem de playback; tudo de um aluno sob um prefixo só).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import timedelta


class MediaStorageError(RuntimeError):
    """O storage não completou a operação.

    Mora na porta, como o ``TtsError`` e o ``LlmError``, e pela mesma razão
    (ADR-0031, item 5): quem captura é o caso de uso, em ``application``, que
    não pode importar ``adapters``.
    """


class MediaStorage(Protocol):
    """Guarda e serve os áudios de um turn.

    Eram três operações, e o docstring dizia que um ``get`` só entraria "por
    extensão, quando o CARD-009 precisar disso, com o motivo escrito". O
    CARD-009 precisou, e o motivo é este: **o worker não está no caminho do
    aluno.** A rejeição da alternativa B do ADR-0024 é sobre a *API* ler o
    objeto para repassá-lo ao cliente — aí a URL assinada perde o propósito,
    porque o produto volta a pagar banda e CPU de streaming. O worker é o
    contrário: ele é o destinatário final dos bytes, não um intermediário. Ele
    precisa do áudio **dentro do processo** para entregá-lo ao STT, e uma URL
    assinada só o obrigaria a baixar de si mesmo por HTTP.

    Quatro operações, portanto, e a assimetria é deliberada: escrita e leitura
    direta são do worker, URL assinada é da API.
    """

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """Grava um objeto.

        ``content_type`` não é enfeite: quem baixa é o player do aluno, direto
        do storage, e sem o cabeçalho certo ele recebe
        ``application/octet-stream`` e pode recusar-se a tocar. É a diferença
        entre o ``AudioInput`` do STT (que **não** carrega content type de
        propósito, porque o decodificador lê os próprios bytes — ADR-0029) e
        aqui: lá o consumidor é nosso código, aqui é um navegador.
        """
        ...

    async def get(self, key: str) -> bytes:
        """Lê um objeto inteiro para a memória — o áudio do aluno, no worker.

        Devolve ``bytes`` porque é exatamente o que a porta de STT consome
        (``AudioInput.data``, ADR-0029): o áudio ainda codificado, com o
        decodificador do adapter identificando o contêiner pelos próprios
        bytes. Nada de caminho de arquivo, nada de stream — um turn tem no
        máximo ~20 s de áudio, e o STT precisa do buffer inteiro de qualquer
        forma para decodificar.

        Levanta ``MediaStorageError`` se a chave não existir. Não há
        ``None``: pedir o input de um turn que existe no banco e não existe no
        storage não é ausência esperada, é o storage tendo perdido o objeto —
        e o caso de uso trata isso como falha de infraestrutura, marcando o
        turn como ``failed``.
        """
        ...

    async def presigned_get_url(self, key: str, ttl: timedelta) -> str:
        """Uma URL temporária que dá acesso de leitura a **um** objeto.

        Assinar é **HMAC local**: não há chamada de rede, custa microssegundos.
        É isso que permitiu ao ADR-0024 decidir "a URL viaja junto do evento do
        trecho" em vez de "o cliente pede quando precisar" — o desenho pedido
        custaria um roundtrip por frase dentro de um orçamento de 1,8 s.

        **O método é ``async`` mesmo assim, e a honestidade é essa:** não é o
        custo que pede ``async``, é o contrato. Um provedor sem assinatura local
        (alternativa B do ADR-0024, guardada para o caso de o storage mudar)
        precisaria de IO aqui, e mudar a assinatura da porta depois obrigaria
        todo chamador a mudar junto.

        ``ttl`` é ``timedelta`` — o ``TimeSpan`` do C# — e não um ``int`` de
        segundos: unidade implícita em nome de parâmetro é como se erra por uma
        ordem de grandeza sem nenhum teste reclamar. O valor vem de ``Settings``
        e a regra do ADR-0024 é uma só: **maior que o playback do turn inteiro**.
        Uma URL que expira enquanto o aluno ainda ouve é bug de produto
        disfarçado de segurança.
        """
        ...

    async def delete_prefix(self, prefix: str) -> int:
        """Apaga tudo sob um prefixo e devolve quantos objetos foram removidos.

        É a operação que o delete de conta (CARD-017, LGPD) executa sobre
        ``student_prefix``. **Este card só a implementa e testa**; ligá-la ao
        fluxo de conta é lá.

        Devolve a contagem porque é o que torna o efeito verificável por teste e
        auditável em log — "apagou" sem número não distingue sucesso de
        prefixo errado, que é justamente o erro que ninguém quer descobrir
        tarde numa operação irreversível.
        """
        ...
