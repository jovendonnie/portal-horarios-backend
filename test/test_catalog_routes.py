import asyncio
import inspect

import pytest
from bson import ObjectId
from fastapi import HTTPException, status

from conftest import mongo_test_session
from src.api.deps import require_admin
from src.api.routes import areas, statuses
from src.models.catalog import ensure_indexes
from src.schemas.area import AreaCreate, AreaUpdate
from src.schemas.estado import EstadoCreate, EstadoUpdate

ACTOR = {"_id": ObjectId(), "role": "admin"}

CATALOGS = [
    (areas, "areas", AreaCreate, AreaUpdate, "area"),
    (statuses, "estados", EstadoCreate, EstadoUpdate, "status"),
]


def _actor_dependency(route_function):
    signature = inspect.signature(route_function)
    param_name = "actor" if "actor" in signature.parameters else "_actor"
    return signature.parameters[param_name].default.dependency


def _status_code_for(module, endpoint) -> int | None:
    for route in module.router.routes:
        if route.endpoint is endpoint:
            return route.status_code
    return None


@pytest.mark.parametrize("module,collection_name,create_cls,update_cls,entry_field", CATALOGS)
def test_routes_require_admin(module, collection_name, create_cls, update_cls, entry_field) -> None:
    assert _actor_dependency(module.create_entry_route) is require_admin
    assert _actor_dependency(module.list_entries_route) is require_admin
    assert _actor_dependency(module.rename_entry_route) is require_admin
    assert _actor_dependency(module.disable_entry_route) is require_admin
    assert _actor_dependency(module.enable_entry_route) is require_admin


def test_router_registers_catalog_routes() -> None:
    from src.main import app

    schema = app.openapi()

    assert set(schema["paths"]["/areas"].keys()) >= {"post", "get"}
    assert set(schema["paths"]["/areas/{entry_id}"].keys()) >= {"patch"}
    assert set(schema["paths"]["/areas/{entry_id}/disable"].keys()) >= {"patch"}
    assert set(schema["paths"]["/areas/{entry_id}/enable"].keys()) >= {"patch"}
    assert set(schema["paths"]["/statuses"].keys()) >= {"post", "get"}
    assert set(schema["paths"]["/statuses/{entry_id}"].keys()) >= {"patch"}
    assert set(schema["paths"]["/statuses/{entry_id}/disable"].keys()) >= {"patch"}
    assert set(schema["paths"]["/statuses/{entry_id}/enable"].keys()) >= {"patch"}


@pytest.mark.parametrize("module,collection_name,create_cls,update_cls,entry_field", CATALOGS)
def test_create_entry_route_returns_created_entry(
    use_test_db, module, collection_name, create_cls, update_cls, entry_field
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)

            created = await module.create_entry_route(create_cls(name="Ventas"), ACTOR)

            assert created.name == "Ventas"
            assert created.is_enabled is True
            assert _status_code_for(module, module.create_entry_route) == status.HTTP_201_CREATED

    asyncio.run(scenario())


@pytest.mark.parametrize("module,collection_name,create_cls,update_cls,entry_field", CATALOGS)
def test_create_entry_route_maps_invalid_name_to_422(
    use_test_db, module, collection_name, create_cls, update_cls, entry_field
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            invalid_data = create_cls.model_construct(name="")

            with pytest.raises(HTTPException) as exc_info:
                await module.create_entry_route(invalid_data, ACTOR)

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())


