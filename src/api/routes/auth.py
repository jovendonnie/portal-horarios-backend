"""Rutas HTTP de autenticación: solo orquestan, sin lógica propia (RF-1, RF-4)."""

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import get_current_user, get_session_token
from src.schemas.auth import LoginRequest, LoginResponse
from src.services import session_service
from src.services.auth_service import AccountLockedError, InvalidCredentialsError, authenticate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest) -> LoginResponse:
    try:
        user = await authenticate(data.email, data.password)
    except AccountLockedError as exc:
        raise HTTPException(status.HTTP_423_LOCKED, str(exc)) from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    token = await session_service.create_session(user)
    return LoginResponse(session_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    token: str = Depends(get_session_token),
    _user: dict = Depends(get_current_user),
) -> None:
    await session_service.end_session(token)
