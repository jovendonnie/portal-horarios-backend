import asyncio
from typing import Any

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from conftest import mongo_test_session
from src.core.database import get_database, start_transaction
from src.models.schedule import (
    DEFAULT_SCHEDULES_COLLECTION,
    SCHEDULE_EXCEPTIONS_COLLECTION,
    delete_day_exception,
    ensure_indexes,
    find_default_schedule,
    find_default_schedules_bulk,
    find_exception,
    find_exceptions_bulk,
    insert_range_exceptions,
    upsert_day_exception,
    upsert_default_schedule,
)


def _make_days() -> list[dict[str, Any]]:
    return [
        {
            "weekday": "monday",
            "works": True,
            "modality": "presencial",
            "time_ranges": [{"start": "08:00", "end": "17:00"}],
        },
        {
            "weekday": "tuesday",
            "works": True,
            "modality": "virtual",
            "time_ranges": [{"start": "08:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}],
        },
        {
            "weekday": "wednesday",
            "works": True,
            "modality": "presencial",
            "time_ranges": [{"start": "08:00", "end": "17:00"}],
        },
        {
            "weekday": "thursday",
            "works": True,
            "modality": "presencial",
            "time_ranges": [{"start": "08:00", "end": "17:00"}],
        },
        {"weekday": "friday", "works": False, "modality": None, "time_ranges": []},
    ]


def test_upsert_default_schedule_round_trips_with_find(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = ObjectId()
            actor_id = ObjectId()
            days = _make_days()

            await upsert_default_schedule(employee_id, days, actor_id)
            found = await find_default_schedule(employee_id)

            assert found is not None
            assert found["days"] == days

    asyncio.run(scenario())


def test_upsert_default_schedule_overwrites_previous_value(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = ObjectId()
            actor_id = ObjectId()

            await upsert_default_schedule(employee_id, _make_days(), actor_id)
            new_days = _make_days()
            new_days[4] = {
                "weekday": "friday",
                "works": True,
                "modality": "virtual",
                "time_ranges": [{"start": "09:00", "end": "13:00"}],
            }
            await upsert_default_schedule(employee_id, new_days, actor_id)

            found = await find_default_schedule(employee_id)

            assert found["days"] == new_days
            assert await get_database()[DEFAULT_SCHEDULES_COLLECTION].count_documents(
                {"employee_id": employee_id}
            ) == 1

    asyncio.run(scenario())


def test_ensure_indexes_rejects_duplicate_employee_id_in_default_schedules(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            employee_id = ObjectId()
            db = get_database()
            await db[DEFAULT_SCHEDULES_COLLECTION].insert_one(
                {"employee_id": employee_id, "days": _make_days()}
            )

            with pytest.raises(DuplicateKeyError):
                await db[DEFAULT_SCHEDULES_COLLECTION].insert_one(
                    {"employee_id": employee_id, "days": _make_days()}
                )

    asyncio.run(scenario())


def test_ensure_indexes_rejects_duplicate_employee_id_and_date_in_exceptions(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            employee_id = ObjectId()
            status_id = ObjectId()
            actor_id = ObjectId()
            db = get_database()
            await db[SCHEDULE_EXCEPTIONS_COLLECTION].insert_one(
                {
                    "employee_id": employee_id,
                    "date": "2026-10-15",
                    "status_id": status_id,
                    "observation": None,
                    "source": "day_override",
                    "range_id": None,
                    "updated_at": None,
                    "updated_by": actor_id,
                }
            )

            with pytest.raises(DuplicateKeyError):
                await db[SCHEDULE_EXCEPTIONS_COLLECTION].insert_one(
                    {
                        "employee_id": employee_id,
                        "date": "2026-10-15",
                        "status_id": status_id,
                        "observation": None,
                        "source": "day_override",
                        "range_id": None,
                        "updated_at": None,
                        "updated_by": actor_id,
                    }
                )

    asyncio.run(scenario())


def test_find_exceptions_bulk_returns_only_matching_documents(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            status_id = ObjectId()
            employee_a = ObjectId()
            employee_b = ObjectId()
            employee_c = ObjectId()

            await upsert_day_exception(employee_a, "2026-10-15", status_id, None, actor_id)
            await upsert_day_exception(employee_b, "2026-10-16", status_id, None, actor_id)
            await upsert_day_exception(employee_c, "2026-10-15", status_id, None, actor_id)

            found = await find_exceptions_bulk(
                [employee_a, employee_b], ["2026-10-15", "2026-10-16"]
            )

            found_keys = {(doc["employee_id"], doc["date"]) for doc in found}
            assert found_keys == {(employee_a, "2026-10-15"), (employee_b, "2026-10-16")}

    asyncio.run(scenario())


def test_upsert_day_exception_creates_day_override(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = ObjectId()
            status_id = ObjectId()
            actor_id = ObjectId()

            document = await upsert_day_exception(
                employee_id, "2026-10-15", status_id, "Cita médica", actor_id
            )

            assert document["source"] == "day_override"
            found = await find_exception(employee_id, "2026-10-15")
            assert found["status_id"] == status_id
            assert found["observation"] == "Cita médica"

    asyncio.run(scenario())


def test_delete_day_exception_is_idempotent(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = ObjectId()
            status_id = ObjectId()
            actor_id = ObjectId()
            await upsert_day_exception(employee_id, "2026-10-15", status_id, None, actor_id)

            first_delete = await delete_day_exception(employee_id, "2026-10-15")
            second_delete = await delete_day_exception(employee_id, "2026-10-15")

            assert first_delete is True
            assert second_delete is False
            assert await find_exception(employee_id, "2026-10-15") is None

    asyncio.run(scenario())


def test_find_default_schedules_bulk_returns_only_matching_documents(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_a = ObjectId()
            employee_b = ObjectId()
            employee_c = ObjectId()
            actor_id = ObjectId()

            await upsert_default_schedule(employee_a, _make_days(), actor_id)
            await upsert_default_schedule(employee_b, _make_days(), actor_id)

            found = await find_default_schedules_bulk([employee_a, employee_c])

            found_employee_ids = {doc["employee_id"] for doc in found}
            assert found_employee_ids == {employee_a}

    asyncio.run(scenario())


def test_insert_range_exceptions_reverts_nothing_on_conflict_inside_transaction(
    use_test_db,
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            employee_id = ObjectId()
            status_id = ObjectId()
            actor_id = ObjectId()
            range_id = ObjectId()

            await upsert_day_exception(employee_id, "2026-10-16", status_id, None, actor_id)

            docs = [
                {
                    "employee_id": employee_id,
                    "date": "2026-10-15",
                    "status_id": status_id,
                    "observation": None,
                    "source": "range_override",
                    "range_id": range_id,
                    "updated_at": None,
                    "updated_by": actor_id,
                },
                {
                    "employee_id": employee_id,
                    "date": "2026-10-16",
                    "status_id": status_id,
                    "observation": None,
                    "source": "range_override",
                    "range_id": range_id,
                    "updated_at": None,
                    "updated_by": actor_id,
                },
            ]

            async with start_transaction() as session:
                with pytest.raises(DuplicateKeyError):
                    await insert_range_exceptions(docs, session=session)
                await session.abort_transaction()

            remaining = await find_exceptions_bulk([employee_id], ["2026-10-15", "2026-10-16"])
            assert [doc["date"] for doc in remaining] == ["2026-10-16"]

    asyncio.run(scenario())
