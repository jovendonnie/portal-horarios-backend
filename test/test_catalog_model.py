import asyncio
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from conftest import mongo_test_session
from src.models.catalog import (
    count_enabled,
    delete_entry,
    ensure_indexes,
    find_entry_by_id,
    find_entry_by_name,
    insert_entry,
    list_entries,
    mark_entry_predefined,
    set_entry_enabled,
    update_entry_name,
)

COLLECTIONS = ["areas", "estados"]


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_ensure_indexes_rejects_duplicate_name_case_and_space_insensitive(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            actor_id = ObjectId()
            ahora = _ahora()

            await insert_entry(collection_name, "Ventas", actor_id, ahora)

            with pytest.raises(DuplicateKeyError):
                await insert_entry(collection_name, "  VENTAS  ", actor_id, ahora)

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_ensure_indexes_rejects_duplicate_name_even_if_disabled(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            actor_id = ObjectId()
            ahora = _ahora()

            entry_id = await insert_entry(collection_name, "Ventas", actor_id, ahora)
            await set_entry_enabled(collection_name, entry_id, False, actor_id, ahora)

            with pytest.raises(DuplicateKeyError):
                await insert_entry(collection_name, "Ventas", actor_id, ahora)

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_list_entries_never_returns_duplicate_ids_with_index_active(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            actor_id = ObjectId()
            ahora = _ahora()

            await insert_entry(collection_name, "Ventas", actor_id, ahora)

            with pytest.raises(DuplicateKeyError):
                await insert_entry(collection_name, "  VENTAS  ", actor_id, ahora)

            entries = await list_entries(collection_name)

            assert len(entries) == 1
            assert len({entry["_id"] for entry in entries}) == len(entries)

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_insert_entry_sets_default_is_enabled_and_created_at(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            entry_id = await insert_entry(collection_name, "Ventas", actor_id, ahora)
            found = await find_entry_by_id(collection_name, entry_id)

            assert found is not None
            assert found["is_enabled"] is True
            assert found["created_at"] is not None
            assert found["created_by"] == actor_id

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_find_entry_by_id_returns_none_when_not_found(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            assert await find_entry_by_id(collection_name, ObjectId()) is None

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_find_entry_by_name_is_case_insensitive(use_test_db, collection_name) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            await insert_entry(collection_name, "Ventas", actor_id, ahora)

            found = await find_entry_by_name(collection_name, "VENTAS")

            assert found is not None
            assert found["name"] == "Ventas"

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_list_entries_filters_by_enabled(use_test_db, collection_name) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            enabled_id = await insert_entry(collection_name, "Ventas", actor_id, ahora)
            disabled_id = await insert_entry(collection_name, "Soporte", actor_id, ahora)
            await set_entry_enabled(collection_name, disabled_id, False, actor_id, ahora)

            all_entries = await list_entries(collection_name)
            enabled_entries = await list_entries(collection_name, enabled=True)
            disabled_entries = await list_entries(collection_name, enabled=False)

            assert {e["_id"] for e in all_entries} == {enabled_id, disabled_id}
            assert {e["_id"] for e in enabled_entries} == {enabled_id}
            assert {e["_id"] for e in disabled_entries} == {disabled_id}

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_update_entry_name_changes_only_name_and_audit_fields(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            other_actor_id = ObjectId()
            ahora = _ahora()
            despues = _ahora()

            entry_id = await insert_entry(collection_name, "Ventas", actor_id, ahora)
            before = await find_entry_by_id(collection_name, entry_id)

            modified = await update_entry_name(
                collection_name, entry_id, "Comercial", other_actor_id, despues
            )
            found = await find_entry_by_id(collection_name, entry_id)

            assert modified is True
            assert found["name"] == "Comercial"
            assert found["updated_at"] is not None
            assert found["updated_by"] == other_actor_id
            assert found["is_enabled"] is True
            assert found["created_at"] == before["created_at"]
            assert found["created_by"] == actor_id

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_count_enabled_counts_only_enabled_entries(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            await insert_entry(collection_name, "Ventas", actor_id, ahora)
            disabled_id = await insert_entry(collection_name, "Soporte", actor_id, ahora)
            await set_entry_enabled(collection_name, disabled_id, False, actor_id, ahora)

            assert await count_enabled(collection_name) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_set_entry_enabled_disables_and_updates_audit_fields(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            entry_id = await insert_entry(collection_name, "Ventas", actor_id, ahora)

            modified = await set_entry_enabled(
                collection_name, entry_id, False, actor_id, ahora
            )
            found = await find_entry_by_id(collection_name, entry_id)

            assert modified is True
            assert found["is_enabled"] is False
            assert found["updated_at"] is not None
            assert found["updated_by"] == actor_id

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_set_entry_enabled_is_idempotent_when_already_enabled(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            entry_id = await insert_entry(collection_name, "Ventas", actor_id, ahora)

            await set_entry_enabled(collection_name, entry_id, True, actor_id, ahora)
            found = await find_entry_by_id(collection_name, entry_id)

            assert found["is_enabled"] is True

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_insert_entry_omits_is_predefined_when_not_given(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            entry_id = await insert_entry(collection_name, "Ventas", actor_id, ahora)
            found = await find_entry_by_id(collection_name, entry_id)

            assert "is_predefined" not in found

    asyncio.run(scenario())


def test_insert_entry_sets_is_predefined_when_given(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            entry_id = await insert_entry(
                "estados", "Presencial", actor_id, ahora, is_predefined=True
            )
            found = await find_entry_by_id("estados", entry_id)

            assert found["is_predefined"] is True

    asyncio.run(scenario())


def test_mark_entry_predefined_sets_flag_without_touching_other_fields(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            entry_id = await insert_entry("estados", "Presencial", actor_id, ahora)
            await set_entry_enabled("estados", entry_id, False, actor_id, ahora)
            before = await find_entry_by_id("estados", entry_id)

            modified = await mark_entry_predefined("estados", entry_id)
            found = await find_entry_by_id("estados", entry_id)

            assert modified is True
            assert found["is_predefined"] is True
            assert found["is_enabled"] is False
            assert found["name"] == "Presencial"
            assert found["updated_at"] == before["updated_at"]
            assert found["updated_by"] == before["updated_by"]

    asyncio.run(scenario())


def test_mark_entry_predefined_returns_false_when_already_set(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            entry_id = await insert_entry(
                "estados", "Presencial", actor_id, ahora, is_predefined=True
            )

            modified = await mark_entry_predefined("estados", entry_id)

            assert modified is False

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_insert_entry_behaves_the_same_with_explicit_session_none(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            without_arg = await insert_entry(collection_name, "Ventas", actor_id, ahora)
            with_none = await insert_entry(
                collection_name, "Soporte", actor_id, ahora, session=None
            )

            assert without_arg is not None
            assert with_none is not None
            assert without_arg != with_none

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_delete_entry_removes_existing_entry(use_test_db, collection_name) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            entry_id = await insert_entry(collection_name, "Ventas", actor_id, ahora)

            deleted = await delete_entry(collection_name, entry_id)
            found = await find_entry_by_id(collection_name, entry_id)

            assert deleted is True
            assert found is None

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_delete_entry_returns_false_when_not_found(use_test_db, collection_name) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            deleted = await delete_entry(collection_name, ObjectId())

            assert deleted is False

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_delete_entry_behaves_the_same_with_explicit_session_none(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            entry_id = await insert_entry(collection_name, "Ventas", actor_id, ahora)

            deleted = await delete_entry(collection_name, entry_id, session=None)
            found = await find_entry_by_id(collection_name, entry_id)

            assert deleted is True
            assert found is None

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_update_entry_name_behaves_the_same_with_explicit_session_none(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            entry_id = await insert_entry(collection_name, "Ventas", actor_id, ahora)

            modified = await update_entry_name(
                collection_name, entry_id, "Comercial", actor_id, ahora, session=None
            )
            found = await find_entry_by_id(collection_name, entry_id)

            assert modified is True
            assert found["name"] == "Comercial"

    asyncio.run(scenario())


@pytest.mark.parametrize("collection_name", COLLECTIONS)
def test_set_entry_enabled_behaves_the_same_with_explicit_session_none(
    use_test_db, collection_name
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            actor_id = ObjectId()
            ahora = _ahora()

            entry_id = await insert_entry(collection_name, "Ventas", actor_id, ahora)

            modified = await set_entry_enabled(
                collection_name, entry_id, False, actor_id, ahora, session=None
            )
            found = await find_entry_by_id(collection_name, entry_id)

            assert modified is True
            assert found["is_enabled"] is False

    asyncio.run(scenario())
