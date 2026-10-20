"""Lógica de negocio de Horarios (RF-1 a RF-6, RNF-1 a RNF-4, RNF-6).

Traduce los algoritmos (a), (b) y (c) de
specs/006-horarios-y-correcciones-de-acceso/plan.md sección 4. No conoce
FastAPI ni HTTPException: esa traducción vive en src/api/routes/schedules.py
(Fase 5, fuera de alcance de este archivo).
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from src.core.database import start_transaction
from src.models import catalog
from src.models import schedule as schedule_model
from src.models.employee import find_employee_by_id
from src.models.employee import list_employees as list_employee_documents
from src.schemas.schedule import (
    DefaultScheduleDayIn,
    EmployeeDefaultScheduleOut,
    EmployeeWeekScheduleOut,
    ScheduleDayEntryOut,
    WeekScheduleResponse,
    WEEKDAYS,
)
from src.services.employee_service import EmployeeNotFoundError, InvalidStatusError

_ABSENCE_STATUS_NAMES = ["Permiso", "Vacaciones", "Licencia", "Incapacidad", "Día libre"]
_BOGOTA_TZ = ZoneInfo("America/Bogota")

_absence_status_ids_cache: set[Any] | None = None


class NonBusinessDayError(Exception):
    """La fecha indicada no es un día hábil (lunes a viernes) (RF-4)."""

    def __init__(self) -> None:
        super().__init__("La fecha indicada no es un día hábil (lunes a viernes)")


class DayConflictError(Exception):
    """Ese día ya pertenece a un rango de fechas con un estado aplicado (RF-4)."""

    def __init__(self) -> None:
        super().__init__("Ese día ya pertenece a un rango de fechas aplicado")


class RangeConflictError(Exception):
    """Algún día del rango ya tiene una excepción o pertenece a otro rango (RF-6)."""

    def __init__(self, dates: list[str]) -> None:
        self.dates = dates
        super().__init__("Algunos días del rango ya tienen una excepción")


class StaleScheduleUpdateError(Exception):
    """El día fue modificado por otra persona desde la última consulta (RNF-1)."""

    def __init__(self) -> None:
        super().__init__("El día fue modificado por otra persona desde la última consulta")


class InvalidRangeError(Exception):
    """El rango de fechas es inválido o no contiene ningún día hábil (RF-6)."""

    def __init__(self) -> None:
        super().__init__("El rango de fechas indicado es inválido")


def today_bogota() -> date:
    return datetime.now(_BOGOTA_TZ).date()


def _is_business_day(day: date) -> bool:
    return day.weekday() < 5


def _business_days_between(start: date, end: date) -> list[date]:
    days = []
    current = start
    while current <= end:
        if _is_business_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_naive_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _empty_default_schedule_days() -> list[dict[str, Any]]:
    return [
        {"weekday": weekday, "works": False, "modality": None, "time_ranges": []}
        for weekday in WEEKDAYS
    ]


async def _get_default_schedule_days(employee_id: Any) -> list[dict[str, Any]]:
    document = await schedule_model.find_default_schedule(employee_id)
    return document["days"] if document is not None else _empty_default_schedule_days()


async def _validate_status_id(status_id: str) -> dict[str, Any]:
    try:
        object_id = ObjectId(status_id)
    except InvalidId as exc:
        raise InvalidStatusError() from exc

    entry = await catalog.find_entry_by_id("estados", object_id)
    if entry is None or not entry["is_enabled"]:
        raise InvalidStatusError()
    return entry


async def _absence_status_ids() -> set[Any]:
    global _absence_status_ids_cache
    if _absence_status_ids_cache is None:
        ids: set[Any] = set()
        for name in _ABSENCE_STATUS_NAMES:
            entry = await catalog.find_entry_by_name("estados", name)
            if entry is not None:
                ids.add(entry["_id"])
        _absence_status_ids_cache = ids
    return _absence_status_ids_cache


def resolve_day(
    employee: dict[str, Any],
    day: date,
    default_schedule_days: list[dict[str, Any]],
    exception: dict[str, Any] | None,
    absence_status_ids: set[Any],
) -> dict[str, Any]:
    """Algoritmo (a) de plan.md: resuelve modalidad, franjas y origen de un día (RF-3)."""
    weekday_name = WEEKDAYS[day.weekday()]
    day_schedule = next(
        (d for d in default_schedule_days if d["weekday"] == weekday_name),
        {"weekday": weekday_name, "works": False, "modality": None, "time_ranges": []},
    )

    if exception is not None:
        status_id = exception["status_id"]
        source = exception["source"]
    else:
        status_id = employee["estado_id"]
        source = "default"

    if status_id in absence_status_ids:
        return {"date": day, "status_id": status_id, "modality": None, "time_ranges": [], "source": source}

    if exception is None and not day_schedule["works"]:
        return {"date": day, "status_id": status_id, "modality": None, "time_ranges": [], "source": source}

    return {
        "date": day,
        "status_id": status_id,
        "modality": day_schedule["modality"],
        "time_ranges": day_schedule["time_ranges"],
        "source": source,
    }


def _build_schedule_day_entry_out(
    resolved: dict[str, Any],
    status_name: str,
    exception: dict[str, Any] | None,
) -> ScheduleDayEntryOut:
    return ScheduleDayEntryOut(
        date=resolved["date"],
        status_id=resolved["status_id"],
        status_name=status_name,
        modality=resolved["modality"],
        time_ranges=resolved["time_ranges"],
        source=resolved["source"],
        observation=(exception or {}).get("observation"),
        updated_at=(exception or {}).get("updated_at"),
    )


async def get_default_schedule(employee_id: Any) -> EmployeeDefaultScheduleOut:
    employee = await find_employee_by_id(employee_id)
    if employee is None:
        raise EmployeeNotFoundError()

    document = await schedule_model.find_default_schedule(employee_id)
    if document is None:
        return EmployeeDefaultScheduleOut(
            employee_id=employee_id,
            days=_empty_default_schedule_days(),
            updated_at=None,
            updated_by=None,
        )
    return EmployeeDefaultScheduleOut(**document)


async def set_default_schedule(
    employee_id: Any, days: list[DefaultScheduleDayIn], actor: dict[str, Any]
) -> EmployeeDefaultScheduleOut:
    employee = await find_employee_by_id(employee_id)
    if employee is None:
        raise EmployeeNotFoundError()

    day_documents = [day.model_dump() for day in days]
    await schedule_model.upsert_default_schedule(employee_id, day_documents, actor.get("_id"))

    updated = await schedule_model.find_default_schedule(employee_id)
    assert updated is not None
    return EmployeeDefaultScheduleOut(**updated)


async def _resolve_catalog_names() -> tuple[dict[str, str], dict[str, str]]:
    area_entries = await catalog.list_entries("areas")
    status_entries = await catalog.list_entries("estados")
    area_names = {str(entry["_id"]): entry["name"] for entry in area_entries}
    status_names = {str(entry["_id"]): entry["name"] for entry in status_entries}
    return area_names, status_names


async def get_week_schedule(employees: list[dict[str, Any]], offset: int) -> WeekScheduleResponse:
    """Algoritmo (b) de plan.md: consulta semanal en lote (RF-2, RNF-3, RNF-6)."""
    absence_ids = await _absence_status_ids()
    today = today_bogota()
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    week_days = [week_start + timedelta(days=i) for i in range(5)]
    week_end = week_days[-1]

    employee_ids = [employee["_id"] for employee in employees]
    date_strings = [day.isoformat() for day in week_days]

    default_docs = await schedule_model.find_default_schedules_bulk(employee_ids)
    default_days_by_employee = {doc["employee_id"]: doc["days"] for doc in default_docs}

    exception_docs = await schedule_model.find_exceptions_bulk(employee_ids, date_strings)
    exceptions_by_key = {(doc["employee_id"], doc["date"]): doc for doc in exception_docs}

    area_names, status_names = await _resolve_catalog_names()

    employees_out = []
    for employee in employees:
        default_days = default_days_by_employee.get(employee["_id"], _empty_default_schedule_days())
        days_out = []
        for day, date_str in zip(week_days, date_strings):
            exception = exceptions_by_key.get((employee["_id"], date_str))
            resolved = resolve_day(employee, day, default_days, exception, absence_ids)
            status_name = status_names.get(str(resolved["status_id"]), "")
            days_out.append(_build_schedule_day_entry_out(resolved, status_name, exception))

        employees_out.append(
            EmployeeWeekScheduleOut(
                employee_id=employee["_id"],
                full_name=employee["nombre_completo"],
                position=employee["cargo"],
                area_name=area_names.get(str(employee.get("area_id")), ""),
                is_active=employee["activo"],
                days=days_out,
            )
        )

    return WeekScheduleResponse(
        week_start=week_start,
        week_end=week_end,
        server_today=today,
        week_offset=offset,
        can_navigate_prev=True,
        can_navigate_next=True,
        employees=employees_out,
    )


async def apply_day_exception(
    employee_id: Any,
    day: date,
    status_id: str,
    observation: str | None,
    expected_updated_at: datetime | None,
    actor: dict[str, Any],
) -> ScheduleDayEntryOut:
    """RF-4, RNF-1."""
    if not _is_business_day(day):
        raise NonBusinessDayError()

    employee = await find_employee_by_id(employee_id)
    if employee is None:
        raise EmployeeNotFoundError()

    status_entry = await _validate_status_id(status_id)

    date_str = day.isoformat()
    current_exception = await schedule_model.find_exception(employee_id, date_str)

    if current_exception is not None and current_exception["source"] == "range_override":
        raise DayConflictError()

    current_updated_at = current_exception["updated_at"] if current_exception is not None else None
    if _as_naive_utc(current_updated_at) != _as_naive_utc(expected_updated_at):
        raise StaleScheduleUpdateError()

    document = await schedule_model.upsert_day_exception(
        employee_id, date_str, status_entry["_id"], observation, actor.get("_id")
    )

    default_days = await _get_default_schedule_days(employee_id)
    absence_ids = await _absence_status_ids()
    resolved = resolve_day(employee, day, default_days, document, absence_ids)
    return _build_schedule_day_entry_out(resolved, status_entry["name"], document)


async def revert_day_exception(
    employee_id: Any,
    day: date,
    expected_updated_at: datetime | None,
    actor: dict[str, Any],
) -> ScheduleDayEntryOut:
    """RF-5, RNF-1."""
    employee = await find_employee_by_id(employee_id)
    if employee is None:
        raise EmployeeNotFoundError()

    date_str = day.isoformat()
    current_exception = await schedule_model.find_exception(employee_id, date_str)
    default_days = await _get_default_schedule_days(employee_id)
    absence_ids = await _absence_status_ids()

    if current_exception is None or current_exception["source"] == "range_override":
        resolved = resolve_day(employee, day, default_days, current_exception, absence_ids)
        status_entry = await catalog.find_entry_by_id("estados", resolved["status_id"])
        status_name = status_entry["name"] if status_entry is not None else ""
        return _build_schedule_day_entry_out(resolved, status_name, current_exception)

    current_updated_at = _as_naive_utc(current_exception["updated_at"])
    if current_updated_at != _as_naive_utc(expected_updated_at):
        raise StaleScheduleUpdateError()

    await schedule_model.delete_day_exception(employee_id, date_str)

    resolved = resolve_day(employee, day, default_days, None, absence_ids)
    status_entry = await catalog.find_entry_by_id("estados", resolved["status_id"])
    status_name = status_entry["name"] if status_entry is not None else ""
    return _build_schedule_day_entry_out(resolved, status_name, None)


async def apply_range_status(
    employee_id: Any,
    start_date: date,
    end_date: date,
    status_id: str,
    actor: dict[str, Any],
) -> list[ScheduleDayEntryOut]:
    """Algoritmo (c) de plan.md: aplicación atómica de un estado a un rango (RF-6, RNF-2)."""
    if start_date > end_date:
        raise InvalidRangeError()

    business_days = _business_days_between(start_date, end_date)
    if not business_days:
        raise InvalidRangeError()

    employee = await find_employee_by_id(employee_id)
    if employee is None:
        raise EmployeeNotFoundError()

    status_entry = await _validate_status_id(status_id)

    date_strings = [day.isoformat() for day in business_days]
    range_id = ObjectId()
    actor_id = actor.get("_id")
    now = _utcnow()

    docs = [
        {
            "employee_id": employee_id,
            "date": date_str,
            "status_id": status_entry["_id"],
            "observation": None,
            "source": "range_override",
            "range_id": range_id,
            "updated_at": now,
            "updated_by": actor_id,
        }
        for date_str in date_strings
    ]

    async with start_transaction() as session:
        try:
            existing = await schedule_model.find_exceptions_bulk(
                [employee_id], date_strings, session=session
            )
            if existing:
                raise RangeConflictError([doc["date"] for doc in existing])

            await schedule_model.insert_range_exceptions(docs, session=session)
        except DuplicateKeyError as exc:
            await session.abort_transaction()
            raise RangeConflictError(date_strings) from exc
        except Exception:
            await session.abort_transaction()
            raise
        else:
            await session.commit_transaction()

    default_days = await _get_default_schedule_days(employee_id)
    absence_ids = await _absence_status_ids()
    results = []
    for day, document in zip(business_days, docs):
        resolved = resolve_day(employee, day, default_days, document, absence_ids)
        results.append(_build_schedule_day_entry_out(resolved, status_entry["name"], document))
    return results


async def get_week_schedule_view(offset: int) -> WeekScheduleResponse:
    """Punto de entrada para la ruta HTTP: resuelve los empleados (todos,
    activos e inactivos — un inactivo sigue apareciendo marcado como tal,
    ver spec.md casos límite) y delega en get_week_schedule (RF-2)."""
    employees = await list_employee_documents()
    return await get_week_schedule(employees, offset)
