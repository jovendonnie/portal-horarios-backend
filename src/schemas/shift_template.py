from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.schemas.schedule import TimeRangeIn, TimeRangeOut, Weekday


class ShiftTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    blocks: list[TimeRangeIn] = Field(min_length=1)
    weekdays: list[Weekday] = Field(min_length=1)

    @model_validator(mode="after")
    def check_weekdays_and_blocks(self) -> "ShiftTemplateCreate":
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("No se puede repetir el mismo día en una plantilla")

        # Jornada partida: los bloques no pueden solaparse entre sí. Se comparan
        # ordenados por hora de inicio; `TimeRangeIn` ya garantizó start < end en
        # cada bloque por separado, y el formato "HH:mm" se ordena como texto.
        ordenados = sorted(self.blocks, key=lambda block: block.start)
        for anterior, siguiente in zip(ordenados, ordenados[1:]):
            if siguiente.start < anterior.end:
                raise ValueError("Los bloques de horario no pueden solaparse entre sí")
        return self


class ShiftTemplateUpdate(ShiftTemplateCreate):
    pass


class ShiftTemplateOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(validation_alias="_id")
    name: str
    blocks: list[TimeRangeOut]
    weekdays: list[Weekday]
    created_at: datetime
    created_by: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None

    @field_validator("id", "created_by", "updated_by", mode="before")
    @classmethod
    def stringify_object_id(cls, value: object) -> object:
        return str(value) if value is not None else value
