"""Lógica de negocio de gestión de cuentas de usuario (RF-3, RNF-1).

Centraliza `deactivate_user` para que `cli.py` y la futura ruta HTTP de
usuarios auditen desde un único lugar, en vez de tocar los modelos
directamente cada uno por su lado (plan.md sección 5, decisión 8).
"""

from datetime import datetime, timezone
from typing import Any

from src.api.deps import canonical_role
from src.core.database import start_transaction
from src.core.security import generate_temporary_password, hash_password
from src.models.session import delete_sessions_by_user
from src.models.user import find_user_by_email, list_users as list_user_documents, update_user
from src.schemas.user import UserOut
from src.services import history_service


class UserNotFoundError(Exception):
    """No existe una cuenta con el correo indicado (RF-3)."""

    def __init__(self) -> None:
        super().__init__("No existe una cuenta con ese correo")


def _utcnow() -> datetime:
    """Hora actual en UTC, naive: coincide con el formato en que Motor devuelve los campos de Mongo."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def deactivate_user(actor: dict[str, Any], email: str) -> dict[str, Any]:
    """Desactiva una cuenta e invalida sus sesiones activas (RF-3, RNF-1).

    La escritura de `is_active=False`, la invalidación de sesiones y la
    entrada de auditoría `deactivate` viajan en la misma transacción: si el
    registro en `history_entries` falla, ninguna de las dos se aplica.
    """
    user = await find_user_by_email(email)
    if user is None:
        raise UserNotFoundError()

    ahora = _utcnow()
    changes = [{"field": "is_active", "old_value": user["is_active"], "new_value": False}]

    async with start_transaction() as session:
        try:
            await update_user(email, {"is_active": False}, session=session)
            sessions_invalidated = await delete_sessions_by_user(user["_id"], session=session)
            await history_service.record_change(
                session, "user", user["_id"], "deactivate", changes, actor, ahora
            )
            await session.commit_transaction()
        except Exception:
            await session.abort_transaction()
            raise

    return {"email": email, "is_active": False, "sessions_invalidated": sessions_invalidated}


async def reset_password(actor: dict[str, Any], email: str) -> dict[str, Any]:
    """Resetea la contraseña de una cuenta e invalida sus sesiones activas (RF-8).

    Genera una contraseña temporal nueva, igual que el alta de cuentas
    (RF-3). La escritura del nuevo hash, la invalidación de sesiones y la
    entrada de auditoría `reset_password` viajan en la misma transacción. El
    historial no guarda el hash ni la contraseña temporal, solo que el campo
    cambió (RF-7).
    """
    user = await find_user_by_email(email)
    if user is None:
        raise UserNotFoundError()

    temporary_password = generate_temporary_password()
    ahora = _utcnow()
    changes = [{"field": "password_hash", "old_value": None, "new_value": None}]

    async with start_transaction() as session:
        try:
            await update_user(
                email, {"password_hash": hash_password(temporary_password)}, session=session
            )
            sessions_invalidated = await delete_sessions_by_user(user["_id"], session=session)
            await history_service.record_change(
                session, "user", user["_id"], "reset_password", changes, actor, ahora
            )
            await session.commit_transaction()
        except Exception:
            await session.abort_transaction()
            raise

    return {
        "email": email,
        "temporary_password": temporary_password,
        "sessions_invalidated": sessions_invalidated,
    }


async def list_users() -> list[UserOut]:
    """Lista todas las cuentas con el rol ya canonicalizado (RF-9, RF-10)."""
    documents = await list_user_documents()
    return [
        UserOut(**{**document, "role": canonical_role(document["role"])})
        for document in documents
    ]
