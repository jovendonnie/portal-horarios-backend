from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession

from src.core.database import get_database

COLLECTION_NAME = "Usuarios"

_IDENTITY_COLLATION = {"locale": "es", "strength": 2}


async def ensure_indexes() -> None:
    db = get_database()
    await db[COLLECTION_NAME].create_index(
        [("nombre_completo", 1), ("cargo", 1), ("area", 1)],
        unique=True,
        collation=_IDENTITY_COLLATION,
    )


def _trim_identity_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.strip() if key in ("nombre_completo", "area") and isinstance(value, str) else value
        for key, value in fields.items()
    }


async def insert_employee(
    document: dict[str, Any], session: AsyncIOMotorClientSession | None = None
) -> Any:
    db = get_database()
    to_insert = _trim_identity_fields(
        {
            "activo": True,
            "creado_en": datetime.now(timezone.utc),
            **document,
        }
    )
    result = await db[COLLECTION_NAME].insert_one(to_insert, session=session)
    return result.inserted_id


async def find_employee_by_id(employee_id: Any) -> dict[str, Any] | None:
    db = get_database()
    return await db[COLLECTION_NAME].find_one({"_id": employee_id})


async def find_employee_by_identity(
    full_name: str, position: str, area: str
) -> dict[str, Any] | None:
    db = get_database()
    return await db[COLLECTION_NAME].find_one(
        {"nombre_completo": full_name, "cargo": position, "area": area},
        collation=_IDENTITY_COLLATION,
    )


async def list_employees() -> list[dict[str, Any]]:
    db = get_database()
    return await db[COLLECTION_NAME].find({}).to_list(length=None)


async def update_employee_fields(
    employee_id: Any,
    updates: dict[str, Any],
    session: AsyncIOMotorClientSession | None = None,
) -> bool:
    db = get_database()
    result = await db[COLLECTION_NAME].update_one(
        {"_id": employee_id}, {"$set": _trim_identity_fields(updates)}, session=session
    )
    return result.modified_count > 0


async def count_employees_by_area(area_id: Any) -> int:
    db = get_database()
    return await db[COLLECTION_NAME].count_documents({"area_id": area_id})


async def count_employees_by_status(estado_id: Any) -> int:
    db = get_database()
    return await db[COLLECTION_NAME].count_documents({"estado_id": estado_id})


async def reassign_area(
    old_area_id: Any,
    new_area_id: Any,
    new_area_name: str,
    session: AsyncIOMotorClientSession | None = None,
) -> int:
    db = get_database()
    result = await db[COLLECTION_NAME].update_many(
        {"area_id": old_area_id},
        {"$set": {"area_id": new_area_id, "area": new_area_name}},
        session=session,
    )
    return result.modified_count


async def reassign_status(
    old_estado_id: Any,
    new_estado_id: Any,
    session: AsyncIOMotorClientSession | None = None,
) -> int:
    db = get_database()
    result = await db[COLLECTION_NAME].update_many(
        {"estado_id": old_estado_id},
        {"$set": {"estado_id": new_estado_id}},
        session=session,
    )
    return result.modified_count


async def update_employee_status_fields(
    employee_id: Any,
    estado_id: Any,
    actor_id: Any,
    ahora: datetime,
    session: AsyncIOMotorClientSession | None = None,
) -> bool:
    db = get_database()
    result = await db[COLLECTION_NAME].update_one(
        {"_id": employee_id},
        {
            "$set": {
                "estado_id": estado_id,
                "estado_actualizado_en": ahora,
                "estado_actualizado_por": actor_id,
            }
        },
        session=session,
    )
    return result.modified_count > 0
