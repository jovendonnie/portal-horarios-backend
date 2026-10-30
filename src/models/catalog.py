from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession

from src.core.database import get_database

_NAME_COLLATION = {"locale": "es", "strength": 2}


async def ensure_indexes(collection_name: str) -> None:
    db = get_database()
    await db[collection_name].create_index(
        "name",
        unique=True,
        collation=_NAME_COLLATION,
    )


async def insert_entry(
    collection_name: str,
    name: str,
    actor_id: Any,
    ahora: datetime,
    session: AsyncIOMotorClientSession | None = None,
    is_predefined: bool | None = None,
    blocks_shifts: bool | None = None,
) -> Any:
    db = get_database()
    document = {
        "name": name.strip(),
        "is_enabled": True,
        "created_at": ahora,
        "created_by": actor_id,
        "updated_at": None,
        "updated_by": None,
    }
    if is_predefined is not None:
        document["is_predefined"] = is_predefined
    if blocks_shifts is not None:
        document["blocks_shifts"] = blocks_shifts
    result = await db[collection_name].insert_one(document, session=session)
    return result.inserted_id


async def find_entry_by_id(collection_name: str, entry_id: Any) -> dict[str, Any] | None:
    db = get_database()
    return await db[collection_name].find_one({"_id": entry_id})


async def find_entry_by_name(collection_name: str, name: str) -> dict[str, Any] | None:
    db = get_database()
    return await db[collection_name].find_one(
        {"name": name}, collation=_NAME_COLLATION
    )


async def list_entries(
    collection_name: str, enabled: bool | None = None
) -> list[dict[str, Any]]:
    db = get_database()
    query = {} if enabled is None else {"is_enabled": enabled}
    return await db[collection_name].find(query).to_list(length=None)


async def update_entry_name(
    collection_name: str,
    entry_id: Any,
    name: str,
    actor_id: Any,
    ahora: datetime,
    session: AsyncIOMotorClientSession | None = None,
) -> bool:
    db = get_database()
    result = await db[collection_name].update_one(
        {"_id": entry_id},
        {"$set": {"name": name.strip(), "updated_at": ahora, "updated_by": actor_id}},
        session=session,
    )
    return result.modified_count > 0


async def mark_entry_predefined(
    collection_name: str,
    entry_id: Any,
    session: AsyncIOMotorClientSession | None = None,
) -> bool:
    db = get_database()
    result = await db[collection_name].update_one(
        {"_id": entry_id},
        {"$set": {"is_predefined": True}},
        session=session,
    )
    return result.modified_count > 0


async def set_entry_blocks_shifts(
    collection_name: str,
    entry_id: Any,
    blocks_shifts: bool,
    actor_id: Any,
    ahora: datetime,
    session: AsyncIOMotorClientSession | None = None,
) -> bool:
    db = get_database()
    result = await db[collection_name].update_one(
        {"_id": entry_id},
        {
            "$set": {
                "blocks_shifts": blocks_shifts,
                "updated_at": ahora,
                "updated_by": actor_id,
            }
        },
        session=session,
    )
    return result.modified_count > 0


async def count_enabled(collection_name: str) -> int:
    db = get_database()
    return await db[collection_name].count_documents({"is_enabled": True})


async def delete_entry(
    collection_name: str,
    entry_id: Any,
    session: AsyncIOMotorClientSession | None = None,
) -> bool:
    db = get_database()
    result = await db[collection_name].delete_one({"_id": entry_id}, session=session)
    return result.deleted_count > 0


async def set_entry_enabled(
    collection_name: str,
    entry_id: Any,
    enabled: bool,
    actor_id: Any,
    ahora: datetime,
    session: AsyncIOMotorClientSession | None = None,
) -> bool:
    db = get_database()
    result = await db[collection_name].update_one(
        {"_id": entry_id},
        {"$set": {"is_enabled": enabled, "updated_at": ahora, "updated_by": actor_id}},
        session=session,
    )
    return result.modified_count > 0
