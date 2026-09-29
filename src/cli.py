"""CLI de administración (RF-2, RF-3, RF-7): interfaz alternativa a la API HTTP.

Solo parsea argumentos e imprime resultados; toda la lógica de negocio vive
en `services/` y `models/`, igual que en `api/routes/` (constitución #3).
"""

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from src.core.database import close_mongo_connection, connect_to_mongo
from src.models.catalog import find_entry_by_name
from src.models.user import find_user_by_email, update_user
from src.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate
from src.schemas.history import HistoryQuery
from src.schemas.user import UserCreate
from src.services.auth_service import EmailAlreadyExistsError, register_user
from src.services import catalog_service, history_service, user_service
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


class _InvalidArgumentsError(Exception):
    pass


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

    unlock_user = subparsers.add_parser("unlock-user", help="Desbloquea una cuenta bloqueada")
    unlock_user.add_argument("--email", required=True)

    deactivate_user = subparsers.add_parser("deactivate-user", help="Desactiva una cuenta")
    deactivate_user.add_argument("--email", required=True)

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


def _entry_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(entry["_id"]), "name": entry["name"], "is_enabled": entry["is_enabled"]}


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
    return {"entry": _entry_payload(entry)}


async def _list_catalog_entries(collection_name: str, enabled: bool | None) -> dict[str, Any]:
    entries = await catalog_service.list_entries(collection_name, enabled)
    return {"entries": [_entry_payload(entry) for entry in entries]}


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
    return {"entry": _entry_payload(entry)}


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
    payload: dict[str, Any] = {"entry": _entry_payload(entry)}
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


def _enabled_filter(args: argparse.Namespace) -> bool | None:
    if getattr(args, "enabled_flag", False):
        return True
    if getattr(args, "disabled_flag", False):
        return False
    return None


async def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "create-admin":
        return await _create_admin(args.name, args.email)
    if args.command == "unlock-user":
        return await _unlock_user(args.email)
    if args.command == "deactivate-user":
        return await _deactivate_user(args.email)
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
    if args.command == "list-statuses":
        return await _list_catalog_entries("estados", _enabled_filter(args))
    if args.command == "update-status":
        return await _update_catalog_entry("estados", "Estado", args.id, args.name)
    if args.command == "enable-status":
        return await _set_catalog_enabled("estados", "Estado", args.id, True)
    if args.command == "disable-status":
        return await _set_catalog_enabled("estados", "Estado", args.id, False)
    return await _list_history(
        args.entity_type, args.entity_id, args.actor_id, args.date_from, args.date_to
    )


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
