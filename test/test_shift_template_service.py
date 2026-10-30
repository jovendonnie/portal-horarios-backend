import asyncio

import pytest
from bson import ObjectId

from conftest import mongo_test_session
from src.models import shift_template
from src.models.history import list_entries as list_history_entries
from src.schemas.shift_template import ShiftTemplateCreate, ShiftTemplateUpdate
from src.services import shift_template_service

ACTOR = {"_id": ObjectId(), "role": "gestion_humana", "full_name": "Admin Actor"}

VALID = {
    "name": "Mañana",
    "blocks": [{"start": "08:00", "end": "17:00"}],
    "weekdays": ["monday", "tuesday"],
}


def test_create_stores_the_template_and_audits_it(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()

            created = await shift_template_service.create_template(
                ShiftTemplateCreate(**VALID), ACTOR
            )

            assert created["name"] == "Mañana"
            assert created["blocks"] == [{"start": "08:00", "end": "17:00"}]
            assert created["weekdays"] == ["monday", "tuesday"]

            entries = await list_history_entries({"entity_type": "shift_template"})
            assert [entry["action"] for entry in entries] == ["create"]
            assert entries[0]["entity_id"] == created["_id"]

    asyncio.run(scenario())


def test_create_rejects_a_duplicate_name_ignoring_case(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()
            await shift_template_service.create_template(ShiftTemplateCreate(**VALID), ACTOR)

            with pytest.raises(shift_template_service.DuplicateTemplateError):
                await shift_template_service.create_template(
                    ShiftTemplateCreate(**{**VALID, "name": "  mañana "}), ACTOR
                )

    asyncio.run(scenario())


def test_create_rejects_a_blank_name(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()
            blank = ShiftTemplateCreate.model_construct(
                name="   ",
                blocks=ShiftTemplateCreate(**VALID).blocks,
                weekdays=["monday"],
            )

            with pytest.raises(shift_template_service.InvalidNameError):
                await shift_template_service.create_template(blank, ACTOR)

    asyncio.run(scenario())


def test_update_replaces_name_blocks_and_weekdays_and_audits_the_diff(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()
            created = await shift_template_service.create_template(
                ShiftTemplateCreate(**VALID), ACTOR
            )

            updated = await shift_template_service.update_template(
                created["_id"],
                ShiftTemplateUpdate(
                    name="Jornada partida",
                    blocks=[{"start": "08:00", "end": "12:00"}, {"start": "14:00", "end": "18:00"}],
                    weekdays=["friday"],
                ),
                ACTOR,
            )

            assert updated["name"] == "Jornada partida"
            assert len(updated["blocks"]) == 2
            assert updated["weekdays"] == ["friday"]
            assert updated["updated_by"] == ACTOR["_id"]

            entries = await list_history_entries(
                {"entity_type": "shift_template", "action": "update"}
            )
            changed_fields = {change["field"] for change in entries[0]["changes"]}
            assert changed_fields == {"name", "blocks", "weekdays"}

    asyncio.run(scenario())


def test_update_without_changes_is_a_noop(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()
            created = await shift_template_service.create_template(
                ShiftTemplateCreate(**VALID), ACTOR
            )

            same = await shift_template_service.update_template(
                created["_id"], ShiftTemplateUpdate(**VALID), ACTOR
            )

            assert same["updated_at"] is None
            entries = await list_history_entries(
                {"entity_type": "shift_template", "action": "update"}
            )
            assert entries == []

    asyncio.run(scenario())


def test_update_rejects_an_unknown_id_and_a_name_taken_by_another_template(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()
            first = await shift_template_service.create_template(
                ShiftTemplateCreate(**VALID), ACTOR
            )
            await shift_template_service.create_template(
                ShiftTemplateCreate(**{**VALID, "name": "Tarde"}), ACTOR
            )

            with pytest.raises(shift_template_service.TemplateNotFoundError):
                await shift_template_service.update_template(
                    ObjectId(), ShiftTemplateUpdate(**VALID), ACTOR
                )

            with pytest.raises(shift_template_service.DuplicateTemplateError):
                await shift_template_service.update_template(
                    first["_id"], ShiftTemplateUpdate(**{**VALID, "name": "Tarde"}), ACTOR
                )

    asyncio.run(scenario())


def test_list_returns_every_template(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()
            await shift_template_service.create_template(ShiftTemplateCreate(**VALID), ACTOR)
            await shift_template_service.create_template(
                ShiftTemplateCreate(**{**VALID, "name": "Tarde"}), ACTOR
            )

            listed = await shift_template_service.list_templates()

            assert [entry["name"] for entry in listed] == ["Mañana", "Tarde"]

    asyncio.run(scenario())
