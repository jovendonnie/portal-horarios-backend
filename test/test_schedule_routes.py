import asyncio
import inspect
from datetime import date, datetime, timezone
from typing import Any

import pytest
from bson import ObjectId
from fastapi import HTTPException

from conftest import mongo_test_session
from src.api.deps import require_read, require_schedule_write
from src.api.routes import schedules
from src.core.database import get_database
from src.models.schedule import upsert_day_exception, upsert_default_schedule
from src.schemas.schedule import (
    BulkAssignmentInput,
    DateRangeStatusChangeInput,
    DayStatusChangeInput,
    DayStatusRevertInput,
    DefaultScheduleDayIn,
    DefaultScheduleUpdate,
    TimeRangeIn,
)
from src.services import schedule_service

ACTOR = {"_id": ObjectId(), "role": "admin", "full_name": "Admin Actor"}


def _reset_absence_cache(monkeypatch) -> None:
    monkeypatch.setattr(schedule_service, "_absence_status_ids_cache", None)


async def _insert_status(name: str, enabled: bool = True) -> dict[str, Any]:
    db = get_database()
    document = {
        "name": name,
        "is_enabled": enabled,
        "is_predefined": True,
        "created_at": datetime.now(timezone.utc),
        "created_by": None,
        "updated_at": None,
        "updated_by": None,
    }
    result = await db["estados"].insert_one(document)
    document["_id"] = result.inserted_id
    return document


async def _insert_employee(status_id: Any, full_name: str = "Carla Gómez") -> dict[str, Any]:
    db = get_database()
    document = {
        "nombre_completo": full_name,
        "cargo": "lider",
        "area": "Ventas",
        "area_id": ObjectId(),
        "estado_id": status_id,
        "activo": True,
        "creado_en": datetime.now(timezone.utc),
        "creado_por": None,
        "estado_actualizado_en": None,
        "estado_actualizado_por": None,
        "actualizado_en": None,
        "actualizado_por": None,
    }
    result = await db["Usuarios"].insert_one(document)
    document["_id"] = result.inserted_id
    return document


def _default_days(works: bool = True) -> list[dict[str, Any]]:
    ranges = [{"start": "08:00", "end": "17:00"}] if works else []
    modality = "presencial" if works else None
    return [
        {"weekday": weekday, "works": works, "modality": modality, "time_ranges": ranges}
        for weekday in schedule_service.WEEKDAYS
    ]


def _actor_dependency(route_function):
    signature = inspect.signature(route_function)
    param_name = "actor" if "actor" in signature.parameters else "_actor"
    return signature.parameters[param_name].default.dependency


# ---------------------------------------------------------------------------
# T030/T031 — dependencia de autorización por ruta (RF-7)
# ---------------------------------------------------------------------------


def test_read_routes_require_read() -> None:
    assert _actor_dependency(schedules.get_week_schedule_route) is require_read
    assert _actor_dependency(schedules.get_default_schedule_route) is require_read


def test_mutation_routes_require_schedule_write() -> None:
    assert _actor_dependency(schedules.update_default_schedule_route) is require_schedule_write
    assert _actor_dependency(schedules.apply_day_status_route) is require_schedule_write
    assert _actor_dependency(schedules.revert_day_status_route) is require_schedule_write
    assert _actor_dependency(schedules.apply_range_status_route) is require_schedule_write
    assert _actor_dependency(schedules.apply_bulk_assignment_route) is require_schedule_write


# ---------------------------------------------------------------------------
# T032 — registro del router
# ---------------------------------------------------------------------------


def test_router_registers_schedule_routes() -> None:
    from src.main import app

    schema = app.openapi()

    assert set(schema["paths"]["/schedules/week"].keys()) >= {"get"}
    assert set(schema["paths"]["/schedules/default/{employee_id}"].keys()) >= {"get", "patch"}
    assert set(schema["paths"]["/schedules/day-status"].keys()) >= {"patch"}
    assert set(schema["paths"]["/schedules/day-status/revert"].keys()) >= {"patch"}
    assert set(schema["paths"]["/schedules/range-status"].keys()) >= {"post"}
    assert set(schema["paths"]["/schedules/bulk"].keys()) >= {"post"}


# ---------------------------------------------------------------------------
# T030 — GET /schedules/week, GET /schedules/default/{employee_id}
# ---------------------------------------------------------------------------


