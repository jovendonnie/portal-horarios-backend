from datetime import datetime, timezone
from typing import Any

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


async def insert_employee(document: dict[str, Any]) -> Any:
    db = get_database()
    to_insert = _trim_identity_fields(
        {
            "activo": True,
            "creado_en": datetime.now(timezone.utc),
            **document,
        }
    )
    result = await db[COLLECTION_NAME].insert_one(to_insert)
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


async def update_employee_fields(employee_id: Any, updates: dict[str, Any]) -> bool:
    db = get_database()
    result = await db[COLLECTION_NAME].update_one(
        {"_id": employee_id}, {"$set": _trim_identity_fields(updates)}
    )
    return result.modified_count > 0
