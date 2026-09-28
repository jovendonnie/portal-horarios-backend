from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession

from src.core.database import get_database

COLLECTION_NAME = "history_entries"


async def ensure_indexes() -> None:
    db = get_database()
    await db[COLLECTION_NAME].create_index([("entity_type", 1), ("entity_id", 1)])
    await db[COLLECTION_NAME].create_index("actor_id")
    await db[COLLECTION_NAME].create_index([("occurred_at", -1)])


async def insert_entry(
    document: dict[str, Any], session: AsyncIOMotorClientSession | None = None
) -> Any:
    db = get_database()
    result = await db[COLLECTION_NAME].insert_one(document, session=session)
    return result.inserted_id


async def list_entries(
    query: dict[str, Any], session: AsyncIOMotorClientSession | None = None
) -> list[dict[str, Any]]:
    db = get_database()
    cursor = db[COLLECTION_NAME].find(query, session=session).sort("occurred_at", -1)
    return await cursor.to_list(length=None)
