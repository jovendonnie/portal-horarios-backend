from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EstadoCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class EstadoUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class EstadoOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    name: str
    is_enabled: bool
    is_predefined: bool = False
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
