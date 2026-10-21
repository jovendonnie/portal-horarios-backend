import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from bson import ObjectId
from conftest import mongo_test_session

from src.core.security import hash_password, verify_password
from src.models import catalog as catalog_model
from src.models.catalog import ensure_indexes as ensure_catalog_indexes
from src.models.employee import ensure_indexes as ensure_employee_indexes
from src.models.history import list_entries
from src.models.session import find_session_by_token, insert_session
from src.models.user import ensure_indexes, find_user_by_email, insert_user
from src import cli

CATALOG_COMMANDS = [
    {
        "create": "create-area",
        "list": "list-areas",
        "update": "update-area",
        "enable": "enable-area",
        "disable": "disable-area",
        "collection_name": "areas",
        "duplicated": "area_duplicated",
        "not_found": "area_not_found",
        "last_enabled": "last_enabled_area",
    },
    {
        "create": "create-status",
        "list": "list-statuses",
        "update": "update-status",
        "enable": "enable-status",
        "disable": "disable-status",
        "collection_name": "estados",
        "duplicated": "status_duplicated",
        "not_found": "status_not_found",
        "last_enabled": "last_enabled_status",
    },
]


def _make_user(email: str, **overrides: Any) -> dict[str, Any]:
    document = {
        "full_name": "Ana Pérez",
        "email": email,
        "password_hash": hash_password("Secreta123"),
        "role": "lider",
        "is_active": True,
    }
    document.update(overrides)
    return document


async def _seed_catalog_entry(collection_name: str, name: str) -> str:
    """Siembra una entrada de catálogo directamente vía el modelo (sin pasar por la CLI)."""
    entry_id = await catalog_model.insert_entry(
        collection_name, name, "admin-id", datetime.now(timezone.utc)
    )
    return str(entry_id)


async def _seed_disabled_catalog_entry(collection_name: str, name: str) -> str:
    """Siembra una entrada de catálogo ya deshabilitada (necesita otra habilitada para no violar la regla de última entrada)."""
    await _seed_catalog_entry(collection_name, "Otra habilitada")
    entry_id = await _seed_catalog_entry(collection_name, name)
    await catalog_model.set_entry_enabled(
        collection_name, ObjectId(entry_id), False, "admin-id", datetime.now(timezone.utc)
    )
    return entry_id


def test_help_lists_all_subcommands() -> None:
    parser = cli._build_parser()
    help_text = parser.format_help()

    assert "create-admin" in help_text
    assert "create-user" in help_text
    assert "unlock-user" in help_text
    assert "deactivate-user" in help_text
    assert "reset-password" in help_text
    assert "create-employee" in help_text
    assert "list-employees" in help_text
    assert "update-employee" in help_text
    assert "set-employee-status" in help_text
    assert "list-history" in help_text
    assert "seed-predefined-statuses" in help_text
    assert "ensure-indexes" in help_text
    assert "show-default-schedule" in help_text
    assert "set-default-schedule" in help_text
    assert "show-week-schedule" in help_text
    assert "set-day-status" in help_text
    assert "revert-day-status" in help_text
    assert "set-range-status" in help_text
    assert "list-users" in help_text
    for commands in CATALOG_COMMANDS:
        assert commands["create"] in help_text
        assert commands["list"] in help_text
        assert commands["update"] in help_text
        assert commands["enable"] in help_text
        assert commands["disable"] in help_text


