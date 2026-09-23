from pydantic import BaseModel


class DaySchedule(BaseModel):

    entrada: str
    salida: str
    estado: str


class SchuleModel(BaseModel):

    importacion_id: str
    usuario_id: str

    lunes: DaySchedule
    martes: DaySchedule
    miercoles: DaySchedule
    jueves: DaySchedule
    viernes: DaySchedule