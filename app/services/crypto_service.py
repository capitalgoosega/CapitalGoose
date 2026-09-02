import os
from cryptography.fernet import Fernet, InvalidToken

_KEY_ENV_VAR = "DOCUMENT_ENCRYPTION_KEY"


def _get_fernet() -> Fernet:
    key = os.environ.get(_KEY_ENV_VAR)
    if not key:
        raise RuntimeError(
            f"{_KEY_ENV_VAR} is not set. Generate one with "
            "`python3 -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"` and add it as a Railway variable."
        )
    return Fernet(key.encode())


def encrypt_bytes(data: bytes) -> bytes:
    return _get_fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    try:
        return _get_fernet().decrypt(token)
    except InvalidToken:
        raise ValueError(
            "Failed to decrypt document — the encryption key may be wrong, "
            "or this document was stored before encryption was added."
        )