def test_create_admin_success_returns_ok_and_temporary_password(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run(
                ["create-admin", "--name", "Ana Pérez", "--email", "ana@hispacontact.com"]
            )

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert payload["user"]["email"] == "ana@hispacontact.com"
            assert payload["user"]["role"] == "admin"
            assert "temporary_password" in payload

            user = await find_user_by_email("ana@hispacontact.com")
            assert user["role"] == "admin"
            assert verify_password(payload["temporary_password"], user["password_hash"])

    asyncio.run(scenario())


def test_create_admin_duplicate_email_returns_conflict_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()

            first = await cli.run(
                ["create-admin", "--name", "Ana Pérez", "--email", "ana@hispacontact.com"]
            )
            assert first == 0
            capsys.readouterr()

            second = await cli.run(
                ["create-admin", "--name", "Ana Pérez", "--email", "ana@hispacontact.com"]
            )

            assert second == 2
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "email_taken"

    asyncio.run(scenario())


@pytest.mark.parametrize("role", ["gestion_humana", "lider"])
def test_create_user_success_returns_ok_and_temporary_password(use_test_db, capsys, role) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run(
                [
                    "create-user",
                    "--name",
                    "Ana Pérez",
                    "--email",
                    "ana@hispacontact.com",
                    "--role",
                    role,
                ]
            )

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert payload["user"]["email"] == "ana@hispacontact.com"
            assert payload["user"]["role"] == role
            assert "temporary_password" in payload

            user = await find_user_by_email("ana@hispacontact.com")
            assert user["role"] == role
            assert verify_password(payload["temporary_password"], user["password_hash"])

    asyncio.run(scenario())


def test_create_user_invalid_role_returns_invalid_arguments_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run(
                [
                    "create-user",
                    "--name",
                    "Ana Pérez",
                    "--email",
                    "ana@hispacontact.com",
                    "--role",
                    "gerente",
                ]
            )

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_arguments"

    asyncio.run(scenario())


def test_create_user_duplicate_email_returns_conflict_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()

            create_args = [
                "create-user",
                "--name",
                "Ana Pérez",
                "--email",
                "ana@hispacontact.com",
                "--role",
                "lider",
            ]
            first = await cli.run(create_args)
            assert first == 0
            capsys.readouterr()

            second = await cli.run(create_args)

            assert second == 2
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "email_taken"

    asyncio.run(scenario())


def test_unlock_user_clears_lock_fields(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            locked_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=10)
            await insert_user(
                _make_user(
                    "bloqueada@hispacontact.com",
                    failed_login_attempts=5,
                    locked_until=locked_until,
                )
            )

            exit_code = await cli.run(["unlock-user", "--email", "bloqueada@hispacontact.com"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert payload["locked_until"] is None

            user = await find_user_by_email("bloqueada@hispacontact.com")
            assert user["locked_until"] is None
            assert user["failed_login_attempts"] == 0

    asyncio.run(scenario())


def test_unlock_user_not_found_returns_not_found_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run(["unlock-user", "--email", "no-existe@hispacontact.com"])

            assert exit_code == 3
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "user_not_found"

    asyncio.run(scenario())


def test_deactivate_user_invalidates_active_sessions_and_returns_count(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            user_id = await insert_user(_make_user("activa@hispacontact.com"))
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            token_a = "token-a"
            token_b = "token-b"
            for token in (token_a, token_b):
                await insert_session(
                    {
                        "session_token": token,
                        "user_id": user_id,
                        "created_at": now,
                        "last_activity_at": now,
                        "expires_at": now + timedelta(minutes=30),
                    }
                )

            exit_code = await cli.run(["deactivate-user", "--email", "activa@hispacontact.com"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert payload["is_active"] is False
            assert payload["sessions_invalidated"] == 2

            user = await find_user_by_email("activa@hispacontact.com")
            assert user["is_active"] is False
            assert await find_session_by_token(token_a) is None
            assert await find_session_by_token(token_b) is None

    asyncio.run(scenario())


def test_deactivate_user_not_found_returns_not_found_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run(["deactivate-user", "--email", "no-existe@hispacontact.com"])

            assert exit_code == 3
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "user_not_found"

    asyncio.run(scenario())


def test_reset_password_success_invalidates_sessions_and_returns_temporary_password(
    use_test_db, capsys
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            user_id = await insert_user(_make_user("activa@hispacontact.com"))
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            token_a, token_b = "token-a", "token-b"
            for token in (token_a, token_b):
                await insert_session(
                    {
                        "session_token": token,
                        "user_id": user_id,
                        "created_at": now,
                        "last_activity_at": now,
                        "expires_at": now + timedelta(minutes=30),
                    }
                )

            exit_code = await cli.run(["reset-password", "--email", "activa@hispacontact.com"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert payload["email"] == "activa@hispacontact.com"
            assert payload["sessions_invalidated"] == 2
            assert "temporary_password" in payload

            user = await find_user_by_email("activa@hispacontact.com")
            assert verify_password(payload["temporary_password"], user["password_hash"])
            assert await find_session_by_token(token_a) is None
            assert await find_session_by_token(token_b) is None

    asyncio.run(scenario())


def test_reset_password_not_found_returns_not_found_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run(["reset-password", "--email", "no-existe@hispacontact.com"])

            assert exit_code == 3
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "user_not_found"

    asyncio.run(scenario())


def test_missing_required_argument_returns_invalid_arguments_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run(["unlock-user"])

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_arguments"

    asyncio.run(scenario())


def test_invalid_email_format_returns_invalid_arguments_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run(["unlock-user", "--email", "no-es-un-correo"])

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_arguments"

    asyncio.run(scenario())


def test_create_employee_success_returns_ok_and_employee(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_employee_indexes()
            await _seed_catalog_entry("areas", "Ventas")
            await _seed_catalog_entry("estados", "Presencial")

            exit_code = await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Carla Gómez",
                    "--position",
                    "lider",
                    "--area",
                    "Ventas",
                    "--status",
                    "Presencial",
                ]
            )

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert payload["employee"]["full_name"] == "Carla Gómez"
            assert payload["employee"]["position"] == "lider"
            assert payload["employee"]["area"] == "Ventas"
            assert payload["employee"]["status"] == "Presencial"
            assert payload["employee"]["is_active"] is True

    asyncio.run(scenario())


def test_create_employee_duplicate_returns_conflict_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_employee_indexes()
            await _seed_catalog_entry("areas", "Ventas")
            await _seed_catalog_entry("estados", "Presencial")

            create_args = [
                "create-employee",
                "--name",
                "Carla Gómez",
                "--position",
                "lider",
                "--area",
                "Ventas",
                "--status",
                "Presencial",
            ]
            first = await cli.run(create_args)
            assert first == 0
            capsys.readouterr()

            second = await cli.run(create_args)

            assert second == 2
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "employee_duplicated"

    asyncio.run(scenario())


def test_create_employee_invalid_position_returns_invalid_arguments_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("areas", "Ventas")
            await _seed_catalog_entry("estados", "Presencial")

            exit_code = await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Carla Gómez",
                    "--position",
                    "gerente",
                    "--area",
                    "Ventas",
                    "--status",
                    "Presencial",
                ]
            )

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_arguments"
            assert "gerente" in payload["message"]

    asyncio.run(scenario())


def test_create_employee_invalid_area_returns_invalid_arguments_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("estados", "Presencial")

            exit_code = await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Carla Gómez",
                    "--position",
                    "lider",
                    "--area",
                    "NoExiste",
                    "--status",
                    "Presencial",
                ]
            )

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_area"

    asyncio.run(scenario())


def test_create_employee_disabled_area_returns_invalid_arguments_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_disabled_catalog_entry("areas", "Ventas")
            await _seed_catalog_entry("estados", "Presencial")

            exit_code = await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Carla Gómez",
                    "--position",
                    "lider",
                    "--area",
                    "Ventas",
                    "--status",
                    "Presencial",
                ]
            )

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_area"

    asyncio.run(scenario())


def test_create_employee_invalid_status_returns_invalid_arguments_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("areas", "Ventas")

            exit_code = await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Carla Gómez",
                    "--position",
                    "lider",
                    "--area",
                    "Ventas",
                    "--status",
                    "NoExiste",
                ]
            )

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_status"

    asyncio.run(scenario())


