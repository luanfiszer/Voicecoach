"""Identificadores fixos de desenvolvimento.

Enquanto não há autenticação (Fase 3), a fatia vertical usa **um** Student
criado pela migration ``d790e74af8f6``. Este módulo é a forma de o código
referir-se a ele sem espalhar o literal.

A migration guarda o mesmo UUID escrito à mão de propósito — migration é
registro histórico e não deve importar código que muda. Quem garante que os
dois não divergem é um teste.
"""

from __future__ import annotations

from uuid import UUID

DEV_STUDENT_ID = UUID("00000000-0000-0000-0000-000000000001")
DEV_STUDENT_DISPLAY_NAME = "Aluno de desenvolvimento"
