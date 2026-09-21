import asyncio

import pytest
from pymongo.errors import DuplicateKeyError

from conftest import mongo_test_session
from src.models.user import ensure_indexes, find_user_by_email, insert_user, update_user


def _make_user(email: str) -> dict:
    return {
        "full_name": "Ana Pérez",
        "email": email,
        "password_hash": "pbkdf2_sha256$260000$deadbeef$deadbeef",
        "role": "lider",
        "is_active": True,
    }


def test_insert_user_and_find_by_email(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await insert_user(_make_user("ana.perez@hispacontact.com"))
            found = await find_user_by_email("ana.perez@hispacontact.com")

            assert found is not None
            assert found["email"] == "ana.perez@hispacontact.com"
            assert found["full_name"] == "Ana Pérez"

    asyncio.run(scenario())


def test_insert_user_with_duplicate_email_raises(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await insert_user(_make_user("duplicado@hispacontact.com"))

            with pytest.raises(DuplicateKeyError):
                await insert_user(_make_user("duplicado@hispacontact.com"))

    asyncio.run(scenario())


def test_insert_user_with_different_email_succeeds(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await insert_user(_make_user("a@hispacontact.com"))
            await insert_user(_make_user("b@hispacontact.com"))

            assert await find_user_by_email("a@hispacontact.com") is not None
            assert await find_user_by_email("b@hispacontact.com") is not None

    asyncio.run(scenario())


def test_update_user_modifies_fields(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_user(_make_user("c@hispacontact.com"))

            modified = await update_user("c@hispacontact.com", {"is_active": False})
            found = await find_user_by_email("c@hispacontact.com")

            assert modified is True
            assert found["is_active"] is False

    asyncio.run(scenario())


def test_find_user_by_email_returns_none_when_not_found(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            assert await find_user_by_email("no-existe@hispacontact.com") is None

    asyncio.run(scenario())
