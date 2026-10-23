import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from conftest import mongo_test_session
from src.models import catalog
from src.models.employee import insert_employee
from src.models.history import list_entries
from src.models.user import insert_user
from src.schemas.history import HistoryQuery
from src.services import history_service

ACTOR = {"_id": ObjectId(), "full_name": "Ana Torres"}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _make_employee_document(**overrides) -> dict:
    document = {"nombre_completo": "Carla Gomez", "cargo": "lider", "area": "Ventas"}
    document.update(overrides)
    return document


def _make_user_document(**overrides) -> dict:
    document = {
        "email": f"{ObjectId()}@example.com",
        "full_name": "Carla Gomez",
        "password_hash": "irrelevant",
        "role": "lider",
        "is_active": True,
    }
    document.update(overrides)
    return document


# --- compute_diff (T011) ---------------------------------------------------


def test_compute_diff_detects_a_single_changed_field() -> None:
    current = {"full_name": "Carla"}
    requested = {"full_name": "Carla Gomez"}

    diff = history_service.compute_diff(current, requested, ["full_name"])

    assert diff == [{"field": "full_name", "old_value": "Carla", "new_value": "Carla Gomez"}]


def test_compute_diff_detects_multiple_changed_fields() -> None:
    current = {"full_name": "Carla", "position": "lider", "area": "Ventas"}
    requested = {"full_name": "Carla", "position": "recursos_humanos", "area": "Marketing"}

    diff = history_service.compute_diff(current, requested, ["full_name", "position", "area"])

    assert diff == [
        {"field": "position", "old_value": "lider", "new_value": "recursos_humanos"},
        {"field": "area", "old_value": "Ventas", "new_value": "Marketing"},
    ]


def test_compute_diff_returns_empty_list_for_no_op() -> None:
    current = {"full_name": "Carla", "position": "lider"}
    requested = {"full_name": "Carla", "position": "lider"}

    diff = history_service.compute_diff(current, requested, ["full_name", "position"])

    assert diff == []


def test_compute_diff_ignores_fields_not_listed() -> None:
    current = {"full_name": "Carla", "position": "lider"}
    requested = {"full_name": "Carla", "position": "recursos_humanos"}

    diff = history_service.compute_diff(current, requested, ["full_name"])

    assert diff == []


def test_compute_diff_treats_same_value_with_different_type_as_a_change() -> None:
    area_id = ObjectId()
    current = {"area_id": area_id}
    requested = {"area_id": str(area_id)}

    diff = history_service.compute_diff(current, requested, ["area_id"])

    assert diff == [{"field": "area_id", "old_value": area_id, "new_value": str(area_id)}]


# --- record_change / record_login_attempt (T014) ---------------------------


