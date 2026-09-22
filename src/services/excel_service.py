import pandas as pd

from io import BytesIO

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.repositories.employees_repository import EmployeesRepository
from src.repositories.schedule_repository import ScheduleRepository


class ExcelService:

    def __init__(self, db: AsyncIOMotorDatabase):
        self.employees_repository = EmployeesRepository(db)
        self.schedule_repository = ScheduleRepository(db)

    async def import_excel(self, archivo):
        contenido = await archivo.read()

        excel = BytesIO(contenido)

        # ==========================
        # LEER EMPLEADOS
        # ==========================

        empleados = pd.read_excel(
            excel,
            sheet_name="empleados",
            skiprows=2,
            usecols="B:D"
        )

        employee_ids = {}

        for _, employee in empleados.iterrows():

            nombre = str(
                employee["Nombre completo"]
            ).strip()

            area = str(
                employee["Area"]
            ).strip()

            cargo = str(
                employee["Cargo"]
            ).strip()

            usuario = await self.employees_repository.create_or_update(
                nombre_completo=nombre,
                area=area,
                cargo=cargo
            )

            employee_ids[nombre] = usuario["_id"]

        # ==========================
        # LEER HORARIOS
        # ==========================

        horarios = pd.read_excel(
            excel,
            sheet_name="horarios",
            skiprows=2,
            usecols="B:Q"
        )

        horarios_procesados = 0

        for _, schedule in horarios.iterrows():

            nombre = str(
                schedule["Nombre completo"]
            ).strip()

            usuario_id = employee_ids.get(nombre)

            if not usuario_id:
                continue

            horario = {
                "usuario_id": usuario_id,

                "lunes": {
                    "entrada": str(schedule["Lunes entrada"]),
                    "salida": str(schedule["lunes salida"]),
                    "estado": str(schedule["Estado"])
                },

                "martes": {
                    "entrada": str(schedule["Martes entrada"]),
                    "salida": str(schedule["Martes salida"]),
                    "estado": str(schedule["Estado.1"])
                },

                "miercoles": {
                    "entrada": str(schedule["Miercoles entrada"]),
                    "salida": str(schedule["Miercoles salida"]),
                    "estado": str(schedule["Estado.2"])
                },

                "jueves": {
                    "entrada": str(schedule["Jueves entrada"]),
                    "salida": str(schedule["Jueves salida"]),
                    "estado": str(schedule["Estado.3"])
                },

                "viernes": {
                    "entrada": str(schedule["Viernes entrada"]),
                    "salida": str(schedule["Viernes salida"]),
                    "estado": str(schedule["Estado.4"])
                }
            }

            await self.schedule_repository.create_or_update(
                usuario_id=usuario_id,
                horario=horario
            )

            horarios_procesados += 1

        return {
            "empleados": len(employee_ids),
            "horarios": horarios_procesados
        }
    