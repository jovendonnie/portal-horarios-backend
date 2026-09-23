from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmployeeCreate(BaseModel):
    full_name: str
    position: Literal["recursos_humanos", "lider"]
    area: str


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    position: Literal["recursos_humanos", "lider"] | None = None
    area: str | None = None


class EmployeeOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    full_name: str = Field(alias="nombre_completo")
    position: str = Field(alias="cargo")
    area: str
    is_active: bool = Field(alias="activo")
    created_by: str | None = Field(default=None, alias="creado_por")
    created_at: datetime = Field(alias="creado_en")
    updated_by: str | None = Field(default=None, alias="actualizado_por")
    updated_at: datetime | None = Field(default=None, alias="actualizado_en")

    @field_validator("id", "created_by", "updated_by", mode="before")
    @classmethod
    def stringify_object_id(cls, value: object) -> object:
        return str(value) if value is not None else value
