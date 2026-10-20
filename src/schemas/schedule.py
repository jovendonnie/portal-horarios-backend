from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday"]
WEEKDAYS: tuple[Weekday, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
)
Modality = Literal["presencial", "virtual"]
ScheduleSource = Literal["default", "day_override", "range_override"]

TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class TimeRangeIn(BaseModel):
    start: str = Field(pattern=TIME_PATTERN)
    end: str = Field(pattern=TIME_PATTERN)

    @model_validator(mode="after")
    def check_start_before_end(self) -> "TimeRangeIn":
        if self.start >= self.end:
            raise ValueError("La hora de inicio debe ser anterior a la hora de fin")
        return self


class TimeRangeOut(BaseModel):
    start: str
    end: str


class DefaultScheduleDayIn(BaseModel):
    weekday: Weekday
    works: bool
    modality: Modality | None = None
    time_ranges: list[TimeRangeIn] = []

    @model_validator(mode="after")
    def normalize_or_validate(self) -> "DefaultScheduleDayIn":
        if not self.works:
            self.modality = None
            self.time_ranges = []
            return self

        if self.modality is None or not self.time_ranges:
            raise ValueError(
                "Debe indicar modalidad y al menos una franja horaria para un "
                "día en que el empleado trabaja"
            )
        return self


class DefaultScheduleDayOut(BaseModel):
    weekday: Weekday
    works: bool
    modality: Modality | None
    time_ranges: list[TimeRangeOut]


class DefaultScheduleUpdate(BaseModel):
    days: list[DefaultScheduleDayIn]

    @model_validator(mode="after")
    def check_exactly_five_weekdays(self) -> "DefaultScheduleUpdate":
        weekdays = [day.weekday for day in self.days]
        if len(weekdays) != 5 or set(weekdays) != set(WEEKDAYS):
            raise ValueError(
                "Debe incluir exactamente los 5 días de la semana, lunes a "
                "viernes, sin repetir"
            )
        return self


class EmployeeDefaultScheduleOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    employee_id: str
    days: list[DefaultScheduleDayOut]
    updated_at: datetime | None = None
    updated_by: str | None = None

    @field_validator("employee_id", "updated_by", mode="before")
    @classmethod
    def stringify_object_id(cls, value: object) -> object:
        return str(value) if value is not None else value


class ScheduleDayEntryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: date
    status_id: str
    status_name: str
    modality: Modality | None
    time_ranges: list[TimeRangeOut]
    source: ScheduleSource
    observation: str | None = None
    updated_at: datetime | None = None

    @field_validator("status_id", mode="before")
    @classmethod
    def stringify_object_id(cls, value: object) -> object:
        return str(value) if value is not None else value


class EmployeeWeekScheduleOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    employee_id: str
    full_name: str
    position: str
    area_name: str
    is_active: bool
    days: list[ScheduleDayEntryOut]

    @field_validator("employee_id", mode="before")
    @classmethod
    def stringify_object_id(cls, value: object) -> object:
        return str(value) if value is not None else value


class WeekScheduleResponse(BaseModel):
    week_start: date
    week_end: date
    server_today: date
    week_offset: int
    can_navigate_prev: bool
    can_navigate_next: bool
    employees: list[EmployeeWeekScheduleOut]


class DayStatusChangeInput(BaseModel):
    employee_id: str
    date: date
    status_id: str
    observation: str | None = None
    expected_updated_at: datetime | None


class DayStatusRevertInput(BaseModel):
    employee_id: str
    date: date
    expected_updated_at: datetime | None


class DateRangeStatusChangeInput(BaseModel):
    employee_id: str
    start_date: date
    end_date: date
    status_id: str
