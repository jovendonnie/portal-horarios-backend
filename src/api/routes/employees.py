"""Rutas HTTP de gestión de empleados: solo orquestan, sin lógica propia (RF-1, RF-2, RF-3, RF-7, RF-8)."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import require_admin, require_read
from src.schemas.employee import (
    EmployeeCreate,
    EmployeeOut,
    EmployeeStatusUpdate,
    EmployeeUpdate,
)
from src.services.employee_service import (
    DuplicateEmployeeError,
    EmployeeNotFoundError,
    InvalidAreaError,
    InvalidPositionError,
    InvalidStatusError,
    create_employee,
    get_employee,
    list_employees,
    update_employee,
    update_employee_status,
)

router = APIRouter(prefix="/employees", tags=["employees"])


def _parse_employee_id(employee_id: str) -> ObjectId:
    try:
        return ObjectId(employee_id)
    except InvalidId as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe un empleado con ese id") from exc


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def create_employee_route(data: EmployeeCreate, actor: dict = Depends(require_admin)) -> EmployeeOut:
    try:
        return await create_employee(actor, data)
    except InvalidPositionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except InvalidAreaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except InvalidStatusError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except DuplicateEmployeeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("", response_model=list[EmployeeOut])
async def list_employees_route(_actor: dict = Depends(require_read)) -> list[EmployeeOut]:
    return await list_employees()


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee_route(employee_id: str, _actor: dict = Depends(require_read)) -> EmployeeOut:
    try:
        return await get_employee(_parse_employee_id(employee_id))
    except EmployeeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.patch("/{employee_id}", response_model=EmployeeOut)
async def update_employee_route(
    employee_id: str, changes: EmployeeUpdate, actor: dict = Depends(require_admin)
) -> EmployeeOut:
    try:
        return await update_employee(actor, _parse_employee_id(employee_id), changes)
    except EmployeeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InvalidPositionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except InvalidAreaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except DuplicateEmployeeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.patch("/{employee_id}/status", response_model=EmployeeOut)
async def update_employee_status_route(
    employee_id: str, changes: EmployeeStatusUpdate, actor: dict = Depends(require_admin)
) -> EmployeeOut:
    try:
        return await update_employee_status(
            _parse_employee_id(employee_id), changes.status_id, actor, datetime.now(timezone.utc)
        )
    except EmployeeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InvalidStatusError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
