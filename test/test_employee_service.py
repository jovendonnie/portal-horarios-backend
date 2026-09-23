import asyncio

import pytest
from bson import ObjectId

from conftest import mongo_test_session
from src.models.employee import ensure_indexes
from src.schemas.employee import EmployeeCreate, EmployeeUpdate
from src.services import employee_service

ACTOR = {"_id": "admin-id"}


def _make_create(full_name: str = "Carla Gómez", position: str = "lider", area: str = "Ventas") -> EmployeeCreate:
    return EmployeeCreate(full_name=full_name, position=position, area=area)


def test_create_employee_sets_is_active_and_created_by(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()

            employee = await employee_service.create_employee(ACTOR, _make_create())

            assert employee.is_active is True
            assert employee.created_by == "admin-id"
            assert employee.full_name == "Carla Gómez"
            assert employee.position == "lider"
            assert employee.area == "Ventas"

    asyncio.run(scenario())


def test_create_employee_rejects_invalid_position(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            invalid_data = EmployeeCreate.model_construct(full_name="X", position="gerente", area="Y")

            with pytest.raises(employee_service.InvalidPositionError):
                await employee_service.create_employee(ACTOR, invalid_data)

    asyncio.run(scenario())


def test_create_employee_rejects_exact_duplicate(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await employee_service.create_employee(ACTOR, _make_create())

            with pytest.raises(employee_service.DuplicateEmployeeError):
                await employee_service.create_employee(ACTOR, _make_create())

    asyncio.run(scenario())


def test_create_employee_rejects_duplicate_with_different_case_and_spaces(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await employee_service.create_employee(ACTOR, _make_create("Carla Gómez", "lider", "Ventas"))

            with pytest.raises(employee_service.DuplicateEmployeeError):
                await employee_service.create_employee(
                    ACTOR, _make_create("  CARLA GÓMEZ  ", "lider", "Ventas")
                )

    asyncio.run(scenario())


def test_get_employee_returns_full_detail(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employee_service.create_employee(ACTOR, _make_create())

            fetched = await employee_service.get_employee(ObjectId(created.id))

            assert fetched.full_name == "Carla Gómez"
            assert fetched.position == "lider"
            assert fetched.area == "Ventas"

    asyncio.run(scenario())


def test_get_employee_raises_not_found(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(employee_service.EmployeeNotFoundError):
                await employee_service.get_employee(ObjectId())

    asyncio.run(scenario())


def test_list_employees_returns_all_translated(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await employee_service.create_employee(ACTOR, _make_create("Empleado Uno"))
            await employee_service.create_employee(
                ACTOR, _make_create("Empleado Dos", area="Soporte")
            )

            employees = await employee_service.list_employees()

            names = {employee.full_name for employee in employees}
            assert names == {"Empleado Uno", "Empleado Dos"}
            assert all(employee.is_active for employee in employees)

    asyncio.run(scenario())


def test_update_employee_partial_success_leaves_rest_unchanged(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employee_service.create_employee(ACTOR, _make_create())

            updated = await employee_service.update_employee(
                ACTOR, ObjectId(created.id), EmployeeUpdate(area="Marketing")
            )

            assert updated.area == "Marketing"
            assert updated.full_name == "Carla Gómez"
            assert updated.position == "lider"
            assert updated.updated_by == "admin-id"

    asyncio.run(scenario())


def test_update_employee_rejects_invalid_position(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employee_service.create_employee(ACTOR, _make_create())
            invalid_changes = EmployeeUpdate.model_construct(position="gerente")

            with pytest.raises(employee_service.InvalidPositionError):
                await employee_service.update_employee(ACTOR, ObjectId(created.id), invalid_changes)

    asyncio.run(scenario())


def test_update_employee_rejects_duplicate_with_another_employee(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await employee_service.create_employee(ACTOR, _make_create("Empleado Uno"))
            second = await employee_service.create_employee(
                ACTOR, _make_create("Empleado Dos", area="Soporte")
            )

            with pytest.raises(employee_service.DuplicateEmployeeError):
                await employee_service.update_employee(
                    ACTOR,
                    ObjectId(second.id),
                    EmployeeUpdate(full_name="Empleado Uno", area="Ventas"),
                )

    asyncio.run(scenario())


def test_update_employee_raises_not_found(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(employee_service.EmployeeNotFoundError):
                await employee_service.update_employee(ACTOR, ObjectId(), EmployeeUpdate(area="X"))

    asyncio.run(scenario())


def test_update_employee_without_identity_change_does_not_raise_false_duplicate(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            created = await employee_service.create_employee(ACTOR, _make_create())

            updated = await employee_service.update_employee(
                ACTOR, ObjectId(created.id), EmployeeUpdate(area="Ventas")
            )

            assert updated.area == "Ventas"
            assert updated.full_name == "Carla Gómez"
            assert updated.position == "lider"

    asyncio.run(scenario())
