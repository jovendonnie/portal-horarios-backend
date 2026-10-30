import asyncio
import inspect

import pytest
from bson import ObjectId
from fastapi import HTTPException, status

from conftest import mongo_test_session
from src.api.deps import require_admin, require_read
from src.api.routes import positions
from src.models.catalog import ensure_indexes
from src.models.history import list_entries as list_history_entries
from src.schemas.position import PositionCreate, PositionDisableOut, PositionUpdate

ACTOR = {"_id": ObjectId(), "role": "gestion_humana", "full_name": "Admin Actor"}


def _actor_dependency(route_function):
    signature = inspect.signature(route_function)
    param_name = "actor" if "actor" in signature.parameters else "_actor"
    return signature.parameters[param_name].default.dependency


def test_routes_require_the_expected_roles() -> None:
    assert _actor_dependency(positions.create_entry_route) is require_admin
    assert _actor_dependency(positions.list_entries_route) is require_read
    assert _actor_dependency(positions.rename_entry_route) is require_admin
    assert _actor_dependency(positions.disable_entry_route) is require_admin
    assert _actor_dependency(positions.enable_entry_route) is require_admin


def test_router_registers_position_routes() -> None:
    from src.main import app

    schema = app.openapi()

    assert set(schema["paths"]["/positions"].keys()) >= {"post", "get"}
    assert set(schema["paths"]["/positions/{entry_id}"].keys()) >= {"patch"}
    assert set(schema["paths"]["/positions/{entry_id}/disable"].keys()) >= {"patch"}
    assert set(schema["paths"]["/positions/{entry_id}/enable"].keys()) >= {"patch"}


def test_disable_response_omits_affected_employees() -> None:
    """El Cargo del empleado sigue siendo la lista fija de la spec 002: no hay
    empleados que contar y devolver 0 sería mentir (plan.md decisión 2)."""
    assert set(PositionDisableOut.model_fields) == {"position"}


def test_create_list_rename_and_toggle_a_position(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("cargos")

            created = await positions.create_entry_route(PositionCreate(name="Practicante"), ACTOR)
            assert created.name == "Practicante"
            assert created.is_enabled is True

            renamed = await positions.rename_entry_route(
                created.id, PositionUpdate(name="Aprendiz"), ACTOR
            )
            assert renamed.name == "Aprendiz"

            # Hace falta un segundo Cargo habilitado: el catálogo no permite
            # deshabilitar el último que queda habilitado.
            other = await positions.create_entry_route(PositionCreate(name="Líder"), ACTOR)

            disabled = await positions.disable_entry_route(other.id, ACTOR)
            assert disabled.position.is_enabled is False

            only_disabled = await positions.list_entries_route(False, ACTOR)
            assert [entry.name for entry in only_disabled] == ["Líder"]

            enabled = await positions.enable_entry_route(other.id, ACTOR)
            assert enabled.is_enabled is True

            everything = await positions.list_entries_route(None, ACTOR)
            assert {entry.name for entry in everything} == {"Aprendiz", "Líder"}

    asyncio.run(scenario())


def test_create_maps_duplicate_name_to_409_ignoring_case(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("cargos")
            await positions.create_entry_route(PositionCreate(name="Practicante"), ACTOR)

            with pytest.raises(HTTPException) as exc_info:
                await positions.create_entry_route(PositionCreate(name="  practicante "), ACTOR)

            assert exc_info.value.status_code == status.HTTP_409_CONFLICT

    asyncio.run(scenario())


def test_create_maps_invalid_name_to_422(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("cargos")

            with pytest.raises(HTTPException) as exc_info:
                await positions.create_entry_route(PositionCreate.model_construct(name="   "), ACTOR)

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())


def test_unknown_or_malformed_id_maps_to_404(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("cargos")

            for entry_id in (str(ObjectId()), "no-es-un-object-id"):
                with pytest.raises(HTTPException) as exc_info:
                    await positions.rename_entry_route(entry_id, PositionUpdate(name="X"), ACTOR)
                assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    asyncio.run(scenario())


def test_disabling_the_last_enabled_position_maps_to_409(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("cargos")
            only_one = await positions.create_entry_route(PositionCreate(name="Practicante"), ACTOR)

            with pytest.raises(HTTPException) as exc_info:
                await positions.disable_entry_route(only_one.id, ACTOR)

            assert exc_info.value.status_code == status.HTTP_409_CONFLICT

    asyncio.run(scenario())


def test_changes_are_audited_as_position_entities(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes("cargos")
            created = await positions.create_entry_route(PositionCreate(name="Practicante"), ACTOR)
            await positions.rename_entry_route(created.id, PositionUpdate(name="Aprendiz"), ACTOR)

            entries = await list_history_entries({"entity_type": "position"})

            assert {entry["action"] for entry in entries} == {"create", "update"}
            assert all(entry["actor_name"] == "Admin Actor" for entry in entries)

    asyncio.run(scenario())
