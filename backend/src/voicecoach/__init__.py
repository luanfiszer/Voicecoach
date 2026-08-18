"""Voicecoach — professor de inglês por conversa de áudio.

Pacote raiz do backend. As camadas estão em subpacotes e a regra de
dependência entre elas está declarada no docstring de cada um, no
``backend/README.md`` e — de forma executável — nos contratos
``[tool.importlinter]`` do ``pyproject.toml``.

Regra em uma linha: **tudo aponta para dentro; ``domain`` não conhece ninguém.**
"""
