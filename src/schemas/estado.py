from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EstadoCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # Un Estado nuevo no bloquea turnos salvo que se diga lo contrario: lo normal
    # es que represente una modalidad de trabajo, no una ausencia (spec 009, RF-5).
    blocks_shifts: bool = False


class EstadoUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class EstadoBlocksShiftsUpdate(BaseModel):
    blocks_shifts: bool


class EstadoOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(validation_alias="_id")
    name: str
    is_enabled: bool
    is_predefined: bool = False
    # Default False para los Estados creados antes de la spec 009, que no tienen
    # la clave en Mongo: se leen sin migración previa (RNF-6).
    blocks_shifts: bool = False
    created_at: datetime
    created_by: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None

    @field_validator("id", "created_by", "updated_by", mode="before")
    @classmethod
    def stringify_object_id(cls, value: object) -> object:
        return str(value) if value is not None else value


class EstadoDisableOut(BaseModel):
    status: EstadoOut
    affected_employees: int
