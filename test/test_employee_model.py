import asyncio

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from conftest import mongo_test_session
from src.models.employee import (
    ensure_indexes,
    find_employee_by_id,
    find_employee_by_identity,
    insert_employee,
    list_employees,
    update_employee_fields,
)


def _make_employee(full_name: str, position: str = "lider", area: str = "Ventas") -> dict:
    return {
        "nombre_completo": full_name,
        "cargo": position,
        "area": area,
    }


def test_ensure_indexes_rejects_duplicate_identity_case_and_space_insensitive(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await insert_employee(_make_employee("Carla Gómez"))

            with pytest.raises(DuplicateKeyError):
                await insert_employee(_make_employee("  CARLA GÓMEZ  "))

    asyncio.run(scenario())


def test_ensure_indexes_allows_different_identity(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await insert_employee(_make_employee("Carla Gómez", area="Ventas"))
            await insert_employee(_make_employee("Carla Gómez", area="Soporte"))

            assert len(await list_employees()) == 2

    asyncio.run(scenario())


def test_insert_employee_sets_default_activo_and_creado_en(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_employee(_make_employee("Ana Pérez"))

            found = await find_employee_by_identity("Ana Pérez", "lider", "Ventas")

            assert found is not None
            assert found["activo"] is True
            assert found["creado_en"] is not None

    asyncio.run(scenario())


def test_find_employee_by_id_returns_matching_document(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            inserted_id = await insert_employee(_make_employee("Luis Torres"))

            found = await find_employee_by_id(inserted_id)

            assert found is not None
            assert found["nombre_completo"] == "Luis Torres"

    asyncio.run(scenario())


def test_find_employee_by_id_returns_none_when_not_found(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            assert await find_employee_by_id(ObjectId()) is None

    asyncio.run(scenario())


def test_find_employee_by_identity_is_case_insensitive(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_employee(_make_employee("Marta Ruiz", "recursos_humanos", "RRHH"))

            found = await find_employee_by_identity("MARTA RUIZ", "recursos_humanos", "RRHH")

            assert found is not None
            assert found["nombre_completo"] == "Marta Ruiz"

    asyncio.run(scenario())


def test_list_employees_returns_all_inserted_documents(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_employee(_make_employee("Empleado Uno"))
            await insert_employee(_make_employee("Empleado Dos"))

            employees = await list_employees()

            names = {employee["nombre_completo"] for employee in employees}
            assert names == {"Empleado Uno", "Empleado Dos"}

    asyncio.run(scenario())


def test_update_employee_fields_changes_only_given_field(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            inserted_id = await insert_employee(_make_employee("Sofía León", "lider", "Ventas"))

            modified = await update_employee_fields(inserted_id, {"area": "Marketing"})
            found = await find_employee_by_id(inserted_id)

            assert modified is True
            assert found["area"] == "Marketing"
            assert found["nombre_completo"] == "Sofía León"
            assert found["cargo"] == "lider"

    asyncio.run(scenario())


def test_update_employee_fields_returns_false_when_not_found(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            modified = await update_employee_fields(ObjectId(), {"area": "Marketing"})

            assert modified is False

    asyncio.run(scenario())
