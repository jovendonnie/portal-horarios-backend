import logging
from contextlib import asynccontextmanager
from functools import partial
from typing import AsyncIterator

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorClientSession,
    AsyncIOMotorDatabase,
)
from pymongo.errors import DuplicateKeyError, OperationFailure

from src.core.config import settings

logger = logging.getLogger(__name__)


class MongoConnection:
    client: AsyncIOMotorClient | None = None


mongo_connection = MongoConnection()


async def arrancar_con_indices() -> tuple[list[str], list[str]]:
    """Crea los índices únicos de cada colección al arrancar, sin tumbar el servicio si ya hay duplicados (RF-12)."""
    from src.models import catalog, employee, history, schedule
    from src.models import user as user_model

    tareas = [
        ("users", user_model.ensure_indexes),
        ("employees", employee.ensure_indexes),
        ("areas", partial(catalog.ensure_indexes, "areas")),
        ("estados", partial(catalog.ensure_indexes, "estados")),
        ("history_entries", history.ensure_indexes),
        ("schedules", schedule.ensure_indexes),
    ]

    created: list[str] = []
    skipped_duplicates: list[str] = []
    for coleccion, ensure_indexes in tareas:
        try:
            await ensure_indexes()
            created.append(coleccion)
        except (DuplicateKeyError, OperationFailure) as exc:
            skipped_duplicates.append(coleccion)
            logger.warning(
                "Índice único de '%s' no se pudo crear: %s. Existen nombres/fechas "
                "duplicadas preexistentes; corregir manualmente y reintentar con "
                "'python -m src.cli ensure-indexes'.",
                coleccion,
                exc,
            )

    return created, skipped_duplicates


async def connect_to_mongo() -> None:
    mongo_connection.client = AsyncIOMotorClient(settings.mongo_uri)
    await arrancar_con_indices()


async def close_mongo_connection() -> None:
    if mongo_connection.client is not None:
        mongo_connection.client.close()


def get_database() -> AsyncIOMotorDatabase:
    return mongo_connection.client[settings.mongo_db_name]


@asynccontextmanager
async def start_transaction() -> AsyncIterator[AsyncIOMotorClientSession]:
    session = await mongo_connection.client.start_session()
    try:
        session.start_transaction()
        yield session
    finally:
        await session.end_session()
