from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession

from src.core.database import get_database

COLLECTION_NAME = "sessions"


async def ensure_indexes() -> None:
    db = get_database()
    await db[COLLECTION_NAME].create_index("expires_at", expireAfterSeconds=0)


async def insert_session(session: dict[str, Any]) -> Any:
    db = get_database()
    result = await db[COLLECTION_NAME].insert_one(session)
    return result.inserted_id


async def find_session_by_token(session_token: str) -> dict[str, Any] | None:
    db = get_database()
    return await db[COLLECTION_NAME].find_one({"session_token": session_token})


async def touch_session(session_token: str, expires_at: datetime) -> bool:
    db = get_database()
    result = await db[COLLECTION_NAME].update_one(
        {"session_token": session_token},
        {"$set": {"last_activity_at": datetime.now(timezone.utc), "expires_at": expires_at}},
    )
    return result.modified_count > 0


async def delete_session(session_token: str) -> bool:
    db = get_database()
    result = await db[COLLECTION_NAME].delete_one({"session_token": session_token})
    return result.deleted_count > 0


async def delete_sessions_by_user(
    user_id: Any, session: AsyncIOMotorClientSession | None = None
) -> int:
    db = get_database()
    result = await db[COLLECTION_NAME].delete_many({"user_id": user_id}, session=session)
    return result.deleted_count
