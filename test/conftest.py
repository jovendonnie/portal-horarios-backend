from contextlib import asynccontextmanager

import pytest

from src.core.config import settings
from src.core.database import close_mongo_connection, connect_to_mongo, get_database

TEST_DB_NAME = "portal_horarios_test"


@pytest.fixture
def use_test_db(monkeypatch):
    """Apunta settings.mongo_db_name a una base de pruebas aislada."""
    monkeypatch.setattr(settings, "mongo_db_name", TEST_DB_NAME)


@asynccontextmanager
async def mongo_test_session():
    """Conecta a la base de pruebas, la deja vacía y cierra la conexión al salir.

    Motor liga el cliente al event loop bajo el que se crea, así que toda
    la conexión + operaciones + cierre debe ocurrir dentro de un único
    `asyncio.run(...)` (no hay pytest-asyncio disponible en este proyecto).
    """
    await connect_to_mongo()
    db = get_database()
    await db.client.drop_database(TEST_DB_NAME)
    try:
        yield db
    finally:
        await db.client.drop_database(TEST_DB_NAME)
        await close_mongo_connection()
