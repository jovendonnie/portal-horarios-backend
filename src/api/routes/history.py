"""Ruta HTTP del historial de auditoría: solo orquesta (RF-5, RF-6, RF-7)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import require_read
from src.schemas.history import EntityType, HistoryEntryOut, HistoryQuery
from src.services.history_service import (
    EntityNotFoundError,
    EntityTypeRequiredError,
    query_history,
)

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=list[HistoryEntryOut])
async def list_history_route(
    entity_type: EntityType | None = None,
    entity_id: str | None = None,
    actor_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _actor: dict = Depends(require_read),
) -> list[HistoryEntryOut]:
    filters = HistoryQuery(
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
    )
    try:
        entries = await query_history(filters)
    except EntityTypeRequiredError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except EntityNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return [HistoryEntryOut(**entry) for entry in entries]