def test_create_employee_disabled_status_returns_invalid_arguments_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("areas", "Ventas")
            await _seed_disabled_catalog_entry("estados", "Presencial")

            exit_code = await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Carla Gómez",
                    "--position",
                    "lider",
                    "--area",
                    "Ventas",
                    "--status",
                    "Presencial",
                ]
            )

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_status"

    asyncio.run(scenario())


def test_list_employees_returns_all_existing(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("areas", "Ventas")
            await _seed_catalog_entry("areas", "RRHH")
            await _seed_catalog_entry("estados", "Presencial")

            await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Empleado Uno",
                    "--position",
                    "lider",
                    "--area",
                    "Ventas",
                    "--status",
                    "Presencial",
                ]
            )
            capsys.readouterr()
            await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Empleado Dos",
                    "--position",
                    "recursos_humanos",
                    "--area",
                    "RRHH",
                    "--status",
                    "Presencial",
                ]
            )
            capsys.readouterr()

            exit_code = await cli.run(["list-employees"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            names = {employee["full_name"] for employee in payload["employees"]}
            assert names == {"Empleado Uno", "Empleado Dos"}

    asyncio.run(scenario())


def test_update_employee_success_returns_updated_fields(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("areas", "Ventas")
            await _seed_catalog_entry("areas", "Marketing")
            await _seed_catalog_entry("estados", "Presencial")

            await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Carla Gómez",
                    "--position",
                    "lider",
                    "--area",
                    "Ventas",
                    "--status",
                    "Presencial",
                ]
            )
            created = json.loads(capsys.readouterr().out)["employee"]

            exit_code = await cli.run(["update-employee", "--id", created["id"], "--area", "Marketing"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert payload["employee"]["area"] == "Marketing"
            assert payload["employee"]["full_name"] == "Carla Gómez"
            assert payload["employee"]["position"] == "lider"
            assert payload["employee"]["status"] == "Presencial"

    asyncio.run(scenario())


def test_update_employee_not_found_returns_not_found_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("areas", "Marketing")

            exit_code = await cli.run(["update-employee", "--id", str(ObjectId()), "--area", "Marketing"])

            assert exit_code == 3
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "employee_not_found"

    asyncio.run(scenario())


def test_update_employee_invalid_position_returns_invalid_arguments_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("areas", "Ventas")
            await _seed_catalog_entry("estados", "Presencial")

            await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Carla Gómez",
                    "--position",
                    "lider",
                    "--area",
                    "Ventas",
                    "--status",
                    "Presencial",
                ]
            )
            created = json.loads(capsys.readouterr().out)["employee"]

            exit_code = await cli.run(["update-employee", "--id", created["id"], "--position", "gerente"])

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_arguments"

    asyncio.run(scenario())


def test_update_employee_invalid_area_returns_invalid_arguments_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("areas", "Ventas")
            await _seed_catalog_entry("estados", "Presencial")

            await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Carla Gómez",
                    "--position",
                    "lider",
                    "--area",
                    "Ventas",
                    "--status",
                    "Presencial",
                ]
            )
            created = json.loads(capsys.readouterr().out)["employee"]

            exit_code = await cli.run(["update-employee", "--id", created["id"], "--area", "NoExiste"])

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_area"

    asyncio.run(scenario())


