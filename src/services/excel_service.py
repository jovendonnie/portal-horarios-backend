import pandas as pd

from io import BytesIO

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.repositories.employees_repository import EmployeesRepository
from src.repositories.schedule_repository import ScheduleRepository
from src.services.excel_validator import ExcelValidator


class ExcelService:

    def __init__(self, db: AsyncIOMotorDatabase):
        self.employees_repository = EmployeesRepository(db)
        self.schedule_repository = ScheduleRepository(db)

    async def import_excel(self, archivo):

        # ==========================
        # VALIDAR ARCHIVO VACÍO
        # ==========================

        contenido = await archivo.read()

        if not contenido:
            return {
                "valido": False,
                "errores": [
                    {
                        "error": "El archivo está vacío."
                    }
                ]
            }

        # ==========================
        # VALIDAR EXTENSIÓN
        # ==========================

        nombre_archivo = archivo.filename or ""

        if not nombre_archivo.lower().endswith(".xlsx"):
            return {
                "valido": False,
                "errores": [
                    {
                        "error": "El archivo debe ser un Excel con formato .xlsx."
                    }
                ]
            }

        # ==========================
        # ABRIR EXCEL
        # ==========================

        excel = BytesIO(contenido)

        try:

            archivo_excel = pd.ExcelFile(excel)

        except Exception:

            return {
                "valido": False,
                "errores": [
                    {
                        "error": "El archivo no es un Excel válido o está dañado."
                    }
                ]
            }

        # ==========================
        # VALIDAR HOJAS
        # ==========================

        hojas_requeridas = [
            "empleados",
            "horarios"
        ]

        errores_hojas = []

        for hoja in hojas_requeridas:

            if hoja not in archivo_excel.sheet_names:

                errores_hojas.append({
                    "hoja": hoja,
                    "error": "Falta esta hoja en el Excel."
                })

        if errores_hojas:

            return {
                "valido": False,
                "errores": errores_hojas
            }

        # ==========================
        # LEER EMPLEADOS
        # ==========================

        try:

            empleados = pd.read_excel(
                excel,
                sheet_name="empleados",
                skiprows=2
            )

            # ==========================
            # LEER HORARIOS
            # ==========================

            horarios = pd.read_excel(
                excel,
                sheet_name="horarios",
                skiprows=2
            )

        except Exception as error:

            return {
                "valido": False,
                "errores": [
                    {
                        "error": "No fue posible leer correctamente el contenido del Excel.",
                        "detalle": str(error)
                    }
                ]
            }

        # ==========================
        # VALIDAR EXCEL
        # ==========================

        errores = ExcelValidator.validate(
            empleados,
            horarios
        )

        # ==========================
        # SI HAY ERRORES
        # NO GUARDAR NADA
        # ==========================

        if errores:

            return {
                "valido": False,
                "errores": errores
            }

        # ==========================
        # GUARDAR EMPLEADOS
        # ==========================

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

            correo = str(
                employee["Correo electronico"]
            ).strip()

            usuario = await self.employees_repository.create_or_update(
                nombre_completo=nombre,
                area=area,
                cargo=cargo,
                correo_electronico=correo
            )

            employee_ids[nombre] = usuario["_id"]

        # ==========================
        # GUARDAR HORARIOS
        # ==========================

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
                    "entrada": str(
                        schedule["Lunes entrada"]
                    ),
                    "salida": str(
                        schedule["lunes salida"]
                    ),
                    "estado": str(
                        schedule["Lunes estado"]
                    )
                },

                "martes": {
                    "entrada": str(
                        schedule["Martes entrada"]
                    ),
                    "salida": str(
                        schedule["Martes salida"]
                    ),
                    "estado": str(
                        schedule["Martes estado"]
                    )
                },

                "miercoles": {
                    "entrada": str(
                        schedule["Miercoles entrada"]
                    ),
                    "salida": str(
                        schedule["Miercoles salida"]
                    ),
                    "estado": str(
                        schedule["Miercoles estado"]
                    )
                },

                "jueves": {
                    "entrada": str(
                        schedule["Jueves entrada"]
                    ),
                    "salida": str(
                        schedule["Jueves salida"]
                    ),
                    "estado": str(
                        schedule["Jueves estado"]
                    )
                },

                "viernes": {
                    "entrada": str(
                        schedule["Viernes entrada"]
                    ),
                    "salida": str(
                        schedule["Viernes salida"]
                    ),
                    "estado": str(
                        schedule["Viernes estado"]
                    )
                }
            }

            await self.schedule_repository.create_or_update(
                usuario_id=usuario_id,
                horario=horario
            )

            horarios_procesados += 1

        # ==========================
        # RESPUESTA
        # ==========================

        return {
            "valido": True,
            "empleados": len(employee_ids),
            "horarios": horarios_procesados
        }