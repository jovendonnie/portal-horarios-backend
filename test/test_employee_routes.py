import asyncio
import inspect
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi import HTTPException

from conftest import mongo_test_session
from src.api.deps import require_admin, require_read
from src.api.routes import employees
from src.models import catalog as catalog_model
from src.models.employee import ensure_indexes
from src.schemas.employee import EmployeeCreate, EmployeeStatusUpdate, EmployeeUpdate

ACTOR = {"_id": "admin-id", "role": "admin", "full_name": "Admin Actor"}


async def _seed_catalog_entry(collection_name: str, name: str) -> str:
    """Reutiliza la entrada si ya existe (idempotente), la crea si no."""
    existing = await catalog_model.find_entry_by_name(collection_name, name)
    if existing is not None:
        return str(existing["_id"])
    entry_id = await catalog_model.insert_entry(
        collection_name, name, ACTOR["_id"], datetime.now(timezone.utc)
    )
    return str(entry_id)


async def _disable_catalog_entry(collection_name: str, entry_id: str) -> None:
    await catalog_model.set_entry_enabled(
        collection_name, ObjectId(entry_id), False, ACTOR["_id"], datetime.now(timezone.utc)
    )


async def _make_create(
    full_name: str = "Carla Gómez",
    position: str = "lider",
    area_name: str = "Ventas",
    status_name: str = "Presencial",
) -> EmployeeCreate:
    area_id = await _seed_catalog_entry("areas", area_name)
    status_id = await _seed_catalog_entry("estados", status_name)
    return EmployeeCreate(full_name=full_name, position=position, area_id=area_id, status_id=status_id)


def _actor_dependency(route_function):
    signature = inspect.signature(route_function)
    param_name = "actor" if "actor" in signature.parameters else "_actor"
    return signature.parameters[param_name].default.dependency


def test_employee_routes_require_admin() -> None:
    assert _actor_dependency(employees.create_employee_route) is require_admin
    assert _actor_dependency(employees.list_employees_route) is require_read
    assert _actor_dependency(employees.get_employee_route) is require_read
    assert _actor_dependency(employees.update_employee_route) is require_admin
    assert _actor_dependency(employees.update_employee_status_route) is require_admin


def test_router_registers_employee_routes() -> None:
    from src.main import app

    schema = app.openapi()

    assert set(schema["paths"]["/employees"].keys()) >= {"post", "get"}
    assert set(schema["paths"]["/employees/{employee_id}"].keys()) >= {"get", "patch"}
    assert set(schema["paths"]["/employees/{employee_id}/status"].keys()) >= {"patch"}


