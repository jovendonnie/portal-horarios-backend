from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    full_name: str
    email: str
    role: Literal["gestion_humana", "lider"]


class UserRoleUpdate(BaseModel):
    role: Literal["gestion_humana", "lider"]


class UserOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(validation_alias="_id")
    full_name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    created_by: str | None = None

    @field_validator("id", "created_by", mode="before")
    @classmethod
    def stringify_object_id(cls, value: object) -> object:
        return str(value) if value is not None else value
