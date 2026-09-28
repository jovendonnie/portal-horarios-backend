import asyncio
import inspect
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from conftest import mongo_test_session
from src.models import history
from src.models.history import ensure_indexes, insert_entry, list_entries

COLLECTION_NAME = "history_entries"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _make_entry(**overrides) -> dict:
    document = {
        "entity_type": "employee",
        "entity_id": ObjectId(),
        "action": "create",
        "actor_id": ObjectId(),
        "actor_name": "Ana Torres",
        "changes": [{"field": "full_name", "old_value": None, "new_value": "Carla Gómez"}],
        "occurred_at": _ahora(),
    }
    document.update(overrides)
    return document


def test_ensure_indexes_creates_the_three_expected_indexes(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session() as db:
            await ensure_indexes()

            indexes = await db[COLLECTION_NAME].list_indexes().to_list(length=None)
            index_keys = [list(index["key"].items()) for index in indexes]

            assert [("entity_type", 1), ("entity_id", 1)] in index_keys
            assert [("actor_id", 1)] in index_keys
            assert [("occurred_at", -1)] in index_keys

    asyncio.run(scenario())


def test_insert_entry_saves_document_as_is_and_returns_id(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session() as db:
            document = _make_entry()

            entry_id = await insert_entry(document)
            found = await db[COLLECTION_NAME].find_one({"_id": entry_id})

            assert found is not None
            assert found["entity_type"] == document["entity_type"]
            assert found["entity_id"] == document["entity_id"]
            assert found["action"] == document["action"]
            assert found["actor_id"] == document["actor_id"]
            assert found["actor_name"] == document["actor_name"]
            assert found["changes"] == document["changes"]
            # Mongo/BSON guarda datetimes naive (UTC) con precisión de
            # milisegundos, por lo que se compara truncando a ese nivel.
            expected = document["occurred_at"].astimezone(timezone.utc).replace(tzinfo=None)
            expected = expected.replace(microsecond=(expected.microsecond // 1000) * 1000)
            assert found["occurred_at"] == expected

    asyncio.run(scenario())


def test_insert_entry_behaves_the_same_with_explicit_session_none(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            without_arg = await insert_entry(_make_entry())
            with_none = await insert_entry(_make_entry(), session=None)

            assert without_arg is not None
            assert with_none is not None
            assert without_arg != with_none

    asyncio.run(scenario())


def test_list_entries_filters_by_query(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = ObjectId()
            other_employee_id = ObjectId()

            employee_entry_id = await insert_entry(
                _make_entry(entity_type="employee", entity_id=employee_id)
            )
            await insert_entry(_make_entry(entity_type="employee", entity_id=other_employee_id))
            await insert_entry(_make_entry(entity_type="area", entity_id=ObjectId()))

            results = await list_entries({"entity_type": "employee", "entity_id": employee_id})

            assert [entry["_id"] for entry in results] == [employee_entry_id]

    asyncio.run(scenario())


def test_list_entries_orders_by_occurred_at_descending(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            entity_id = ObjectId()
            base = _ahora()

            oldest_id = await insert_entry(
                _make_entry(entity_id=entity_id, occurred_at=base - timedelta(minutes=10))
            )
            newest_id = await insert_entry(
                _make_entry(entity_id=entity_id, occurred_at=base)
            )
            middle_id = await insert_entry(
                _make_entry(entity_id=entity_id, occurred_at=base - timedelta(minutes=5))
            )

            results = await list_entries({"entity_id": entity_id})

            assert [entry["_id"] for entry in results] == [newest_id, middle_id, oldest_id]

    asyncio.run(scenario())


def test_module_exposes_no_update_or_delete_functions() -> None:
    public_functions = [
        name
        for name, _ in inspect.getmembers(history, inspect.iscoroutinefunction)
        if not name.startswith("_")
    ]

    assert not any(name.startswith("update") for name in public_functions)
    assert not any(name.startswith("delete") for name in public_functions)
