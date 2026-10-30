import asyncio
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from conftest import mongo_test_session
from src.models import shift_template

ACTOR_ID = ObjectId()
BLOCKS = [{"start": "08:00", "end": "17:00"}]
WEEKDAYS = ["monday", "wednesday"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_insert_find_list_and_update_a_template(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()

            template_id = await shift_template.insert_template(
                "  Mañana  ", BLOCKS, WEEKDAYS, ACTOR_ID, _now()
            )

            stored = await shift_template.find_template_by_id(template_id)
            assert stored["name"] == "Mañana"  # insert recorta el nombre
            assert stored["blocks"] == BLOCKS
            assert stored["weekdays"] == WEEKDAYS
            assert stored["created_by"] == ACTOR_ID
            assert stored["updated_at"] is None

            by_name = await shift_template.find_template_by_name("MAÑANA")
            assert by_name is not None  # collation case-insensitive
            assert by_name["_id"] == template_id

            await shift_template.insert_template(
                "Tarde", [{"start": "14:00", "end": "22:00"}], ["friday"], ACTOR_ID, _now()
            )
            listed = await shift_template.list_templates()
            assert [entry["name"] for entry in listed] == ["Mañana", "Tarde"]  # ordenado por nombre

            updated = await shift_template.update_template(
                template_id,
                "Mañana extendida",
                [{"start": "07:00", "end": "16:00"}],
                ["tuesday"],
                ACTOR_ID,
                _now(),
            )
            assert updated is True

            after = await shift_template.find_template_by_id(template_id)
            assert after["name"] == "Mañana extendida"
            assert after["weekdays"] == ["tuesday"]
            assert after["updated_by"] == ACTOR_ID
            assert after["created_at"] == stored["created_at"]  # el alta no se toca

    asyncio.run(scenario())


def test_name_index_rejects_duplicates_ignoring_case_and_spaces(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()
            await shift_template.insert_template("Mañana", BLOCKS, WEEKDAYS, ACTOR_ID, _now())

            with pytest.raises(DuplicateKeyError):
                await shift_template.insert_template("mañana", BLOCKS, WEEKDAYS, ACTOR_ID, _now())

    asyncio.run(scenario())


def test_lookups_return_none_when_the_template_does_not_exist(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()

            assert await shift_template.find_template_by_id(ObjectId()) is None
            assert await shift_template.find_template_by_name("Inexistente") is None
            assert await shift_template.list_templates() == []
            assert await shift_template.update_template(
                ObjectId(), "X", BLOCKS, WEEKDAYS, ACTOR_ID, _now()
            ) is False

    asyncio.run(scenario())
