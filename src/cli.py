"""CLI de administración (RF-2, RF-3, RF-7): interfaz alternativa a la API HTTP.

Solo parsea argumentos e imprime resultados; toda la lógica de negocio vive
en `services/` y `models/`, igual que en `api/routes/` (constitución #3).
"""

import argparse
import asyncio
import json
import re
import sys
from datetime import date, datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pydantic import ValidationError

from src.core.database import arrancar_con_indices, close_mongo_connection, connect_to_mongo
from src.models.catalog import find_entry_by_name
from src.models.user import find_user_by_email, update_user
from src.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate
from src.schemas.history import HistoryQuery
from src.schemas.schedule import DefaultScheduleUpdate
from src.schemas.user import UserCreate
from src.services.auth_service import EmailAlreadyExistsError, register_user
from src.services import (
    catalog_cleanup_service,
    catalog_service,
    history_service,
    schedule_service,
    user_service,
)
from src.services.employee_service import (
    DuplicateEmployeeError,
    EmployeeNotFoundError,
    InvalidAreaError,
    InvalidPositionError,
    InvalidStatusError,
    create_employee,
    list_employees,
    update_employee,
    update_employee_status,
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_CONFLICT = 2
EXIT_NOT_FOUND = 3
EXIT_INVALID_ARGS = 4

_ENTITY_CODE = {"Área": "area", "Estado": "status"}
_CATALOG_LABELS = {"areas": "Área", "estados": "Estado"}


class _InvalidArgumentsError(Exception):
    pass


class _InvalidDaysError(Exception):
    pass


class _ConfirmationRequiredError(Exception):
    def __init__(self) -> None:
        super().__init__("Debe incluir --confirm para ejecutar la limpieza de duplicados")


class _UserNotFoundError(Exception):
    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"No existe una cuenta con el correo {email}")


class _ArgumentParser(argparse.ArgumentParser):
    """Convierte los errores de argparse al mismo contrato JSON que el resto de la CLI."""

    def error(self, message: str) -> None:
        _print_error("invalid_arguments", message)
        raise SystemExit(EXIT_INVALID_ARGS)


def _print_success(payload: dict[str, Any]) -> None:
    print(json.dumps({"status": "ok", **payload}, ensure_ascii=False))


def _print_error(code: str, message: str) -> None:
    error = {"status": "error", "code": code, "message": message}
    print(json.dumps(error, ensure_ascii=False), file=sys.stderr)


def _validate_email(email: str) -> None:
    if not EMAIL_RE.match(email):
        raise _InvalidArgumentsError(f"Correo con formato inválido: {email}")


