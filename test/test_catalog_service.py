import asyncio
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from conftest import mongo_test_session
from src.models import catalog as catalog_model
from src.models.catalog import ensure_indexes
from src.models.history import list_entries as list_history_entries
from src.services import catalog_service

ACTOR = {"_id": ObjectId(), "full_name": "Admin Actor"}

CATALOGS = [("areas", "Área"), ("estados", "Estado")]

_ENTITY_TYPES = {"areas": "area", "estados": "status"}


async def _count_assigned_stub(entry_id) -> int:
    return 3


def test_invalid_name_error_is_exception_with_spanish_message() -> None:
    error = catalog_service.InvalidNameError()

    assert isinstance(error, Exception)
    assert "nombre" in str(error).lower()


def test_duplicate_entry_error_is_exception_with_spanish_message() -> None:
    error = catalog_service.DuplicateEntryError("Área")

    assert isinstance(error, Exception)
    assert "Área" in str(error)


def test_entry_not_found_error_is_exception_with_spanish_message() -> None:
    error = catalog_service.EntryNotFoundError("Área")

    assert isinstance(error, Exception)
    assert "Área" in str(error)


def test_last_enabled_entry_error_is_exception_with_spanish_message() -> None:
    error = catalog_service.LastEnabledEntryError("Área")

    assert isinstance(error, Exception)
    assert "Área" in str(error)


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_create_entry_success(use_test_db, collection_name, entity_label) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)

            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )

            assert entry["name"] == "Ventas"
            assert entry["is_enabled"] is True
            assert entry["created_by"] == ACTOR["_id"]

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_create_entry_rejects_empty_name(use_test_db, collection_name, entity_label) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)

            with pytest.raises(catalog_service.InvalidNameError):
                await catalog_service.create_entry(collection_name, entity_label, "", ACTOR)

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_create_entry_rejects_name_longer_than_100_chars(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)

            with pytest.raises(catalog_service.InvalidNameError):
                await catalog_service.create_entry(
                    collection_name, entity_label, "x" * 101, ACTOR
                )

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_create_entry_rejects_exact_duplicate(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            await catalog_service.create_entry(collection_name, entity_label, "Ventas", ACTOR)

            with pytest.raises(catalog_service.DuplicateEntryError):
                await catalog_service.create_entry(
                    collection_name, entity_label, "Ventas", ACTOR
                )

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_create_entry_rejects_duplicate_case_and_space_insensitive(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            await catalog_service.create_entry(collection_name, entity_label, "Ventas", ACTOR)

            with pytest.raises(catalog_service.DuplicateEntryError):
                await catalog_service.create_entry(
                    collection_name, entity_label, "  VENTAS  ", ACTOR
                )

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_create_entry_rejects_duplicate_against_disabled_entry(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )
            await catalog_service.create_entry(collection_name, entity_label, "Soporte", ACTOR)
            await catalog_service.set_enabled(
                collection_name, entity_label, entry["_id"], False, ACTOR, _count_assigned_stub
            )

            with pytest.raises(catalog_service.DuplicateEntryError):
                await catalog_service.create_entry(
                    collection_name, entity_label, "Ventas", ACTOR
                )

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_create_entry_raises_duplicate_entry_error_on_race_condition(
    use_test_db, monkeypatch, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)

            async def _raise_duplicate_key(*args, **kwargs):
                raise DuplicateKeyError("E11000 duplicate key error")

            monkeypatch.setattr(catalog_model, "insert_entry", _raise_duplicate_key)

            with pytest.raises(catalog_service.DuplicateEntryError):
                await catalog_service.create_entry(
                    collection_name, entity_label, "Ventas", ACTOR
                )

            assert await catalog_model.find_entry_by_name(collection_name, "Ventas") is None

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_list_entries_filters_by_enabled(use_test_db, collection_name, entity_label) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            enabled_entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )
            disabled_entry = await catalog_service.create_entry(
                collection_name, entity_label, "Soporte", ACTOR
            )
            await catalog_service.set_enabled(
                collection_name,
                entity_label,
                disabled_entry["_id"],
                False,
                ACTOR,
                _count_assigned_stub,
            )

            all_entries = await catalog_service.list_entries(collection_name)
            enabled_entries = await catalog_service.list_entries(collection_name, enabled=True)
            disabled_entries = await catalog_service.list_entries(collection_name, enabled=False)

            assert {e["_id"] for e in all_entries} == {enabled_entry["_id"], disabled_entry["_id"]}
            assert {e["_id"] for e in enabled_entries} == {enabled_entry["_id"]}
            assert {e["_id"] for e in disabled_entries} == {disabled_entry["_id"]}

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_rename_entry_success(use_test_db, collection_name, entity_label) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )

            renamed = await catalog_service.rename_entry(
                collection_name, entity_label, entry["_id"], "Comercial", ACTOR
            )

            assert renamed["name"] == "Comercial"

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_rename_entry_raises_not_found(use_test_db, collection_name, entity_label) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)

            with pytest.raises(catalog_service.EntryNotFoundError):
                await catalog_service.rename_entry(
                    collection_name, entity_label, ObjectId(), "Comercial", ACTOR
                )

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_rename_entry_rejects_name_used_by_another_entry(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            await catalog_service.create_entry(collection_name, entity_label, "Ventas", ACTOR)
            other_entry = await catalog_service.create_entry(
                collection_name, entity_label, "Soporte", ACTOR
            )

            with pytest.raises(catalog_service.DuplicateEntryError):
                await catalog_service.rename_entry(
                    collection_name, entity_label, other_entry["_id"], "Ventas", ACTOR
                )

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_rename_entry_raises_duplicate_entry_error_on_race_condition(
    use_test_db, monkeypatch, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )

            async def _raise_duplicate_key(*args, **kwargs):
                raise DuplicateKeyError("E11000 duplicate key error")

            monkeypatch.setattr(catalog_model, "update_entry_name", _raise_duplicate_key)

            with pytest.raises(catalog_service.DuplicateEntryError):
                await catalog_service.rename_entry(
                    collection_name, entity_label, entry["_id"], "Comercial", ACTOR
                )

            unchanged = await catalog_model.find_entry_by_id(collection_name, entry["_id"])
            assert unchanged["name"] == "Ventas"

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_rename_entry_with_same_name_does_not_raise(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )

            renamed = await catalog_service.rename_entry(
                collection_name, entity_label, entry["_id"], "Ventas", ACTOR
            )

            assert renamed["name"] == "Ventas"

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_set_enabled_disable_returns_affected_count(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )
            await catalog_service.create_entry(collection_name, entity_label, "Soporte", ACTOR)

            updated, affected = await catalog_service.set_enabled(
                collection_name, entity_label, entry["_id"], False, ACTOR, _count_assigned_stub
            )

            assert updated["is_enabled"] is False
            assert affected == 3

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_set_enabled_raises_last_enabled_entry_error(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )

            with pytest.raises(catalog_service.LastEnabledEntryError):
                await catalog_service.set_enabled(
                    collection_name,
                    entity_label,
                    entry["_id"],
                    False,
                    ACTOR,
                    _count_assigned_stub,
                )

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_set_enabled_disable_already_disabled_is_idempotent(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )
            await catalog_service.create_entry(collection_name, entity_label, "Soporte", ACTOR)

            disabled_once, _ = await catalog_service.set_enabled(
                collection_name, entity_label, entry["_id"], False, ACTOR, _count_assigned_stub
            )

            disabled_again, affected_again = await catalog_service.set_enabled(
                collection_name, entity_label, entry["_id"], False, ACTOR, _count_assigned_stub
            )

            assert disabled_again["is_enabled"] is False
            assert disabled_again["updated_at"] == disabled_once["updated_at"]
            assert affected_again is None

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_set_enabled_enable_again(use_test_db, collection_name, entity_label) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )
            await catalog_service.create_entry(collection_name, entity_label, "Soporte", ACTOR)
            await catalog_service.set_enabled(
                collection_name, entity_label, entry["_id"], False, ACTOR, _count_assigned_stub
            )

            updated, affected = await catalog_service.set_enabled(
                collection_name, entity_label, entry["_id"], True, ACTOR, _count_assigned_stub
            )

            assert updated["is_enabled"] is True
            assert affected is None

    asyncio.run(scenario())


