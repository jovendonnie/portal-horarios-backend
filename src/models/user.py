from datetime import datetime, timezone
from typing import Any

from src.core.database import get_database

COLLECTION_NAME = "users"


async def ensure_indexes() -> None:
    db = get_database()
    await db[COLLECTION_NAME].create_index("email", unique=True)


async def insert_user(user: dict[str, Any]) -> Any:
    db = get_database()
    document = {
        "failed_login_attempts": 0,
        "locked_until": None,
        "created_at": datetime.now(timezone.utc),
        **user,
    }
    result = await db[COLLECTION_NAME].insert_one(document)
    return result.inserted_id


async def find_user_by_email(email: str) -> dict[str, Any] | None:
    db = get_database()
    return await db[COLLECTION_NAME].find_one({"email": email})


async def find_user_by_id(user_id: Any) -> dict[str, Any] | None:
    db = get_database()
    return await db[COLLECTION_NAME].find_one({"_id": user_id})


async def update_user(email: str, updates: dict[str, Any]) -> bool:
    db = get_database()
    result = await db[COLLECTION_NAME].update_one({"email": email}, {"$set": updates})
    return result.modified_count > 0
