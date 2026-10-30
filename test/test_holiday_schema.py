import pytest
from pydantic import ValidationError

from src.schemas.holiday import (
    HolidayBlocksShiftsUpdate,
    HolidayCreate,
    HolidayDeleteOut,
    HolidayImportOut,
    HolidayOut,
)


def test_create_accepts_iso_date_and_name() -> None:
    holiday = HolidayCreate(date="2026-01-12", name="Día de los Reyes Magos")

    assert holiday.date == "2026-01-12"
    assert holiday.name == "Día de los Reyes Magos"


@pytest.mark.parametrize(
    "date",
    ["2026-1-12", "12-01-2026", "2026/01/12", "", "2026-01-12T00:00:00"],
)
def test_create_rejects_dates_outside_yyyy_mm_dd(date) -> None:
    with pytest.raises(ValidationError):
        HolidayCreate(date=date, name="Día de la empresa")


@pytest.mark.parametrize("name", ["", "x" * 101])
def test_create_rejects_invalid_name(name) -> None:
    with pytest.raises(ValidationError):
        HolidayCreate(date="2026-01-12", name=name)


def test_out_exposes_only_the_fields_the_portal_consumes() -> None:
    assert set(HolidayOut.model_fields) == {"date", "name", "type", "blocks_shifts"}


def test_out_accepts_a_mongo_document_with_extra_fields() -> None:
    holiday_out = HolidayOut(
        date="2026-12-25", name="Navidad", type="nacional", blocks_shifts=True
    )

    assert holiday_out.type == "nacional"
    assert holiday_out.blocks_shifts is True


def test_out_rejects_an_unknown_type() -> None:
    with pytest.raises(ValidationError):
        HolidayOut(date="2026-12-25", name="Navidad", type="regional", blocks_shifts=True)


def test_blocks_shifts_update_requires_a_boolean() -> None:
    assert HolidayBlocksShiftsUpdate(blocks_shifts=False).blocks_shifts is False

    with pytest.raises(ValidationError):
        HolidayBlocksShiftsUpdate(blocks_shifts="quizás")


def test_delete_out_returns_the_deleted_date() -> None:
    assert HolidayDeleteOut(date="2026-01-12").date == "2026-01-12"


def test_import_out_carries_imported_days_and_skipped_dates() -> None:
    result = HolidayImportOut(
        imported=[{"date": "2026-01-01", "name": "Año Nuevo", "type": "nacional", "blocks_shifts": True}],
        skipped_dates=["2026-12-25"],
    )

    assert [entry.date for entry in result.imported] == ["2026-01-01"]
    assert result.skipped_dates == ["2026-12-25"]
