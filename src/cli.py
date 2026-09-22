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

from src.core.database import close_mongo_connection, connect_to_mongo
from src.models.session import delete_sessions_by_user
from src.models.user import find_user_by_email, update_user
from src.schemas.user import UserCreate
from src.services.auth_service import EmailAlreadyExistsError, register_user

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


async def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "create-admin":
        return await _create_admin(args.name, args.email)
    if args.command == "unlock-user":
        return await _unlock_user(args.email)
    return await _deactivate_user(args.email)


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
