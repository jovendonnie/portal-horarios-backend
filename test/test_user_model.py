import asyncio

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from conftest import mongo_test_session
from src.models.user import (
    ensure_indexes,
    find_user_by_email,
    find_user_by_id,
    insert_user,
    list_users,
    update_user,
)


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


def test_find_user_by_id_returns_matching_document(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            inserted_id = await insert_user(_make_user("d@hispacontact.com"))

            found = await find_user_by_id(inserted_id)

            assert found is not None
            assert found["email"] == "d@hispacontact.com"

    asyncio.run(scenario())


def test_find_user_by_id_returns_none_when_not_found(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            assert await find_user_by_id(ObjectId()) is None

    asyncio.run(scenario())


def test_insert_user_behaves_the_same_with_explicit_session_none(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            without_arg = await insert_user(_make_user("sin-sesion@hispacontact.com"))
            with_none = await insert_user(
                _make_user("con-sesion-nula@hispacontact.com"), session=None
            )

            assert without_arg is not None
            assert with_none is not None
            assert without_arg != with_none

    asyncio.run(scenario())


def test_list_users_returns_all_inserted_accounts(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_user(_make_user("lista-a@hispacontact.com"))
            await insert_user(_make_user("lista-b@hispacontact.com"))

            users = await list_users()

            assert {user["email"] for user in users} == {
                "lista-a@hispacontact.com",
                "lista-b@hispacontact.com",
            }

    asyncio.run(scenario())


def test_list_users_returns_empty_list_when_no_accounts(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            assert await list_users() == []

    asyncio.run(scenario())


def test_update_user_behaves_the_same_with_explicit_session_none(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_user(_make_user("update-sesion-nula@hispacontact.com"))

            modified = await update_user(
                "update-sesion-nula@hispacontact.com", {"is_active": False}, session=None
            )
            found = await find_user_by_email("update-sesion-nula@hispacontact.com")

            assert modified is True
            assert found["is_active"] is False

    asyncio.run(scenario())