def test_update_employee_disabled_area_returns_invalid_arguments_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("areas", "Ventas")
            await _seed_catalog_entry("estados", "Presencial")
            await _seed_disabled_catalog_entry("areas", "Marketing")

            await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Carla Gómez",
                    "--position",
                    "lider",
                    "--area",
                    "Ventas",
                    "--status",
                    "Presencial",
                ]
            )
            created = json.loads(capsys.readouterr().out)["employee"]

            exit_code = await cli.run(["update-employee", "--id", created["id"], "--area", "Marketing"])

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_area"

    asyncio.run(scenario())


def test_set_employee_status_success_returns_ok_and_updated_status(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("areas", "Ventas")
            await _seed_catalog_entry("estados", "Presencial")
            await _seed_catalog_entry("estados", "Vacaciones")

            await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Carla Gómez",
                    "--position",
                    "lider",
                    "--area",
                    "Ventas",
                    "--status",
                    "Presencial",
                ]
            )
            created = json.loads(capsys.readouterr().out)["employee"]

            exit_code = await cli.run(
                ["set-employee-status", "--id", created["id"], "--status", "Vacaciones"]
            )

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert payload["employee"]["id"] == created["id"]
            assert payload["employee"]["status"] == "Vacaciones"
            assert payload["employee"]["status_updated_at"] is not None
            assert payload["employee"]["status_updated_by"] is None

    asyncio.run(scenario())


def test_set_employee_status_not_found_returns_not_found_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("estados", "Vacaciones")

            exit_code = await cli.run(
                ["set-employee-status", "--id", str(ObjectId()), "--status", "Vacaciones"]
            )

            assert exit_code == 3
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "employee_not_found"

    asyncio.run(scenario())


def test_set_employee_status_invalid_status_returns_invalid_arguments_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("areas", "Ventas")
            await _seed_catalog_entry("estados", "Presencial")

            await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Carla Gómez",
                    "--position",
                    "lider",
                    "--area",
                    "Ventas",
                    "--status",
                    "Presencial",
                ]
            )
            created = json.loads(capsys.readouterr().out)["employee"]

            exit_code = await cli.run(
                ["set-employee-status", "--id", created["id"], "--status", "NoExiste"]
            )

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_status"

    asyncio.run(scenario())


def test_set_employee_status_disabled_status_returns_invalid_arguments_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_catalog_entry("areas", "Ventas")
            await _seed_catalog_entry("estados", "Presencial")

            await cli.run(
                [
                    "create-employee",
                    "--name",
                    "Carla Gómez",
                    "--position",
                    "lider",
                    "--area",
                    "Ventas",
                    "--status",
                    "Presencial",
                ]
            )
            created = json.loads(capsys.readouterr().out)["employee"]

            await _seed_disabled_catalog_entry("estados", "Vacaciones")

            exit_code = await cli.run(
                ["set-employee-status", "--id", created["id"], "--status", "Vacaciones"]
            )

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_status"

    asyncio.run(scenario())


