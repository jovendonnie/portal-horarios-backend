from contextlib import asynccontextmanager
from typing import AsyncIterator

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorClientSession,
    AsyncIOMotorDatabase,
)

from src.core.config import settings


class MongoConnection:
    client: AsyncIOMotorClient | None = None


mongo_connection = MongoConnection()


async def connect_to_mongo() -> None:
    mongo_connection.client = AsyncIOMotorClient(settings.mongo_uri)


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