def _build_parser() -> _ArgumentParser:
    parser = _ArgumentParser(prog="python -m src.cli", description="CLI de administración")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_admin = subparsers.add_parser("create-admin", help="Crea una cuenta con rol admin")
    create_admin.add_argument("--name", required=True)
    create_admin.add_argument("--email", required=True)

    create_user_parser = subparsers.add_parser(
        "create-user", help="Crea una cuenta con rol gestion_humana o lider"
    )
    create_user_parser.add_argument("--name", required=True)
    create_user_parser.add_argument("--email", required=True)
    create_user_parser.add_argument(
        "--role", required=True, choices=["gestion_humana", "lider"]
    )

    unlock_user = subparsers.add_parser("unlock-user", help="Desbloquea una cuenta bloqueada")
    unlock_user.add_argument("--email", required=True)

    deactivate_user = subparsers.add_parser("deactivate-user", help="Desactiva una cuenta")
    deactivate_user.add_argument("--email", required=True)

    reset_password_parser = subparsers.add_parser(
        "reset-password", help="Resetea la contraseña de una cuenta"
    )
    reset_password_parser.add_argument("--email", required=True)

    create_employee_parser = subparsers.add_parser("create-employee", help="Crea un empleado")
    create_employee_parser.add_argument("--name", required=True)
    create_employee_parser.add_argument("--position", required=True)
    create_employee_parser.add_argument("--area", required=True)
    create_employee_parser.add_argument("--status", required=True)

    subparsers.add_parser("list-employees", help="Lista los empleados")

    update_employee_parser = subparsers.add_parser("update-employee", help="Edita un empleado")
    update_employee_parser.add_argument("--id", required=True)
    update_employee_parser.add_argument("--name")
    update_employee_parser.add_argument("--position")
    update_employee_parser.add_argument("--area")

    set_employee_status_parser = subparsers.add_parser(
        "set-employee-status", help="Actualiza el Estado actual de un empleado"
    )
    set_employee_status_parser.add_argument("--id", required=True)
    set_employee_status_parser.add_argument("--status", required=True)

    create_area_parser = subparsers.add_parser("create-area", help="Crea un Área")
    create_area_parser.add_argument("--name", required=True)

    list_areas_parser = subparsers.add_parser("list-areas", help="Lista las Áreas")
    area_filter_group = list_areas_parser.add_mutually_exclusive_group()
    area_filter_group.add_argument("--enabled", action="store_true", dest="enabled_flag")
    area_filter_group.add_argument("--disabled", action="store_true", dest="disabled_flag")

    update_area_parser = subparsers.add_parser("update-area", help="Renombra un Área")
    update_area_parser.add_argument("--id", required=True)
    update_area_parser.add_argument("--name", required=True)

    enable_area_parser = subparsers.add_parser("enable-area", help="Habilita un Área")
    enable_area_parser.add_argument("--id", required=True)

    disable_area_parser = subparsers.add_parser("disable-area", help="Deshabilita un Área")
    disable_area_parser.add_argument("--id", required=True)

    create_status_parser = subparsers.add_parser("create-status", help="Crea un Estado")
    create_status_parser.add_argument("--name", required=True)

    subparsers.add_parser(
        "seed-predefined-statuses",
        help="Asegura que los 7 Estados predefinidos existan y estén marcados como tales",
    )

    list_statuses_parser = subparsers.add_parser("list-statuses", help="Lista los Estados")
    status_filter_group = list_statuses_parser.add_mutually_exclusive_group()
    status_filter_group.add_argument("--enabled", action="store_true", dest="enabled_flag")
    status_filter_group.add_argument("--disabled", action="store_true", dest="disabled_flag")

    update_status_parser = subparsers.add_parser("update-status", help="Renombra un Estado")
    update_status_parser.add_argument("--id", required=True)
    update_status_parser.add_argument("--name", required=True)

    enable_status_parser = subparsers.add_parser("enable-status", help="Habilita un Estado")
    enable_status_parser.add_argument("--id", required=True)

    disable_status_parser = subparsers.add_parser("disable-status", help="Deshabilita un Estado")
    disable_status_parser.add_argument("--id", required=True)

    list_history_parser = subparsers.add_parser(
        "list-history", help="Consulta el historial de auditoría"
    )
    list_history_parser.add_argument(
        "--entity-type",
        dest="entity_type",
        choices=["employee", "area", "status", "user", "login"],
    )
    list_history_parser.add_argument("--entity-id", dest="entity_id")
    list_history_parser.add_argument("--actor-id", dest="actor_id")
    list_history_parser.add_argument("--from", dest="date_from")
    list_history_parser.add_argument("--to", dest="date_to")

    subparsers.add_parser(
        "ensure-indexes", help="Reintenta crear los índices únicos pendientes"
    )

    show_default_schedule_parser = subparsers.add_parser(
        "show-default-schedule", help="Muestra el horario habitual de un empleado"
    )
    show_default_schedule_parser.add_argument("--employee-id", required=True, dest="employee_id")

    set_default_schedule_parser = subparsers.add_parser(
        "set-default-schedule", help="Reemplaza el horario habitual de un empleado"
    )
    set_default_schedule_parser.add_argument("--employee-id", required=True, dest="employee_id")
    set_default_schedule_parser.add_argument("--days-json", required=True, dest="days_json")

    show_week_schedule_parser = subparsers.add_parser(
        "show-week-schedule", help="Consulta el horario semanal de todos los empleados"
    )
    show_week_schedule_parser.add_argument("--offset", type=int, default=0)

    set_day_status_parser = subparsers.add_parser(
        "set-day-status", help="Aplica una excepción puntual a un día de un empleado"
    )
    set_day_status_parser.add_argument("--employee-id", required=True, dest="employee_id")
    set_day_status_parser.add_argument("--date", required=True)
    set_day_status_parser.add_argument("--status", required=True)
    set_day_status_parser.add_argument(
        "--expected-updated-at", dest="expected_updated_at", default=None
    )
    set_day_status_parser.add_argument("--observation", default=None)

    revert_day_status_parser = subparsers.add_parser(
        "revert-day-status", help="Revierte la excepción puntual de un día de un empleado"
    )
    revert_day_status_parser.add_argument("--employee-id", required=True, dest="employee_id")
    revert_day_status_parser.add_argument("--date", required=True)
    revert_day_status_parser.add_argument(
        "--expected-updated-at", dest="expected_updated_at", default=None
    )

    set_range_status_parser = subparsers.add_parser(
        "set-range-status", help="Aplica un Estado a un rango de fechas de un empleado"
    )
    set_range_status_parser.add_argument("--employee-id", required=True, dest="employee_id")
    set_range_status_parser.add_argument("--start-date", required=True, dest="start_date")
    set_range_status_parser.add_argument("--end-date", required=True, dest="end_date")
    set_range_status_parser.add_argument("--status", required=True)

    subparsers.add_parser("list-users", help="Lista las cuentas de usuario")

    diagnose_duplicates_parser = subparsers.add_parser(
        "diagnose-catalog-duplicates",
        help="Reporta duplicados de nombre en un catálogo sin modificar nada",
    )
    diagnose_duplicates_parser.add_argument(
        "--collection", required=True, choices=["areas", "estados"]
    )

    clean_duplicates_parser = subparsers.add_parser(
        "clean-catalog-duplicates",
        help="Elimina duplicados de nombre en un catálogo, reasignando referencias",
    )
    clean_duplicates_parser.add_argument(
        "--collection", required=True, choices=["areas", "estados"]
    )
    clean_duplicates_parser.add_argument("--confirm", action="store_true")

    return parser