@pytest.mark.parametrize("commands", CATALOG_COMMANDS)
def test_create_catalog_entry_success(use_test_db, capsys, commands) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_catalog_indexes(commands["collection_name"])

            exit_code = await cli.run([commands["create"], "--name", "Ventas"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert payload["entry"]["name"] == "Ventas"
            assert payload["entry"]["is_enabled"] is True

    asyncio.run(scenario())


@pytest.mark.parametrize("commands", CATALOG_COMMANDS)
def test_create_catalog_entry_duplicate_returns_conflict_exit_code(use_test_db, capsys, commands) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_catalog_indexes(commands["collection_name"])
            await cli.run([commands["create"], "--name", "Ventas"])
            capsys.readouterr()

            exit_code = await cli.run([commands["create"], "--name", "Ventas"])

            assert exit_code == 2
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == commands["duplicated"]

    asyncio.run(scenario())


@pytest.mark.parametrize("commands", CATALOG_COMMANDS)
def test_create_catalog_entry_invalid_name_returns_invalid_args_exit_code(
    use_test_db, capsys, commands
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run([commands["create"], "--name", ""])

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_name"

    asyncio.run(scenario())


@pytest.mark.parametrize("commands", CATALOG_COMMANDS)
def test_list_catalog_entries_returns_all(use_test_db, capsys, commands) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await cli.run([commands["create"], "--name", "Ventas"])
            capsys.readouterr()
            await cli.run([commands["create"], "--name", "Soporte"])
            capsys.readouterr()

            exit_code = await cli.run([commands["list"]])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            names = {entry["name"] for entry in payload["entries"]}
            assert names == {"Ventas", "Soporte"}

    asyncio.run(scenario())


@pytest.mark.parametrize("commands", CATALOG_COMMANDS)
def test_list_catalog_entries_filters_by_disabled(use_test_db, capsys, commands) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await cli.run([commands["create"], "--name", "Ventas"])
            capsys.readouterr()
            await cli.run([commands["create"], "--name", "Soporte"])
            created = json.loads(capsys.readouterr().out)["entry"]
            await cli.run([commands["disable"], "--id", created["id"]])
            capsys.readouterr()

            exit_code = await cli.run([commands["list"], "--disabled"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            names = {entry["name"] for entry in payload["entries"]}
            assert names == {"Soporte"}

    asyncio.run(scenario())


@pytest.mark.parametrize("commands", CATALOG_COMMANDS)
def test_update_catalog_entry_success(use_test_db, capsys, commands) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await cli.run([commands["create"], "--name", "Ventas"])
            created = json.loads(capsys.readouterr().out)["entry"]

            exit_code = await cli.run(
                [commands["update"], "--id", created["id"], "--name", "Comercial"]
            )

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert payload["entry"]["name"] == "Comercial"

    asyncio.run(scenario())


@pytest.mark.parametrize("commands", CATALOG_COMMANDS)
def test_update_catalog_entry_not_found_returns_not_found_exit_code(
    use_test_db, capsys, commands
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run(
                [commands["update"], "--id", str(ObjectId()), "--name", "Comercial"]
            )

            assert exit_code == 3
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == commands["not_found"]

    asyncio.run(scenario())


@pytest.mark.parametrize("commands", CATALOG_COMMANDS)
def test_disable_catalog_entry_success_returns_affected_employees(
    use_test_db, capsys, commands
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await cli.run([commands["create"], "--name", "Ventas"])
            created = json.loads(capsys.readouterr().out)["entry"]
            await cli.run([commands["create"], "--name", "Soporte"])
            capsys.readouterr()

            exit_code = await cli.run([commands["disable"], "--id", created["id"]])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert payload["entry"]["is_enabled"] is False
            assert payload["affected_employees"] == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("commands", CATALOG_COMMANDS)
def test_disable_catalog_entry_last_enabled_returns_conflict_exit_code(
    use_test_db, capsys, commands
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await cli.run([commands["create"], "--name", "Ventas"])
            created = json.loads(capsys.readouterr().out)["entry"]

            exit_code = await cli.run([commands["disable"], "--id", created["id"]])

            assert exit_code == 2
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == commands["last_enabled"]

    asyncio.run(scenario())


@pytest.mark.parametrize("commands", CATALOG_COMMANDS)
def test_disable_catalog_entry_not_found_returns_not_found_exit_code(
    use_test_db, capsys, commands
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run([commands["disable"], "--id", str(ObjectId())])

            assert exit_code == 3
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == commands["not_found"]

    asyncio.run(scenario())


@pytest.mark.parametrize("commands", CATALOG_COMMANDS)
def test_enable_catalog_entry_success(use_test_db, capsys, commands) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await cli.run([commands["create"], "--name", "Ventas"])
            created = json.loads(capsys.readouterr().out)["entry"]
            await cli.run([commands["create"], "--name", "Soporte"])
            capsys.readouterr()
            await cli.run([commands["disable"], "--id", created["id"]])
            capsys.readouterr()

            exit_code = await cli.run([commands["enable"], "--id", created["id"]])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert payload["entry"]["is_enabled"] is True

    asyncio.run(scenario())


@pytest.mark.parametrize("commands", CATALOG_COMMANDS)
def test_enable_catalog_entry_not_found_returns_not_found_exit_code(
    use_test_db, capsys, commands
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run([commands["enable"], "--id", str(ObjectId())])

            assert exit_code == 3
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == commands["not_found"]

    asyncio.run(scenario())


def test_seed_predefined_statuses_creates_the_seven(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_catalog_indexes("estados")

            exit_code = await cli.run(["seed-predefined-statuses"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert len(payload["entries"]) == 7
            assert all(entry["is_predefined"] is True for entry in payload["entries"])

    asyncio.run(scenario())


def test_seed_predefined_statuses_is_idempotent(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_catalog_indexes("estados")
            await cli.run(["seed-predefined-statuses"])
            capsys.readouterr()

            exit_code = await cli.run(["seed-predefined-statuses"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert len(payload["entries"]) == 7

    asyncio.run(scenario())


def test_create_status_marks_entry_as_not_predefined(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_catalog_indexes("estados")

            exit_code = await cli.run(["create-status", "--name", "Presencial"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["entry"]["is_predefined"] is False

    asyncio.run(scenario())


def test_create_area_does_not_include_is_predefined(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_catalog_indexes("areas")

            exit_code = await cli.run(["create-area", "--name", "Ventas"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert "is_predefined" not in payload["entry"]

    asyncio.run(scenario())


def test_deactivate_user_creates_history_entry(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_user(_make_user("activa@hispacontact.com"))

            exit_code = await cli.run(["deactivate-user", "--email", "activa@hispacontact.com"])

            assert exit_code == 0
            capsys.readouterr()

            user = await find_user_by_email("activa@hispacontact.com")
            entries = await list_entries({"entity_type": "user", "entity_id": user["_id"]})
            assert len(entries) == 1
            assert entries[0]["action"] == "deactivate"

    asyncio.run(scenario())


def test_list_history_without_filters_returns_all_entries(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await cli.run(["create-area", "--name", "Ventas"])
            capsys.readouterr()

            exit_code = await cli.run(["list-history"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert len(payload["entries"]) == 1
            entry = payload["entries"][0]
            assert entry["entity_type"] == "area"
            assert entry["action"] == "create"
            assert entry["actor_name"] == "CLI"
            assert entry["changes"] == []
            assert "occurred_at" in entry

    asyncio.run(scenario())


def test_list_history_filters_by_entity_type(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await cli.run(["create-area", "--name", "Ventas"])
            capsys.readouterr()
            await cli.run(["create-status", "--name", "Presencial"])
            capsys.readouterr()

            exit_code = await cli.run(["list-history", "--entity-type", "area"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert {entry["entity_type"] for entry in payload["entries"]} == {"area"}

    asyncio.run(scenario())


def test_list_history_with_nonexistent_entity_id_returns_not_found_exit_code(
    use_test_db, capsys
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run(
                ["list-history", "--entity-type", "employee", "--entity-id", str(ObjectId())]
            )

            assert exit_code == 3
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "entity_not_found"

    asyncio.run(scenario())


def test_list_history_with_entity_id_without_entity_type_returns_invalid_arguments_exit_code(
    use_test_db, capsys
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run(["list-history", "--entity-id", str(ObjectId())])

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_arguments"
            assert payload["message"] == "entity-id requiere especificar entity-type"

    asyncio.run(scenario())


def test_list_history_filters_without_matches_returns_ok_and_empty_list(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await cli.run(["create-area", "--name", "Ventas"])
            capsys.readouterr()

            exit_code = await cli.run(["list-history", "--actor-id", str(ObjectId())])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert payload["entries"] == []

    asyncio.run(scenario())


# --- Fase 10: ensure-indexes, horarios, list-users (T046-T051) ---


def _next_monday() -> date:
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7
    return today + timedelta(days=days_ahead)


async def _seed_employee(capsys, area: str = "Ventas", status: str = "Presencial") -> str:
    await ensure_employee_indexes()
    await _seed_catalog_entry("areas", area)
    await _seed_catalog_entry("estados", status)

    await cli.run(
        [
            "create-employee",
            "--name",
            "Carla Gómez",
            "--position",
            "lider",
            "--area",
            area,
            "--status",
            status,
        ]
    )
    created = json.loads(capsys.readouterr().out)["employee"]
    return created["id"]


def test_ensure_indexes_returns_created_collections(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run(["ensure-indexes"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ok"
            assert set(payload["created"]) == {
                "users",
                "employees",
                "areas",
                "estados",
                "history_entries",
                "schedules",
            }
            assert payload["skipped_duplicates"] == []

    asyncio.run(scenario())


def test_show_default_schedule_returns_empty_template_when_not_configured(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = await _seed_employee(capsys)

            exit_code = await cli.run(["show-default-schedule", "--employee-id", employee_id])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["employee_id"] == employee_id
            assert len(payload["days"]) == 5
            assert all(day["works"] is False for day in payload["days"])
            assert payload["updated_at"] is None
            assert payload["updated_by"] is None

    asyncio.run(scenario())


def test_show_default_schedule_employee_not_found_returns_not_found_exit_code(
    use_test_db, capsys
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            exit_code = await cli.run(
                ["show-default-schedule", "--employee-id", str(ObjectId())]
            )

            assert exit_code == 3
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "employee_not_found"

    asyncio.run(scenario())


def test_set_default_schedule_success_returns_updated_days(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = await _seed_employee(capsys)
            days_json = json.dumps(
                [
                    {
                        "weekday": "monday",
                        "works": True,
                        "modality": "presencial",
                        "time_ranges": [{"start": "08:00", "end": "17:00"}],
                    },
                    {"weekday": "tuesday", "works": False, "modality": None, "time_ranges": []},
                    {"weekday": "wednesday", "works": False, "modality": None, "time_ranges": []},
                    {"weekday": "thursday", "works": False, "modality": None, "time_ranges": []},
                    {"weekday": "friday", "works": False, "modality": None, "time_ranges": []},
                ]
            )

            exit_code = await cli.run(
                ["set-default-schedule", "--employee-id", employee_id, "--days-json", days_json]
            )

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            monday = next(day for day in payload["days"] if day["weekday"] == "monday")
            assert monday["works"] is True
            assert monday["modality"] == "presencial"
            assert monday["time_ranges"] == [{"start": "08:00", "end": "17:00"}]

    asyncio.run(scenario())


def test_set_default_schedule_with_malformed_json_returns_invalid_days_exit_code(
    use_test_db, capsys
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = await _seed_employee(capsys)

            exit_code = await cli.run(
                [
                    "set-default-schedule",
                    "--employee-id",
                    employee_id,
                    "--days-json",
                    "no-es-json",
                ]
            )

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_days"

    asyncio.run(scenario())


def test_set_default_schedule_with_incomplete_days_returns_invalid_days_exit_code(
    use_test_db, capsys
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = await _seed_employee(capsys)
            days_json = json.dumps(
                [{"weekday": "monday", "works": False, "modality": None, "time_ranges": []}]
            )

            exit_code = await cli.run(
                ["set-default-schedule", "--employee-id", employee_id, "--days-json", days_json]
            )

            assert exit_code == 4
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "invalid_days"

    asyncio.run(scenario())


def test_show_week_schedule_returns_week_schedule_response(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await _seed_employee(capsys)

            exit_code = await cli.run(["show-week-schedule"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["week_offset"] == 0
            assert "week_start" in payload
            assert "week_end" in payload
            assert "server_today" in payload
            assert len(payload["employees"]) == 1
            assert payload["employees"][0]["full_name"] == "Carla Gómez"
            assert len(payload["employees"][0]["days"]) == 5

    asyncio.run(scenario())


def test_set_day_status_success_returns_day_entry(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = await _seed_employee(capsys)
            await _seed_catalog_entry("estados", "Vacaciones")
            monday = _next_monday().isoformat()

            exit_code = await cli.run(
                [
                    "set-day-status",
                    "--employee-id",
                    employee_id,
                    "--date",
                    monday,
                    "--status",
                    "Vacaciones",
                    "--observation",
                    "Cita médica",
                ]
            )

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["employee_id"] == employee_id
            assert payload["date"] == monday
            assert payload["status_name"] == "Vacaciones"
            assert payload["source"] == "day_override"
            assert payload["observation"] == "Cita médica"

    asyncio.run(scenario())


def test_set_day_status_stale_update_returns_conflict_exit_code(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = await _seed_employee(capsys)
            await _seed_catalog_entry("estados", "Vacaciones")
            monday = _next_monday().isoformat()

            first = await cli.run(
                [
                    "set-day-status",
                    "--employee-id",
                    employee_id,
                    "--date",
                    monday,
                    "--status",
                    "Vacaciones",
                ]
            )
            assert first == 0
            capsys.readouterr()

            second = await cli.run(
                [
                    "set-day-status",
                    "--employee-id",
                    employee_id,
                    "--date",
                    monday,
                    "--status",
                    "Vacaciones",
                ]
            )

            assert second == 2
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "stale_update"

    asyncio.run(scenario())


def test_revert_day_status_without_existing_exception_is_noop(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = await _seed_employee(capsys)
            monday = _next_monday().isoformat()

            exit_code = await cli.run(
                ["revert-day-status", "--employee-id", employee_id, "--date", monday]
            )

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload["employee_id"] == employee_id
            assert payload["date"] == monday
            assert payload["source"] == "default"

    asyncio.run(scenario())


def test_set_range_status_success_returns_days(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = await _seed_employee(capsys)
            await _seed_catalog_entry("estados", "Vacaciones")
            monday = _next_monday()
            tuesday = monday + timedelta(days=1)

            exit_code = await cli.run(
                [
                    "set-range-status",
                    "--employee-id",
                    employee_id,
                    "--start-date",
                    monday.isoformat(),
                    "--end-date",
                    tuesday.isoformat(),
                    "--status",
                    "Vacaciones",
                ]
            )

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert len(payload["days"]) == 2
            assert {day["date"] for day in payload["days"]} == {
                monday.isoformat(),
                tuesday.isoformat(),
            }
            assert all(day["source"] == "range_override" for day in payload["days"])

    asyncio.run(scenario())


def test_set_range_status_conflict_returns_overlapping_dates(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = await _seed_employee(capsys)
            await _seed_catalog_entry("estados", "Vacaciones")
            monday = _next_monday()
            tuesday = monday + timedelta(days=1)
            wednesday = monday + timedelta(days=2)

            await cli.run(
                [
                    "set-day-status",
                    "--employee-id",
                    employee_id,
                    "--date",
                    tuesday.isoformat(),
                    "--status",
                    "Vacaciones",
                ]
            )
            capsys.readouterr()

            exit_code = await cli.run(
                [
                    "set-range-status",
                    "--employee-id",
                    employee_id,
                    "--start-date",
                    monday.isoformat(),
                    "--end-date",
                    wednesday.isoformat(),
                    "--status",
                    "Vacaciones",
                ]
            )

            assert exit_code == 2
            payload = json.loads(capsys.readouterr().err)
            assert payload["status"] == "error"
            assert payload["code"] == "range_conflict"
            assert payload["overlapping_dates"] == [tuesday.isoformat()]

    asyncio.run(scenario())


def test_list_users_excludes_password_hash_and_canonicalizes_role(use_test_db, capsys) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await insert_user(_make_user("admin-legacy@hispacontact.com", role="admin"))
            await insert_user(_make_user("lider@hispacontact.com", role="lider"))

            exit_code = await cli.run(["list-users"])

            assert exit_code == 0
            payload = json.loads(capsys.readouterr().out)
            assert len(payload["users"]) == 2
            for user in payload["users"]:
                assert "password_hash" not in user
            roles = {user["email"]: user["role"] for user in payload["users"]}
            assert roles["admin-legacy@hispacontact.com"] == "gestion_humana"
            assert roles["lider@hispacontact.com"] == "lider"

    asyncio.run(scenario())
