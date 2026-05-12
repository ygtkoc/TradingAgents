// AES-256-GCM encryption for exchange API key payloads.
//
// Design contract:
//   - Plaintext lives only in Edge Function memory during processing.
//   - Output is a Uint8Array: [12-byte random IV | AES-GCM ciphertext+tag].
//   - The service stores only the opaque encrypted blob (bytea column).
//   - The encryption key is derived from API_KEY_ENCRYPTION_SECRET via SHA-256.
//
// TODO(production): Migrate to Supabase Vault (pgsodium.crypto_aead_det_encrypt)
//   so the encryption key never lives in an environment variable. The Vault key
//   will be stored in pgsodium.key, referenced via vault_key_id column.
//   The Edge Function would call a SECURITY DEFINER SQL function for
//   encrypt/decrypt instead of doing it in-process.

import { API_KEY_ENCRYPTION_SECRET } from "./config.ts"

let _cachedKey: CryptoKey | null = null

async function getDerivedKey(): Promise<CryptoKey> {
  if (_cachedKey) return _cachedKey

  const raw = new TextEncoder().encode(API_KEY_ENCRYPTION_SECRET)
  // Derive a fixed-length 256-bit key from the secret via SHA-256.
  // In production (Vault), this step is replaced by a KMS-managed key.
  const digest = await crypto.subtle.digest("SHA-256", raw)

  _cachedKey = await crypto.subtle.importKey(
    "raw",
    digest,
    { name: "AES-GCM" },
    false, // not extractable
    ["encrypt", "decrypt"],
  )
  return _cachedKey
}

// Encrypts a plaintext string.
// Returns Uint8Array: 12-byte IV followed by ciphertext+GCM-tag.
export async function encrypt(plaintext: string): Promise<Uint8Array> {
  const key = await getDerivedKey()
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const encoded = new TextEncoder().encode(plaintext)

  const cipherBuffer = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, tagLength: 128 },
    key,
    encoded,
  )

  const result = new Uint8Array(12 + cipherBuffer.byteLength)
  result.set(iv, 0)
  result.set(new Uint8Array(cipherBuffer), 12)
  return result
}

// Decrypts a payload produced by encrypt().
// Throws if the ciphertext has been tampered with (GCM authentication failure).
export async function decrypt(payload: Uint8Array): Promise<string> {
  if (payload.byteLength < 13) {
    throw new Error("Invalid encrypted payload: too short")
  }
  const key = await getDerivedKey()
  const iv = payload.slice(0, 12)
  const ciphertext = payload.slice(12)

  const plainBuffer = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv, tagLength: 128 },
    key,
    ciphertext,
  )
  return new TextDecoder().decode(plainBuffer)
}

// Converts a Uint8Array to a PostgreSQL bytea-compatible base64 string.
// PostgREST decodes base64 strings into bytea columns automatically.
export function toStorageBase64(bytes: Uint8Array): string {
  let binary = ""
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

// Converts a base64 string (as returned from PostgREST for a bytea column)
// back to a Uint8Array for decryption.
export function fromStorageBase64(b64: string): Uint8Array {
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}