async def _create_admin(name: str, email: str) -> dict[str, Any]:
    _validate_email(email)
    data = UserCreate.model_construct(full_name=name, email=email, role="admin")
    result = await register_user({"_id": None, "full_name": "CLI"}, data)
    return {
        "user": {
            "id": str(result.user["_id"]),
            "email": result.user["email"],
            "role": result.user["role"],
        },
        "temporary_password": result.temporary_password,
    }


async def _create_user(name: str, email: str, role: str) -> dict[str, Any]:
    _validate_email(email)
    data = UserCreate(full_name=name, email=email, role=role)
    result = await register_user({"_id": None, "full_name": "CLI"}, data)
    return {
        "user": {
            "id": str(result.user["_id"]),
            "email": result.user["email"],
            "role": result.user["role"],
        },
        "temporary_password": result.temporary_password,
    }


async def _unlock_user(email: str) -> dict[str, Any]:
    _validate_email(email)
    user = await find_user_by_email(email)
    if user is None:
        raise _UserNotFoundError(email)

    await update_user(email, {"failed_login_attempts": 0, "locked_until": None})
    return {"email": email, "locked_until": None}


async def _deactivate_user(email: str) -> dict[str, Any]:
    _validate_email(email)
    return await user_service.deactivate_user({"_id": None, "full_name": "CLI"}, email)


async def _reset_password(email: str) -> dict[str, Any]:
    _validate_email(email)
    return await user_service.reset_password({"_id": None, "full_name": "CLI"}, email)


def _employee_payload(employee: EmployeeOut) -> dict[str, Any]:
    return {
        "id": employee.id,
        "full_name": employee.full_name,
        "position": employee.position,
        "area": employee.area,
        "status": employee.status_name,
        "is_active": employee.is_active,
    }


