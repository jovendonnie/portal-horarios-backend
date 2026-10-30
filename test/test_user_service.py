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


def test_list_users_normalizes_legacy_admin_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await insert_user({**_make_user("admin-legacy@hispacontact.com"), "role": "admin"})

            users = await user_service.list_users()

            assert len(users) == 1
            assert users[0].role == "gestion_humana"

    asyncio.run(scenario())


def test_list_users_excludes_password_hash(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await insert_user(_make_user("ana@hispacontact.com"))

            users = await user_service.list_users()

            assert len(users) == 1
            assert "password_hash" not in users[0].model_dump()

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


# --- Spec 009: cambiar el rol y retirar el acceso por id (RF-7, RF-8) ---

def test_change_role_updates_the_role_and_creates_history_entry(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("ana@hispacontact.com"))

            updated = await user_service.change_role(ACTOR, user_id, "gestion_humana")

            assert updated["role"] == "gestion_humana"

            entries = await list_entries({"entity_type": "user", "entity_id": user_id})
            assert [entry["action"] for entry in entries] == ["update"]
            assert entries[0]["changes"] == [
                {"field": "role", "old_value": "lider", "new_value": "gestion_humana"}
            ]

    asyncio.run(scenario())


def test_change_role_invalidates_active_sessions(use_test_db) -> None:
    """El rol viaja dentro de la sesión: sin cerrarla, el rol nuevo no aplicaría."""
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("ana@hispacontact.com"))
            await insert_session(_make_session(user_id, "token-vigente"))

            await user_service.change_role(ACTOR, user_id, "gestion_humana")

            assert await find_session_by_token("token-vigente") is None

    asyncio.run(scenario())


def test_change_role_to_the_same_role_is_a_noop(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("ana@hispacontact.com"))
            await insert_session(_make_session(user_id, "token-vigente"))

            unchanged = await user_service.change_role(ACTOR, user_id, "lider")

            assert unchanged["role"] == "lider"
            assert await find_session_by_token("token-vigente") is not None
            assert await list_entries({"entity_type": "user", "entity_id": user_id}) == []

    asyncio.run(scenario())


def test_change_role_rejects_the_actors_own_account(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("gestion@hispacontact.com"))
            self_actor = {"_id": user_id, "full_name": "Gestión Humana"}

            with pytest.raises(user_service.SelfTargetError):
                await user_service.change_role(self_actor, user_id, "lider")

            assert (await find_user_by_email("gestion@hispacontact.com"))["role"] == "lider"

    asyncio.run(scenario())


def test_change_role_with_an_unknown_id_raises(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            from bson import ObjectId

            await ensure_indexes()

            with pytest.raises(user_service.UserIdNotFoundError):
                await user_service.change_role(ACTOR, ObjectId(), "lider")

    asyncio.run(scenario())


def test_deactivate_user_by_id_marks_inactive_and_invalidates_sessions(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("ana@hispacontact.com"))
            await insert_session(_make_session(user_id, "token-vigente"))

            updated = await user_service.deactivate_user_by_id(ACTOR, user_id)

            assert updated["is_active"] is False
            assert await find_session_by_token("token-vigente") is None

            entries = await list_entries({"entity_type": "user", "entity_id": user_id})
            assert [entry["action"] for entry in entries] == ["deactivate"]

    asyncio.run(scenario())


def test_deactivate_user_by_id_on_an_already_inactive_account_is_a_noop(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("ana@hispacontact.com", is_active=False))

            unchanged = await user_service.deactivate_user_by_id(ACTOR, user_id)

            assert unchanged["is_active"] is False
            assert await list_entries({"entity_type": "user", "entity_id": user_id}) == []

    asyncio.run(scenario())


def test_deactivate_user_by_id_rejects_the_actors_own_account(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("gestion@hispacontact.com"))
            self_actor = {"_id": user_id, "full_name": "Gestión Humana"}

            with pytest.raises(user_service.SelfTargetError):
                await user_service.deactivate_user_by_id(self_actor, user_id)

            assert (await find_user_by_email("gestion@hispacontact.com"))["is_active"] is True

    asyncio.run(scenario())


def test_deactivate_user_by_id_with_an_unknown_id_raises(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            from bson import ObjectId

            await ensure_indexes()

            with pytest.raises(user_service.UserIdNotFoundError):
                await user_service.deactivate_user_by_id(ACTOR, ObjectId())

    asyncio.run(scenario())
