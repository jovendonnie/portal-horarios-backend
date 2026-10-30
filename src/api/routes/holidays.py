"""Rutas HTTP del calendario de Festivos: solo orquestan (spec 009, RF-3, RF-4)."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import require_admin, require_read
from src.schemas.holiday import (
    HolidayBlocksShiftsUpdate,
    HolidayCreate,
    HolidayDeleteOut,
    HolidayImportOut,
    HolidayOut,
)
from src.services import holiday_service

router = APIRouter(prefix="/holidays", tags=["holidays"])


@router.get("", response_model=list[HolidayOut])
async def list_holidays_route(
    year: int = Query(ge=1900, le=2200), _actor: dict = Depends(require_read)
) -> list[HolidayOut]:
    holidays = await holiday_service.list_holidays(year)
    return [HolidayOut(**entry) for entry in holidays]


@router.post("", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
async def create_holiday_route(
    data: HolidayCreate, actor: dict = Depends(require_admin)
) -> HolidayOut:
    try:
        entry = await holiday_service.create_holiday(data.date, data.name, actor)
    except holiday_service.DuplicateHolidayError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return HolidayOut(**entry)


@router.post("/import", response_model=HolidayImportOut)
async def import_national_holidays_route(
    year: int = Query(ge=1900, le=2200), actor: dict = Depends(require_admin)
) -> HolidayImportOut:
    result = await holiday_service.import_national_holidays(year, actor)
    return HolidayImportOut(
        imported=[HolidayOut(**entry) for entry in result["imported"]],
        skipped_dates=result["skipped_dates"],
    )


@router.patch("/{date}", response_model=HolidayOut)
async def set_blocks_shifts_route(
    date: str, changes: HolidayBlocksShiftsUpdate, actor: dict = Depends(require_admin)
) -> HolidayOut:
    try:
        entry = await holiday_service.set_blocks_shifts(date, changes.blocks_shifts, actor)
    except holiday_service.HolidayNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return HolidayOut(**entry)


@router.delete("/{date}", response_model=HolidayDeleteOut)
async def delete_holiday_route(date: str, actor: dict = Depends(require_admin)) -> HolidayDeleteOut:
    try:
        deleted_date = await holiday_service.delete_holiday(date, actor)
    except holiday_service.HolidayNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except holiday_service.NationalHolidayError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return HolidayDeleteOut(date=deleted_date)
