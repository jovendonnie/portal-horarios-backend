"""Rutas HTTP del catálogo de Estados: solo orquestan (RF-4, RF-5, RF-6)."""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import require_admin, require_read
from src.schemas.estado import EstadoCreate, EstadoDisableOut, EstadoOut, EstadoUpdate
from src.services import catalog_service

router = APIRouter(prefix="/statuses", tags=["statuses"])

COLLECTION_NAME = "estados"
ENTITY_LABEL = "Estado"


async def _count_assigned_employees(_entry_id: ObjectId) -> int:
    # Placeholder hasta Fase 6 (count_employees_by_status en models/employee.py).
    return 0


def _parse_entry_id(entry_id: str) -> ObjectId:
    try:
        return ObjectId(entry_id)
    except InvalidId as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe un {ENTITY_LABEL} con ese id") from exc


@router.post("", response_model=EstadoOut, status_code=status.HTTP_201_CREATED)
async def create_entry_route(data: EstadoCreate, actor: dict = Depends(require_admin)) -> EstadoOut:
    try:
        entry = await catalog_service.create_entry(COLLECTION_NAME, ENTITY_LABEL, data.name, actor)
    except catalog_service.InvalidNameError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except catalog_service.DuplicateEntryError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return EstadoOut(**entry)


@router.get("", response_model=list[EstadoOut])
async def list_entries_route(
    enabled: bool | None = None, _actor: dict = Depends(require_read)
) -> list[EstadoOut]:
    entries = await catalog_service.list_entries(COLLECTION_NAME, enabled)
    return [EstadoOut(**entry) for entry in entries]


@router.patch("/{entry_id}", response_model=EstadoOut)
async def rename_entry_route(
    entry_id: str, changes: EstadoUpdate, actor: dict = Depends(require_admin)
) -> EstadoOut:
    try:
        entry = await catalog_service.rename_entry(
            COLLECTION_NAME, ENTITY_LABEL, _parse_entry_id(entry_id), changes.name, actor
        )
    except catalog_service.EntryNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except catalog_service.InvalidNameError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except catalog_service.DuplicateEntryError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return EstadoOut(**entry)


@router.patch("/{entry_id}/disable", response_model=EstadoDisableOut)
async def disable_entry_route(entry_id: str, actor: dict = Depends(require_admin)) -> EstadoDisableOut:
    try:
        entry, affected = await catalog_service.set_enabled(
            COLLECTION_NAME, ENTITY_LABEL, _parse_entry_id(entry_id), False, actor, _count_assigned_employees
        )
    except catalog_service.EntryNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except catalog_service.LastEnabledEntryError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return EstadoDisableOut(status=EstadoOut(**entry), affected_employees=affected or 0)


@router.patch("/{entry_id}/enable", response_model=EstadoOut)
async def enable_entry_route(entry_id: str, actor: dict = Depends(require_admin)) -> EstadoOut:
    try:
        entry, _affected = await catalog_service.set_enabled(
            COLLECTION_NAME, ENTITY_LABEL, _parse_entry_id(entry_id), True, actor, _count_assigned_employees
        )
    except catalog_service.EntryNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return EstadoOut(**entry)
