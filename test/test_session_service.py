import asyncio
from datetime import datetime, timedelta
from typing import Any
from unittest import mock

import pytest

from conftest import mongo_test_session
from src.core.config import settings
from src.models.session import find_session_by_token
from src.models.user import insert_user, update_user
from src.services import session_service


def _make_user(email: str) -> dict[str, Any]:
    return {
        "full_name": "Ana Pérez",
        "email": email,
        "password_hash": "pbkdf2_sha256$260000$deadbeef$deadbeef",
        "role": "lider",
        "is_active": True,
    }


async def _insert_and_fetch_user(email: str) -> dict[str, Any]:
    user_id = await insert_user(_make_user(email))
    return {"_id": user_id, "email": email}


def test_create_session_inserts_session_document(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            user = await _insert_and_fetch_user("ana@hispacontact.com")

            token = await session_service.create_session(user)
            session = await find_session_by_token(token)

            assert session is not None
            assert session["user_id"] == user["_id"]
            expected_expiry = session["last_activity_at"] + timedelta(
                minutes=settings.session_inactivity_minutes
            )
            assert session["expires_at"] == expected_expiry

    asyncio.run(scenario())


def test_end_session_invalidates_token(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            user = await _insert_and_fetch_user("ana@hispacontact.com")
            token = await session_service.create_session(user)

            await session_service.end_session(token)

            assert await find_session_by_token(token) is None
            with pytest.raises(session_service.InvalidSessionError):
                await session_service.validate_session(token)

    asyncio.run(scenario())


def test_validate_session_rejects_unknown_token(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(session_service.InvalidSessionError):
                await session_service.validate_session("token-inexistente")

    asyncio.run(scenario())


def test_validate_session_rejects_expired_session(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            user = await _insert_and_fetch_user("ana@hispacontact.com")

            frozen_now = datetime(2026, 1, 1, 12, 0, 0)
            with mock.patch.object(session_service, "_utcnow", return_value=frozen_now):
                token = await session_service.create_session(user)

            expired_time = frozen_now + timedelta(
                minutes=settings.session_inactivity_minutes + 1
            )
            with mock.patch.object(session_service, "_utcnow", return_value=expired_time):
                with pytest.raises(session_service.InvalidSessionError):
                    await session_service.validate_session(token)

    asyncio.run(scenario())


def test_validate_session_extends_expiry_on_success(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            user = await _insert_and_fetch_user("ana@hispacontact.com")
            token = await session_service.create_session(user)
            original = await find_session_by_token(token)

            await session_service.validate_session(token)

            updated = await find_session_by_token(token)
            assert updated["last_activity_at"] >= original["last_activity_at"]
            assert updated["expires_at"] > original["expires_at"]

    asyncio.run(scenario())


def test_validate_session_rejects_deactivated_user(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            user = await _insert_and_fetch_user("ana@hispacontact.com")
            token = await session_service.create_session(user)

            await update_user("ana@hispacontact.com", {"is_active": False})

            with pytest.raises(session_service.InvalidSessionError):
                await session_service.validate_session(token)

    asyncio.run(scenario())


def test_validate_session_returns_user_document_on_success(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            user = await _insert_and_fetch_user("ana@hispacontact.com")
            token = await session_service.create_session(user)

            validated_user = await session_service.validate_session(token)

            assert validated_user["email"] == "ana@hispacontact.com"
            assert validated_user["is_active"] is True

    asyncio.run(scenario())
