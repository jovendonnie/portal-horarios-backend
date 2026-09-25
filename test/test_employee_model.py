import asyncio
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from conftest import mongo_test_session
from src.models.employee import (
    count_employees_by_area,
    count_employees_by_status,
    ensure_indexes,
    find_employee_by_id,
    find_employee_by_identity,
    insert_employee,
    list_employees,
    update_employee_fields,
    update_employee_status_fields,
)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


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


def test_insert_employee_persists_area_id_and_estado_id_without_touching_legacy_area(
    use_test_db,
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            area_id = ObjectId()
            estado_id = ObjectId()
            actor_id = ObjectId()
            ahora = _ahora()

            inserted_id = await insert_employee(
                {
                    **_make_employee("Elena Ruiz", area="Ventas"),
                    "area_id": area_id,
                    "estado_id": estado_id,
                    "estado_actualizado_en": ahora,
                    "estado_actualizado_por": actor_id,
                }
            )
            found = await find_employee_by_id(inserted_id)

            assert found["area_id"] == area_id
            assert found["estado_id"] == estado_id
            assert found["estado_actualizado_en"] is not None
            assert found["estado_actualizado_por"] == actor_id
            assert found["area"] == "Ventas"

    asyncio.run(scenario())


def test_update_employee_fields_can_set_area_id_without_touching_legacy_area(
    use_test_db,
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            inserted_id = await insert_employee(_make_employee("Bruno Salas", area="Ventas"))
            nuevo_area_id = ObjectId()

            modified = await update_employee_fields(inserted_id, {"area_id": nuevo_area_id})
            found = await find_employee_by_id(inserted_id)

            assert modified is True
            assert found["area_id"] == nuevo_area_id
            assert found["area"] == "Ventas"

    asyncio.run(scenario())


def test_count_employees_by_area_counts_only_matching_area_id(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            area_a = ObjectId()
            area_b = ObjectId()
            await insert_employee({**_make_employee("Uno"), "area_id": area_a})
            await insert_employee({**_make_employee("Dos", area="Soporte"), "area_id": area_a})
            await insert_employee({**_make_employee("Tres", area="Marketing"), "area_id": area_b})

            assert await count_employees_by_area(area_a) == 2
            assert await count_employees_by_area(area_b) == 1
            assert await count_employees_by_area(ObjectId()) == 0

    asyncio.run(scenario())


def test_count_employees_by_status_counts_only_matching_estado_id(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            estado_a = ObjectId()
            estado_b = ObjectId()
            await insert_employee({**_make_employee("Uno"), "estado_id": estado_a})
            await insert_employee({**_make_employee("Dos", area="Soporte"), "estado_id": estado_a})
            await insert_employee(
                {**_make_employee("Tres", area="Marketing"), "estado_id": estado_b}
            )

            assert await count_employees_by_status(estado_a) == 2
            assert await count_employees_by_status(estado_b) == 1
            assert await count_employees_by_status(ObjectId()) == 0

    asyncio.run(scenario())


def test_update_employee_status_fields_updates_status_and_dedicated_audit_only(
    use_test_db,
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            viejo_estado = ObjectId()
            nuevo_estado = ObjectId()
            actor_id = ObjectId()
            ahora = _ahora()

            inserted_id = await insert_employee(
                {**_make_employee("Nora Vidal"), "estado_id": viejo_estado}
            )
            before = await find_employee_by_id(inserted_id)

            modified = await update_employee_status_fields(
                inserted_id, nuevo_estado, actor_id, ahora
            )
            found = await find_employee_by_id(inserted_id)

            assert modified is True
            assert found["estado_id"] == nuevo_estado
            assert found["estado_actualizado_en"] is not None
            assert found["estado_actualizado_por"] == actor_id
            assert found.get("actualizado_en") == before.get("actualizado_en")
            assert found.get("actualizado_por") == before.get("actualizado_por")
            assert found["activo"] == before["activo"]

    asyncio.run(scenario())


def test_update_employee_status_fields_does_not_interfere_with_generic_audit_fields(
    use_test_db,
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            inserted_id = await insert_employee(_make_employee("Iván Costa"))

            actor_edicion = ObjectId()
            await update_employee_fields(
                inserted_id,
                {
                    "nombre_completo": "Iván Costa Actualizado",
                    "actualizado_en": _ahora(),
                    "actualizado_por": actor_edicion,
                },
            )
            after_edit = await find_employee_by_id(inserted_id)

            actor_estado = ObjectId()
            nuevo_estado = ObjectId()
            await update_employee_status_fields(
                inserted_id, nuevo_estado, actor_estado, _ahora()
            )
            found = await find_employee_by_id(inserted_id)

            assert found["actualizado_en"] == after_edit["actualizado_en"]
            assert found["actualizado_por"] == actor_edicion
            assert found["estado_id"] == nuevo_estado
            assert found["estado_actualizado_en"] is not None
            assert found["estado_actualizado_por"] == actor_estado

    asyncio.run(scenario())


def test_update_employee_status_fields_returns_false_when_not_found(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            modified = await update_employee_status_fields(
                ObjectId(), ObjectId(), ObjectId(), _ahora()
            )

            assert modified is False

    asyncio.run(scenario())
