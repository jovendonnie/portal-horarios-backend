import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from conftest import mongo_test_session
from src.models import catalog as catalog_model
from src.models.employee import find_employee_by_id, insert_employee
from src.models.history import list_entries as list_history_entries
from src.models.schedule import find_exception, upsert_day_exception
from src.schemas.history import HistoryEntryOut
from src.services import catalog_cleanup_service, history_service

ACTOR = {"_id": ObjectId(), "full_name": "Admin Actor"}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# --- diagnose_duplicates (T010-T011) ----------------------------------------


def test_diagnose_duplicates_picks_entry_with_more_references_as_keeper(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            base = _ahora()
            older_id = await catalog_model.insert_entry("areas", "Recursos Humanos", ACTOR["_id"], base)
            newer_id = await catalog_model.insert_entry(
                "areas", " recursos humanos ", ACTOR["_id"], base + timedelta(seconds=1)
            )
            await insert_employee(
                {"nombre_completo": "Con Referencia", "cargo": "lider", "area": " recursos humanos ", "area_id": newer_id}
            )

            report = await catalog_cleanup_service.diagnose_duplicates("areas", "Área")

            assert len(report) == 1
            group = report[0]
            assert group["normalized_name"] == "recursos humanos"
            assert group["keep_id"] == newer_id
            counts = {entry["_id"]: entry["reference_count"] for entry in group["entries"]}
            assert counts == {older_id: 0, newer_id: 1}

    asyncio.run(scenario())


def test_diagnose_duplicates_breaks_reference_tie_by_oldest_created_at(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            base = _ahora()
            older_id = await catalog_model.insert_entry("areas", "Ventas", ACTOR["_id"], base)
            newer_id = await catalog_model.insert_entry(
                "areas", " ventas ", ACTOR["_id"], base + timedelta(seconds=1)
            )

            report = await catalog_cleanup_service.diagnose_duplicates("areas", "Área")

            assert len(report) == 1
            assert report[0]["keep_id"] == older_id
            assert newer_id in {entry["_id"] for entry in report[0]["entries"]}

    asyncio.run(scenario())


def test_diagnose_duplicates_returns_empty_list_when_no_duplicates(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await catalog_model.insert_entry("areas", "Ventas", ACTOR["_id"], _ahora())

            report = await catalog_cleanup_service.diagnose_duplicates("areas", "Área")

            assert report == []

    asyncio.run(scenario())


# --- clean_duplicates (T013-T014) -------------------------------------------


def test_clean_duplicates_reassigns_employees_and_deletes_duplicate_area(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            base = _ahora()
            kept_id = await catalog_model.insert_entry("areas", "Ventas", ACTOR["_id"], base)
            duplicate_id = await catalog_model.insert_entry(
                "areas", " ventas ", ACTOR["_id"], base + timedelta(seconds=1)
            )
            await insert_employee(
                {"nombre_completo": "Kept Uno", "cargo": "lider", "area": "Ventas", "area_id": kept_id}
            )
            await insert_employee(
                {"nombre_completo": "Kept Dos", "cargo": "lider", "area": "Ventas", "area_id": kept_id}
            )
            loser_employee_id = await insert_employee(
                {"nombre_completo": "Loser Uno", "cargo": "lider", "area": " ventas ", "area_id": duplicate_id}
            )

            result = await catalog_cleanup_service.clean_duplicates("areas", "Área", ACTOR)

            assert result == [
                {
                    "normalized_name": "ventas",
                    "kept_id": kept_id,
                    "deleted_ids": [duplicate_id],
                    "reassigned_employees": 1,
                    "reassigned_exceptions": 0,
                }
            ]
            assert await catalog_model.find_entry_by_id("areas", duplicate_id) is None
            loser_employee = await find_employee_by_id(loser_employee_id)
            assert loser_employee["area_id"] == kept_id
            assert loser_employee["area"] == "Ventas"

            history_entries = await list_history_entries({"entity_id": duplicate_id})
            assert len(history_entries) == 1
            assert history_entries[0]["action"] == "delete_duplicate"
            assert history_entries[0]["entity_type"] == "area"

    asyncio.run(scenario())


def test_clean_duplicates_reassigns_employees_and_exceptions_for_estados(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            base = _ahora()
            kept_id = await catalog_model.insert_entry("estados", "Activo", ACTOR["_id"], base)
            duplicate_id = await catalog_model.insert_entry(
                "estados", " activo ", ACTOR["_id"], base + timedelta(seconds=1)
            )
            for name in ("Kept Uno", "Kept Dos", "Kept Tres"):
                await insert_employee(
                    {"nombre_completo": name, "cargo": "lider", "area": "Ventas", "estado_id": kept_id}
                )
            loser_employee_id = await insert_employee(
                {"nombre_completo": "Loser Dos", "cargo": "lider", "area": "Ventas", "estado_id": duplicate_id}
            )
            await upsert_day_exception(loser_employee_id, "2026-11-01", duplicate_id, None, ACTOR["_id"])

            result = await catalog_cleanup_service.clean_duplicates("estados", "Estado", ACTOR)

            assert result == [
                {
                    "normalized_name": "activo",
                    "kept_id": kept_id,
                    "deleted_ids": [duplicate_id],
                    "reassigned_employees": 1,
                    "reassigned_exceptions": 1,
                }
            ]
            loser_employee = await find_employee_by_id(loser_employee_id)
            assert loser_employee["estado_id"] == kept_id
            exception = await find_exception(loser_employee_id, "2026-11-01")
            assert exception["status_id"] == kept_id

    asyncio.run(scenario())


def test_clean_duplicates_is_atomic_when_history_fails_mid_group(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            base = _ahora()
            kept_id = await catalog_model.insert_entry("areas", "Ventas", ACTOR["_id"], base)
            loser_a_id = await catalog_model.insert_entry(
                "areas", " ventas ", ACTOR["_id"], base + timedelta(seconds=1)
            )
            loser_b_id = await catalog_model.insert_entry(
                "areas", "VENTAS", ACTOR["_id"], base + timedelta(seconds=2)
            )
            await insert_employee(
                {"nombre_completo": "Kept Uno", "cargo": "lider", "area": "Ventas", "area_id": kept_id}
            )
            await insert_employee(
                {"nombre_completo": "Kept Dos", "cargo": "lider", "area": "Ventas", "area_id": kept_id}
            )
            employee_a_id = await insert_employee(
                {"nombre_completo": "Perdedor A", "cargo": "lider", "area": " ventas ", "area_id": loser_a_id}
            )
            employee_b_id = await insert_employee(
                {"nombre_completo": "Perdedor B", "cargo": "lider", "area": "VENTAS", "area_id": loser_b_id}
            )

            original_record_change = history_service.record_change
            call_count = 0

            async def _flaky_record_change(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise RuntimeError("fallo simulado")
                return await original_record_change(*args, **kwargs)

            monkeypatch.setattr(
                catalog_cleanup_service.history_service, "record_change", _flaky_record_change
            )

            with pytest.raises(RuntimeError):
                await catalog_cleanup_service.clean_duplicates("areas", "Área", ACTOR)

            assert await catalog_model.find_entry_by_id("areas", loser_a_id) is not None
            assert await catalog_model.find_entry_by_id("areas", loser_b_id) is not None
            employee_a = await find_employee_by_id(employee_a_id)
            employee_b = await find_employee_by_id(employee_b_id)
            assert employee_a["area_id"] == loser_a_id
            assert employee_b["area_id"] == loser_b_id

    asyncio.run(scenario())


def test_clean_duplicates_history_entry_is_serializable_as_history_entry_out(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            base = _ahora()
            kept_id = await catalog_model.insert_entry("areas", "Ventas", ACTOR["_id"], base)
            duplicate_id = await catalog_model.insert_entry(
                "areas", " ventas ", ACTOR["_id"], base + timedelta(seconds=1)
            )
            await insert_employee(
                {"nombre_completo": "Kept Uno", "cargo": "lider", "area": "Ventas", "area_id": kept_id}
            )

            await catalog_cleanup_service.clean_duplicates("areas", "Área", ACTOR)

            history_entries = await list_history_entries({"entity_id": duplicate_id})
            assert len(history_entries) == 1
            entry_out = HistoryEntryOut(**history_entries[0])
            merged_into_change = next(
                change for change in entry_out.changes if change.field == "merged_into_id"
            )
            assert merged_into_change.new_value == str(kept_id)

    asyncio.run(scenario())


def test_clean_duplicates_is_idempotent_on_immediate_rerun(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            base = _ahora()
            await catalog_model.insert_entry("areas", "Ventas", ACTOR["_id"], base)
            await catalog_model.insert_entry("areas", " ventas ", ACTOR["_id"], base + timedelta(seconds=1))

            first_run = await catalog_cleanup_service.clean_duplicates("areas", "Área", ACTOR)
            second_run = await catalog_cleanup_service.clean_duplicates("areas", "Área", ACTOR)

            assert len(first_run) == 1
            assert second_run == []

    asyncio.run(scenario())
