import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from conftest import mongo_test_session
from src.core.security import verify_password
from src.models.history import list_entries
from src.models.session import find_session_by_token, insert_session
from src.models.user import ensure_indexes, find_user_by_email, insert_user
from src.services import history_service, user_service

ACTOR = {"_id": "admin-id", "full_name": "Admin Uno"}


def _make_user(email: str, is_active: bool = True) -> dict[str, Any]:
    return {
        "full_name": "Ana Pérez",
        "email": email,
        "password_hash": "hash-irrelevante",
        "role": "lider",
        "is_active": is_active,
    }


def _make_session(user_id: Any, token: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        "session_token": token,
        "user_id": user_id,
        "created_at": now,
        "last_activity_at": now,
        "expires_at": now + timedelta(minutes=30),
    }


def test_deactivate_user_marks_inactive_and_creates_history_entry(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("ana@hispacontact.com"))

            result = await user_service.deactivate_user(ACTOR, "ana@hispacontact.com")

            assert result == {
                "email": "ana@hispacontact.com",
                "is_active": False,
                "sessions_invalidated": 0,
            }

            user = await find_user_by_email("ana@hispacontact.com")
            assert user["is_active"] is False

            entries = await list_entries({"entity_type": "user", "entity_id": user_id})
            assert len(entries) == 1
            entry = entries[0]
            assert entry["action"] == "deactivate"
            assert entry["actor_id"] == "admin-id"
            assert entry["actor_name"] == "Admin Uno"
            assert entry["changes"] == [
                {"field": "is_active", "old_value": True, "new_value": False}
            ]

    asyncio.run(scenario())


def test_deactivate_user_invalidates_active_sessions(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("ana@hispacontact.com"))
            token_a, token_b = "token-a", "token-b"
            await insert_session(_make_session(user_id, token_a))
            await insert_session(_make_session(user_id, token_b))

            result = await user_service.deactivate_user(ACTOR, "ana@hispacontact.com")

            assert result["sessions_invalidated"] == 2
            assert await find_session_by_token(token_a) is None
            assert await find_session_by_token(token_b) is None

    asyncio.run(scenario())


def test_deactivate_user_not_found_raises(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()

            with pytest.raises(user_service.UserNotFoundError):
                await user_service.deactivate_user(ACTOR, "no-existe@hispacontact.com")

    asyncio.run(scenario())


def test_deactivate_user_atomicity_reverts_when_history_insert_fails(
    use_test_db, monkeypatch
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("ana@hispacontact.com"))
            await insert_session(_make_session(user_id, "token-a"))

            async def failing_insert_entry(document, session=None):
                raise RuntimeError("boom")

            monkeypatch.setattr(history_service, "insert_entry", failing_insert_entry)

            with pytest.raises(RuntimeError):
                await user_service.deactivate_user(ACTOR, "ana@hispacontact.com")

            user = await find_user_by_email("ana@hispacontact.com")
            assert user["is_active"] is True
            assert await find_session_by_token("token-a") is not None

    asyncio.run(scenario())


def test_reset_password_generates_new_password_and_creates_history_entry(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("ana@hispacontact.com"))

            result = await user_service.reset_password(ACTOR, "ana@hispacontact.com")

            assert result["email"] == "ana@hispacontact.com"
            assert result["sessions_invalidated"] == 0
            assert "temporary_password" in result

            user = await find_user_by_email("ana@hispacontact.com")
            assert verify_password(result["temporary_password"], user["password_hash"])

            entries = await list_entries({"entity_type": "user", "entity_id": user_id})
            assert len(entries) == 1
            entry = entries[0]
            assert entry["action"] == "reset_password"
            assert entry["actor_id"] == "admin-id"
            assert entry["actor_name"] == "Admin Uno"
            assert entry["changes"] == [
                {"field": "password_hash", "old_value": None, "new_value": None}
            ]

    asyncio.run(scenario())


def test_reset_password_invalidates_active_sessions(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("ana@hispacontact.com"))
            token_a, token_b = "token-a", "token-b"
            await insert_session(_make_session(user_id, token_a))
            await insert_session(_make_session(user_id, token_b))

            result = await user_service.reset_password(ACTOR, "ana@hispacontact.com")

            assert result["sessions_invalidated"] == 2
            assert await find_session_by_token(token_a) is None
            assert await find_session_by_token(token_b) is None

    asyncio.run(scenario())


def test_reset_password_not_found_raises(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()

            with pytest.raises(user_service.UserNotFoundError):
                await user_service.reset_password(ACTOR, "no-existe@hispacontact.com")

    asyncio.run(scenario())


def test_reset_password_atomicity_reverts_when_history_insert_fails(
    use_test_db, monkeypatch
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("ana@hispacontact.com"))
            await insert_session(_make_session(user_id, "token-a"))
            original_user = await find_user_by_email("ana@hispacontact.com")

            async def failing_insert_entry(document, session=None):
                raise RuntimeError("boom")

            monkeypatch.setattr(history_service, "insert_entry", failing_insert_entry)

            with pytest.raises(RuntimeError):
                await user_service.reset_password(ACTOR, "ana@hispacontact.com")

            user = await find_user_by_email("ana@hispacontact.com")
            assert user["password_hash"] == original_user["password_hash"]
            assert await find_session_by_token("token-a") is not None

    asyncio.run(scenario())
