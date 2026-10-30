import asyncio
from datetime import date as date_type

import pytest
from bson import ObjectId

from conftest import mongo_test_session
from src.models import holiday
from src.models.history import list_entries as list_history_entries
from src.services import holiday_service

ACTOR = {"_id": ObjectId(), "role": "gestion_humana", "full_name": "Admin Actor"}


# --- Festivos nacionales: función pura, sin Mongo ---

@pytest.mark.parametrize(
    "year,expected_easter",
    [(2024, "2024-03-31"), (2025, "2025-04-20"), (2026, "2026-04-05")],
)
def test_easter_sunday_matches_the_known_dates(year, expected_easter) -> None:
    assert holiday_service._easter_sunday(year).isoformat() == expected_easter


def test_national_holidays_of_2026_are_the_eighteen_official_dates() -> None:
    dates = [date for date, _ in holiday_service.national_holidays(2026)]

    assert dates == [
        "2026-01-01",  # Año Nuevo
        "2026-01-12",  # Reyes Magos, trasladado al lunes
        "2026-03-23",  # San José, trasladado al lunes
        "2026-04-02",  # Jueves Santo
        "2026-04-03",  # Viernes Santo
        "2026-05-01",  # Día del Trabajo
        "2026-05-18",  # Ascensión
        "2026-06-08",  # Corpus Christi
        "2026-06-15",  # Sagrado Corazón
        "2026-06-29",  # San Pedro y San Pablo
        "2026-07-20",  # Independencia
        "2026-08-07",  # Batalla de Boyacá
        "2026-08-17",  # Asunción, trasladada al lunes
        "2026-10-12",  # Día de la Raza
        "2026-11-02",  # Todos los Santos, trasladado al lunes
        "2026-11-16",  # Independencia de Cartagena, trasladada al lunes
        "2026-12-08",  # Inmaculada Concepción
        "2026-12-25",  # Navidad
    ]


def test_emiliani_holidays_always_fall_on_monday() -> None:
    movable_names = {name for _, _, name in holiday_service._EMILIANI_HOLIDAYS}

    for year in (2024, 2025, 2026, 2027):
        for date, name in holiday_service.national_holidays(year):
            if name in movable_names:
                assert date_type.fromisoformat(date).weekday() == 0, (year, date, name)


def test_holy_thursday_and_friday_keep_their_weekday() -> None:
    for year in (2024, 2025, 2026):
        by_name = {name: date for date, name in holiday_service.national_holidays(year)}

        assert date_type.fromisoformat(by_name["Jueves Santo"]).weekday() == 3
        assert date_type.fromisoformat(by_name["Viernes Santo"]).weekday() == 4


def test_two_celebrations_on_the_same_date_become_one_day_with_both_names() -> None:
    """En 2025 el Sagrado Corazón y San Pedro y San Pablo caen ambos el 30 de junio:
    la fecha es la clave del calendario, así que es un solo día (RF-4)."""
    holidays_2025 = holiday_service.national_holidays(2025)
    by_date = dict(holidays_2025)

    assert len(holidays_2025) == 17
    assert len({date for date, _ in holidays_2025}) == 17
    assert by_date["2025-06-30"] == "Sagrado Corazón de Jesús · San Pedro y San Pablo"


# --- Reglas con persistencia ---

