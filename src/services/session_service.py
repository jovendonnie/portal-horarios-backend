"""Lógica de negocio del servicio de sesión (RF-4, RF-5, RF-6)."""

from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.config import settings
from src.core.security import generate_session_token
from src.models.session import delete_session, find_session_by_token, insert_session, touch_session
from src.models.user import find_user_by_id


class InvalidSessionError(Exception):
    """El token no corresponde a una sesión válida (inexistente, expirada o usuario inactivo)."""

    def __init__(self) -> None:
        super().__init__("Sesión inválida o expirada")


def _utcnow() -> datetime:
    """Hora actual en UTC, naive: coincide con el formato en que Motor devuelve los campos de Mongo."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def create_session(user: dict[str, Any]) -> str:
    """Crea una sesión para `user` y devuelve el token generado (RF-4, RF-5)."""
    now = _utcnow()
    token = generate_session_token()
    await insert_session(
        {
            "session_token": token,
            "user_id": user["_id"],
            "created_at": now,
            "last_activity_at": now,
            "expires_at": now + timedelta(minutes=settings.session_inactivity_minutes),
        }
    )
    return token


async def end_session(token: str) -> None:
    """Invalida la sesión asociada a `token` (RF-4)."""
    await delete_session(token)


async def validate_session(token: str) -> dict[str, Any]:
    """Valida `token`: existe, no expiró y su usuario sigue activo (RF-5, RF-6).

    Si es válida, extiende `expires_at` (expiración por inactividad) y
    devuelve el documento del usuario.
    """
    session = await find_session_by_token(token)
    if session is None:
        raise InvalidSessionError()

    now = _utcnow()
    if session["expires_at"] <= now:
        raise InvalidSessionError()

    user = await find_user_by_id(session["user_id"])
    if user is None or not user.get("is_active"):
        raise InvalidSessionError()

    new_expires_at = now + timedelta(minutes=settings.session_inactivity_minutes)
    await touch_session(token, new_expires_at)

    return user
