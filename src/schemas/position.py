from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PositionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class PositionUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class PositionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(validation_alias="_id")
    name: str
    is_enabled: bool
    created_at: datetime
    created_by: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None

    @field_validator("id", "created_by", "updated_by", mode="before")
    @classmethod
    def stringify_object_id(cls, value: object) -> object:
        return str(value) if value is not None else value


class PositionDisableOut(BaseModel):
    """Sin `affected_employees`: el Cargo del empleado sigue siendo la lista fija de
    la spec 002, así que no hay empleados que contar y devolver 0 sería mentir
    (spec 009, plan.md decisión 2)."""

    position: PositionOut
