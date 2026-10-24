"""pgcrypto-backed encryption helpers for sensitive Finding columns.

Rather than encrypting/decrypting in Python (which would mean the key
passes through application memory on every read and doesn't benefit from
Postgres's own crypto functions), encryption and decryption are performed
inside SQL via pgcrypto's pgp_sym_encrypt/pgp_sym_decrypt, using the shared
symmetric key from settings.PGCRYPTO_KEY. These helpers wrap that so
services never write raw SQL themselves.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings


def encrypt_text(db: Session, plaintext: str | None) -> bytes | None:
    """Encrypt a plaintext string into bytes suitable for a LargeBinary
    column, using pgcrypto's pgp_sym_encrypt. Returns None for None input
    (nullable sensitive fields stay NULL rather than encrypting an empty
    marker)."""
    if plaintext is None:
        return None
    result = db.execute(
        text("SELECT pgp_sym_encrypt(:plaintext, :key)"),
        {"plaintext": plaintext, "key": settings.PGCRYPTO_KEY},
    ).scalar_one()
    return result


def decrypt_text(db: Session, ciphertext: bytes | None) -> str | None:
    """Decrypt bytes previously produced by encrypt_text back into a
    plaintext string. Returns None for None input."""
    if ciphertext is None:
        return None
    result = db.execute(
        text("SELECT pgp_sym_decrypt(:ciphertext, :key)"),
        {"ciphertext": ciphertext, "key": settings.PGCRYPTO_KEY},
    ).scalar_one()
    return result