def _employee_status_payload(employee: EmployeeOut) -> dict[str, Any]:
    return {
        "id": employee.id,
        "status": employee.status_name,
        "status_updated_at": employee.status_updated_at.isoformat()
        if employee.status_updated_at is not None
        else None,
        "status_updated_by": employee.status_updated_by,
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _resolve_catalog_id(collection_name: str, name: str, error_cls: type[Exception]) -> str:
    """Resuelve un nombre de Área/Estado a su id (decisión 11, plan.md sección 6): la CLI recibe nombres, no ObjectIds."""
    entry = await find_entry_by_name(collection_name, name)
    if entry is None or not entry["is_enabled"]:
        raise error_cls()
    return str(entry["_id"])


async def _create_employee(name: str, position: str, area: str, status: str) -> dict[str, Any]:
    area_id = await _resolve_catalog_id("areas", area, InvalidAreaError)
    status_id = await _resolve_catalog_id("estados", status, InvalidStatusError)
    data = EmployeeCreate.model_construct(
        full_name=name, position=position, area_id=area_id, status_id=status_id
    )
    employee = await create_employee({"_id": None, "full_name": "CLI"}, data)
    return {"employee": _employee_payload(employee)}


async def _list_employees() -> dict[str, Any]:
    employees = await list_employees()
    return {"employees": [_employee_payload(employee) for employee in employees]}


async def _update_employee(
    employee_id: str, name: str | None, position: str | None, area: str | None
) -> dict[str, Any]:
    try:
        object_id = ObjectId(employee_id)
    except InvalidId as exc:
        raise EmployeeNotFoundError() from exc

    changes_kwargs: dict[str, Any] = {}
    if name is not None:
        changes_kwargs["full_name"] = name
    if position is not None:
        changes_kwargs["position"] = position
    if area is not None:
        changes_kwargs["area_id"] = await _resolve_catalog_id("areas", area, InvalidAreaError)
    changes = EmployeeUpdate.model_construct(**changes_kwargs)

    employee = await update_employee({"_id": None, "full_name": "CLI"}, object_id, changes)
    return {"employee": _employee_payload(employee)}


async def _set_employee_status(employee_id: str, status: str) -> dict[str, Any]:
    try:
        object_id = ObjectId(employee_id)
    except InvalidId as exc:
        raise EmployeeNotFoundError() from exc

    status_id = await _resolve_catalog_id("estados", status, InvalidStatusError)
    employee = await update_employee_status(
        object_id, status_id, {"_id": None, "full_name": "CLI"}, _utcnow()
    )
    return {"employee": _employee_status_payload(employee)}


def _entry_payload(entry: dict[str, Any], *, include_predefined: bool = False) -> dict[str, Any]:
    payload = {"id": str(entry["_id"]), "name": entry["name"], "is_enabled": entry["is_enabled"]}
    if include_predefined:
        payload["is_predefined"] = entry.get("is_predefined", False)
    return payload


async def _count_assigned_stub(_entry_id: Any) -> int:
    # Placeholder hasta Fase 6 (count_employees_by_area/count_employees_by_status).
    return 0


def _parse_catalog_id(entry_id: str, entity_label: str) -> ObjectId:
    try:
        return ObjectId(entry_id)
    except InvalidId as exc:
        raise catalog_service.EntryNotFoundError(entity_label) from exc


async def _create_catalog_entry(collection_name: str, entity_label: str, name: str) -> dict[str, Any]:
    entry = await catalog_service.create_entry(
        collection_name, entity_label, name, {"_id": None, "full_name": "CLI"}
    )
    return {"entry": _entry_payload(entry, include_predefined=collection_name == "estados")}


async def _seed_predefined_statuses() -> dict[str, Any]:
    entries = await catalog_service.seed_predefined_estados({"_id": None, "full_name": "Sistema"})
    return {"entries": [_entry_payload(entry, include_predefined=True) for entry in entries]}


async def _list_catalog_entries(collection_name: str, enabled: bool | None) -> dict[str, Any]:
    entries = await catalog_service.list_entries(collection_name, enabled)
    include_predefined = collection_name == "estados"
    return {
        "entries": [_entry_payload(entry, include_predefined=include_predefined) for entry in entries]
    }


async def _update_catalog_entry(
    collection_name: str, entity_label: str, entry_id: str, name: str
) -> dict[str, Any]:
    entry = await catalog_service.rename_entry(
        collection_name,
        entity_label,
        _parse_catalog_id(entry_id, entity_label),
        name,
        {"_id": None, "full_name": "CLI"},
    )
    return {"entry": _entry_payload(entry, include_predefined=collection_name == "estados")}


async def _set_catalog_enabled(
    collection_name: str, entity_label: str, entry_id: str, enabled: bool
) -> dict[str, Any]:
    entry, affected = await catalog_service.set_enabled(
        collection_name,
        entity_label,
        _parse_catalog_id(entry_id, entity_label),
        enabled,
        {"_id": None, "full_name": "CLI"},
        _count_assigned_stub,
    )
    payload: dict[str, Any] = {
        "entry": _entry_payload(entry, include_predefined=collection_name == "estados")
    }
    if not enabled:
        payload["affected_employees"] = affected or 0
    return payload


def _parse_history_date(value: str | None, flag: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise _InvalidArgumentsError(f"Fecha con formato inválido en {flag}: {value}") from exc


def _history_entry_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(entry["_id"]),
        "entity_type": entry["entity_type"],
        "entity_id": str(entry["entity_id"]) if entry["entity_id"] is not None else None,
        "action": entry["action"],
        "actor_id": str(entry["actor_id"]) if entry["actor_id"] is not None else None,
        "actor_name": entry["actor_name"],
        "changes": entry["changes"],
        "occurred_at": entry["occurred_at"].isoformat(),
    }


async def _list_history(
    entity_type: str | None,
    entity_id: str | None,
    actor_id: str | None,
    date_from: str | None,
    date_to: str | None,
) -> dict[str, Any]:
    filters = HistoryQuery(
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        date_from=_parse_history_date(date_from, "--from"),
        date_to=_parse_history_date(date_to, "--to"),
    )
    entries = await history_service.query_history(filters)
    return {"entries": [_history_entry_payload(entry) for entry in entries]}


def _parse_employee_object_id(employee_id: str) -> ObjectId:
    try:
        return ObjectId(employee_id)
    except InvalidId as exc:
        raise EmployeeNotFoundError() from exc


def _parse_date_arg(value: str, flag: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _InvalidArgumentsError(f"Fecha con formato inválido en {flag}: {value}") from exc


def _time_ranges_payload(time_ranges: list[Any]) -> list[dict[str, Any]]:
    return [{"start": time_range.start, "end": time_range.end} for time_range in time_ranges]


def _default_schedule_payload(schedule: Any) -> dict[str, Any]:
    return {
        "employee_id": schedule.employee_id,
        "days": [
            {
                "weekday": day.weekday,
                "works": day.works,
                "modality": day.modality,
                "time_ranges": _time_ranges_payload(day.time_ranges),
            }
            for day in schedule.days
        ],
        "updated_at": schedule.updated_at.isoformat() if schedule.updated_at is not None else None,
        "updated_by": schedule.updated_by,
    }


def _schedule_day_entry_payload(employee_id: str, entry: Any) -> dict[str, Any]:
    return {
        "employee_id": employee_id,
        "date": entry.date.isoformat(),
        "status_id": entry.status_id,
        "status_name": entry.status_name,
        "modality": entry.modality,
        "time_ranges": _time_ranges_payload(entry.time_ranges),
        "observation": entry.observation,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at is not None else None,
        "source": entry.source,
    }


def _week_schedule_payload(response: Any) -> dict[str, Any]:
    return {
        "week_start": response.week_start.isoformat(),
        "week_end": response.week_end.isoformat(),
        "server_today": response.server_today.isoformat(),
        "week_offset": response.week_offset,
        "can_navigate_prev": response.can_navigate_prev,
        "can_navigate_next": response.can_navigate_next,
        "employees": [
            {
                "employee_id": employee.employee_id,
                "full_name": employee.full_name,
                "position": employee.position,
                "area_name": employee.area_name,
                "is_active": employee.is_active,
                "days": [
                    _schedule_day_entry_payload(employee.employee_id, day)
                    for day in employee.days
                ],
            }
            for employee in response.employees
        ],
    }


def _user_payload(user: Any) -> dict[str, Any]:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
        "created_by": user.created_by,
    }


async def _ensure_indexes() -> dict[str, Any]:
    created, skipped_duplicates = await arrancar_con_indices()
    return {"created": created, "skipped_duplicates": skipped_duplicates}


async def _show_default_schedule(employee_id: str) -> dict[str, Any]:
    object_id = _parse_employee_object_id(employee_id)
    schedule = await schedule_service.get_default_schedule(object_id)
    return _default_schedule_payload(schedule)


async def _set_default_schedule(employee_id: str, days_json: str) -> dict[str, Any]:
    object_id = _parse_employee_object_id(employee_id)
    try:
        raw_days = json.loads(days_json)
        update = DefaultScheduleUpdate(days=raw_days)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise _InvalidDaysError(f"--days-json inválido: {exc}") from exc

    schedule = await schedule_service.set_default_schedule(
        object_id, update.days, {"_id": None, "full_name": "CLI"}
    )
    return _default_schedule_payload(schedule)


async def _show_week_schedule(offset: int) -> dict[str, Any]:
    response = await schedule_service.get_week_schedule_view(offset)
    return _week_schedule_payload(response)


async def _set_day_status(
    employee_id: str,
    day_str: str,
    status: str,
    expected_updated_at: str | None,
    observation: str | None,
) -> dict[str, Any]:
    object_id = _parse_employee_object_id(employee_id)
    day = _parse_date_arg(day_str, "--date")
    status_id = await _resolve_catalog_id("estados", status, InvalidStatusError)
    expected = _parse_history_date(expected_updated_at, "--expected-updated-at")

    entry = await schedule_service.apply_day_exception(
        object_id, day, status_id, observation, expected, {"_id": None, "full_name": "CLI"}
    )
    return _schedule_day_entry_payload(employee_id, entry)


async def _revert_day_status(
    employee_id: str, day_str: str, expected_updated_at: str | None
) -> dict[str, Any]:
    object_id = _parse_employee_object_id(employee_id)
    day = _parse_date_arg(day_str, "--date")
    expected = _parse_history_date(expected_updated_at, "--expected-updated-at")

    entry = await schedule_service.revert_day_exception(
        object_id, day, expected, {"_id": None, "full_name": "CLI"}
    )
    return _schedule_day_entry_payload(employee_id, entry)


async def _set_range_status(
    employee_id: str, start_date_str: str, end_date_str: str, status: str
) -> dict[str, Any]:
    object_id = _parse_employee_object_id(employee_id)
    start_date = _parse_date_arg(start_date_str, "--start-date")
    end_date = _parse_date_arg(end_date_str, "--end-date")
    status_id = await _resolve_catalog_id("estados", status, InvalidStatusError)

    entries = await schedule_service.apply_range_status(
        object_id, start_date, end_date, status_id, {"_id": None, "full_name": "CLI"}
    )
    return {"days": [_schedule_day_entry_payload(employee_id, entry) for entry in entries]}


async def _list_users() -> dict[str, Any]:
    users = await user_service.list_users()
    return {"users": [_user_payload(user) for user in users]}


def _duplicate_entry_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(entry["_id"]),
        "name": entry["name"],
        "is_enabled": entry["is_enabled"],
        "created_at": entry["created_at"].isoformat(),
        "reference_count": entry["reference_count"],
    }