def test_get_week_schedule_route_returns_week_schedule_response(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            monkeypatch.setattr(schedule_service, "today_bogota", lambda: date(2026, 10, 14))
            status = await _insert_status("Presencial")
            await _insert_employee(status["_id"])

            result = await schedules.get_week_schedule_route(offset=0, _actor=ACTOR)

            assert result.week_start == date(2026, 10, 12)
            assert len(result.employees) == 1

    asyncio.run(scenario())


def test_get_default_schedule_route_returns_empty_template(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status = await _insert_status("Presencial")
            employee = await _insert_employee(status["_id"])

            result = await schedules.get_default_schedule_route(
                str(employee["_id"]), _actor=ACTOR
            )

            assert len(result.days) == 5
            assert all(not day.works for day in result.days)

    asyncio.run(scenario())


def test_get_default_schedule_route_raises_404_for_unknown_employee(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(HTTPException) as exc_info:
                await schedules.get_default_schedule_route(str(ObjectId()), _actor=ACTOR)

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())


def test_get_default_schedule_route_raises_404_for_malformed_id(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(HTTPException) as exc_info:
                await schedules.get_default_schedule_route("no-es-un-id", _actor=ACTOR)

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# T031 — rutas de mutación
# ---------------------------------------------------------------------------


def test_update_default_schedule_route_success(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status = await _insert_status("Presencial")
            employee = await _insert_employee(status["_id"])

            days = [
                DefaultScheduleDayIn(
                    weekday=weekday,
                    works=True,
                    modality="presencial",
                    time_ranges=[{"start": "08:00", "end": "17:00"}],
                )
                for weekday in schedule_service.WEEKDAYS
            ]
            data = DefaultScheduleUpdate(days=days)

            result = await schedules.update_default_schedule_route(
                str(employee["_id"]), data, actor=ACTOR
            )

            assert all(day.works for day in result.days)

    asyncio.run(scenario())


def test_update_default_schedule_route_raises_404_for_unknown_employee(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            days = [
                DefaultScheduleDayIn(weekday=weekday, works=False)
                for weekday in schedule_service.WEEKDAYS
            ]
            data = DefaultScheduleUpdate(days=days)

            with pytest.raises(HTTPException) as exc_info:
                await schedules.update_default_schedule_route(str(ObjectId()), data, actor=ACTOR)

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())


def test_apply_day_status_route_success(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Permiso")
            employee = await _insert_employee(status["_id"])
            await upsert_default_schedule(employee["_id"], _default_days(works=True), ACTOR["_id"])

            data = DayStatusChangeInput(
                employee_id=str(employee["_id"]),
                date="2026-10-13",
                status_id=str(status["_id"]),
                observation="Cita médica",
                expected_updated_at=None,
            )

            result = await schedules.apply_day_status_route(data, actor=ACTOR)

            assert result.source == "day_override"
            assert result.status_name == "Permiso"

    asyncio.run(scenario())


def test_apply_day_status_route_maps_day_conflict_to_409(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Vacaciones")
            employee = await _insert_employee(status["_id"])
            db = get_database()
            await db["schedule_exceptions"].insert_one(
                {
                    "employee_id": employee["_id"],
                    "date": "2026-10-13",
                    "status_id": status["_id"],
                    "observation": None,
                    "source": "range_override",
                    "range_id": ObjectId(),
                    "updated_at": datetime.now(timezone.utc),
                    "updated_by": ACTOR["_id"],
                }
            )

            data = DayStatusChangeInput(
                employee_id=str(employee["_id"]),
                date="2026-10-13",
                status_id=str(status["_id"]),
                expected_updated_at=None,
            )

            with pytest.raises(HTTPException) as exc_info:
                await schedules.apply_day_status_route(data, actor=ACTOR)

            assert exc_info.value.status_code == 409

    asyncio.run(scenario())


def test_apply_day_status_route_maps_invalid_status_to_422(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status = await _insert_status("Permiso")
            employee = await _insert_employee(status["_id"])

            data = DayStatusChangeInput(
                employee_id=str(employee["_id"]),
                date="2026-10-13",
                status_id=str(ObjectId()),
                expected_updated_at=None,
            )

            with pytest.raises(HTTPException) as exc_info:
                await schedules.apply_day_status_route(data, actor=ACTOR)

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())


def test_apply_day_status_route_raises_404_for_malformed_employee_id(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            data = DayStatusChangeInput(
                employee_id="no-es-un-id",
                date="2026-10-13",
                status_id=str(ObjectId()),
                expected_updated_at=None,
            )

            with pytest.raises(HTTPException) as exc_info:
                await schedules.apply_day_status_route(data, actor=ACTOR)

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())


def test_revert_day_status_route_success_noop(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Presencial")
            employee = await _insert_employee(status["_id"])
            await upsert_default_schedule(employee["_id"], _default_days(works=True), ACTOR["_id"])

            data = DayStatusRevertInput(
                employee_id=str(employee["_id"]), date="2026-10-13", expected_updated_at=None
            )

            result = await schedules.revert_day_status_route(data, actor=ACTOR)

            assert result.source == "default"

    asyncio.run(scenario())


def test_revert_day_status_route_maps_stale_update_to_409(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Permiso")
            employee = await _insert_employee(status["_id"])
            await upsert_day_exception(employee["_id"], "2026-10-13", status["_id"], None, ACTOR["_id"])

            data = DayStatusRevertInput(
                employee_id=str(employee["_id"]), date="2026-10-13", expected_updated_at=None
            )

            with pytest.raises(HTTPException) as exc_info:
                await schedules.revert_day_status_route(data, actor=ACTOR)

            assert exc_info.value.status_code == 409

    asyncio.run(scenario())


def test_apply_range_status_route_success(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Vacaciones")
            employee = await _insert_employee(status["_id"])
            await upsert_default_schedule(employee["_id"], _default_days(works=True), ACTOR["_id"])

            data = DateRangeStatusChangeInput(
                employee_id=str(employee["_id"]),
                start_date="2026-10-12",
                end_date="2026-10-14",
                status_id=str(status["_id"]),
            )

            result = await schedules.apply_range_status_route(data, actor=ACTOR)

            assert len(result) == 3
            assert all(entry.source == "range_override" for entry in result)

    asyncio.run(scenario())


def test_apply_range_status_route_maps_conflict_to_409(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Vacaciones")
            employee = await _insert_employee(status["_id"])
            await upsert_day_exception(employee["_id"], "2026-10-13", status["_id"], None, ACTOR["_id"])

            data = DateRangeStatusChangeInput(
                employee_id=str(employee["_id"]),
                start_date="2026-10-12",
                end_date="2026-10-14",
                status_id=str(status["_id"]),
            )

            with pytest.raises(HTTPException) as exc_info:
                await schedules.apply_range_status_route(data, actor=ACTOR)

            assert exc_info.value.status_code == 409

    asyncio.run(scenario())


def test_apply_range_status_route_maps_invalid_range_to_422(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status = await _insert_status("Vacaciones")
            employee = await _insert_employee(status["_id"])

            data = DateRangeStatusChangeInput(
                employee_id=str(employee["_id"]),
                start_date="2026-10-17",
                end_date="2026-10-18",
                status_id=str(status["_id"]),
            )  # sábado y domingo únicamente

            with pytest.raises(HTTPException) as exc_info:
                await schedules.apply_range_status_route(data, actor=ACTOR)

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Spec 008 — POST /schedules/bulk
# ---------------------------------------------------------------------------


def test_apply_bulk_assignment_route_success(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Presencial")
            employee = await _insert_employee(status["_id"])

            data = BulkAssignmentInput(
                employee_ids=[str(employee["_id"])],
                start_date="2026-10-12",
                end_date="2026-10-13",
                weekdays=["monday", "tuesday"],
                kind="shift",
                modality="presencial",
                time_ranges=[TimeRangeIn(start="08:00", end="12:00")],
            )

            result = await schedules.apply_bulk_assignment_route(data, actor=ACTOR)

            assert len(result.created) == 2
            assert result.skipped == []
            assert all(entry.source == "shift_override" for entry in result.created)

    asyncio.run(scenario())


def test_apply_bulk_assignment_route_maps_invalid_range_to_422(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status = await _insert_status("Presencial")
            employee = await _insert_employee(status["_id"])

            data = BulkAssignmentInput(
                employee_ids=[str(employee["_id"])],
                start_date="2026-10-17",
                end_date="2026-10-18",
                weekdays=["monday"],
                kind="shift",
                modality="presencial",
                time_ranges=[TimeRangeIn(start="08:00", end="12:00")],
            )  # sábado y domingo, no coincide con ningún día hábil

            with pytest.raises(HTTPException) as exc_info:
                await schedules.apply_bulk_assignment_route(data, actor=ACTOR)

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())


def test_apply_bulk_assignment_route_skips_conflicting_day(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Presencial")
            employee = await _insert_employee(status["_id"])
            await upsert_day_exception(employee["_id"], "2026-10-13", status["_id"], None, ACTOR["_id"])

            data = BulkAssignmentInput(
                employee_ids=[str(employee["_id"])],
                start_date="2026-10-12",
                end_date="2026-10-13",
                weekdays=["monday", "tuesday"],
                kind="shift",
                modality="presencial",
                time_ranges=[TimeRangeIn(start="08:00", end="12:00")],
            )

            result = await schedules.apply_bulk_assignment_route(data, actor=ACTOR)

            assert len(result.created) == 1
            assert len(result.skipped) == 1

    asyncio.run(scenario())
