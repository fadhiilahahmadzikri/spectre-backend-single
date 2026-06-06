"""AES-256-GCM encryption for sensitive data."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from spectre.config import Settings


class AESEncryption:
    """AES-256-GCM authenticated encryption for sensitive data.

    Used for:
    - Face embedding vectors (bytes → encrypted bytes)
    - TOTP secrets
    """

    _NONCE_SIZE = 12  # 96 bits — recommended for AES-GCM

    def __init__(self, settings: Settings) -> None:
        key_b64 = settings.encryption_key
        try:
            self._key = base64.b64decode(key_b64)
        except Exception:
            # If not valid base64, use raw bytes (dev fallback)
            self._key = key_b64.encode("utf-8")[:32].ljust(32, b"\0")

        if len(self._key) != 32:
            raise ValueError(
                f"Encryption key must be exactly 32 bytes, got {len(self._key)}. "
                "Generate with: python -c \"import os,base64; print(base64.b64encode(os.urandom(32)).decode())\""
            )
        self._aesgcm = AESGCM(self._key)

    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt data with AES-256-GCM.

        Returns:
            nonce (12 bytes) + ciphertext + tag concatenated.
        """
        nonce = os.urandom(self._NONCE_SIZE)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, encrypted: bytes) -> bytes:
        """Decrypt AES-256-GCM encrypted data.

        Args:
            encrypted: nonce (12 bytes) + ciphertext + tag.

        Returns:
            Original plaintext bytes.
        """
        nonce = encrypted[: self._NONCE_SIZE]
        ciphertext = encrypted[self._NONCE_SIZE :]
        return self._aesgcm.decrypt(nonce, ciphertext, None)

    def encrypt_string(self, plaintext: str) -> str:
        """Encrypt a string, returning base64-encoded result."""
        encrypted = self.encrypt(plaintext.encode("utf-8"))
        return base64.b64encode(encrypted).decode("ascii")

    def decrypt_string(self, encrypted_b64: str) -> str:
        """Decrypt a base64-encoded encrypted string."""
        encrypted = base64.b64decode(encrypted_b64)
        plaintext = self.decrypt(encrypted)
        return plaintext.decode("utf-8")
