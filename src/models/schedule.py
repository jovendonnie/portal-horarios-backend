from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession

from src.core.database import get_database

DEFAULT_SCHEDULES_COLLECTION = "default_schedules"
SCHEDULE_EXCEPTIONS_COLLECTION = "schedule_exceptions"


async def ensure_indexes() -> None:
    db = get_database()
    await db[DEFAULT_SCHEDULES_COLLECTION].create_index("employee_id", unique=True)
    await db[SCHEDULE_EXCEPTIONS_COLLECTION].create_index(
        [("employee_id", 1), ("date", 1)], unique=True
    )


async def find_default_schedule(employee_id: Any) -> dict[str, Any] | None:
    db = get_database()
    return await db[DEFAULT_SCHEDULES_COLLECTION].find_one({"employee_id": employee_id})


async def upsert_default_schedule(
    employee_id: Any,
    days: list[dict[str, Any]],
    actor: Any,
    session: AsyncIOMotorClientSession | None = None,
) -> Any:
    db = get_database()
    now = datetime.now(timezone.utc)
    await db[DEFAULT_SCHEDULES_COLLECTION].update_one(
        {"employee_id": employee_id},
        {
            "$set": {
                "employee_id": employee_id,
                "days": days,
                "updated_at": now,
                "updated_by": actor,
            }
        },
        upsert=True,
        session=session,
    )
    return employee_id


async def find_exception(employee_id: Any, date: str) -> dict[str, Any] | None:
    db = get_database()
    return await db[SCHEDULE_EXCEPTIONS_COLLECTION].find_one(
        {"employee_id": employee_id, "date": date}
    )


async def find_exceptions_bulk(
    employee_ids: list[Any],
    dates: list[str],
    session: AsyncIOMotorClientSession | None = None,
) -> list[dict[str, Any]]:
    db = get_database()
    return (
        await db[SCHEDULE_EXCEPTIONS_COLLECTION]
        .find(
            {"employee_id": {"$in": employee_ids}, "date": {"$in": dates}},
            session=session,
        )
        .to_list(length=None)
    )


async def find_default_schedules_bulk(employee_ids: list[Any]) -> list[dict[str, Any]]:
    db = get_database()
    return (
        await db[DEFAULT_SCHEDULES_COLLECTION]
        .find({"employee_id": {"$in": employee_ids}})
        .to_list(length=None)
    )


async def upsert_day_exception(
    employee_id: Any,
    date: str,
    status_id: Any,
    observation: str | None,
    actor: Any,
    session: AsyncIOMotorClientSession | None = None,
) -> dict[str, Any]:
    db = get_database()
    now = datetime.now(timezone.utc)
    document = {
        "employee_id": employee_id,
        "date": date,
        "status_id": status_id,
        "observation": observation,
        "source": "day_override",
        "range_id": None,
        "updated_at": now,
        "updated_by": actor,
    }
    await db[SCHEDULE_EXCEPTIONS_COLLECTION].update_one(
        {"employee_id": employee_id, "date": date},
        {"$set": document},
        upsert=True,
        session=session,
    )
    return document


async def delete_day_exception(
    employee_id: Any,
    date: str,
    session: AsyncIOMotorClientSession | None = None,
) -> bool:
    db = get_database()
    result = await db[SCHEDULE_EXCEPTIONS_COLLECTION].delete_one(
        {"employee_id": employee_id, "date": date}, session=session
    )
    return result.deleted_count > 0


async def insert_range_exceptions(
    docs: list[dict[str, Any]], session: AsyncIOMotorClientSession | None = None
) -> list[Any]:
    db = get_database()
    inserted_ids = []
    for doc in docs:
        result = await db[SCHEDULE_EXCEPTIONS_COLLECTION].insert_one(doc, session=session)
        inserted_ids.append(result.inserted_id)
    return inserted_ids
