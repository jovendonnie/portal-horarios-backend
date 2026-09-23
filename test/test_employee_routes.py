import asyncio
import inspect

import pytest
from bson import ObjectId
from fastapi import HTTPException

from conftest import mongo_test_session
from src.api.deps import require_admin
from src.api.routes import employees
from src.models.employee import ensure_indexes
from src.schemas.employee import EmployeeCreate, EmployeeUpdate

ACTOR = {"_id": "admin-id", "role": "admin"}


def _actor_dependency(route_function):
    signature = inspect.signature(route_function)
    param_name = "actor" if "actor" in signature.parameters else "_actor"
    return signature.parameters[param_name].default.dependency


def test_employee_routes_require_admin() -> None:
    assert _actor_dependency(employees.create_employee_route) is require_admin
    assert _actor_dependency(employees.list_employees_route) is require_admin
    assert _actor_dependency(employees.get_employee_route) is require_admin
    assert _actor_dependency(employees.update_employee_route) is require_admin


def test_router_registers_employee_routes() -> None:
    from src.main import app

    schema = app.openapi()

    assert set(schema["paths"]["/employees"].keys()) >= {"post", "get"}
    assert set(schema["paths"]["/employees/{employee_id}"].keys()) >= {"get", "patch"}


def test_create_employee_route_returns_created_employee(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            data = EmployeeCreate(full_name="Carla Gómez", position="lider", area="Ventas")

            created = await employees.create_employee_route(data, ACTOR)

            assert created.full_name == "Carla Gómez"
            assert created.is_active is True

    asyncio.run(scenario())


def test_create_employee_route_maps_invalid_position_to_422(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            invalid_data = EmployeeCreate.model_construct(full_name="X", position="gerente", area="Y")

            with pytest.raises(HTTPException) as exc_info:
                await employees.create_employee_route(invalid_data, ACTOR)

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())


def test_create_employee_route_maps_duplicate_to_409(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            data = EmployeeCreate(full_name="Carla Gómez", position="lider", area="Ventas")
            await employees.create_employee_route(data, ACTOR)

            with pytest.raises(HTTPException) as exc_info:
                await employees.create_employee_route(data, ACTOR)

            assert exc_info.value.status_code == 409

    asyncio.run(scenario())


def test_list_employees_route_returns_all(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await employees.create_employee_route(
                EmployeeCreate(full_name="Empleado Uno", position="lider", area="Ventas"), ACTOR
            )

            result = await employees.list_employees_route(ACTOR)

            assert len(result) == 1
            assert result[0].full_name == "Empleado Uno"

    asyncio.run(scenario())


def test_get_employee_route_returns_detail(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employees.create_employee_route(
                EmployeeCreate(full_name="Carla Gómez", position="lider", area="Ventas"), ACTOR
            )

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
            created = await employees.create_employee_route(
                EmployeeCreate(full_name="Carla Gómez", position="lider", area="Ventas"), ACTOR
            )

            updated = await employees.update_employee_route(
                created.id, EmployeeUpdate(area="Marketing"), ACTOR
            )

            assert updated.area == "Marketing"
            assert updated.full_name == "Carla Gómez"

    asyncio.run(scenario())


def test_update_employee_route_maps_not_found_to_404(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(HTTPException) as exc_info:
                await employees.update_employee_route(
                    str(ObjectId()), EmployeeUpdate(area="Marketing"), ACTOR
                )

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())


def test_update_employee_route_maps_duplicate_to_409(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await employees.create_employee_route(
                EmployeeCreate(full_name="Empleado Uno", position="lider", area="Ventas"), ACTOR
            )
            second = await employees.create_employee_route(
                EmployeeCreate(full_name="Empleado Dos", position="lider", area="Soporte"), ACTOR
            )

            with pytest.raises(HTTPException) as exc_info:
                await employees.update_employee_route(
                    second.id, EmployeeUpdate(full_name="Empleado Uno", area="Ventas"), ACTOR
                )

            assert exc_info.value.status_code == 409

    asyncio.run(scenario())


def test_update_employee_route_maps_invalid_position_to_422(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employees.create_employee_route(
                EmployeeCreate(full_name="Carla Gómez", position="lider", area="Ventas"), ACTOR
            )
            invalid_changes = EmployeeUpdate.model_construct(position="gerente")

            with pytest.raises(HTTPException) as exc_info:
                await employees.update_employee_route(created.id, invalid_changes, ACTOR)

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())