def test_create_employee_route_returns_created_employee(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()

            created = await employees.create_employee_route(await _make_create(), ACTOR)

            assert created.full_name == "Carla Gómez"
            assert created.is_active is True
            assert created.area_name == "Ventas"
            assert created.status_name == "Presencial"

    asyncio.run(scenario())


def test_create_employee_route_maps_invalid_position_to_422(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            invalid_data = EmployeeCreate.model_construct(
                full_name="X", position="gerente", area_id="x", status_id="y"
            )

            with pytest.raises(HTTPException) as exc_info:
                await employees.create_employee_route(invalid_data, ACTOR)

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())


def test_create_employee_route_maps_duplicate_to_409(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            data = await _make_create()
            await employees.create_employee_route(data, ACTOR)

            with pytest.raises(HTTPException) as exc_info:
                await employees.create_employee_route(data, ACTOR)

            assert exc_info.value.status_code == 409

    asyncio.run(scenario())


def test_list_employees_route_returns_all(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await employees.create_employee_route(await _make_create("Empleado Uno"), ACTOR)
            await employees.create_employee_route(
                await _make_create("Empleado Dos", area_name="Soporte"), ACTOR
            )

            result = await employees.list_employees_route(ACTOR)

            names = {employee.full_name for employee in result}
            assert names == {"Empleado Uno", "Empleado Dos"}

    asyncio.run(scenario())


def test_get_employee_route_returns_detail(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            created = await employees.create_employee_route(await _make_create(), ACTOR)

            fetched = await employees.get_employee_route(created.id, ACTOR)

            assert fetched.full_name == "Carla Gómez"

    asyncio.run(scenario())


def test_get_employee_route_maps_not_found_to_404(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(HTTPException) as exc_info:
                await employees.get_employee_route(str(ObjectId()), ACTOR)

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())


def test_get_employee_route_maps_malformed_id_to_404(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(HTTPException) as exc_info:
                await employees.get_employee_route("no-es-un-object-id", ACTOR)

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())


def test_update_employee_route_returns_updated_employee(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            created = await employees.create_employee_route(await _make_create(), ACTOR)

            updated = await employees.update_employee_route(
                created.id, EmployeeUpdate(full_name="Carla Gómez Actualizada"), ACTOR
            )

            assert updated.full_name == "Carla Gómez Actualizada"
            assert updated.area == "Ventas"

    asyncio.run(scenario())


def test_update_employee_route_maps_not_found_to_404(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(HTTPException) as exc_info:
                await employees.update_employee_route(
                    str(ObjectId()), EmployeeUpdate(full_name="X"), ACTOR
                )

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())


def test_update_employee_route_maps_duplicate_to_409(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            ventas_area_id = await _seed_catalog_entry("areas", "Ventas")
            await employees.create_employee_route(await _make_create("Empleado Uno"), ACTOR)
            second = await employees.create_employee_route(
                await _make_create("Empleado Dos", area_name="Soporte"), ACTOR
            )

            with pytest.raises(HTTPException) as exc_info:
                await employees.update_employee_route(
                    second.id,
                    EmployeeUpdate(full_name="Empleado Uno", area_id=ventas_area_id),
                    ACTOR,
                )

            assert exc_info.value.status_code == 409

    asyncio.run(scenario())


def test_update_employee_route_maps_invalid_position_to_422(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            created = await employees.create_employee_route(await _make_create(), ACTOR)
            invalid_changes = EmployeeUpdate.model_construct(position="gerente")

            with pytest.raises(HTTPException) as exc_info:
                await employees.update_employee_route(created.id, invalid_changes, ACTOR)

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())


# --- T038: POST /employees mapea InvalidAreaError/InvalidStatusError a 422 ---


def test_create_employee_route_returns_422_for_invalid_area(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status_id = await _seed_catalog_entry("estados", "Presencial")
            data = EmployeeCreate(
                full_name="Carla Gómez", position="lider", area_id=str(ObjectId()), status_id=status_id
            )

            with pytest.raises(HTTPException) as exc_info:
                await employees.create_employee_route(data, ACTOR)

            assert exc_info.value.status_code == 422
            assert exc_info.value.detail

    asyncio.run(scenario())


def test_create_employee_route_returns_422_for_disabled_area(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            area_id = await _seed_catalog_entry("areas", "Ventas")
            status_id = await _seed_catalog_entry("estados", "Presencial")
            await _disable_catalog_entry("areas", area_id)
            data = EmployeeCreate(
                full_name="Carla Gómez", position="lider", area_id=area_id, status_id=status_id
            )

            with pytest.raises(HTTPException) as exc_info:
                await employees.create_employee_route(data, ACTOR)

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())


def test_create_employee_route_returns_422_for_invalid_status(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            area_id = await _seed_catalog_entry("areas", "Ventas")
            data = EmployeeCreate(
                full_name="Carla Gómez", position="lider", area_id=area_id, status_id=str(ObjectId())
            )

            with pytest.raises(HTTPException) as exc_info:
                await employees.create_employee_route(data, ACTOR)

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())


# --- T038: PATCH /employees/{id} mapea InvalidAreaError a 422 ---


def test_update_employee_route_returns_422_for_invalid_area(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employees.create_employee_route(await _make_create(), ACTOR)

            with pytest.raises(HTTPException) as exc_info:
                await employees.update_employee_route(
                    created.id, EmployeeUpdate(area_id=str(ObjectId())), ACTOR
                )

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())


def test_update_employee_route_returns_422_for_disabled_area(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employees.create_employee_route(await _make_create(), ACTOR)
            other_area_id = await _seed_catalog_entry("areas", "Soporte")
            await _disable_catalog_entry("areas", other_area_id)

            with pytest.raises(HTTPException) as exc_info:
                await employees.update_employee_route(
                    created.id, EmployeeUpdate(area_id=other_area_id), ACTOR
                )

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())


# --- T039: PATCH /employees/{id}/status ---


def test_update_employee_status_route_updates_status_fields(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            created = await employees.create_employee_route(await _make_create(), ACTOR)
            new_status_id = await _seed_catalog_entry("estados", "Vacaciones")

            updated = await employees.update_employee_status_route(
                created.id, EmployeeStatusUpdate(status_id=new_status_id), ACTOR
            )

            assert updated.status_name == "Vacaciones"
            assert updated.status_updated_at is not None
            assert updated.status_updated_by == "admin-id"
            assert updated.full_name == created.full_name
            assert updated.area == created.area

    asyncio.run(scenario())


def test_update_employee_status_route_raises_404_for_unknown_employee(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status_id = await _seed_catalog_entry("estados", "Vacaciones")

            with pytest.raises(HTTPException) as exc_info:
                await employees.update_employee_status_route(
                    str(ObjectId()), EmployeeStatusUpdate(status_id=status_id), ACTOR
                )

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())


def test_update_employee_status_route_raises_404_for_malformed_id(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status_id = await _seed_catalog_entry("estados", "Vacaciones")

            with pytest.raises(HTTPException) as exc_info:
                await employees.update_employee_status_route(
                    "no-es-un-object-id", EmployeeStatusUpdate(status_id=status_id), ACTOR
                )

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())


def test_update_employee_status_route_returns_422_for_invalid_status(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employees.create_employee_route(await _make_create(), ACTOR)

            with pytest.raises(HTTPException) as exc_info:
                await employees.update_employee_status_route(
                    created.id, EmployeeStatusUpdate(status_id=str(ObjectId())), ACTOR
                )

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())


def test_update_employee_status_route_returns_422_for_disabled_status(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employees.create_employee_route(await _make_create(), ACTOR)
            other_status_id = await _seed_catalog_entry("estados", "Vacaciones")
            await _disable_catalog_entry("estados", other_status_id)

            with pytest.raises(HTTPException) as exc_info:
                await employees.update_employee_status_route(
                    created.id, EmployeeStatusUpdate(status_id=other_status_id), ACTOR
                )

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())
