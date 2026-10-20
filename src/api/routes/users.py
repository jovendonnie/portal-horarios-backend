"""Ruta HTTP de alta de cuentas: solo orquesta, sin lógica propia (RF-3)."""

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import require_admin, require_read
from src.schemas.user import UserCreate, UserOut
from src.services.auth_service import EmailAlreadyExistsError, register_user
from src.services.user_service import list_users

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, actor: dict = Depends(require_admin)) -> dict:
    try:
        result = await register_user(actor, data)
    except EmailAlreadyExistsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return result.user


@router.get("", response_model=list[UserOut])
async def list_users_route(_actor: dict = Depends(require_read)) -> list[UserOut]:
    return await list_users()