def _duplicate_group_payload(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "normalized_name": group["normalized_name"],
        "entries": [_duplicate_entry_payload(entry) for entry in group["entries"]],
        "keep_id": str(group["keep_id"]),
    }


async def _diagnose_catalog_duplicates(collection_name: str) -> dict[str, Any]:
    groups = await catalog_cleanup_service.diagnose_duplicates(
        collection_name, _CATALOG_LABELS[collection_name]
    )
    return {
        "collection": collection_name,
        "duplicate_groups": [_duplicate_group_payload(group) for group in groups],
        "total_duplicate_groups": len(groups),
    }


def _cleaned_group_payload(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "normalized_name": group["normalized_name"],
        "kept_id": str(group["kept_id"]),
        "deleted_ids": [str(entry_id) for entry_id in group["deleted_ids"]],
        "reassigned_employees": group["reassigned_employees"],
        "reassigned_exceptions": group["reassigned_exceptions"],
    }


async def _clean_catalog_duplicates(collection_name: str, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise _ConfirmationRequiredError()

    groups = await catalog_cleanup_service.clean_duplicates(
        collection_name, _CATALOG_LABELS[collection_name], {"_id": None, "full_name": "CLI"}
    )
    return {
        "collection": collection_name,
        "cleaned_groups": [_cleaned_group_payload(group) for group in groups],
        "total_duplicate_groups_cleaned": len(groups),
    }


def _enabled_filter(args: argparse.Namespace) -> bool | None:
    if getattr(args, "enabled_flag", False):
        return True
    if getattr(args, "disabled_flag", False):
        return False
    return None


async def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "create-admin":
        return await _create_admin(args.name, args.email)
    if args.command == "create-user":
        return await _create_user(args.name, args.email, args.role)
    if args.command == "unlock-user":
        return await _unlock_user(args.email)
    if args.command == "deactivate-user":
        return await _deactivate_user(args.email)
    if args.command == "reset-password":
        return await _reset_password(args.email)
    if args.command == "create-employee":
        return await _create_employee(args.name, args.position, args.area, args.status)
    if args.command == "list-employees":
        return await _list_employees()
    if args.command == "update-employee":
        return await _update_employee(args.id, args.name, args.position, args.area)
    if args.command == "set-employee-status":
        return await _set_employee_status(args.id, args.status)
    if args.command == "create-area":
        return await _create_catalog_entry("areas", "Área", args.name)
    if args.command == "list-areas":
        return await _list_catalog_entries("areas", _enabled_filter(args))
    if args.command == "update-area":
        return await _update_catalog_entry("areas", "Área", args.id, args.name)
    if args.command == "enable-area":
        return await _set_catalog_enabled("areas", "Área", args.id, True)
    if args.command == "disable-area":
        return await _set_catalog_enabled("areas", "Área", args.id, False)
    if args.command == "create-status":
        return await _create_catalog_entry("estados", "Estado", args.name)
    if args.command == "seed-predefined-statuses":
        return await _seed_predefined_statuses()
    if args.command == "list-statuses":
        return await _list_catalog_entries("estados", _enabled_filter(args))
    if args.command == "update-status":
        return await _update_catalog_entry("estados", "Estado", args.id, args.name)
    if args.command == "enable-status":
        return await _set_catalog_enabled("estados", "Estado", args.id, True)
    if args.command == "disable-status":
        return await _set_catalog_enabled("estados", "Estado", args.id, False)
    if args.command == "list-history":
        return await _list_history(
            args.entity_type, args.entity_id, args.actor_id, args.date_from, args.date_to
        )
    if args.command == "ensure-indexes":
        return await _ensure_indexes()
    if args.command == "show-default-schedule":
        return await _show_default_schedule(args.employee_id)
    if args.command == "set-default-schedule":
        return await _set_default_schedule(args.employee_id, args.days_json)
    if args.command == "show-week-schedule":
        return await _show_week_schedule(args.offset)
    if args.command == "set-day-status":
        return await _set_day_status(
            args.employee_id, args.date, args.status, args.expected_updated_at, args.observation
        )
    if args.command == "revert-day-status":
        return await _revert_day_status(args.employee_id, args.date, args.expected_updated_at)
    if args.command == "set-range-status":
        return await _set_range_status(
            args.employee_id, args.start_date, args.end_date, args.status
        )
    if args.command == "diagnose-catalog-duplicates":
        return await _diagnose_catalog_duplicates(args.collection)
    if args.command == "clean-catalog-duplicates":
        return await _clean_catalog_duplicates(args.collection, args.confirm)
    return await _list_users()


async def _execute(args: argparse.Namespace) -> int:
    try:
        payload = await _dispatch(args)
    except _InvalidArgumentsError as exc:
        _print_error("invalid_arguments", str(exc))
        return EXIT_INVALID_ARGS
    except EmailAlreadyExistsError:
        _print_error("email_taken", "Ya existe una cuenta con ese correo")
        return EXIT_CONFLICT
    except (_UserNotFoundError, user_service.UserNotFoundError):
        _print_error("user_not_found", "No existe una cuenta con ese correo")
        return EXIT_NOT_FOUND
    except InvalidPositionError as exc:
        _print_error("invalid_arguments", str(exc))
        return EXIT_INVALID_ARGS
    except DuplicateEmployeeError as exc:
        _print_error("employee_duplicated", str(exc))
        return EXIT_CONFLICT
    except EmployeeNotFoundError as exc:
        _print_error("employee_not_found", str(exc))
        return EXIT_NOT_FOUND
    except InvalidAreaError as exc:
        _print_error("invalid_area", str(exc))
        return EXIT_INVALID_ARGS
    except InvalidStatusError as exc:
        _print_error("invalid_status", str(exc))
        return EXIT_INVALID_ARGS
    except catalog_service.InvalidNameError as exc:
        _print_error("invalid_name", str(exc))
        return EXIT_INVALID_ARGS
    except catalog_service.DuplicateEntryError as exc:
        _print_error(f"{_ENTITY_CODE[exc.entity_label]}_duplicated", str(exc))
        return EXIT_CONFLICT
    except catalog_service.EntryNotFoundError as exc:
        _print_error(f"{_ENTITY_CODE[exc.entity_label]}_not_found", str(exc))
        return EXIT_NOT_FOUND
    except catalog_service.LastEnabledEntryError as exc:
        _print_error(f"last_enabled_{_ENTITY_CODE[exc.entity_label]}", str(exc))
        return EXIT_CONFLICT
    except history_service.EntityNotFoundError:
        _print_error("entity_not_found", "No existe una entidad de ese tipo con ese id")
        return EXIT_NOT_FOUND
    except history_service.EntityTypeRequiredError:
        _print_error("invalid_arguments", "entity-id requiere especificar entity-type")
        return EXIT_INVALID_ARGS
    except _InvalidDaysError as exc:
        _print_error("invalid_days", str(exc))
        return EXIT_INVALID_ARGS
    except _ConfirmationRequiredError as exc:
        _print_error("confirmation_required", str(exc))
        return EXIT_INVALID_ARGS
    except schedule_service.RangeConflictError as exc:
        error = {
            "status": "error",
            "code": "range_conflict",
            "message": str(exc),
            "overlapping_dates": exc.dates,
        }
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return EXIT_CONFLICT
    except schedule_service.DayConflictError as exc:
        _print_error("range_conflict", str(exc))
        return EXIT_CONFLICT
    except schedule_service.StaleScheduleUpdateError as exc:
        _print_error("stale_update", str(exc))
        return EXIT_CONFLICT
    except schedule_service.NonBusinessDayError as exc:
        _print_error("non_business_day", str(exc))
        return EXIT_INVALID_ARGS
    except schedule_service.InvalidRangeError as exc:
        _print_error("invalid_range", str(exc))
        return EXIT_INVALID_ARGS
    except Exception as exc:  # infraestructura/imprevisto
        _print_error("unexpected_error", str(exc))
        return EXIT_UNEXPECTED

    _print_success(payload)
    return EXIT_OK


async def run(argv: list[str] | None = None) -> int:
    """Parsea, despacha e imprime. Asume que ya hay una conexión Mongo activa."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else EXIT_OK

    return await _execute(args)


async def _main_async(argv: list[str] | None) -> int:
    await connect_to_mongo()
    try:
        return await run(argv)
    finally:
        await close_mongo_connection()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main_async(argv))


if __name__ == "__main__":
    sys.exit(main())
