"""Rutas HTTP de gestión de cuentas: solo orquestan, sin lógica propia (RF-3)."""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import canonical_role, require_admin, require_read
from src.schemas.user import UserCreate, UserOut, UserRoleUpdate
from src.services.auth_service import EmailAlreadyExistsError, register_user
from src.services.user_service import (
    SelfTargetError,
    UserIdNotFoundError,
    change_role,
    deactivate_user_by_id,
    list_users,
)

router = APIRouter(prefix="/users", tags=["users"])


def _to_user_out(user: dict) -> UserOut:
    """Canonicaliza el rol legacy `admin` igual que hace `list_users` (RF-9)."""
    return UserOut(**{**user, "role": canonical_role(user["role"])})


def _parse_user_id(user_id: str) -> ObjectId:
    try:
        return ObjectId(user_id)
    except InvalidId as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe una cuenta con ese id") from exc


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


@router.patch("/{user_id}", response_model=UserOut)
async def change_role_route(
    user_id: str, changes: UserRoleUpdate, actor: dict = Depends(require_admin)
) -> UserOut:
    try:
        user = await change_role(actor, _parse_user_id(user_id), changes.role)
    except UserIdNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except SelfTargetError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _to_user_out(user)


@router.patch("/{user_id}/deactivate", response_model=UserOut)
async def deactivate_user_route(user_id: str, actor: dict = Depends(require_admin)) -> UserOut:
    try:
        user = await deactivate_user_by_id(actor, _parse_user_id(user_id))
    except UserIdNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except SelfTargetError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _to_user_out(user)
