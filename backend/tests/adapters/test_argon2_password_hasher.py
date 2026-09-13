"""``Argon2PasswordHasher`` — o hash de senha de verdade (ADR-0007, CARD-049)."""

from __future__ import annotations

from voicecoach.adapters.auth.argon2_password_hasher import Argon2PasswordHasher


async def test_hash_e_verify_fazem_roundtrip() -> None:
    hasher = Argon2PasswordHasher()

    hash_ = await hasher.hash("senha-correta-123")

    assert await hasher.verify("senha-correta-123", hash_) is True


async def test_senha_errada_nao_confere() -> None:
    hasher = Argon2PasswordHasher()
    hash_ = await hasher.hash("senha-correta-123")

    assert await hasher.verify("senha-errada", hash_) is False


async def test_hash_malformado_nao_propaga_e_devolve_false() -> None:
    """Cobre o caminho que o `_HASH_DE_PREENCHIMENTO` do login exercitaria se
    algum dia um hash de outro formato chegasse aqui — a porta promete nunca
    deixar `InvalidHashError` escapar.
    """
    hasher = Argon2PasswordHasher()

    assert await hasher.verify("qualquer", "isto-nao-e-um-hash-argon2") is False


async def test_dois_hashes_da_mesma_senha_sao_diferentes() -> None:
    """O salt é aleatório por chamada — duas senhas iguais nunca produzem o
    mesmo hash, o que é a defesa contra tabela arco-íris.
    """
    hasher = Argon2PasswordHasher()

    primeiro = await hasher.hash("mesma-senha")
    segundo = await hasher.hash("mesma-senha")

    assert primeiro != segundo
    assert await hasher.verify("mesma-senha", primeiro) is True
    assert await hasher.verify("mesma-senha", segundo) is True
