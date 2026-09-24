"""Rutas HTTP del catálogo de Áreas: solo orquestan (RF-1, RF-2, RF-3)."""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import require_admin
from src.schemas.area import AreaCreate, AreaDisableOut, AreaOut, AreaUpdate
from src.services import catalog_service

router = APIRouter(prefix="/areas", tags=["areas"])

COLLECTION_NAME = "areas"
ENTITY_LABEL = "Área"


async def _count_assigned_employees(_entry_id: ObjectId) -> int:
    # Placeholder hasta Fase 6 (count_employees_by_area en models/employee.py).
    return 0


def _parse_entry_id(entry_id: str) -> ObjectId:
    try:
        return ObjectId(entry_id)
    except InvalidId as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe un {ENTITY_LABEL} con ese id") from exc


@router.post("", response_model=AreaOut, status_code=status.HTTP_201_CREATED)
async def create_entry_route(data: AreaCreate, actor: dict = Depends(require_admin)) -> AreaOut:
    try:
        entry = await catalog_service.create_entry(COLLECTION_NAME, ENTITY_LABEL, data.name, actor)
    except catalog_service.InvalidNameError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except catalog_service.DuplicateEntryError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return AreaOut(**entry)


@router.get("", response_model=list[AreaOut])
async def list_entries_route(
    enabled: bool | None = None, _actor: dict = Depends(require_admin)
) -> list[AreaOut]:
    entries = await catalog_service.list_entries(COLLECTION_NAME, enabled)
    return [AreaOut(**entry) for entry in entries]


@router.patch("/{entry_id}", response_model=AreaOut)
async def rename_entry_route(
    entry_id: str, changes: AreaUpdate, actor: dict = Depends(require_admin)
) -> AreaOut:
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
    return AreaOut(**entry)


@router.patch("/{entry_id}/disable", response_model=AreaDisableOut)
async def disable_entry_route(entry_id: str, actor: dict = Depends(require_admin)) -> AreaDisableOut:
    try:
        entry, affected = await catalog_service.set_enabled(
            COLLECTION_NAME, ENTITY_LABEL, _parse_entry_id(entry_id), False, actor, _count_assigned_employees
        )
    except catalog_service.EntryNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except catalog_service.LastEnabledEntryError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return AreaDisableOut(area=AreaOut(**entry), affected_employees=affected or 0)


@router.patch("/{entry_id}/enable", response_model=AreaOut)
async def enable_entry_route(entry_id: str, actor: dict = Depends(require_admin)) -> AreaOut:
    try:
        entry, _affected = await catalog_service.set_enabled(
            COLLECTION_NAME, ENTITY_LABEL, _parse_entry_id(entry_id), True, actor, _count_assigned_employees
        )
    except catalog_service.EntryNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return AreaOut(**entry)
