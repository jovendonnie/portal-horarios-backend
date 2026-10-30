from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession

from src.core.database import get_database

COLLECTION_NAME = "holidays"


async def ensure_indexes() -> None:
    db = get_database()
    await db[COLLECTION_NAME].create_index("date", unique=True)


async def insert_holiday(
    date: str,
    name: str,
    holiday_type: str,
    blocks_shifts: bool,
    actor_id: Any,
    ahora: datetime,
    session: AsyncIOMotorClientSession | None = None,
) -> Any:
    db = get_database()
    document = {
        "date": date,
        "name": name.strip(),
        "type": holiday_type,
        "blocks_shifts": blocks_shifts,
        "created_at": ahora,
        "created_by": actor_id,
        "updated_at": None,
        "updated_by": None,
    }
    result = await db[COLLECTION_NAME].insert_one(document, session=session)
    return result.inserted_id


async def find_holiday_by_date(date: str) -> dict[str, Any] | None:
    db = get_database()
    return await db[COLLECTION_NAME].find_one({"date": date})


async def find_holiday_by_id(holiday_id: Any) -> dict[str, Any] | None:
    """Solo para resolver el `entity_id` de una entrada de auditoría: el resto del
    dominio direcciona el día por su fecha."""
    db = get_database()
    return await db[COLLECTION_NAME].find_one({"_id": holiday_id})


async def list_holidays_by_year(year: int) -> list[dict[str, Any]]:
    """Los días de un año, ordenados por fecha.

    Filtra por prefijo `YYYY-` en vez de por un campo `year` aparte: la fecha es
    texto `YYYY-MM-DD`, así que el prefijo ancla el índice único por `date` y
    ordena cronológicamente sin conversión.
    """
    db = get_database()
    cursor = db[COLLECTION_NAME].find({"date": {"$regex": f"^{year:04d}-"}}).sort("date", 1)
    return await cursor.to_list(length=None)


async def set_blocks_shifts(
    date: str,
    blocks_shifts: bool,
    actor_id: Any,
    ahora: datetime,
    session: AsyncIOMotorClientSession | None = None,
) -> bool:
    db = get_database()
    result = await db[COLLECTION_NAME].update_one(
        {"date": date},
        {"$set": {"blocks_shifts": blocks_shifts, "updated_at": ahora, "updated_by": actor_id}},
        session=session,
    )
    return result.modified_count > 0


async def delete_holiday(
    date: str, session: AsyncIOMotorClientSession | None = None
) -> bool:
    db = get_database()
    result = await db[COLLECTION_NAME].delete_one({"date": date}, session=session)
    return result.deleted_count > 0
