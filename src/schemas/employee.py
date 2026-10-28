from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EmployeePosition = Literal["recursos_humanos", "lider", "practicante"]


class EmployeeCreate(BaseModel):
    full_name: str
    position: EmployeePosition
    area_id: str
    status_id: str


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    position: EmployeePosition | None = None
    area_id: str | None = None


class EmployeeStatusUpdate(BaseModel):
    status_id: str


class EmployeeOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(validation_alias="_id")
    full_name: str = Field(validation_alias="nombre_completo")
    position: str = Field(validation_alias="cargo")
    area: str
    area_name: str
    status_name: str
    is_active: bool = Field(validation_alias="activo")
    created_by: str | None = Field(default=None, validation_alias="creado_por")
    created_at: datetime = Field(validation_alias="creado_en")
    updated_by: str | None = Field(default=None, validation_alias="actualizado_por")
    updated_at: datetime | None = Field(default=None, validation_alias="actualizado_en")
    status_updated_at: datetime | None = Field(default=None, validation_alias="estado_actualizado_en")
    status_updated_by: str | None = Field(default=None, validation_alias="estado_actualizado_por")

    @field_validator(
        "id", "created_by", "updated_by", "status_updated_by", mode="before"
    )
    @classmethod
    def stringify_object_id(cls, value: object) -> object:
        return str(value) if value is not None else value
