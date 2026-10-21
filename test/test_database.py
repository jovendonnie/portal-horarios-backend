import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorClientSession
from pymongo.errors import DuplicateKeyError

from conftest import mongo_test_session
from src.core.database import connect_to_mongo, start_transaction
from src.models import user as user_model

COLLECTION_NAME = "transaction_probe"


def test_start_transaction_yields_session_with_active_transaction(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            async with start_transaction() as session:
                assert isinstance(session, AsyncIOMotorClientSession)
                assert session.in_transaction is True

                await session.abort_transaction()

    asyncio.run(scenario())


def test_write_inside_transaction_is_discarded_when_aborted_manually(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session() as db:
            async with start_transaction() as session:
                result = await db[COLLECTION_NAME].insert_one(
                    {"marker": "should-not-persist"}, session=session
                )
                await session.abort_transaction()

            found = await db[COLLECTION_NAME].find_one({"_id": result.inserted_id})

            assert found is None

    asyncio.run(scenario())


def test_write_inside_transaction_persists_when_committed_manually(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session() as db:
            async with start_transaction() as session:
                result = await db[COLLECTION_NAME].insert_one(
                    {"marker": "should-persist"}, session=session
                )
                await session.commit_transaction()

            found = await db[COLLECTION_NAME].find_one({"_id": result.inserted_id})

            assert found is not None
            assert found["marker"] == "should-persist"

    asyncio.run(scenario())


def test_connect_to_mongo_soft_fails_when_index_has_preexisting_duplicates(
    use_test_db, monkeypatch, caplog
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():

            async def _raise_duplicate() -> None:
                raise DuplicateKeyError("nombres duplicados preexistentes")

            monkeypatch.setattr(user_model, "ensure_indexes", _raise_duplicate)

            with caplog.at_level(logging.WARNING):
                await connect_to_mongo()

            assert "users" in caplog.text

    asyncio.run(scenario())
