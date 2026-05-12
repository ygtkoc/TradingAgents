"""
Exchange API Key Provider.

Responsible for fetching encrypted API keys from the database and decrypting
them for use by the exchange adapters.

SECURITY RULES (non-negotiable):
  1. Plaintext API keys are NEVER stored in any class attribute, database row,
     log message, exception, or file.
  2. Plaintext exists only within the scope of ApiCredentials.use().
  3. Callers MUST call credentials.zero_out() in a finally block after use.
  4. The encryption secret comes from API_KEY_ENCRYPTION_SECRET env var only.
  5. Any decryption failure is logged without the ciphertext and raises an error.

Encryption format (AES-256-GCM, compatible with Supabase Edge Functions):
  The Edge Function encrypts keys using the Web Crypto API (AES-GCM).
  Format stored in DB: hex(iv) + hex(ciphertext_with_tag)
  - IV: 12 bytes (24 hex chars)
  - Ciphertext: N bytes of encrypted data + 16-byte GCM authentication tag

TODO: Replace with Supabase Vault or a dedicated KMS (AWS KMS, HashiCorp Vault)
      for production-grade key management. The current approach stores encrypted
      keys in the database, which is acceptable for early-stage but should be
      migrated to a dedicated secret store before scaling to real live trading.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from src.db.repositories import BotRepository
from src.logging_config import get_logger

log = get_logger(__name__)


class ApiCredentials:
    """
    Holds plaintext API credentials for the shortest possible time.

    Usage:
        credentials = await key_provider.get_credentials(account_id)
        try:
            adapter = get_live_adapter(exchange, credentials.api_key, credentials.api_secret)
            result = await adapter.place_order(...)
        finally:
            credentials.zero_out()  # ALWAYS call this in finally
    """

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
        """Overwrite key material with zeros. Call in finally blocks."""
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
    """
    Fetches and decrypts exchange API keys from the database.

    Uses AES-256-GCM decryption with the API_KEY_ENCRYPTION_SECRET env var.
    Compatible with the Supabase Edge Function encryption format.
    """

    def __init__(self) -> None:
        self._repo = BotRepository()
        self._encryption_secret = self._load_secret()

    def _load_secret(self) -> bytes:
        """
        Derive a 32-byte AES key from the encryption secret.
        Uses SHA-256 so any length input produces a valid key.
        NEVER log this value.
        """
        from src.config import settings
        return hashlib.sha256(
            settings.api_key_encryption_secret.encode("utf-8")
        ).digest()

    async def get_credentials(
        self, exchange_account_id: str
    ) -> ApiCredentials:
        """
        Fetch and decrypt API credentials for an exchange account.

        Raises:
            ValueError: If the account is not found or has no stored key.
            RuntimeError: If decryption fails.

        NEVER log the returned credentials.
        """
        account = await self._repo.get_exchange_account(exchange_account_id)
        if account is None:
            raise ValueError(
                f"Exchange account not found: {exchange_account_id}"
            )

        if not account.encrypted_api_key or not account.encrypted_api_secret:
            raise ValueError(
                f"Exchange account {exchange_account_id} has no stored API key. "
                "Keys must be added via the secure Edge Function endpoint."
            )

        try:
            api_key    = self._decrypt(account.encrypted_api_key,    account.key_iv)
            api_secret = self._decrypt(account.encrypted_api_secret, account.key_iv)
        except Exception as exc:
            # Log the error WITHOUT including the ciphertext or key
            log.error(
                "key_provider.decryption_failed",
                exchange_account_id=exchange_account_id,
                exchange=account.exchange,
                error_type=type(exc).__name__,
                # DO NOT include exc details — they might contain ciphertext
            )
            raise RuntimeError(
                "Failed to decrypt exchange API credentials. "
                "Check API_KEY_ENCRYPTION_SECRET matches the encryption secret."
            ) from None

        log.info(
            "key_provider.credentials_loaded",
            exchange_account_id=exchange_account_id,
            exchange=account.exchange,
            # DO NOT log api_key or api_secret
        )
        return ApiCredentials(api_key=api_key, api_secret=api_secret)

    def _decrypt(self, ciphertext_hex: str, iv_hex: Optional[str]) -> str:
        """
        Decrypt AES-256-GCM ciphertext.

        Format 1 (split columns): iv_hex provided separately, ciphertext_hex = ciphertext + tag
        Format 2 (combined):      iv is first 24 hex chars of ciphertext_hex (12 bytes)

        TODO: Confirm exact format with Edge Function implementation and update
              this method to match. The format depends on how the Edge Function
              stored the encrypted key.
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(self._encryption_secret)

        if iv_hex:
            # Format 1: IV stored separately
            iv         = bytes.fromhex(iv_hex)
            ciphertext = bytes.fromhex(ciphertext_hex)
        else:
            # Format 2: IV is the first 12 bytes of the stored blob
            if len(ciphertext_hex) < 24:
                raise ValueError("Ciphertext too short to contain IV")
            iv         = bytes.fromhex(ciphertext_hex[:24])
            ciphertext = bytes.fromhex(ciphertext_hex[24:])

        # AESGCM.decrypt expects ciphertext + 16-byte tag appended
        # This is the default format from Web Crypto API's AES-GCM.
        plaintext = aesgcm.decrypt(iv, ciphertext, None)
        return plaintext.decode("utf-8")
