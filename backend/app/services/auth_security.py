"""Security primitives for account/session flows; not an HTTP authentication system."""
from __future__ import annotations
import hashlib, hmac, re, secrets
from dataclasses import dataclass

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

@dataclass(frozen=True)
class PasswordHash:
    encoded: str

def normalize_email(email: str) -> str:
    if not isinstance(email, str): raise ValueError("invalid_email")
    normalized = email.strip().lower()
    if len(normalized) > 320 or not _EMAIL_RE.fullmatch(normalized): raise ValueError("invalid_email")
    return normalized

def hash_password(password: str) -> PasswordHash:
    if not isinstance(password, str) or not 12 <= len(password) <= 1024: raise ValueError("password_length_out_of_range")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN, maxmem=64 * 1024 * 1024)
    return PasswordHash("scrypt$" + str(_SCRYPT_N) + "$" + str(_SCRYPT_R) + "$" + str(_SCRYPT_P) + "$" + salt.hex() + "$" + digest.hex())

def verify_password(password: str, encoded: str) -> bool:
    if not isinstance(password, str) or not isinstance(encoded, str): return False
    try:
        algorithm, n_text, r_text, p_text, salt_hex, digest_hex = encoded.split("$")
        n, r, p = int(n_text), int(r_text), int(p_text)
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
        if algorithm != "scrypt" or n != _SCRYPT_N or r != _SCRYPT_R or p != _SCRYPT_P: return False
        if len(salt) != 16 or len(expected) != _SCRYPT_DKLEN: return False
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected), maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, MemoryError): return False

def new_opaque_token() -> str:
    """Create a high-entropy bearer token; persist only token_digest(token)."""
    return secrets.token_urlsafe(32)

def token_digest(token: str) -> str:
    if not isinstance(token, str) or not 32 <= len(token) <= 512: raise ValueError("invalid_token")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def constant_time_token_match(candidate: str, expected_digest: str) -> bool:
    try: return hmac.compare_digest(token_digest(candidate), expected_digest)
    except ValueError: return False
