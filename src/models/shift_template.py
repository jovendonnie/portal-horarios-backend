from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession

from src.core.database import get_database

COLLECTION_NAME = "shift_templates"

_NAME_COLLATION = {"locale": "es", "strength": 2}


async def ensure_indexes() -> None:
    db = get_database()
    await db[COLLECTION_NAME].create_index(
        "name",
        unique=True,
        collation=_NAME_COLLATION,
    )


async def insert_template(
    name: str,
    blocks: list[dict[str, str]],
    weekdays: list[str],
    actor_id: Any,
    ahora: datetime,
    session: AsyncIOMotorClientSession | None = None,
) -> Any:
    db = get_database()
    document = {
        "name": name.strip(),
        "blocks": blocks,
        "weekdays": weekdays,
        "created_at": ahora,
        "created_by": actor_id,
        "updated_at": None,
        "updated_by": None,
    }
    result = await db[COLLECTION_NAME].insert_one(document, session=session)
    return result.inserted_id


async def find_template_by_id(template_id: Any) -> dict[str, Any] | None:
    db = get_database()
    return await db[COLLECTION_NAME].find_one({"_id": template_id})


async def find_template_by_name(name: str) -> dict[str, Any] | None:
    db = get_database()
    return await db[COLLECTION_NAME].find_one({"name": name}, collation=_NAME_COLLATION)


async def list_templates() -> list[dict[str, Any]]:
    db = get_database()
    return await db[COLLECTION_NAME].find({}).sort("name", 1).to_list(length=None)


async def update_template(
    template_id: Any,
    name: str,
    blocks: list[dict[str, str]],
    weekdays: list[str],
    actor_id: Any,
    ahora: datetime,
    session: AsyncIOMotorClientSession | None = None,
) -> bool:
    db = get_database()
    result = await db[COLLECTION_NAME].update_one(
        {"_id": template_id},
        {
            "$set": {
                "name": name.strip(),
                "blocks": blocks,
                "weekdays": weekdays,
                "updated_at": ahora,
                "updated_by": actor_id,
            }
        },
        session=session,
    )
    return result.modified_count > 0
