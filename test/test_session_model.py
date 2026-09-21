import asyncio
from datetime import datetime, timedelta, timezone

from conftest import mongo_test_session
from src.models.session import (
    delete_session,
    delete_sessions_by_user,
    ensure_indexes,
    find_session_by_token,
    insert_session,
    touch_session,
)


def _make_session(token: str, user_id: str = "user-1") -> dict:
    now = datetime.now(timezone.utc)
    return {
        "session_token": token,
        "user_id": user_id,
        "created_at": now,
        "last_activity_at": now,
        "expires_at": now + timedelta(minutes=30),
    }


def test_ensure_indexes_creates_ttl_index_on_expires_at(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session() as db:
            await ensure_indexes()

            indexes = await db["sessions"].index_information()
            expires_at_index = next(
                info for info in indexes.values() if info.get("key") == [("expires_at", 1)]
            )

            assert expires_at_index["expireAfterSeconds"] == 0

    asyncio.run(scenario())


def test_insert_session_and_find_by_token(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_session(_make_session("tok-1"))

            found = await find_session_by_token("tok-1")

            assert found is not None
            assert found["session_token"] == "tok-1"
            assert found["user_id"] == "user-1"

    asyncio.run(scenario())


def test_touch_session_updates_expiry(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_session(_make_session("tok-2"))
            new_expiry = datetime.now(timezone.utc) + timedelta(minutes=60)

            updated = await touch_session("tok-2", new_expiry)
            found = await find_session_by_token("tok-2")

            assert updated is True
            assert found["expires_at"] > datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
                minutes=45
            )

    asyncio.run(scenario())


def test_delete_session_removes_it(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_session(_make_session("tok-3"))

            deleted = await delete_session("tok-3")

            assert deleted is True
            assert await find_session_by_token("tok-3") is None

    asyncio.run(scenario())


def test_delete_sessions_by_user_removes_all_and_counts_them(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_session(_make_session("tok-4", user_id="user-2"))
            await insert_session(_make_session("tok-5", user_id="user-2"))
            await insert_session(_make_session("tok-6", user_id="user-3"))

            deleted_count = await delete_sessions_by_user("user-2")

            assert deleted_count == 2
            assert await find_session_by_token("tok-4") is None
            assert await find_session_by_token("tok-5") is None
            assert await find_session_by_token("tok-6") is not None

    asyncio.run(scenario())
