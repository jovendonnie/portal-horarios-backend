from typing import Literal

from pydantic import BaseModel, Field

HolidayType = Literal["nacional", "empresa"]

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


class HolidayCreate(BaseModel):
    date: str = Field(pattern=DATE_PATTERN)
    name: str = Field(min_length=1, max_length=100)


class HolidayBlocksShiftsUpdate(BaseModel):
    blocks_shifts: bool


class HolidayOut(BaseModel):
    date: str
    name: str
    type: HolidayType
    blocks_shifts: bool


class HolidayDeleteOut(BaseModel):
    """El DELETE responde con la fecha eliminada en el cuerpo, no 204: el cliente
    del portal parsea el cuerpo de toda respuesta (spec 009, plan.md sección 1)."""

    date: str


class HolidayImportOut(BaseModel):
    imported: list[HolidayOut]
    skipped_dates: list[str]
