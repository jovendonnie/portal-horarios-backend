import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from conftest import mongo_test_session

from src.core.security import hash_password, verify_password
from src.models.session import find_session_by_token, insert_session
from src.models.user import ensure_indexes, find_user_by_email, insert_user
from src import cli


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


def test_help_lists_all_subcommands() -> None:
    parser = cli._build_parser()
    help_text = parser.format_help()

    assert "create-admin" in help_text
    assert "unlock-user" in help_text
    assert "deactivate-user" in help_text


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
