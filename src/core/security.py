import hashlib
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 260_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    hash_bytes = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${hash_bytes.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    _algorithm, iterations_str, salt_hex, hash_hex = password_hash.split("$")
    salt = bytes.fromhex(salt_hex)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations_str))
    return secrets.compare_digest(candidate.hex(), hash_hex)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)
