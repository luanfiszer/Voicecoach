"""Corte de `spoken_reply` em trechos prontos para o TTS, enquanto ela cresce.

Este módulo tem **dois modos de falha opostos**, e o desenho existe para evitar
os dois:

- **cortar cedo demais** — ``[.!?]`` seguido de espaço acerta ``"Mr. Smith"``,
  ``"i.e."`` e as iniciais de um nome. Uma sentença partida no meio vira dois
  áudios com prosódia errada;
- **cortar tarde demais** — o fim do buffer, com ``partial_mode="trailing-
  strings"``, é **sempre** texto possivelmente incompleto. Por isso só sai o que
  tem delimitador **e mais texto depois dele**: é o texto seguinte que prova que
  a sentença anterior fechou.

``"3.5 hours"`` não precisa de tratamento: o ponto ali é seguido de dígito, e a
fronteira exige espaço.
"""

from __future__ import annotations

import re

# Depois da primeira, os trechos são agrupados até este tamanho. O TTS tem custo
# LINEAR (RTF ~0,10 constante — medição §4.2), então trecho maior não sai mais
# caro por caractere; o que ele economiza é evento, arquivo e round-trip.
MAX_CHUNK_CHARS = 200

# A primeira sentença é a que define o tempo até o primeiro áudio, então ela sai
# sozinha e o quanto antes. Só não sai se for curta demais para valer um arquivo
# de áudio próprio ("Hi." sozinho): aí espera a seguinte e vai junto.
MIN_FIRST_CHARS = 12

# Um ponto depois destas NÃO fecha sentença. Lista curta e em minúsculas; nome
# de pessoa com inicial ("J. Smith") é coberto pela regra de letra única.
_ABREVIACOES = frozenset(
    {"mr", "mrs", "ms", "dr", "prof", "st", "sr", "jr", "vs", "etc", "i.e", "e.g"}
)

# Delimitador, aspas/parênteses de fechamento opcionais, e ESPAÇO. O espaço é
# parte do casamento de propósito: sem ele, "3.5" viraria fronteira.
_FRONTEIRA = re.compile(r"[.!?]['\")\]]*\s+")

# A "palavra" imediatamente antes do ponto, pontos internos incluídos — é o que
# distingue "i.e." de "there.".
_PALAVRA_ANTERIOR = re.compile(r"[A-Za-z.]+$")


def _e_fronteira(texto: str, pos: int) -> bool:
    """O caractere em `pos` fecha mesmo uma sentença?

    ``!`` e ``?`` não abreviam nada, então só o ponto precisa de exame.
    """
    if texto[pos] != ".":
        return True
    achado = _PALAVRA_ANTERIOR.search(texto[:pos])
    if achado is None:
        return True
    palavra = achado.group().lower()
    # Letra única é inicial de nome ("J. Smith"), nunca fim de frase.
    return len(palavra) != 1 and palavra not in _ABREVIACOES


def _fronteiras_fechadas(texto: str) -> list[int]:
    """Índices onde uma sentença termina, contando só as PROVADAMENTE fechadas.

    "Provadamente" é literal: se o casamento vai até o fim do texto, não existe
    texto depois do delimitador, e o buffer pode simplesmente ter parado ali no
    meio da geração. Esse não conta.
    """
    fins: list[int] = []
    for m in _FRONTEIRA.finditer(texto):
        if m.end() >= len(texto):
            continue
        if _e_fronteira(texto, m.start()):
            fins.append(m.end())
    return fins


class SentenceCutter:
    """Recebe a fala inteira a cada atualização e devolve só o que é novo.

    Guarda um único inteiro — quanto do texto já foi entregue. É estado **de uma
    geração**, criado e descartado dentro de uma chamada; o adapter continua sem
    estado entre chamadas.
    """

    def __init__(self) -> None:
        self._entregue = 0
        self._primeira_saiu = False

    def feed(self, fala: str) -> list[str]:
        """Trechos prontos a partir da fala acumulada até agora."""
        trechos: list[str] = []
        for fim in _fronteiras_fechadas(fala):
            if fim <= self._entregue:
                continue
            candidato = fala[self._entregue : fim].strip()
            if not candidato:
                continue
            if not self._primeira_saiu:
                if len(candidato) < MIN_FIRST_CHARS:
                    continue  # curta demais: espera a próxima fronteira
                self._primeira_saiu = True
            elif len(candidato) < MAX_CHUNK_CHARS:
                continue  # agrupa: a próxima fronteira decide
            trechos.append(candidato)
            self._entregue = fim
        return trechos

    def flush(self, fala: str) -> list[str]:
        """O resto, quando a geração terminou e não há mais texto por vir.

        Só aqui a última sentença pode sair: até a geração fechar, ela é
        indistinguível de uma sentença que ainda vai crescer.
        """
        resto = fala[self._entregue :].strip()
        self._entregue = len(fala)
        if not resto:
            return []
        self._primeira_saiu = True
        return [resto]
