import asyncio
from datetime import date, datetime, timezone
from typing import Any

import pytest
from bson import ObjectId

from conftest import mongo_test_session
from src.core.database import get_database
from src.models import schedule as schedule_model
from src.models.schedule import find_exceptions_bulk, upsert_day_exception, upsert_default_schedule
from src.schemas.schedule import TimeRangeIn
from src.services import schedule_service
from src.services.employee_service import EmployeeNotFoundError

ACTOR = {"_id": ObjectId()}


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


async def _insert_area(name: str = "Ventas") -> dict[str, Any]:
    db = get_database()
    document = {
        "name": name,
        "is_enabled": True,
        "created_at": datetime.now(timezone.utc),
        "created_by": None,
        "updated_at": None,
        "updated_by": None,
    }
    result = await db["areas"].insert_one(document)
    document["_id"] = result.inserted_id
    return document


async def _insert_employee(
    status_id: Any,
    area_id: Any | None = None,
    active: bool = True,
    full_name: str = "Carla Gómez",
) -> dict[str, Any]:
    db = get_database()
    document = {
        "nombre_completo": full_name,
        "cargo": "lider",
        "area": "Ventas",
        "area_id": area_id or ObjectId(),
        "estado_id": status_id,
        "activo": active,
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


# ---------------------------------------------------------------------------
# T020 — resolve_day (síncrono, sin Mongo)
# ---------------------------------------------------------------------------


def test_resolve_day_default_origin_working_day() -> None:
    status_id = ObjectId()
    employee = {"estado_id": status_id}
    day = date(2026, 10, 12)  # lunes

    resolved = schedule_service.resolve_day(employee, day, _default_days(works=True), None, set())

    assert resolved["source"] == "default"
    assert resolved["modality"] == "presencial"
    assert resolved["time_ranges"] == [{"start": "08:00", "end": "17:00"}]


def test_resolve_day_default_origin_non_working_day() -> None:
    status_id = ObjectId()
    employee = {"estado_id": status_id}
    day = date(2026, 10, 12)

    resolved = schedule_service.resolve_day(employee, day, _default_days(works=False), None, set())

    assert resolved["source"] == "default"
    assert resolved["modality"] is None
    assert resolved["time_ranges"] == []


def test_resolve_day_day_override_absence() -> None:
    absence_id = ObjectId()
    employee = {"estado_id": ObjectId()}
    day = date(2026, 10, 12)
    exception = {"status_id": absence_id, "source": "day_override"}

    resolved = schedule_service.resolve_day(
        employee, day, _default_days(works=True), exception, {absence_id}
    )

    assert resolved["source"] == "day_override"
    assert resolved["status_id"] == absence_id
    assert resolved["modality"] is None
    assert resolved["time_ranges"] == []


def test_resolve_day_exception_not_absence_inherits_default_modality() -> None:
    status_id = ObjectId()
    employee = {"estado_id": ObjectId()}
    day = date(2026, 10, 12)
    exception = {"status_id": status_id, "source": "range_override"}

    resolved = schedule_service.resolve_day(
        employee, day, _default_days(works=True), exception, set()
    )

    assert resolved["source"] == "range_override"
    assert resolved["status_id"] == status_id
    assert resolved["modality"] == "presencial"
    assert resolved["time_ranges"] == [{"start": "08:00", "end": "17:00"}]


# ---------------------------------------------------------------------------
# Spec 008 RF-5 — resolve_day con modalidad/franjas propias (shift_override)
# ---------------------------------------------------------------------------


def test_resolve_day_shift_override_uses_its_own_modality_and_ranges() -> None:
    status_id = ObjectId()
    employee = {"estado_id": status_id}
    day = date(2026, 10, 12)
    exception = {
        "status_id": status_id,
        "source": "shift_override",
        "modality": "virtual",
        "time_ranges": [{"start": "09:00", "end": "13:00"}],
    }

    resolved = schedule_service.resolve_day(
        employee, day, _default_days(works=True), exception, set()
    )

    assert resolved["source"] == "shift_override"
    assert resolved["modality"] == "virtual"
    assert resolved["time_ranges"] == [{"start": "09:00", "end": "13:00"}]


def test_resolve_day_shift_override_absence_wins_over_own_modality() -> None:
    absence_id = ObjectId()
    employee = {"estado_id": ObjectId()}
    day = date(2026, 10, 12)
    exception = {
        "status_id": absence_id,
        "source": "shift_override",
        "modality": "virtual",
        "time_ranges": [{"start": "09:00", "end": "13:00"}],
    }

    resolved = schedule_service.resolve_day(
        employee, day, _default_days(works=True), exception, {absence_id}
    )

    assert resolved["modality"] is None
    assert resolved["time_ranges"] == []


def test_resolve_day_old_style_exception_without_override_keys_falls_back_to_default() -> None:
    """Las excepciones creadas antes de la spec 008 nunca tienen modality/time_ranges."""
    status_id = ObjectId()
    employee = {"estado_id": ObjectId()}
    day = date(2026, 10, 12)
    exception = {"status_id": status_id, "source": "day_override"}

    resolved = schedule_service.resolve_day(
        employee, day, _default_days(works=True), exception, set()
    )

    assert resolved["modality"] == "presencial"
    assert resolved["time_ranges"] == [{"start": "08:00", "end": "17:00"}]


# ---------------------------------------------------------------------------
# T022 — get_default_schedule / set_default_schedule
# ---------------------------------------------------------------------------


def test_get_default_schedule_returns_empty_template_when_never_configured(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status = await _insert_status("Presencial")
            employee = await _insert_employee(status["_id"])

            result = await schedule_service.get_default_schedule(employee["_id"])

            assert len(result.days) == 5
            assert all(not day.works for day in result.days)
            assert all(day.modality is None for day in result.days)

    asyncio.run(scenario())


def test_get_default_schedule_raises_not_found_for_unknown_employee(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(EmployeeNotFoundError):
                await schedule_service.get_default_schedule(ObjectId())

    asyncio.run(scenario())


def test_set_default_schedule_round_trips_with_get(use_test_db) -> None:
    from src.schemas.schedule import DefaultScheduleDayIn

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

            set_result = await schedule_service.set_default_schedule(employee["_id"], days, ACTOR)
            get_result = await schedule_service.get_default_schedule(employee["_id"])

            assert set_result.days == get_result.days
            assert all(day.works for day in get_result.days)

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# T024 — get_week_schedule
# ---------------------------------------------------------------------------


def test_get_week_schedule_offsets_give_distinct_consecutive_weeks(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            monkeypatch.setattr(schedule_service, "today_bogota", lambda: date(2026, 10, 14))

            status = await _insert_status("Presencial")
            area = await _insert_area()
            employee = await _insert_employee(status["_id"], area_id=area["_id"])
            await upsert_default_schedule(employee["_id"], _default_days(works=True), ACTOR["_id"])

            current = await schedule_service.get_week_schedule([employee], offset=0)
            previous = await schedule_service.get_week_schedule([employee], offset=-1)
            following = await schedule_service.get_week_schedule([employee], offset=1)

            assert current.week_start == date(2026, 10, 12)
            assert current.week_end == date(2026, 10, 16)
            assert current.server_today == date(2026, 10, 14)
            assert previous.week_start == date(2026, 10, 5)
            assert following.week_start == date(2026, 10, 19)
            assert current.can_navigate_prev is True
            assert current.can_navigate_next is True

    asyncio.run(scenario())


def test_get_week_schedule_absence_day_hides_modality_and_ranges(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            monkeypatch.setattr(schedule_service, "today_bogota", lambda: date(2026, 10, 14))

            status = await _insert_status("Presencial")
            absence_status = await _insert_status("Permiso")
            employee = await _insert_employee(status["_id"])
            await upsert_default_schedule(employee["_id"], _default_days(works=True), ACTOR["_id"])
            await upsert_day_exception(
                employee["_id"], "2026-10-13", absence_status["_id"], None, ACTOR["_id"]
            )

            result = await schedule_service.get_week_schedule([employee], offset=0)

            tuesday = next(d for d in result.employees[0].days if d.date == date(2026, 10, 13))
            assert tuesday.source == "day_override"
            assert tuesday.modality is None
            assert tuesday.time_ranges == []
            assert tuesday.status_name == "Permiso"

    asyncio.run(scenario())


def test_get_week_schedule_includes_inactive_employee_marked_as_such(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            monkeypatch.setattr(schedule_service, "today_bogota", lambda: date(2026, 10, 14))

            status = await _insert_status("Presencial")
            employee = await _insert_employee(status["_id"], active=False)

            result = await schedule_service.get_week_schedule([employee], offset=0)

            assert result.employees[0].is_active is False

    asyncio.run(scenario())


def test_get_week_schedule_view_fetches_all_employees_including_inactive(
    use_test_db, monkeypatch
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            monkeypatch.setattr(schedule_service, "today_bogota", lambda: date(2026, 10, 14))

            status = await _insert_status("Presencial")
            await _insert_employee(status["_id"], active=True, full_name="Carla Activa")
            await _insert_employee(status["_id"], active=False, full_name="Luis Inactivo")

            result = await schedule_service.get_week_schedule_view(offset=0)

            full_names = {employee.full_name for employee in result.employees}
            assert full_names == {"Carla Activa", "Luis Inactivo"}
            inactive = next(e for e in result.employees if e.full_name == "Luis Inactivo")
            assert inactive.is_active is False

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# T027 — apply_day_exception / revert_day_exception
# ---------------------------------------------------------------------------


def test_apply_day_exception_success_without_prior_exception(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Presencial")
            absence_status = await _insert_status("Permiso")
            employee = await _insert_employee(status["_id"])
            await upsert_default_schedule(employee["_id"], _default_days(works=True), ACTOR["_id"])

            result = await schedule_service.apply_day_exception(
                employee["_id"],
                date(2026, 10, 13),
                str(absence_status["_id"]),
                "Cita médica",
                None,
                ACTOR,
            )

            assert result.source == "day_override"
            assert result.status_name == "Permiso"
            assert result.modality is None
            assert result.observation == "Cita médica"

    asyncio.run(scenario())


def test_apply_day_exception_rejects_non_business_day(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status = await _insert_status("Permiso")
            employee = await _insert_employee(status["_id"])

            with pytest.raises(schedule_service.NonBusinessDayError):
                await schedule_service.apply_day_exception(
                    employee["_id"], date(2026, 10, 17), str(status["_id"]), None, None, ACTOR
                )  # sábado

    asyncio.run(scenario())


def test_apply_day_exception_rejects_stale_expected_updated_at(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Permiso")
            employee = await _insert_employee(status["_id"])
            await upsert_default_schedule(employee["_id"], _default_days(works=True), ACTOR["_id"])
            await upsert_day_exception(employee["_id"], "2026-10-13", status["_id"], None, ACTOR["_id"])

            with pytest.raises(schedule_service.StaleScheduleUpdateError):
                await schedule_service.apply_day_exception(
                    employee["_id"], date(2026, 10, 13), str(status["_id"]), None, None, ACTOR
                )

    asyncio.run(scenario())


def test_apply_day_exception_rejects_day_covered_by_range(use_test_db, monkeypatch) -> None:
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

            with pytest.raises(schedule_service.DayConflictError):
                await schedule_service.apply_day_exception(
                    employee["_id"], date(2026, 10, 13), str(status["_id"]), None, None, ACTOR
                )

    asyncio.run(scenario())


def test_revert_day_exception_without_prior_exception_is_noop(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Presencial")
            employee = await _insert_employee(status["_id"])
            await upsert_default_schedule(employee["_id"], _default_days(works=True), ACTOR["_id"])

            result = await schedule_service.revert_day_exception(
                employee["_id"], date(2026, 10, 13), None, ACTOR
            )

            assert result.source == "default"

    asyncio.run(scenario())


def test_revert_day_exception_on_range_override_is_noop_and_does_not_modify(
    use_test_db, monkeypatch
) -> None:
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

            result = await schedule_service.revert_day_exception(
                employee["_id"], date(2026, 10, 13), None, ACTOR
            )

            assert result.source == "range_override"
            remaining = await find_exceptions_bulk([employee["_id"]], ["2026-10-13"])
            assert len(remaining) == 1

    asyncio.run(scenario())


def test_revert_day_exception_deletes_day_override_and_falls_back_to_default(
    use_test_db, monkeypatch
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Permiso")
            employee = await _insert_employee(status["_id"])
            await upsert_default_schedule(employee["_id"], _default_days(works=True), ACTOR["_id"])
            await upsert_day_exception(employee["_id"], "2026-10-13", status["_id"], None, ACTOR["_id"])
            # Vuelve a leer de Mongo (no el dict devuelto por upsert_day_exception):
            # BSON solo guarda precisión de milisegundos, así que es el valor
            # persistido el que un cliente real vería en un GET previo.
            stored = await schedule_model.find_exception(employee["_id"], "2026-10-13")

            result = await schedule_service.revert_day_exception(
                employee["_id"], date(2026, 10, 13), stored["updated_at"], ACTOR
            )

            assert result.source == "default"
            remaining = await find_exceptions_bulk([employee["_id"]], ["2026-10-13"])
            assert remaining == []

    asyncio.run(scenario())


def test_revert_day_exception_rejects_stale_expected_updated_at(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Permiso")
            employee = await _insert_employee(status["_id"])
            await upsert_day_exception(employee["_id"], "2026-10-13", status["_id"], None, ACTOR["_id"])

            with pytest.raises(schedule_service.StaleScheduleUpdateError):
                await schedule_service.revert_day_exception(
                    employee["_id"], date(2026, 10, 13), None, ACTOR
                )

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# T029 — apply_range_status
# ---------------------------------------------------------------------------


def test_apply_range_status_applies_only_business_days(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Vacaciones")
            employee = await _insert_employee(status["_id"])
            await upsert_default_schedule(employee["_id"], _default_days(works=True), ACTOR["_id"])

            results = await schedule_service.apply_range_status(
                employee["_id"], date(2026, 10, 16), date(2026, 10, 20), str(status["_id"]), ACTOR
            )  # viernes a martes, cruza fin de semana

            result_dates = [entry.date for entry in results]
            assert result_dates == [date(2026, 10, 16), date(2026, 10, 19), date(2026, 10, 20)]
            assert all(entry.source == "range_override" for entry in results)

    asyncio.run(scenario())


def test_apply_range_status_rejects_invalid_range(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status = await _insert_status("Vacaciones")
            employee = await _insert_employee(status["_id"])

            with pytest.raises(schedule_service.InvalidRangeError):
                await schedule_service.apply_range_status(
                    employee["_id"], date(2026, 10, 20), date(2026, 10, 16), str(status["_id"]), ACTOR
                )

            with pytest.raises(schedule_service.InvalidRangeError):
                await schedule_service.apply_range_status(
                    employee["_id"], date(2026, 10, 17), date(2026, 10, 18), str(status["_id"]), ACTOR
                )  # sábado y domingo únicamente

    asyncio.run(scenario())


def test_apply_range_status_rejects_conflict_with_existing_exception(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Vacaciones")
            employee = await _insert_employee(status["_id"])
            await upsert_day_exception(employee["_id"], "2026-10-14", status["_id"], None, ACTOR["_id"])

            with pytest.raises(schedule_service.RangeConflictError) as exc_info:
                await schedule_service.apply_range_status(
                    employee["_id"], date(2026, 10, 12), date(2026, 10, 16), str(status["_id"]), ACTOR
                )

            assert exc_info.value.dates == ["2026-10-14"]
            remaining = await find_exceptions_bulk(
                [employee["_id"]],
                ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"],
            )
            assert len(remaining) == 1

    asyncio.run(scenario())


def test_apply_range_status_atomicity_reverts_everything_on_partial_failure(
    use_test_db, monkeypatch
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Vacaciones")
            employee = await _insert_employee(status["_id"])

            call_count = {"value": 0}

            async def failing_insert_range_exceptions(docs, session=None):
                call_count["value"] += 1
                raise RuntimeError("boom")

            monkeypatch.setattr(
                schedule_service.schedule_model,
                "insert_range_exceptions",
                failing_insert_range_exceptions,
            )

            with pytest.raises(RuntimeError):
                await schedule_service.apply_range_status(
                    employee["_id"], date(2026, 10, 12), date(2026, 10, 14), str(status["_id"]), ACTOR
                )

            remaining = await find_exceptions_bulk(
                [employee["_id"]], ["2026-10-12", "2026-10-13", "2026-10-14"]
            )
            assert remaining == []
            assert call_count["value"] == 1

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Spec 008 — apply_bulk_assignment
# ---------------------------------------------------------------------------


def test_apply_bulk_assignment_shift_creates_shift_override_for_each_employee_and_day(
    use_test_db, monkeypatch
) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Presencial")
            carla = await _insert_employee(status["_id"], full_name="Carla Gómez")
            diego = await _insert_employee(status["_id"], full_name="Diego Ruiz")

            created, skipped = await schedule_service.apply_bulk_assignment(
                [str(carla["_id"]), str(diego["_id"])],
                date(2026, 10, 12),
                date(2026, 10, 13),
                ["monday", "tuesday"],
                "shift",
                None,
                "virtual",
                [TimeRangeIn(start="09:00", end="13:00")],
                ACTOR,
            )

            assert skipped == []
            assert len(created) == 4  # 2 empleados x 2 días
            assert all(entry.source == "shift_override" for entry in created)
            assert all(entry.modality == "virtual" for entry in created)
            assert all(entry.time_ranges[0].start == "09:00" for entry in created)

    asyncio.run(scenario())


def test_apply_bulk_assignment_status_creates_range_override(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Vacaciones")
            employee = await _insert_employee(status["_id"])

            created, skipped = await schedule_service.apply_bulk_assignment(
                [str(employee["_id"])],
                date(2026, 10, 12),
                date(2026, 10, 14),
                ["monday", "tuesday", "wednesday"],
                "status",
                str(status["_id"]),
                None,
                [],
                ACTOR,
            )

            assert skipped == []
            assert len(created) == 3
            assert all(entry.source == "range_override" for entry in created)
            assert all(entry.modality is None for entry in created)  # Vacaciones es ausencia

    asyncio.run(scenario())


def test_apply_bulk_assignment_skips_existing_exception_and_continues(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Presencial")
            employee = await _insert_employee(status["_id"])
            await upsert_day_exception(employee["_id"], "2026-10-13", status["_id"], None, ACTOR["_id"])

            created, skipped = await schedule_service.apply_bulk_assignment(
                [str(employee["_id"])],
                date(2026, 10, 12),
                date(2026, 10, 13),
                ["monday", "tuesday"],
                "shift",
                None,
                "presencial",
                [TimeRangeIn(start="08:00", end="12:00")],
                ACTOR,
            )

            assert len(created) == 1
            assert created[0].date == date(2026, 10, 12)
            assert len(skipped) == 1
            assert skipped[0].skipped_date == date(2026, 10, 13)
            assert "ya tiene asignado" in skipped[0].reason

    asyncio.run(scenario())


def test_apply_bulk_assignment_skips_unknown_employee_and_continues(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            _reset_absence_cache(monkeypatch)
            status = await _insert_status("Presencial")
            employee = await _insert_employee(status["_id"])
            unknown_id = str(ObjectId())

            created, skipped = await schedule_service.apply_bulk_assignment(
                [str(employee["_id"]), unknown_id],
                date(2026, 10, 12),
                date(2026, 10, 12),
                ["monday"],
                "shift",
                None,
                "presencial",
                [TimeRangeIn(start="08:00", end="12:00")],
                ACTOR,
            )

            assert len(created) == 1
            assert len(skipped) == 1
            assert skipped[0].employee_id == unknown_id
            assert skipped[0].skipped_date is None
            assert skipped[0].reason == "empleado no encontrado"

    asyncio.run(scenario())


def test_apply_bulk_assignment_rejects_range_with_no_matching_weekday(use_test_db, monkeypatch) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            status = await _insert_status("Presencial")
            employee = await _insert_employee(status["_id"])

            with pytest.raises(schedule_service.InvalidRangeError):
                await schedule_service.apply_bulk_assignment(
                    [str(employee["_id"])],
                    date(2026, 10, 12),  # lunes
                    date(2026, 10, 12),
                    ["friday"],  # no coincide con ningún día del rango
                    "shift",
                    None,
                    "presencial",
                    [TimeRangeIn(start="08:00", end="12:00")],
                    ACTOR,
                )

    asyncio.run(scenario())
