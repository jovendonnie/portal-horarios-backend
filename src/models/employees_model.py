from pydantic import BaseModel


class EmployeeModel(BaseModel):

    nombre_completo: str
    area: str
    cargo: str
    correo_electronico: str
    activo: bool = True