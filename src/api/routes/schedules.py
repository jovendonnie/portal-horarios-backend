"""Rutas HTTP de Horarios: solo orquestan (RF-1, RF-2, RF-4, RF-5, RF-6, RF-7)."""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import require_read, require_schedule_write
from src.schemas.schedule import (
    DateRangeStatusChangeInput,
    DayStatusChangeInput,
    DayStatusRevertInput,
    DefaultScheduleUpdate,
    EmployeeDefaultScheduleOut,
    ScheduleDayEntryOut,
    WeekScheduleResponse,
)
from src.services.employee_service import EmployeeNotFoundError, InvalidStatusError
from src.services.schedule_service import (
    DayConflictError,
    InvalidRangeError,
    NonBusinessDayError,
    RangeConflictError,
    StaleScheduleUpdateError,
    apply_day_exception,
    apply_range_status,
    get_default_schedule,
    get_week_schedule_view,
    revert_day_exception,
    set_default_schedule,
)

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _parse_employee_id(employee_id: str) -> ObjectId:
    try:
        return ObjectId(employee_id)
    except InvalidId as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe un empleado con ese id") from exc


@router.get("/week", response_model=WeekScheduleResponse)
async def get_week_schedule_route(
    offset: int = 0, _actor: dict = Depends(require_read)
) -> WeekScheduleResponse:
    return await get_week_schedule_view(offset)


@router.get("/default/{employee_id}", response_model=EmployeeDefaultScheduleOut)
async def get_default_schedule_route(
    employee_id: str, _actor: dict = Depends(require_read)
) -> EmployeeDefaultScheduleOut:
    try:
        return await get_default_schedule(_parse_employee_id(employee_id))
    except EmployeeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.patch("/default/{employee_id}", response_model=EmployeeDefaultScheduleOut)
async def update_default_schedule_route(
    employee_id: str, data: DefaultScheduleUpdate, actor: dict = Depends(require_schedule_write)
) -> EmployeeDefaultScheduleOut:
    try:
        return await set_default_schedule(_parse_employee_id(employee_id), data.days, actor)
    except EmployeeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.patch("/day-status", response_model=ScheduleDayEntryOut)
async def apply_day_status_route(
    data: DayStatusChangeInput, actor: dict = Depends(require_schedule_write)
) -> ScheduleDayEntryOut:
    try:
        return await apply_day_exception(
            _parse_employee_id(data.employee_id),
            data.date,
            data.status_id,
            data.observation,
            data.expected_updated_at,
            actor,
        )
    except EmployeeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except (InvalidStatusError, NonBusinessDayError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except (DayConflictError, StaleScheduleUpdateError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.patch("/day-status/revert", response_model=ScheduleDayEntryOut)
async def revert_day_status_route(
    data: DayStatusRevertInput, actor: dict = Depends(require_schedule_write)
) -> ScheduleDayEntryOut:
    try:
        return await revert_day_exception(
            _parse_employee_id(data.employee_id), data.date, data.expected_updated_at, actor
        )
    except EmployeeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except StaleScheduleUpdateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/range-status", response_model=list[ScheduleDayEntryOut])
async def apply_range_status_route(
    data: DateRangeStatusChangeInput, actor: dict = Depends(require_schedule_write)
) -> list[ScheduleDayEntryOut]:
    try:
        return await apply_range_status(
            _parse_employee_id(data.employee_id),
            data.start_date,
            data.end_date,
            data.status_id,
            actor,
        )
    except EmployeeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except (InvalidStatusError, InvalidRangeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except RangeConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
