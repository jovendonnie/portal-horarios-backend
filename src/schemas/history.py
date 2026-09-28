from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EntityType = Literal["employee", "area", "status", "user", "login"]


class HistoryChange(BaseModel):
    field: str
    old_value: Any
    new_value: Any


class HistoryEntryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    entity_type: EntityType
    entity_id: str | None = None
    action: str
    actor_id: str | None = None
    actor_name: str
    changes: list[HistoryChange]
    occurred_at: datetime

    @field_validator("id", "entity_id", "actor_id", mode="before")
    @classmethod
    def stringify_object_id(cls, value: object) -> object:
        return str(value) if value is not None else value


class HistoryQuery(BaseModel):
    entity_type: EntityType | None = None
    entity_id: str | None = None
    actor_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
