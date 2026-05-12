"""
Exchange API Key Provider — identical to Execution Engine version.

Fetches encrypted API keys from DB and decrypts them (AES-256-GCM).
Plaintext exists only within ApiCredentials.use() scope.
Callers MUST call credentials.zero_out() in a finally block.

NEVER log decrypted keys. NEVER store in class attributes beyond lifecycle.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from src.logging_config import get_logger

log = get_logger(__name__)


class ApiCredentials:
    def __init__(self, api_key: str, api_secret: str) -> None:
        self._key    = api_key
        self._secret = api_secret
        self._zeroed = False

    @property
    def api_key(self) -> str:
        if self._zeroed:
            raise RuntimeError("ApiCredentials have been zeroed out.")
        return self._key

    @property
    def api_secret(self) -> str:
        if self._zeroed:
            raise RuntimeError("ApiCredentials have been zeroed out.")
        return self._secret

    def zero_out(self) -> None:
        self._key    = "\x00" * len(self._key)
        self._secret = "\x00" * len(self._secret)
        self._zeroed = True

    def __repr__(self) -> str:
        return "ApiCredentials(REDACTED)"

    def __str__(self) -> str:
        return "ApiCredentials(REDACTED)"

    def __del__(self) -> None:
        if not self._zeroed:
            self.zero_out()


class KeyProvider:
    """Fetches and decrypts exchange API keys using AES-256-GCM."""

    def __init__(self) -> None:
        self._encryption_secret = self._load_secret()

    def _load_secret(self) -> bytes:
        from src.config import settings
        return hashlib.sha256(
            settings.api_key_encryption_secret.encode("utf-8")
        ).digest()

    async def get_credentials(self, exchange_account_id: str) -> ApiCredentials:
        """
        Fetch and decrypt API credentials for an exchange account.

        Raises:
            ValueError:   Account not found or has no stored key.
            RuntimeError: Decryption failed.
        """
        from src.db.repositories import ContextRepository
        repo    = ContextRepository()
        account = await repo.get_exchange_account(exchange_account_id)

        if account is None:
            raise ValueError(f"Exchange account not found: {exchange_account_id}")

        if not account.encrypted_api_key or not account.encrypted_api_secret:
            raise ValueError(
                f"Exchange account {exchange_account_id} has no stored API key."
            )

        try:
            api_key    = self._decrypt(account.encrypted_api_key,    account.key_iv)
            api_secret = self._decrypt(account.encrypted_api_secret, account.key_iv)
        except Exception as exc:
            log.error(
                "key_provider.decryption_failed",
                exchange_account_id=exchange_account_id,
                exchange=account.exchange,
                error_type=type(exc).__name__,
                # DO NOT log ciphertext or exc details
            )
            raise RuntimeError(
                "Failed to decrypt exchange API credentials."
            ) from None

        log.info(
            "key_provider.credentials_loaded",
            exchange_account_id=exchange_account_id,
            exchange=account.exchange,
        )
        return ApiCredentials(api_key=api_key, api_secret=api_secret)

    def _decrypt(self, ciphertext_hex: str, iv_hex: Optional[str]) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(self._encryption_secret)

        if iv_hex:
            iv         = bytes.fromhex(iv_hex)
            ciphertext = bytes.fromhex(ciphertext_hex)
        else:
            if len(ciphertext_hex) < 24:
                raise ValueError("Ciphertext too short to contain IV")
            iv         = bytes.fromhex(ciphertext_hex[:24])
            ciphertext = bytes.fromhex(ciphertext_hex[24:])

        plaintext = aesgcm.decrypt(iv, ciphertext, None)
        return plaintext.decode("utf-8")
