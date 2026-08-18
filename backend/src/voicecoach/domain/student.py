"""``Student`` — a conta do aluno (linguagem ubíqua da visão §A).

Deliberadamente magro nesta fase. O que **não** entra aqui, com o card que o
traz (a reconciliação de telas mostrou que nenhuma tela desta fatia usa nada
disso — excesso é erro tão caro quanto falta, visão §F):

- ``email`` / ``password_hash`` / código de convite → auth é Fase 3; aqui o
  Student vem de seed;
- ``cefr_level`` → Fase 6, e é **faixa** (``A2-B1``), não escalar: criar o campo
  agora seria criar o formato errado;
- ``daily_quota_minutes`` → CARD-015; a tela mostra saldo *calculado*, não
  configuração por aluno.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Student:
    """Quem fala com o professor.

    ``@dataclass`` gera ``__init__``, ``__repr__`` e ``__eq__`` a partir dos
    campos anotados — é o ``record`` do C#, com uma diferença sem paralelo: ao
    gerar ``__eq__`` ele **desabilita o hash** (``__hash__ = None``), porque
    objeto mutável com igualdade por valor não pode ter hash estável. Ou seja,
    estas entidades não servem como chave de dict nem elemento de set — o que
    nenhum caso deste card pede. Se um dia pedir, aí se define identidade por
    ``id``, e o gatilho é visível: um ``TypeError: unhashable type``.
    """

    id: UUID
    display_name: str
    created_at: datetime
