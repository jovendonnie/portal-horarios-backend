from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ImportacionExcelModel(BaseModel):

    fecha_subida: datetime
    nombre_archivo: str
    desde: datetime
    hasta: Optional[datetime] = None
    vigente: bool = True