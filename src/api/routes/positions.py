"""Rutas HTTP del catálogo de Cargos: solo orquestan (spec 009, RF-1).

La colección se llama `cargos` (dominio en español, igual que `areas` y
`estados`) pero el path es `/positions`, que es el que ya consume el portal.
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import require_admin, require_read
from src.schemas.position import (
    PositionCreate,
    PositionDisableOut,
    PositionOut,
    PositionUpdate,
)
from src.services import catalog_service

router = APIRouter(prefix="/positions", tags=["positions"])

COLLECTION_NAME = "cargos"
ENTITY_LABEL = "Cargo"


async def _count_assigned_employees(_entry_id: ObjectId) -> int:
    # El Cargo del empleado es todavía la lista fija de la spec 002, no una
    # referencia a este catálogo: no hay empleados que contar. El conteo no se
    # expone en la respuesta (PositionDisableOut no lo lleva).
    return 0


def _parse_entry_id(entry_id: str) -> ObjectId:
    try:
        return ObjectId(entry_id)
    except InvalidId as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe un {ENTITY_LABEL} con ese id") from exc


@router.post("", response_model=PositionOut, status_code=status.HTTP_201_CREATED)
async def create_entry_route(data: PositionCreate, actor: dict = Depends(require_admin)) -> PositionOut:
    try:
        entry = await catalog_service.create_entry(COLLECTION_NAME, ENTITY_LABEL, data.name, actor)
    except catalog_service.InvalidNameError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except catalog_service.DuplicateEntryError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return PositionOut(**entry)


@router.get("", response_model=list[PositionOut])
async def list_entries_route(
    enabled: bool | None = None, _actor: dict = Depends(require_read)
) -> list[PositionOut]:
    entries = await catalog_service.list_entries(COLLECTION_NAME, enabled)
    return [PositionOut(**entry) for entry in entries]


@router.patch("/{entry_id}", response_model=PositionOut)
async def rename_entry_route(
    entry_id: str, changes: PositionUpdate, actor: dict = Depends(require_admin)
) -> PositionOut:
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
    return PositionOut(**entry)


@router.patch("/{entry_id}/disable", response_model=PositionDisableOut)
async def disable_entry_route(entry_id: str, actor: dict = Depends(require_admin)) -> PositionDisableOut:
    try:
        entry, _affected = await catalog_service.set_enabled(
            COLLECTION_NAME, ENTITY_LABEL, _parse_entry_id(entry_id), False, actor, _count_assigned_employees
        )
    except catalog_service.EntryNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except catalog_service.LastEnabledEntryError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return PositionDisableOut(position=PositionOut(**entry))


@router.patch("/{entry_id}/enable", response_model=PositionOut)
async def enable_entry_route(entry_id: str, actor: dict = Depends(require_admin)) -> PositionOut:
    try:
        entry, _affected = await catalog_service.set_enabled(
            COLLECTION_NAME, ENTITY_LABEL, _parse_entry_id(entry_id), True, actor, _count_assigned_employees
        )
    except catalog_service.EntryNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return PositionOut(**entry)
