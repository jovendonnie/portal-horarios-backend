import asyncio
import inspect

import pytest
from bson import ObjectId
from fastapi import HTTPException, status

from conftest import mongo_test_session
from src.api.deps import require_admin, require_read
from src.api.routes import holidays
from src.models import holiday
from src.schemas.holiday import HolidayBlocksShiftsUpdate, HolidayCreate

ACTOR = {"_id": ObjectId(), "role": "gestion_humana", "full_name": "Admin Actor"}


def _actor_dependency(route_function):
    signature = inspect.signature(route_function)
    param_name = "actor" if "actor" in signature.parameters else "_actor"
    return signature.parameters[param_name].default.dependency


def test_routes_require_the_expected_roles() -> None:
    assert _actor_dependency(holidays.list_holidays_route) is require_read
    assert _actor_dependency(holidays.create_holiday_route) is require_admin
    assert _actor_dependency(holidays.import_national_holidays_route) is require_admin
    assert _actor_dependency(holidays.set_blocks_shifts_route) is require_admin
    assert _actor_dependency(holidays.delete_holiday_route) is require_admin


def test_router_registers_holiday_routes() -> None:
    from src.main import app

    schema = app.openapi()

    assert set(schema["paths"]["/holidays"].keys()) >= {"get", "post"}
    assert set(schema["paths"]["/holidays/import"].keys()) >= {"post"}
    assert set(schema["paths"]["/holidays/{date}"].keys()) >= {"patch", "delete"}


def test_delete_answers_with_a_body_instead_of_204() -> None:
    """El cliente del portal parsea el cuerpo de toda respuesta: un 204 lo haría
    fallar (plan.md sección 1)."""
    route = next(
        route
        for route in holidays.router.routes
        if route.endpoint is holidays.delete_holiday_route
    )

    assert route.status_code is None
    assert "date" in holidays.HolidayDeleteOut.model_fields


def test_create_list_toggle_and_delete_a_company_day(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()

            created = await holidays.create_holiday_route(
                HolidayCreate(date="2026-06-15", name="Aniversario"), ACTOR
            )
            assert created.type == "empresa"
            assert created.blocks_shifts is True

            listed = await holidays.list_holidays_route(2026, ACTOR)
            assert [entry.date for entry in listed] == ["2026-06-15"]
            assert await holidays.list_holidays_route(2025, ACTOR) == []

            toggled = await holidays.set_blocks_shifts_route(
                "2026-06-15", HolidayBlocksShiftsUpdate(blocks_shifts=False), ACTOR
            )
            assert toggled.blocks_shifts is False

            deleted = await holidays.delete_holiday_route("2026-06-15", ACTOR)
            assert deleted.date == "2026-06-15"

    asyncio.run(scenario())


def test_create_maps_a_taken_date_to_409(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()
            await holidays.create_holiday_route(
                HolidayCreate(date="2026-06-15", name="Aniversario"), ACTOR
            )

            with pytest.raises(HTTPException) as exc_info:
                await holidays.create_holiday_route(
                    HolidayCreate(date="2026-06-15", name="Otro"), ACTOR
                )

            assert exc_info.value.status_code == status.HTTP_409_CONFLICT

    asyncio.run(scenario())


def test_missing_date_maps_to_404(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()

            with pytest.raises(HTTPException) as exc_info:
                await holidays.set_blocks_shifts_route(
                    "2026-06-15", HolidayBlocksShiftsUpdate(blocks_shifts=True), ACTOR
                )
            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

            with pytest.raises(HTTPException) as exc_info:
                await holidays.delete_holiday_route("2026-06-15", ACTOR)
            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    asyncio.run(scenario())


def test_import_returns_the_imported_days_and_rejects_deleting_a_national_one(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()

            result = await holidays.import_national_holidays_route(2026, ACTOR)
            assert len(result.imported) == 18
            assert result.skipped_dates == []

            again = await holidays.import_national_holidays_route(2026, ACTOR)
            assert again.imported == []
            assert len(again.skipped_dates) == 18

            with pytest.raises(HTTPException) as exc_info:
                await holidays.delete_holiday_route("2026-12-25", ACTOR)
            assert exc_info.value.status_code == status.HTTP_409_CONFLICT

    asyncio.run(scenario())
