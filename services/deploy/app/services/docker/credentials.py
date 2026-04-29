"""
Credential encryption — AES-256 via Fernet.
SSH keys, deploy tokens, and environment secrets are always encrypted before
being stored in the database.
"""

import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from app.core.config import settings


def _get_fernet() -> Fernet:
    """Derive a Fernet key from SECRET_KEY using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"jarviis-deploy-v1",  # static salt is OK here — key material comes from SECRET_KEY
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(settings.SECRET_KEY.encode()))
    return Fernet(key)


_fernet = _get_fernet()


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns base64-encoded ciphertext."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a previously encrypted string."""
    return _fernet.decrypt(ciphertext.encode()).decode()


def encrypt_dict(data: dict) -> str:
    """Encrypt a dict as JSON."""
    import json
    return encrypt(json.dumps(data))


def decrypt_dict(ciphertext: str) -> dict:
    """Decrypt a previously encrypted dict."""
    import json
    return json.loads(decrypt(ciphertext))
