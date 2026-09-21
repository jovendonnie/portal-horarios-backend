from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

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
