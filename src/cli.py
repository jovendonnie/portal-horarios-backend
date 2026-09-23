"""CLI de administración (RF-2, RF-3, RF-7): interfaz alternativa a la API HTTP.

Solo parsea argumentos e imprime resultados; toda la lógica de negocio vive
en `services/` y `models/`, igual que en `api/routes/` (constitución #3).
"""

import argparse
import asyncio
import json
import re
import sys
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from src.core.database import close_mongo_connection, connect_to_mongo
from src.models.session import delete_sessions_by_user
from src.models.user import find_user_by_email, update_user
from src.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate
from src.schemas.user import UserCreate
from src.services.auth_service import EmailAlreadyExistsError, register_user
from src.services.employee_service import (
    DuplicateEmployeeError,
    EmployeeNotFoundError,
    InvalidPositionError,
    create_employee,
    list_employees,
    update_employee,
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_CONFLICT = 2
EXIT_NOT_FOUND = 3
EXIT_INVALID_ARGS = 4


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

    subparsers.add_parser("list-employees", help="Lista los empleados")

    update_employee_parser = subparsers.add_parser("update-employee", help="Edita un empleado")
    update_employee_parser.add_argument("--id", required=True)
    update_employee_parser.add_argument("--name")
    update_employee_parser.add_argument("--position")
    update_employee_parser.add_argument("--area")

    return parser


async def _create_admin(name: str, email: str) -> dict[str, Any]:
    _validate_email(email)
    data = UserCreate.model_construct(full_name=name, email=email, role="admin")
    result = await register_user({"_id": None}, data)
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
    user = await find_user_by_email(email)
    if user is None:
        raise _UserNotFoundError(email)

    await update_user(email, {"is_active": False})
    sessions_invalidated = await delete_sessions_by_user(user["_id"])
    return {"email": email, "is_active": False, "sessions_invalidated": sessions_invalidated}


def _employee_payload(employee: EmployeeOut) -> dict[str, Any]:
    return {
        "id": employee.id,
        "full_name": employee.full_name,
        "position": employee.position,
        "area": employee.area,
        "is_active": employee.is_active,
    }


async def _create_employee(name: str, position: str, area: str) -> dict[str, Any]:
    data = EmployeeCreate.model_construct(full_name=name, position=position, area=area)
    employee = await create_employee({"_id": None}, data)
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
        changes_kwargs["area"] = area
    changes = EmployeeUpdate.model_construct(**changes_kwargs)

    employee = await update_employee({"_id": None}, object_id, changes)
    return {"employee": _employee_payload(employee)}


async def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "create-admin":
        return await _create_admin(args.name, args.email)
    if args.command == "unlock-user":
        return await _unlock_user(args.email)
    if args.command == "deactivate-user":
        return await _deactivate_user(args.email)
    if args.command == "create-employee":
        return await _create_employee(args.name, args.position, args.area)
    if args.command == "list-employees":
        return await _list_employees()
    return await _update_employee(args.id, args.name, args.position, args.area)


async def _execute(args: argparse.Namespace) -> int:
    try:
        payload = await _dispatch(args)
    except _InvalidArgumentsError as exc:
        _print_error("invalid_arguments", str(exc))
        return EXIT_INVALID_ARGS
    except EmailAlreadyExistsError:
        _print_error("email_taken", "Ya existe una cuenta con ese correo")
        return EXIT_CONFLICT
    except _UserNotFoundError:
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
