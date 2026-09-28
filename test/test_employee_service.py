import asyncio
from datetime import datetime, timezone

import pytest
from bson import ObjectId

from conftest import mongo_test_session
from src.models import catalog as catalog_model
from src.models.employee import ensure_indexes, find_employee_by_identity
from src.models.employee import find_employee_by_id as find_employee_document
from src.models.history import list_entries
from src.schemas.employee import EmployeeCreate, EmployeeUpdate
from src.services import employee_service, history_service

ACTOR = {"_id": "admin-id", "full_name": "Admin Actor"}


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


async def _rename_catalog_entry(collection_name: str, entry_id: str, new_name: str) -> None:
    await catalog_model.update_entry_name(
        collection_name, ObjectId(entry_id), new_name, ACTOR["_id"], datetime.now(timezone.utc)
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


# --- create_employee: caso feliz y auditoría de Estado (T033) ---


def test_create_employee_sets_is_active_and_created_by(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()

            employee = await employee_service.create_employee(ACTOR, await _make_create())

            assert employee.is_active is True
            assert employee.created_by == "admin-id"
            assert employee.full_name == "Carla Gómez"
            assert employee.position == "lider"
            assert employee.area == "Ventas"

    asyncio.run(scenario())


def test_create_employee_populates_status_audit_fields(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()

            employee = await employee_service.create_employee(
                ACTOR, await _make_create(status_name="Presencial")
            )

            assert employee.area_name == "Ventas"
            assert employee.status_name == "Presencial"
            assert employee.status_updated_at is not None
            assert employee.status_updated_by == "admin-id"

    asyncio.run(scenario())


def test_create_employee_rejects_invalid_position(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            invalid_data = EmployeeCreate.model_construct(
                full_name="X", position="gerente", area_id="x", status_id="y"
            )

            with pytest.raises(employee_service.InvalidPositionError):
                await employee_service.create_employee(ACTOR, invalid_data)

    asyncio.run(scenario())


# --- create_employee: validación de catálogo (T032, T033) ---


def test_create_employee_rejects_nonexistent_area(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status_id = await _seed_catalog_entry("estados", "Presencial")
            data = EmployeeCreate(
                full_name="Carla Gómez", position="lider", area_id=str(ObjectId()), status_id=status_id
            )

            with pytest.raises(employee_service.InvalidAreaError):
                await employee_service.create_employee(ACTOR, data)

    asyncio.run(scenario())


def test_create_employee_rejects_disabled_area(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            area_id = await _seed_catalog_entry("areas", "Ventas")
            status_id = await _seed_catalog_entry("estados", "Presencial")
            await _disable_catalog_entry("areas", area_id)

            data = EmployeeCreate(
                full_name="Carla Gómez", position="lider", area_id=area_id, status_id=status_id
            )

            with pytest.raises(employee_service.InvalidAreaError):
                await employee_service.create_employee(ACTOR, data)

    asyncio.run(scenario())


def test_create_employee_rejects_nonexistent_status(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            area_id = await _seed_catalog_entry("areas", "Ventas")
            data = EmployeeCreate(
                full_name="Carla Gómez", position="lider", area_id=area_id, status_id=str(ObjectId())
            )

            with pytest.raises(employee_service.InvalidStatusError):
                await employee_service.create_employee(ACTOR, data)

    asyncio.run(scenario())


def test_create_employee_rejects_disabled_status(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            area_id = await _seed_catalog_entry("areas", "Ventas")
            status_id = await _seed_catalog_entry("estados", "Presencial")
            await _disable_catalog_entry("estados", status_id)

            data = EmployeeCreate(
                full_name="Carla Gómez", position="lider", area_id=area_id, status_id=status_id
            )

            with pytest.raises(employee_service.InvalidStatusError):
                await employee_service.create_employee(ACTOR, data)

    asyncio.run(scenario())


def test_create_employee_rejects_malformed_area_id(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status_id = await _seed_catalog_entry("estados", "Presencial")
            data = EmployeeCreate(
                full_name="Carla Gómez",
                position="lider",
                area_id="no-es-un-object-id",
                status_id=status_id,
            )

            with pytest.raises(employee_service.InvalidAreaError):
                await employee_service.create_employee(ACTOR, data)

    asyncio.run(scenario())


# --- create_employee: duplicados (comportamiento heredado de spec 002) ---


def test_create_employee_rejects_exact_duplicate(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await employee_service.create_employee(ACTOR, await _make_create())

            with pytest.raises(employee_service.DuplicateEmployeeError):
                await employee_service.create_employee(ACTOR, await _make_create())

    asyncio.run(scenario())


def test_create_employee_rejects_duplicate_with_different_case_and_spaces(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await employee_service.create_employee(
                ACTOR, await _make_create("Carla Gómez", "lider", "Ventas")
            )

            with pytest.raises(employee_service.DuplicateEmployeeError):
                await employee_service.create_employee(
                    ACTOR, await _make_create("  CARLA GÓMEZ  ", "lider", "Ventas")
                )

    asyncio.run(scenario())


# --- get_employee / list_employees ---


def test_get_employee_returns_full_detail(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employee_service.create_employee(ACTOR, await _make_create())

            fetched = await employee_service.get_employee(ObjectId(created.id))

            assert fetched.full_name == "Carla Gómez"
            assert fetched.position == "lider"
            assert fetched.area == "Ventas"
            assert fetched.area_name == "Ventas"
            assert fetched.status_name == "Presencial"

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
            await employee_service.create_employee(ACTOR, await _make_create("Empleado Uno"))
            await employee_service.create_employee(
                ACTOR, await _make_create("Empleado Dos", area_name="Soporte")
            )

            employees = await employee_service.list_employees()

            names = {employee.full_name for employee in employees}
            assert names == {"Empleado Uno", "Empleado Dos"}
            assert all(employee.is_active for employee in employees)
            areas_by_name = {employee.full_name: employee.area_name for employee in employees}
            assert areas_by_name == {"Empleado Uno": "Ventas", "Empleado Dos": "Soporte"}

    asyncio.run(scenario())


def test_list_employees_resolves_names_with_bounded_catalog_queries(use_test_db, monkeypatch) -> None:
    """T035: como máximo una consulta a areas y una a estados, sin importar N empleados."""

    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            for index in range(10):
                data = await _make_create(
                    f"Empleado {index}", area_name="Ventas", status_name="Presencial"
                )
                await employee_service.create_employee(ACTOR, data)

            call_count = {"areas": 0, "estados": 0}
            original_list_entries = catalog_model.list_entries

            async def counting_list_entries(collection_name, enabled=None):
                call_count[collection_name] += 1
                return await original_list_entries(collection_name, enabled)

            monkeypatch.setattr(catalog_model, "list_entries", counting_list_entries)

            employees = await employee_service.list_employees()

            assert len(employees) == 10
            assert call_count["areas"] <= 1
            assert call_count["estados"] <= 1
            assert all(employee.area_name == "Ventas" for employee in employees)
            assert all(employee.status_name == "Presencial" for employee in employees)

    asyncio.run(scenario())


# --- update_employee: identidad (comportamiento heredado de spec 002) ---


def test_update_employee_partial_success_leaves_rest_unchanged(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employee_service.create_employee(ACTOR, await _make_create())

            updated = await employee_service.update_employee(
                ACTOR, ObjectId(created.id), EmployeeUpdate(full_name="Carla Gómez Actualizada")
            )

            assert updated.full_name == "Carla Gómez Actualizada"
            assert updated.area == "Ventas"
            assert updated.position == "lider"
            assert updated.updated_by == "admin-id"

    asyncio.run(scenario())


def test_update_employee_rejects_invalid_position(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employee_service.create_employee(ACTOR, await _make_create())
            invalid_changes = EmployeeUpdate.model_construct(position="gerente")

            with pytest.raises(employee_service.InvalidPositionError):
                await employee_service.update_employee(ACTOR, ObjectId(created.id), invalid_changes)

    asyncio.run(scenario())


def test_update_employee_raises_not_found(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(employee_service.EmployeeNotFoundError):
                await employee_service.update_employee(
                    ACTOR, ObjectId(), EmployeeUpdate(full_name="X")
                )

    asyncio.run(scenario())


# --- update_employee: validación de area_id (T034) ---


def test_update_employee_only_name_does_not_validate_or_touch_area(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            area_id = await _seed_catalog_entry("areas", "Ventas")
            status_id = await _seed_catalog_entry("estados", "Presencial")
            created = await employee_service.create_employee(
                ACTOR,
                EmployeeCreate(
                    full_name="Carla Gómez", position="lider", area_id=area_id, status_id=status_id
                ),
            )

            # Si update_employee validara area_id aunque no venga en el PATCH,
            # esto fallaría con InvalidAreaError.
            await _disable_catalog_entry("areas", area_id)

            updated = await employee_service.update_employee(
                ACTOR, ObjectId(created.id), EmployeeUpdate(full_name="Carla Gómez Actualizada")
            )

            assert updated.full_name == "Carla Gómez Actualizada"
            assert updated.area == "Ventas"
            assert updated.area_name == "Ventas"
            assert updated.status_updated_at == created.status_updated_at
            assert updated.status_updated_by == created.status_updated_by

    asyncio.run(scenario())


def test_update_employee_rejects_nonexistent_area(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employee_service.create_employee(ACTOR, await _make_create())

            with pytest.raises(employee_service.InvalidAreaError):
                await employee_service.update_employee(
                    ACTOR, ObjectId(created.id), EmployeeUpdate(area_id=str(ObjectId()))
                )

    asyncio.run(scenario())


def test_update_employee_rejects_disabled_area(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employee_service.create_employee(ACTOR, await _make_create())
            other_area_id = await _seed_catalog_entry("areas", "Soporte")
            await _disable_catalog_entry("areas", other_area_id)

            with pytest.raises(employee_service.InvalidAreaError):
                await employee_service.update_employee(
                    ACTOR, ObjectId(created.id), EmployeeUpdate(area_id=other_area_id)
                )

    asyncio.run(scenario())


def test_update_employee_with_valid_area_changes_area_and_legacy_field(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            created = await employee_service.create_employee(ACTOR, await _make_create())
            new_area_id = await _seed_catalog_entry("areas", "Marketing")

            updated = await employee_service.update_employee(
                ACTOR, ObjectId(created.id), EmployeeUpdate(area_id=new_area_id)
            )

            assert updated.area == "Marketing"
            assert updated.area_name == "Marketing"
            assert updated.full_name == "Carla Gómez"
            assert updated.position == "lider"

    asyncio.run(scenario())


def test_update_employee_rejects_duplicate_with_another_employee(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            ventas_area_id = await _seed_catalog_entry("areas", "Ventas")
            await employee_service.create_employee(ACTOR, await _make_create("Empleado Uno"))
            second = await employee_service.create_employee(
                ACTOR, await _make_create("Empleado Dos", area_name="Soporte")
            )

            with pytest.raises(employee_service.DuplicateEmployeeError):
                await employee_service.update_employee(
                    ACTOR,
                    ObjectId(second.id),
                    EmployeeUpdate(full_name="Empleado Uno", area_id=ventas_area_id),
                )

    asyncio.run(scenario())


def test_update_employee_without_identity_change_does_not_raise_false_duplicate(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            area_id = await _seed_catalog_entry("areas", "Ventas")
            status_id = await _seed_catalog_entry("estados", "Presencial")
            created = await employee_service.create_employee(
                ACTOR,
                EmployeeCreate(
                    full_name="Carla Gómez", position="lider", area_id=area_id, status_id=status_id
                ),
            )

            updated = await employee_service.update_employee(
                ACTOR, ObjectId(created.id), EmployeeUpdate(area_id=area_id)
            )

            assert updated.area == "Ventas"
            assert updated.full_name == "Carla Gómez"
            assert updated.position == "lider"

    asyncio.run(scenario())


# --- update_employee_status (T036) ---


def test_update_employee_status_updates_dedicated_audit_fields(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            created = await employee_service.create_employee(ACTOR, await _make_create())
            new_status_id = await _seed_catalog_entry("estados", "Vacaciones")
            ahora = datetime(2026, 9, 25, 12, 0, 0)

            updated = await employee_service.update_employee_status(
                ObjectId(created.id), new_status_id, ACTOR, ahora
            )

            assert updated.status_name == "Vacaciones"
            assert updated.status_updated_at == ahora
            assert updated.status_updated_by == "admin-id"
            # No toca identidad ni auditoría genérica del empleado.
            assert updated.full_name == created.full_name
            assert updated.position == created.position
            assert updated.area == created.area
            assert updated.updated_at == created.updated_at
            assert updated.updated_by == created.updated_by
            assert updated.is_active == created.is_active

    asyncio.run(scenario())


def test_update_employee_status_rejects_nonexistent_status(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employee_service.create_employee(ACTOR, await _make_create())

            with pytest.raises(employee_service.InvalidStatusError):
                await employee_service.update_employee_status(
                    ObjectId(created.id), str(ObjectId()), ACTOR, datetime.now(timezone.utc)
                )

    asyncio.run(scenario())


def test_update_employee_status_rejects_disabled_status(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            created = await employee_service.create_employee(ACTOR, await _make_create())
            other_status_id = await _seed_catalog_entry("estados", "Vacaciones")
            await _disable_catalog_entry("estados", other_status_id)

            with pytest.raises(employee_service.InvalidStatusError):
                await employee_service.update_employee_status(
                    ObjectId(created.id), other_status_id, ACTOR, datetime.now(timezone.utc)
                )

    asyncio.run(scenario())


def test_update_employee_status_raises_not_found(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status_id = await _seed_catalog_entry("estados", "Vacaciones")

            with pytest.raises(employee_service.EmployeeNotFoundError):
                await employee_service.update_employee_status(
                    ObjectId(), status_id, ACTOR, datetime.now(timezone.utc)
                )

    asyncio.run(scenario())


# --- RNF-4: renombrar/deshabilitar catálogo no reescribe el documento del empleado (T037) ---


def test_renaming_or_disabling_catalog_entry_does_not_rewrite_employee_document(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            area_id = await _seed_catalog_entry("areas", "Ventas")
            status_id = await _seed_catalog_entry("estados", "Presencial")
            created = await employee_service.create_employee(
                ACTOR,
                EmployeeCreate(
                    full_name="Carla Gómez", position="lider", area_id=area_id, status_id=status_id
                ),
            )

            document_before = await find_employee_document(ObjectId(created.id))
            assert document_before is not None

            await _rename_catalog_entry("areas", area_id, "Ventas Renombrada")
            await _rename_catalog_entry("estados", status_id, "Presencial Renombrado")
            await _disable_catalog_entry("estados", status_id)

            document_after = await find_employee_document(ObjectId(created.id))
            assert document_after == document_before  # ningún campo del empleado cambió

            refreshed = await employee_service.get_employee(ObjectId(created.id))
            assert refreshed.area_name == "Ventas Renombrada"
            assert refreshed.status_name == "Presencial Renombrado"
            assert refreshed.area == "Ventas"  # campo legado, congelado al crear

            # Sigue apareciendo en list_employees() con su Estado deshabilitado resuelto.
            listed = await employee_service.list_employees()
            assert any(
                employee.full_name == "Carla Gómez" and employee.status_name == "Presencial Renombrado"
                for employee in listed
            )

    asyncio.run(scenario())


def test_disabling_area_of_assigned_employee_does_not_change_document(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            created = await employee_service.create_employee(ACTOR, await _make_create())

            document_before = await find_employee_document(ObjectId(created.id))
            await _disable_catalog_entry("areas", await _seed_catalog_entry("areas", "Ventas"))
            document_after = await find_employee_document(ObjectId(created.id))

            assert document_after == document_before
            refreshed = await employee_service.get_employee(ObjectId(created.id))
            assert refreshed.area_name == "Ventas"  # sigue resolviendo aunque esté deshabilitada

    asyncio.run(scenario())


# --- Auditoría del historial en create_employee / update_employee / update_employee_status (T021-T024) ---


def test_create_employee_generates_create_and_status_change_entries(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()

            created = await employee_service.create_employee(
                ACTOR, await _make_create(status_name="Presencial")
            )

            entries = await list_entries(
                {"entity_type": "employee", "entity_id": ObjectId(created.id)}
            )

            assert len(entries) == 2
            actions = {entry["action"] for entry in entries}
            assert actions == {"create", "status_change"}

            create_entry = next(entry for entry in entries if entry["action"] == "create")
            changes_by_field = {change["field"]: change for change in create_entry["changes"]}
            assert changes_by_field["full_name"] == {
                "field": "full_name",
                "old_value": None,
                "new_value": "Carla Gómez",
            }
            assert changes_by_field["position"] == {
                "field": "position",
                "old_value": None,
                "new_value": "lider",
            }
            assert changes_by_field["area"] == {
                "field": "area",
                "old_value": None,
                "new_value": "Ventas",
            }
            assert create_entry["actor_id"] == ACTOR["_id"]
            assert create_entry["actor_name"] == ACTOR["full_name"]

            status_entry = next(entry for entry in entries if entry["action"] == "status_change")
            assert status_entry["changes"] == [
                {"field": "status", "old_value": None, "new_value": "Presencial"}
            ]

    asyncio.run(scenario())


def test_update_employee_multiple_fields_generates_single_history_entry(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            created = await employee_service.create_employee(ACTOR, await _make_create())
            new_area_id = await _seed_catalog_entry("areas", "Marketing")

            await employee_service.update_employee(
                ACTOR,
                ObjectId(created.id),
                EmployeeUpdate(full_name="Carla Gómez Editada", area_id=new_area_id),
            )

            entries = await list_entries(
                {
                    "entity_type": "employee",
                    "entity_id": ObjectId(created.id),
                    "action": "update",
                }
            )

            assert len(entries) == 1
            changes_by_field = {change["field"]: change for change in entries[0]["changes"]}
            assert changes_by_field["full_name"]["old_value"] == "Carla Gómez"
            assert changes_by_field["full_name"]["new_value"] == "Carla Gómez Editada"
            assert changes_by_field["area"]["old_value"] == "Ventas"
            assert changes_by_field["area"]["new_value"] == "Marketing"
            assert "position" not in changes_by_field

    asyncio.run(scenario())


def test_update_employee_no_op_does_not_generate_history_entry_or_touch_audit_fields(
    use_test_db,
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            created = await employee_service.create_employee(ACTOR, await _make_create())

            updated = await employee_service.update_employee(
                ACTOR, ObjectId(created.id), EmployeeUpdate(full_name="Carla Gómez")
            )

            entries = await list_entries(
                {
                    "entity_type": "employee",
                    "entity_id": ObjectId(created.id),
                    "action": "update",
                }
            )

            assert entries == []
            assert updated.updated_at is None
            assert updated.updated_by is None

    asyncio.run(scenario())


def test_update_employee_status_generates_entry_with_old_and_new_status_names(
    use_test_db,
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            created = await employee_service.create_employee(
                ACTOR, await _make_create(status_name="Presencial")
            )
            new_status_id = await _seed_catalog_entry("estados", "Vacaciones")

            await employee_service.update_employee_status(
                ObjectId(created.id), new_status_id, ACTOR, datetime.now(timezone.utc)
            )

            entries = await list_entries(
                {
                    "entity_type": "employee",
                    "entity_id": ObjectId(created.id),
                    "action": "status_change",
                }
            )

            assert len(entries) == 2
            latest = entries[0]
            change = latest["changes"][0]
            assert change["field"] == "status"
            assert change["old_value"] == "Presencial"
            assert change["new_value"] == "Vacaciones"

    asyncio.run(scenario())


def test_create_employee_atomicity_reverts_employee_insert_when_history_insert_fails(
    use_test_db, monkeypatch
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()

            async def failing_insert_entry(document, session=None):
                raise RuntimeError("boom")

            monkeypatch.setattr(history_service, "insert_entry", failing_insert_entry)

            with pytest.raises(RuntimeError):
                await employee_service.create_employee(ACTOR, await _make_create())

            assert await find_employee_by_identity("Carla Gómez", "lider", "Ventas") is None

    asyncio.run(scenario())
