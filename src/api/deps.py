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


async def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Exige que el usuario autenticado tenga rol `admin`, o responde 403 (RF-3)."""
    if user.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No autorizado")
    return user