def test_create_registers_a_company_day_that_blocks_shifts(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()

            created = await holiday_service.create_holiday(
                "2026-06-15", "Aniversario", ACTOR
            )

            assert created["type"] == "empresa"
            assert created["blocks_shifts"] is True

            entries = await list_history_entries({"entity_type": "holiday"})
            assert [entry["action"] for entry in entries] == ["create"]

    asyncio.run(scenario())


def test_create_rejects_a_date_already_registered(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()
            await holiday_service.create_holiday("2026-06-15", "Aniversario", ACTOR)

            with pytest.raises(holiday_service.DuplicateHolidayError):
                await holiday_service.create_holiday("2026-06-15", "Otro día", ACTOR)

    asyncio.run(scenario())


def test_set_blocks_shifts_toggles_the_day_and_audits_the_diff(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()
            await holiday_service.create_holiday("2026-06-15", "Aniversario", ACTOR)

            updated = await holiday_service.set_blocks_shifts("2026-06-15", False, ACTOR)
            assert updated["blocks_shifts"] is False

            entries = await list_history_entries({"entity_type": "holiday", "action": "update"})
            assert entries[0]["changes"] == [
                {"field": "blocks_shifts", "old_value": True, "new_value": False}
            ]

            # Volver a pedir el mismo valor es un no-op: no agrega auditoría.
            await holiday_service.set_blocks_shifts("2026-06-15", False, ACTOR)
            entries_after = await list_history_entries(
                {"entity_type": "holiday", "action": "update"}
            )
            assert len(entries_after) == 1

    asyncio.run(scenario())


def test_delete_removes_a_company_day_but_rejects_a_national_one(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()
            await holiday_service.create_holiday("2026-06-15", "Aniversario", ACTOR)
            await holiday_service.import_national_holidays(2026, ACTOR)

            deleted = await holiday_service.delete_holiday("2026-06-15", ACTOR)
            assert deleted == "2026-06-15"
            assert await holiday.find_holiday_by_date("2026-06-15") is None

            with pytest.raises(holiday_service.NationalHolidayError):
                await holiday_service.delete_holiday("2026-12-25", ACTOR)
            assert await holiday.find_holiday_by_date("2026-12-25") is not None

    asyncio.run(scenario())


def test_operations_on_an_unregistered_date_raise_not_found(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()

            with pytest.raises(holiday_service.HolidayNotFoundError):
                await holiday_service.set_blocks_shifts("2026-06-15", True, ACTOR)

            with pytest.raises(holiday_service.HolidayNotFoundError):
                await holiday_service.delete_holiday("2026-06-15", ACTOR)

    asyncio.run(scenario())


def test_import_creates_the_year_and_skips_what_already_exists(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()

            first = await holiday_service.import_national_holidays(2026, ACTOR)
            assert len(first["imported"]) == 18
            assert first["skipped_dates"] == []
            assert all(entry["type"] == "nacional" for entry in first["imported"])
            assert all(entry["blocks_shifts"] is True for entry in first["imported"])

            # Reimportar no duplica nada y reporta las 18 fechas omitidas.
            second = await holiday_service.import_national_holidays(2026, ACTOR)
            assert second["imported"] == []
            assert len(second["skipped_dates"]) == 18
            assert len(await holiday.list_holidays_by_year(2026)) == 18

    asyncio.run(scenario())


def test_import_preserves_a_day_already_configured_by_hand(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()
            # Navidad registrada a mano como día de la empresa en que sí se trabaja.
            await holiday_service.create_holiday("2026-12-25", "Jornada especial", ACTOR)
            await holiday_service.set_blocks_shifts("2026-12-25", False, ACTOR)

            result = await holiday_service.import_national_holidays(2026, ACTOR)

            assert "2026-12-25" in result["skipped_dates"]
            preserved = await holiday.find_holiday_by_date("2026-12-25")
            assert preserved["name"] == "Jornada especial"
            assert preserved["type"] == "empresa"
            assert preserved["blocks_shifts"] is False

    asyncio.run(scenario())


def test_list_returns_the_days_of_the_requested_year(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await holiday.ensure_indexes()
            await holiday_service.create_holiday("2026-06-15", "Aniversario", ACTOR)
            await holiday_service.create_holiday("2025-06-15", "Aniversario anterior", ACTOR)

            listed = await holiday_service.list_holidays(2026)

            assert [entry["date"] for entry in listed] == ["2026-06-15"]
            assert await holiday_service.list_holidays(2030) == []

    asyncio.run(scenario())