# --- Auditoría del historial en create_entry / rename_entry / set_enabled (T025-T028) ---


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_create_entry_generates_create_history_entry(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)

            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )

            entries = await list_history_entries(
                {"entity_type": _ENTITY_TYPES[collection_name], "entity_id": entry["_id"]}
            )

            assert len(entries) == 1
            assert entries[0]["action"] == "create"
            assert entries[0]["actor_id"] == ACTOR["_id"]
            assert entries[0]["actor_name"] == ACTOR["full_name"]
            assert entries[0]["changes"] == []

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_rename_entry_with_different_name_generates_update_entry(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )

            await catalog_service.rename_entry(
                collection_name, entity_label, entry["_id"], "Comercial", ACTOR
            )

            entries = await list_history_entries(
                {
                    "entity_type": _ENTITY_TYPES[collection_name],
                    "entity_id": entry["_id"],
                    "action": "update",
                }
            )

            assert len(entries) == 1
            assert entries[0]["changes"] == [
                {"field": "name", "old_value": "Ventas", "new_value": "Comercial"}
            ]

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_rename_entry_with_same_name_does_not_generate_history_entry(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )

            await catalog_service.rename_entry(
                collection_name, entity_label, entry["_id"], "Ventas", ACTOR
            )

            entries = await list_history_entries(
                {
                    "entity_type": _ENTITY_TYPES[collection_name],
                    "entity_id": entry["_id"],
                    "action": "update",
                }
            )

            assert entries == []

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_set_enabled_disable_generates_disable_history_entry(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )
            await catalog_service.create_entry(collection_name, entity_label, "Soporte", ACTOR)

            await catalog_service.set_enabled(
                collection_name, entity_label, entry["_id"], False, ACTOR, _count_assigned_stub
            )

            entries = await list_history_entries(
                {
                    "entity_type": _ENTITY_TYPES[collection_name],
                    "entity_id": entry["_id"],
                    "action": "disable",
                }
            )

            assert len(entries) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_set_enabled_enable_again_generates_enable_history_entry(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )
            await catalog_service.create_entry(collection_name, entity_label, "Soporte", ACTOR)
            await catalog_service.set_enabled(
                collection_name, entity_label, entry["_id"], False, ACTOR, _count_assigned_stub
            )

            await catalog_service.set_enabled(
                collection_name, entity_label, entry["_id"], True, ACTOR, _count_assigned_stub
            )

            entries = await list_history_entries(
                {
                    "entity_type": _ENTITY_TYPES[collection_name],
                    "entity_id": entry["_id"],
                    "action": "enable",
                }
            )

            assert len(entries) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name,entity_label", CATALOGS)
