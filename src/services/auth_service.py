"""Lógica de negocio de autenticación y alta de cuentas (RF-1, RF-2, RF-3, RF-7)."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from src.core.config import settings
from src.core.security import hash_password, verify_password
from src.models.user import find_user_by_email, insert_user, update_user
from src.schemas.user import UserCreate


class InvalidCredentialsError(Exception):
    """Correo o contraseña incorrectos: mensaje único, no distingue la causa (RF-1)."""

    def __init__(self) -> None:
        super().__init__("Correo o contraseña incorrectos")


class AccountLockedError(Exception):
    """La cuenta está bloqueada temporalmente por intentos fallidos (RF-2)."""

    def __init__(self, locked_until: datetime) -> None:
        self.locked_until = locked_until
        super().__init__("La cuenta está bloqueada temporalmente")


class EmailAlreadyExistsError(Exception):
    """Ya existe una cuenta registrada con ese correo (RF-3)."""

    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"Ya existe una cuenta con el correo {email}")


@dataclass(frozen=True)
class RegisteredUser:
    """Resultado de dar de alta una cuenta: el documento creado y su co git diff specs/001-login/tasks.mdntraseña temporal."""

    user: dict[str, Any]
    temporary_password: str


def _utcnow() -> datetime:
    """Hora actual en UTC, naive: coincide con el formato en que Motor devuelve los campos de Mongo."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _generate_temporary_password() -> str:
    """Contraseña temporal aleatoria; el admin la comunica fuera de banda (decisión #6 de plan.md)."""
    return secrets.token_urlsafe(9)


async def authenticate(email: str, password: str) -> dict[str, Any]:
    """Autentica con la racha de intentos fallidos de plan.md sección 4 (RF-1, RF-2, RF-7)."""
    now = _utcnow()
    user = await find_user_by_email(email)

    if user is None:
        raise InvalidCredentialsError()

    locked_until = user.get("locked_until")
    if locked_until is not None and now < locked_until:
        raise AccountLockedError(locked_until)

    if verify_password(password, user["password_hash"]):
        await update_user(email, {"failed_login_attempts": 0, "locked_until": None})
        user["failed_login_attempts"] = 0
        user["locked_until"] = None
        return user

    failed_attempts = user.get("failed_login_attempts", 0) + 1
    updates: dict[str, Any] = {"failed_login_attempts": failed_attempts}

    if failed_attempts >= settings.max_failed_attempts:
        updates["locked_until"] = now + timedelta(minutes=settings.lockout_minutes)
        updates["failed_login_attempts"] = 0

    await update_user(email, updates)
    raise InvalidCredentialsError()


async def register_user(actor: dict[str, Any], data: UserCreate) -> RegisteredUser:
    """Da de alta una cuenta con contraseña temporal generada por el sistema (RF-3, RF-7)."""
    temporary_password = _generate_temporary_password()
    document = {
        "full_name": data.full_name,
        "email": data.email,
        "password_hash": hash_password(temporary_password),
        "role": data.role,
        "is_active": True,
        "created_by": actor.get("_id"),
    }

    try:
        await insert_user(document)
    except DuplicateKeyError as exc:
        raise EmailAlreadyExistsError(data.email) from exc

    created = await find_user_by_email(data.email)
    assert created is not None
    return RegisteredUser(user=created, temporary_password=temporary_password)
