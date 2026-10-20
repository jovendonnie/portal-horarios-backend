"""Dependencias de autenticación/autorización para las rutas HTTP (RF-6)."""

from typing import Any

from fastapi import Depends, Header, HTTPException, status

from src.services.session_service import InvalidSessionError, validate_session


async def get_session_token(authorization: str | None = Header(default=None)) -> str:
    """Extrae el token de sesión del header `Authorization: Bearer <token>`."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado")
    return authorization.removeprefix("Bearer ").strip()


async def get_current_user(token: str = Depends(get_session_token)) -> dict[str, Any]:
    """Resuelve el usuario autenticado a partir del token de sesión, o responde 401."""
    try:
        return await validate_session(token)
    except InvalidSessionError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión inválida o expirada")


def canonical_role(role: str) -> str:
    """Normaliza el rol legacy `admin` al valor canónico `gestion_humana` (RF-9)."""
    return "gestion_humana" if role == "admin" else role


async def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Exige Gestión Humana (`admin` o `gestion_humana`), o responde 403 (RF-9)."""
    if canonical_role(user.get("role", "")) != "gestion_humana":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No autorizado")
    return user


async def require_read(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Exige un rol autenticado con acceso de lectura (admin, gestion_humana o lider), o responde 403."""
    if user.get("role") not in {"admin", "gestion_humana", "lider"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No autorizado")
    return user


async def require_schedule_write(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Exige Gestión Humana (`admin` o `gestion_humana`) para mutar Horarios, o responde 403 (RF-7)."""
    if canonical_role(user.get("role", "")) != "gestion_humana":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No autorizado")
    return user