@pytest.mark.parametrize("module,collection_name,create_cls,update_cls,entry_field", CATALOGS)
def test_create_entry_route_maps_duplicate_to_409(
    use_test_db, module, collection_name, create_cls, update_cls, entry_field
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            await module.create_entry_route(create_cls(name="Ventas"), ACTOR)

            with pytest.raises(HTTPException) as exc_info:
                await module.create_entry_route(create_cls(name="Ventas"), ACTOR)

            assert exc_info.value.status_code == 409

    asyncio.run(scenario())


@pytest.mark.parametrize("module,collection_name,create_cls,update_cls,entry_field", CATALOGS)
def test_list_entries_route_filters_by_enabled(
    use_test_db, module, collection_name, create_cls, update_cls, entry_field
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            await module.create_entry_route(create_cls(name="Ventas"), ACTOR)
            disabled = await module.create_entry_route(create_cls(name="Soporte"), ACTOR)
            await module.disable_entry_route(disabled.id, ACTOR)

            disabled_only = await module.list_entries_route(False, ACTOR)

            assert [entry.name for entry in disabled_only] == ["Soporte"]

    asyncio.run(scenario())


@pytest.mark.parametrize("module,collection_name,create_cls,update_cls,entry_field", CATALOGS)
def test_rename_entry_route_returns_renamed_entry(
    use_test_db, module, collection_name, create_cls, update_cls, entry_field
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            created = await module.create_entry_route(create_cls(name="Ventas"), ACTOR)

            renamed = await module.rename_entry_route(created.id, update_cls(name="Comercial"), ACTOR)

            assert renamed.name == "Comercial"

    asyncio.run(scenario())


@pytest.mark.parametrize("module,collection_name,create_cls,update_cls,entry_field", CATALOGS)
def test_rename_entry_route_maps_not_found_to_404(
    use_test_db, module, collection_name, create_cls, update_cls, entry_field
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)

            with pytest.raises(HTTPException) as exc_info:
                await module.rename_entry_route(str(ObjectId()), update_cls(name="Comercial"), ACTOR)

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())


@pytest.mark.parametrize("module,collection_name,create_cls,update_cls,entry_field", CATALOGS)
def test_rename_entry_route_maps_duplicate_to_409(
    use_test_db, module, collection_name, create_cls, update_cls, entry_field
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            await module.create_entry_route(create_cls(name="Ventas"), ACTOR)
            other = await module.create_entry_route(create_cls(name="Soporte"), ACTOR)

            with pytest.raises(HTTPException) as exc_info:
                await module.rename_entry_route(other.id, update_cls(name="Ventas"), ACTOR)

            assert exc_info.value.status_code == 409

    asyncio.run(scenario())


@pytest.mark.parametrize("module,collection_name,create_cls,update_cls,entry_field", CATALOGS)
def test_disable_entry_route_returns_affected_count(
    use_test_db, module, collection_name, create_cls, update_cls, entry_field
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await module.create_entry_route(create_cls(name="Ventas"), ACTOR)
            await module.create_entry_route(create_cls(name="Soporte"), ACTOR)

            result = await module.disable_entry_route(entry.id, ACTOR)

            assert getattr(result, entry_field).is_enabled is False
            assert result.affected_employees == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("module,collection_name,create_cls,update_cls,entry_field", CATALOGS)
def test_disable_entry_route_maps_last_enabled_to_409(
    use_test_db, module, collection_name, create_cls, update_cls, entry_field
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await module.create_entry_route(create_cls(name="Ventas"), ACTOR)

            with pytest.raises(HTTPException) as exc_info:
                await module.disable_entry_route(entry.id, ACTOR)

            assert exc_info.value.status_code == 409

    asyncio.run(scenario())


@pytest.mark.parametrize("module,collection_name,create_cls,update_cls,entry_field", CATALOGS)
def test_disable_entry_route_maps_not_found_to_404(
    use_test_db, module, collection_name, create_cls, update_cls, entry_field
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)

            with pytest.raises(HTTPException) as exc_info:
                await module.disable_entry_route(str(ObjectId()), ACTOR)

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())


@pytest.mark.parametrize("module,collection_name,create_cls,update_cls,entry_field", CATALOGS)
def test_enable_entry_route_returns_enabled_entry(
    use_test_db, module, collection_name, create_cls, update_cls, entry_field
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)
            entry = await module.create_entry_route(create_cls(name="Ventas"), ACTOR)
            await module.create_entry_route(create_cls(name="Soporte"), ACTOR)
            await module.disable_entry_route(entry.id, ACTOR)

            enabled = await module.enable_entry_route(entry.id, ACTOR)

            assert enabled.is_enabled is True

    asyncio.run(scenario())


@pytest.mark.parametrize("module,collection_name,create_cls,update_cls,entry_field", CATALOGS)
def test_enable_entry_route_maps_not_found_to_404(
    use_test_db, module, collection_name, create_cls, update_cls, entry_field
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes(collection_name)

            with pytest.raises(HTTPException) as exc_info:
                await module.enable_entry_route(str(ObjectId()), ACTOR)

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())