def test_set_enabled_already_disabled_does_not_generate_extra_history_entry(
    use_test_db, collection_name, entity_label
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await catalog_service.create_entry(
                collection_name, entity_label, "Ventas", ACTOR
            )
            await catalog_service.create_entry(collection_name, entity_label, "Soporte", ACTOR)
            await catalog_service.set_enabled(
                collection_name, entity_label, entry["_id"], False, ACTOR, _count_assigned_stub
            )

            await catalog_service.set_enabled(
                collection_name, entity_label, entry["_id"], False, ACTOR, _count_assigned_stub
            )

            entries = await list_history_entries(
                {
                    "entity_type": _ENTITY_TYPES[collection_name],
                    "entity_id": entry["_id"],
                    "action": "disable",
                }
            )

            assert len(entries) == 1

    asyncio.run(scenario())


def test_create_entry_marks_new_status_as_not_predefined(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("estados")

            entry = await catalog_service.create_entry("estados", "Estado", "Presencial", ACTOR)

            assert entry["is_predefined"] is False

    asyncio.run(scenario())


def test_create_entry_does_not_add_is_predefined_to_areas(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("areas")

            entry = await catalog_service.create_entry("areas", "Área", "Ventas", ACTOR)

            assert "is_predefined" not in entry

    asyncio.run(scenario())


def test_seed_predefined_estados_creates_the_seven_from_an_empty_catalog(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("estados")

            entries = await catalog_service.seed_predefined_estados(ACTOR)

            assert [entry["name"] for entry in entries] == catalog_service.PREDEFINED_STATUS_NAMES
            assert all(entry["is_predefined"] is True for entry in entries)
            assert all(entry["is_enabled"] is True for entry in entries)

    asyncio.run(scenario())


def test_seed_predefined_estados_recognizes_existing_entry_by_name_without_duplicating(
    use_test_db,
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("estados")
            await catalog_service.create_entry("estados", "Estado", "Otro habilitado", ACTOR)
            existing = await catalog_service.create_entry("estados", "Estado", "Presencial", ACTOR)
            await catalog_service.set_enabled(
                "estados", "Estado", existing["_id"], False, ACTOR, _count_assigned_stub
            )

            entries = await catalog_service.seed_predefined_estados(ACTOR)

            presencial = next(entry for entry in entries if entry["name"] == "Presencial")
            assert presencial["_id"] == existing["_id"]
            assert presencial["is_predefined"] is True
            assert presencial["is_enabled"] is False

            all_entries = await catalog_service.list_entries("estados")
            assert len([e for e in all_entries if e["name"] == "Presencial"]) == 1

    asyncio.run(scenario())


def test_seed_predefined_estados_is_idempotent(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("estados")

            first = await catalog_service.seed_predefined_estados(ACTOR)
            second = await catalog_service.seed_predefined_estados(ACTOR)

            assert {e["_id"] for e in first} == {e["_id"] for e in second}
            all_entries = await catalog_service.list_entries("estados")
            assert len(all_entries) == len(catalog_service.PREDEFINED_STATUS_NAMES)

            history_entries = await list_history_entries({"entity_type": "status"})
            assert len(history_entries) == len(catalog_service.PREDEFINED_STATUS_NAMES)

    asyncio.run(scenario())


# --- Spec 009: Estados que bloquean turnos (RF-5) ---

def test_create_entry_marks_new_status_as_not_blocking_shifts_by_default(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("estados")

            entry = await catalog_service.create_entry("estados", "Estado", "Comisión", ACTOR)

            assert entry["blocks_shifts"] is False

    asyncio.run(scenario())


def test_create_entry_accepts_a_status_that_blocks_shifts(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("estados")

            entry = await catalog_service.create_entry(
                "estados", "Estado", "Suspensión", ACTOR, blocks_shifts=True
            )

            assert entry["blocks_shifts"] is True

    asyncio.run(scenario())


def test_create_entry_does_not_add_blocks_shifts_to_other_catalogs(use_test_db) -> None:
    """El indicador es exclusivo de Estados: en Áreas y Cargos la clave no se escribe."""
    async def scenario() -> None:
        async with mongo_test_session():
            for collection_name, entity_label in (("areas", "Área"), ("cargos", "Cargo")):
                await ensure_indexes(collection_name)

                entry = await catalog_service.create_entry(
                    collection_name, entity_label, "Ventas", ACTOR, blocks_shifts=True
                )

                assert "blocks_shifts" not in entry

    asyncio.run(scenario())


def test_set_blocks_shifts_updates_the_status_and_audits_the_diff(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("estados")
            created = await catalog_service.create_entry("estados", "Estado", "Comisión", ACTOR)

            updated = await catalog_service.set_blocks_shifts(
                "estados", "Estado", created["_id"], True, ACTOR
            )

            assert updated["blocks_shifts"] is True
            assert updated["updated_by"] == ACTOR["_id"]

            entries = await list_history_entries(
                {"entity_type": "status", "entity_id": created["_id"], "action": "update"}
            )
            assert entries[0]["changes"] == [
                {"field": "blocks_shifts", "old_value": False, "new_value": True}
            ]

    asyncio.run(scenario())


def test_set_blocks_shifts_with_the_same_value_is_a_noop(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("estados")
            created = await catalog_service.create_entry("estados", "Estado", "Comisión", ACTOR)

            await catalog_service.set_blocks_shifts(
                "estados", "Estado", created["_id"], False, ACTOR
            )

            entries = await list_history_entries(
                {"entity_type": "status", "entity_id": created["_id"], "action": "update"}
            )
            assert entries == []

    asyncio.run(scenario())


def test_set_blocks_shifts_rejects_an_unknown_id(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("estados")

            with pytest.raises(catalog_service.EntryNotFoundError):
                await catalog_service.set_blocks_shifts(
                    "estados", "Estado", ObjectId(), True, ACTOR
                )

    asyncio.run(scenario())


def test_seed_classifies_which_predefined_statuses_block_shifts(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("estados")

            entries = await catalog_service.seed_predefined_estados(ACTOR)

            by_name = {entry["name"]: entry["blocks_shifts"] for entry in entries}
            assert by_name == {
                "Presencial": False,
                "Virtual/Casa": False,
                "Permiso": True,
                "Vacaciones": True,
                "Licencia": True,
                "Incapacidad": True,
                "Día libre": True,
            }

    asyncio.run(scenario())


def test_seed_classifies_a_status_that_already_existed_without_the_field(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("estados")
            # Simula un Estado creado antes de la spec 009: sin la clave en Mongo.
            await catalog_model.insert_entry(
                "estados", "Vacaciones", ACTOR["_id"], datetime.now(timezone.utc)
            )

            entries = await catalog_service.seed_predefined_estados(ACTOR)

            vacaciones = next(entry for entry in entries if entry["name"] == "Vacaciones")
            assert vacaciones["blocks_shifts"] is True

    asyncio.run(scenario())


def test_seed_does_not_revert_a_manual_classification(use_test_db) -> None:
    """`blocks_shifts` solo se escribe cuando la clave no existe: si Gestión Humana
    ya lo cambió a mano, volver a correr el seed no lo revierte."""
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("estados")
            seeded = await catalog_service.seed_predefined_estados(ACTOR)
            presencial = next(entry for entry in seeded if entry["name"] == "Presencial")
            await catalog_service.set_blocks_shifts(
                "estados", "Estado", presencial["_id"], True, ACTOR
            )

            again = await catalog_service.seed_predefined_estados(ACTOR)

            presencial_again = next(entry for entry in again if entry["name"] == "Presencial")
            assert presencial_again["blocks_shifts"] is True

    asyncio.run(scenario())
