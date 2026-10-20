import asyncio
from typing import Any

import pytest
from fastapi import HTTPException

from conftest import mongo_test_session
from src.api.deps import (
    canonical_role,
    get_current_user,
    get_session_token,
    require_admin,
    require_read,
    require_schedule_write,
)
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


def test_require_admin_allows_gestion_humana_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            gestion_humana = await _insert_and_fetch_user(
                "gestion-humana-admin@hispacontact.com", role="gestion_humana"
            )

            result = await require_admin(user=gestion_humana)

            assert result == gestion_humana

    asyncio.run(scenario())


def test_require_admin_rejects_non_admin_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            lider = await _insert_and_fetch_user("lider@hispacontact.com", role="lider")

            with pytest.raises(HTTPException) as exc_info:
                await require_admin(user=lider)

            assert exc_info.value.status_code == 403

    asyncio.run(scenario())


def test_require_read_allows_admin_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            admin = await _insert_and_fetch_user("admin2@hispacontact.com", role="admin")

            result = await require_read(user=admin)

            assert result == admin

    asyncio.run(scenario())


def test_require_read_allows_gestion_humana_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            gestion_humana = await _insert_and_fetch_user(
                "gestion_humana@hispacontact.com", role="gestion_humana"
            )

            result = await require_read(user=gestion_humana)

            assert result == gestion_humana

    asyncio.run(scenario())


def test_require_read_allows_lider_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            lider = await _insert_and_fetch_user("lider2@hispacontact.com", role="lider")

            result = await require_read(user=lider)

            assert result == lider

    asyncio.run(scenario())


def test_require_read_rejects_unknown_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            invitado = await _insert_and_fetch_user("invitado@hispacontact.com", role="invitado")

            with pytest.raises(HTTPException) as exc_info:
                await require_read(user=invitado)

            assert exc_info.value.status_code == 403

    asyncio.run(scenario())


def test_canonical_role_maps_admin_to_gestion_humana() -> None:
    assert canonical_role("admin") == "gestion_humana"


def test_canonical_role_is_idempotent_for_gestion_humana() -> None:
    assert canonical_role("gestion_humana") == "gestion_humana"


def test_canonical_role_leaves_other_roles_unchanged() -> None:
    assert canonical_role("lider") == "lider"


def test_require_schedule_write_allows_admin_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            admin = await _insert_and_fetch_user("admin-horarios@hispacontact.com", role="admin")

            result = await require_schedule_write(user=admin)

            assert result == admin

    asyncio.run(scenario())


def test_require_schedule_write_allows_gestion_humana_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            gestion_humana = await _insert_and_fetch_user(
                "gestion-humana-horarios@hispacontact.com", role="gestion_humana"
            )

            result = await require_schedule_write(user=gestion_humana)

            assert result == gestion_humana

    asyncio.run(scenario())


def test_require_schedule_write_rejects_lider_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            lider = await _insert_and_fetch_user("lider-horarios@hispacontact.com", role="lider")

            with pytest.raises(HTTPException) as exc_info:
                await require_schedule_write(user=lider)

            assert exc_info.value.status_code == 403

    asyncio.run(scenario())
