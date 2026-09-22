import asyncio
from typing import Any

import pytest
from fastapi import HTTPException

from conftest import mongo_test_session
from src.api.deps import get_current_user, get_session_token, require_admin
from src.models.user import insert_user
from src.services import session_service


def _make_user(email: str, role: str = "lider") -> dict[str, Any]:
    return {
        "full_name": "Ana Pérez",
        "email": email,
        "password_hash": "pbkdf2_sha256$260000$deadbeef$deadbeef",
        "role": role,
        "is_active": True,
    }


async def _insert_and_fetch_user(email: str, role: str = "lider") -> dict[str, Any]:
    user_id = await insert_user(_make_user(email, role))
    return {"_id": user_id, "email": email, "role": role}


def test_get_session_token_rejects_missing_header(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(HTTPException) as exc_info:
                await get_session_token(authorization=None)

            assert exc_info.value.status_code == 401

    asyncio.run(scenario())


def test_get_session_token_rejects_malformed_header(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(HTTPException) as exc_info:
                await get_session_token(authorization="Token abc123")

            assert exc_info.value.status_code == 401

    asyncio.run(scenario())


def test_get_session_token_extracts_token_from_bearer_header(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            token = await get_session_token(authorization="Bearer abc123")

            assert token == "abc123"

    asyncio.run(scenario())


def test_get_current_user_returns_user_for_valid_session(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            user = await _insert_and_fetch_user("ana@hispacontact.com")
            token = await session_service.create_session(user)

            current_user = await get_current_user(token=token)

            assert current_user["email"] == "ana@hispacontact.com"

    asyncio.run(scenario())


def test_get_current_user_rejects_unknown_token(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token="token-inexistente")

            assert exc_info.value.status_code == 401

    asyncio.run(scenario())


def test_require_admin_allows_admin_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            admin = await _insert_and_fetch_user("admin@hispacontact.com", role="admin")

            result = await require_admin(user=admin)

            assert result == admin

    asyncio.run(scenario())


def test_require_admin_rejects_non_admin_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            lider = await _insert_and_fetch_user("lider@hispacontact.com", role="lider")

            with pytest.raises(HTTPException) as exc_info:
                await require_admin(user=lider)

            assert exc_info.value.status_code == 403

    asyncio.run(scenario())