def test_record_change_inserts_entry_with_correct_fields(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            entity_id = ObjectId()
            ahora = _ahora()
            changes = [{"field": "full_name", "old_value": "Carla", "new_value": "Carla G."}]

            await history_service.record_change(
                None, "employee", entity_id, "update", changes, ACTOR, ahora
            )

            entries = await list_entries({"entity_id": entity_id})

            assert len(entries) == 1
            entry = entries[0]
            assert entry["entity_type"] == "employee"
            assert entry["action"] == "update"
            assert entry["actor_id"] == ACTOR["_id"]
            assert entry["actor_name"] == "Ana Torres"
            assert entry["changes"] == changes

    asyncio.run(scenario())


def test_record_change_actor_name_is_a_snapshot_not_a_live_reference(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor = {"_id": ObjectId(), "full_name": "Ana Torres"}
            entity_id = ObjectId()
            ahora = _ahora()

            await history_service.record_change(None, "employee", entity_id, "create", [], actor, ahora)

            actor["full_name"] = "Otro Nombre"

            entries = await list_entries({"entity_id": entity_id})

            assert entries[0]["actor_name"] == "Ana Torres"

    asyncio.run(scenario())


def test_record_change_returns_inserted_document_with_id_set(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            entity_id = ObjectId()
            ahora = _ahora()

            result = await history_service.record_change(
                None, "employee", entity_id, "create", [], ACTOR, ahora
            )

            assert result["_id"] is not None
            entries = await list_entries({"entity_id": entity_id})
            assert entries[0]["_id"] == result["_id"]

    asyncio.run(scenario())


def test_record_change_accepts_delete_duplicate_action_without_a_literal_restriction(
    use_test_db,
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            entity_id = ObjectId()
            kept_id = ObjectId()
            ahora = _ahora()
            changes = [
                {"field": "merged_into_id", "old_value": None, "new_value": kept_id},
                {"field": "reassigned_employees", "old_value": None, "new_value": 1},
            ]

            await history_service.record_change(
                None, "area", entity_id, "delete_duplicate", changes, ACTOR, ahora
            )

            entries = await list_entries({"entity_id": entity_id})

            assert len(entries) == 1
            assert entries[0]["action"] == "delete_duplicate"
            assert entries[0]["changes"] == changes

    asyncio.run(scenario())


def test_record_login_attempt_with_existing_user_uses_user_id_and_name(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            user_id = await insert_user(_make_user_document(full_name="Ana Torres"))
            user = {"_id": user_id, "full_name": "Ana Torres"}
            ahora = _ahora()

            await history_service.record_login_attempt(
                None, "login_success", "ana@example.com", user, ahora
            )

            entries = await list_entries({"entity_type": "login", "actor_id": user_id})

            assert len(entries) == 1
            entry = entries[0]
            assert entry["entity_type"] == "login"
            assert entry["entity_id"] is None
            assert entry["action"] == "login_success"
            assert entry["actor_id"] == user_id
            assert entry["actor_name"] == "Ana Torres"
            assert entry["changes"] == []

    asyncio.run(scenario())


def test_record_login_attempt_without_user_uses_attempted_email(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            ahora = _ahora()

            await history_service.record_login_attempt(
                None, "login_failed", "correo-no-registrado@example.com", None, ahora
            )

            entries = await list_entries({"entity_type": "login", "actor_id": None})

            assert len(entries) == 1
            entry = entries[0]
            assert entry["entity_id"] is None
            assert entry["action"] == "login_failed"
            assert entry["actor_id"] is None
            assert entry["actor_name"] == "correo-no-registrado@example.com"
            assert entry["changes"] == []

    asyncio.run(scenario())


# --- resolve_entity_exists / query_history (T017) ---------------------------


def test_resolve_entity_exists_true_and_false_for_employee(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = await insert_employee(_make_employee_document())

            assert await history_service.resolve_entity_exists("employee", str(employee_id)) is True
            assert await history_service.resolve_entity_exists("employee", str(ObjectId())) is False

    asyncio.run(scenario())


def test_resolve_entity_exists_true_and_false_for_area(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            area_id = await catalog.insert_entry("areas", "Ventas", ACTOR["_id"], _ahora())

            assert await history_service.resolve_entity_exists("area", str(area_id)) is True
            assert await history_service.resolve_entity_exists("area", str(ObjectId())) is False

    asyncio.run(scenario())


def test_resolve_entity_exists_true_and_false_for_status(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status_id = await catalog.insert_entry("estados", "Activo", ACTOR["_id"], _ahora())

            assert await history_service.resolve_entity_exists("status", str(status_id)) is True
            assert await history_service.resolve_entity_exists("status", str(ObjectId())) is False

    asyncio.run(scenario())


def test_resolve_entity_exists_true_and_false_for_user(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            user_id = await insert_user(_make_user_document())

            assert await history_service.resolve_entity_exists("user", str(user_id)) is True
            assert await history_service.resolve_entity_exists("user", str(ObjectId())) is False

    asyncio.run(scenario())


def test_resolve_entity_exists_false_for_malformed_entity_id(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            assert await history_service.resolve_entity_exists("employee", "not-an-object-id") is False

    asyncio.run(scenario())


def test_resolve_entity_exists_raises_for_login_entity_type(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(ValueError):
                await history_service.resolve_entity_exists("login", str(ObjectId()))

    asyncio.run(scenario())


def test_query_history_raises_entity_not_found_for_nonexistent_entity_id(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            filters = HistoryQuery(entity_type="employee", entity_id=str(ObjectId()))

            with pytest.raises(history_service.EntityNotFoundError):
                await history_service.query_history(filters)

    asyncio.run(scenario())


def test_query_history_raises_entity_type_required_without_entity_type(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            filters = HistoryQuery(entity_id=str(ObjectId()))

            with pytest.raises(history_service.EntityTypeRequiredError):
                await history_service.query_history(filters)

    asyncio.run(scenario())


def test_query_history_combines_entity_type_actor_id_and_date_range(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            employee_id = await insert_employee(_make_employee_document())
            other_actor = {"_id": ObjectId(), "full_name": "Otro Actor"}
            base = _ahora()

            await history_service.record_change(
                None, "employee", employee_id, "create", [], ACTOR, base
            )
            matching_id = (
                await list_entries({"entity_id": employee_id, "actor_id": ACTOR["_id"]})
            )[0]["_id"]

            await history_service.record_change(
                None, "employee", employee_id, "update", [], other_actor, base
            )
            await history_service.record_change(
                None, "area", ObjectId(), "create", [], ACTOR, base
            )
            await history_service.record_change(
                None,
                "employee",
                employee_id,
                "update",
                [],
                ACTOR,
                base - timedelta(days=10),
            )

            filters = HistoryQuery(
                entity_type="employee",
                actor_id=str(ACTOR["_id"]),
                date_from=base - timedelta(minutes=1),
                date_to=base + timedelta(minutes=1),
            )

            results = await history_service.query_history(filters)

            assert [entry["_id"] for entry in results] == [matching_id]

    asyncio.run(scenario())


def test_query_history_returns_empty_list_for_inverted_date_range(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            base = _ahora()
            await history_service.record_change(
                None, "area", ObjectId(), "create", [], ACTOR, base
            )

            filters = HistoryQuery(date_from=base, date_to=base - timedelta(days=1))

            results = await history_service.query_history(filters)

            assert results == []

    asyncio.run(scenario())


def test_query_history_returns_empty_list_for_actor_id_with_no_matches(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await history_service.record_change(
                None, "area", ObjectId(), "create", [], ACTOR, _ahora()
            )

            filters = HistoryQuery(actor_id=str(ObjectId()))

            results = await history_service.query_history(filters)

            assert results == []

    asyncio.run(scenario())


def test_query_history_returns_empty_list_for_malformed_actor_id(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await history_service.record_change(
                None, "area", ObjectId(), "create", [], ACTOR, _ahora()
            )

            filters = HistoryQuery(actor_id="not-an-object-id")

            results = await history_service.query_history(filters)

            assert results == []

    asyncio.run(scenario())


def test_query_history_skips_entity_existence_check_for_login_entity_type(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            filters = HistoryQuery(entity_type="login", entity_id=str(ObjectId()))

            results = await history_service.query_history(filters)

            assert results == []

    asyncio.run(scenario())
