import asyncio
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from conftest import mongo_test_session
from src.models import holiday

ACTOR_ID = ObjectId()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_insert_find_toggle_and_delete_a_holiday(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()

            holiday_id = await holiday.insert_holiday(
                "2026-01-12", "  Reyes Magos  ", "nacional", True, ACTOR_ID, _now()
            )

            stored = await holiday.find_holiday_by_date("2026-01-12")
            assert stored["name"] == "Reyes Magos"  # insert recorta el nombre
            assert stored["type"] == "nacional"
            assert stored["blocks_shifts"] is True
            assert stored["created_by"] == ACTOR_ID

            by_id = await holiday.find_holiday_by_id(holiday_id)
            assert by_id["date"] == "2026-01-12"

            assert await holiday.set_blocks_shifts("2026-01-12", False, ACTOR_ID, _now()) is True
            toggled = await holiday.find_holiday_by_date("2026-01-12")
            assert toggled["blocks_shifts"] is False
            assert toggled["updated_by"] == ACTOR_ID

            assert await holiday.delete_holiday("2026-01-12") is True
            assert await holiday.find_holiday_by_date("2026-01-12") is None

    asyncio.run(scenario())


def test_date_index_rejects_two_days_on_the_same_date(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()
            await holiday.insert_holiday(
                "2026-01-12", "Reyes Magos", "nacional", True, ACTOR_ID, _now()
            )

            with pytest.raises(DuplicateKeyError):
                await holiday.insert_holiday(
                    "2026-01-12", "Día de la empresa", "empresa", True, ACTOR_ID, _now()
                )

    asyncio.run(scenario())


def test_list_by_year_returns_only_that_year_sorted_by_date(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()
            for date in ("2026-12-25", "2025-12-25", "2026-01-01", "2027-01-01"):
                await holiday.insert_holiday(date, "Festivo", "nacional", True, ACTOR_ID, _now())

            listed = await holiday.list_holidays_by_year(2026)

            assert [entry["date"] for entry in listed] == ["2026-01-01", "2026-12-25"]

    asyncio.run(scenario())


def test_operations_on_a_missing_date_report_no_change(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()

            assert await holiday.find_holiday_by_date("2026-06-15") is None
            assert await holiday.find_holiday_by_id(ObjectId()) is None
            assert await holiday.list_holidays_by_year(2026) == []
            assert await holiday.set_blocks_shifts("2026-06-15", True, ACTOR_ID, _now()) is False
            assert await holiday.delete_holiday("2026-06-15") is False

    asyncio.run(scenario())
