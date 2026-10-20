import pytest
from bson import ObjectId
from pydantic import ValidationError

from src.schemas.schedule import (
    DateRangeStatusChangeInput,
    DayStatusChangeInput,
    DayStatusRevertInput,
    DefaultScheduleDayIn,
    DefaultScheduleUpdate,
    EmployeeDefaultScheduleOut,
    EmployeeWeekScheduleOut,
    ScheduleDayEntryOut,
    TimeRangeIn,
    WeekScheduleResponse,
)


def _working_day(weekday: str = "monday") -> DefaultScheduleDayIn:
    return DefaultScheduleDayIn(
        weekday=weekday,
        works=True,
        modality="presencial",
        time_ranges=[{"start": "08:00", "end": "17:00"}],
    )


def _non_working_day(weekday: str) -> DefaultScheduleDayIn:
    return DefaultScheduleDayIn(weekday=weekday, works=False)


def _make_five_days() -> list[DefaultScheduleDayIn]:
    return [
        _working_day("monday"),
        _working_day("tuesday"),
        _working_day("wednesday"),
        _working_day("thursday"),
        _non_working_day("friday"),
    ]


def test_time_range_in_rejects_start_after_end() -> None:
    with pytest.raises(ValidationError):
        TimeRangeIn(start="17:00", end="08:00")


def test_time_range_in_rejects_equal_start_and_end() -> None:
    with pytest.raises(ValidationError):
        TimeRangeIn(start="08:00", end="08:00")


def test_default_schedule_day_in_normalizes_non_working_day() -> None:
    day = DefaultScheduleDayIn(
        weekday="friday",
        works=False,
        modality="presencial",
        time_ranges=[{"start": "08:00", "end": "17:00"}],
    )

    assert day.modality is None
    assert day.time_ranges == []


def test_default_schedule_day_in_requires_modality_and_ranges_when_working() -> None:
    with pytest.raises(ValidationError):
        DefaultScheduleDayIn(weekday="monday", works=True)


def test_default_schedule_day_in_rejects_working_day_without_time_ranges() -> None:
    with pytest.raises(ValidationError):
        DefaultScheduleDayIn(weekday="monday", works=True, modality="virtual")


def test_default_schedule_update_accepts_exactly_five_days() -> None:
    update = DefaultScheduleUpdate(days=_make_five_days())

    assert len(update.days) == 5


def test_default_schedule_update_rejects_wrong_length() -> None:
    with pytest.raises(ValidationError):
        DefaultScheduleUpdate(days=_make_five_days()[:4])


def test_default_schedule_update_rejects_duplicate_weekday() -> None:
    days = _make_five_days()[:4] + [_working_day("monday")]

    with pytest.raises(ValidationError):
        DefaultScheduleUpdate(days=days)


def test_employee_default_schedule_out_stringifies_object_ids() -> None:
    employee_id = ObjectId()
    actor_id = ObjectId()

    out = EmployeeDefaultScheduleOut(
        employee_id=employee_id,
        days=[
            {
                "weekday": "monday",
                "works": True,
                "modality": "presencial",
                "time_ranges": [{"start": "08:00", "end": "17:00"}],
            }
        ],
        updated_at=None,
        updated_by=actor_id,
    )

    assert out.employee_id == str(employee_id)
    assert out.updated_by == str(actor_id)


def test_schedule_day_entry_out_rejects_invalid_source() -> None:
    with pytest.raises(ValidationError):
        ScheduleDayEntryOut(
            date="2026-10-15",
            status_id=ObjectId(),
            status_name="Permiso",
            modality=None,
            time_ranges=[],
            source="algo_invalido",
        )


@pytest.mark.parametrize("source", ["default", "day_override", "range_override"])
def test_schedule_day_entry_out_accepts_valid_sources(source: str) -> None:
    entry = ScheduleDayEntryOut(
        date="2026-10-15",
        status_id=ObjectId(),
        status_name="Presencial",
        modality="presencial",
        time_ranges=[{"start": "08:00", "end": "17:00"}],
        source=source,
    )

    assert entry.source == source


def test_employee_week_schedule_out_builds_with_day_entries() -> None:
    week_schedule = EmployeeWeekScheduleOut(
        employee_id=ObjectId(),
        full_name="Carla Gómez",
        position="lider",
        area_name="Ventas",
        is_active=True,
        days=[
            ScheduleDayEntryOut(
                date="2026-10-15",
                status_id=ObjectId(),
                status_name="Presencial",
                modality="presencial",
                time_ranges=[{"start": "08:00", "end": "17:00"}],
                source="default",
            )
        ],
    )

    assert len(week_schedule.days) == 1


def test_week_schedule_response_model_dump_includes_expected_keys() -> None:
    response = WeekScheduleResponse(
        week_start="2026-10-12",
        week_end="2026-10-16",
        server_today="2026-10-14",
        week_offset=0,
        can_navigate_prev=True,
        can_navigate_next=True,
        employees=[],
    )

    dumped_keys = set(response.model_dump().keys())

    assert {
        "week_start",
        "week_end",
        "server_today",
        "week_offset",
        "can_navigate_prev",
        "can_navigate_next",
        "employees",
    }.issubset(dumped_keys)


def test_day_status_change_input_requires_expected_updated_at() -> None:
    with pytest.raises(ValidationError):
        DayStatusChangeInput(
            employee_id=str(ObjectId()),
            date="2026-10-15",
            status_id=str(ObjectId()),
        )


def test_day_status_change_input_builds_with_all_fields() -> None:
    change = DayStatusChangeInput(
        employee_id=str(ObjectId()),
        date="2026-10-15",
        status_id=str(ObjectId()),
        observation="Cita médica",
        expected_updated_at="2026-10-14T09:00:00Z",
    )

    assert change.observation == "Cita médica"


def test_day_status_revert_input_requires_expected_updated_at() -> None:
    with pytest.raises(ValidationError):
        DayStatusRevertInput(employee_id=str(ObjectId()), date="2026-10-15")


def test_day_status_change_input_accepts_none_as_expected_updated_at() -> None:
    change = DayStatusChangeInput(
        employee_id=str(ObjectId()),
        date="2026-10-15",
        status_id=str(ObjectId()),
        expected_updated_at=None,
    )

    assert change.expected_updated_at is None


def test_day_status_revert_input_accepts_none_as_expected_updated_at() -> None:
    revert = DayStatusRevertInput(
        employee_id=str(ObjectId()), date="2026-10-15", expected_updated_at=None
    )

    assert revert.expected_updated_at is None


def test_date_range_status_change_input_does_not_validate_date_order() -> None:
    range_input = DateRangeStatusChangeInput(
        employee_id=str(ObjectId()),
        start_date="2026-10-20",
        end_date="2026-10-15",
        status_id=str(ObjectId()),
    )

    assert range_input.start_date > range_input.end_date
