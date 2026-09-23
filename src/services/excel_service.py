import pandas as pd

from io import BytesIO
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.repositories.employees_repository import EmployeesRepository
from src.repositories.schedule_repository import ScheduleRepository
from src.repositories.importation_repository import ImportacionRepository
from src.repositories.old_schedule_repository import OldScheduleRepository
from src.repositories.old_employee_repository import OldEmployeeRepository
from src.services.excel_validator import ExcelValidator


class ExcelService:

    def __init__(self, db: AsyncIOMotorDatabase):
        self.employees_repository = EmployeesRepository(db)
        self.schedule_repository = ScheduleRepository(db)
        self.importacion_repository = ImportacionRepository(db)
        self.old_schedule_repository = OldScheduleRepository(db)
        self.old_employee_repository = OldEmployeeRepository(db)

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
        # LEER EXCEL
        # ==========================

        try:

            empleados = pd.read_excel(
                excel,
                sheet_name="empleados",
                skiprows=2
            )

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
        # FECHA DE LA IMPORTACIÓN
        # ==========================

        fecha_actual = datetime.now()

        # ==========================
        # OBTENER EMPLEADOS DEL NUEVO EXCEL
        # ==========================

        empleados_excel = set()

        for _, employee in empleados.iterrows():

            correo = str(
                employee["Correo electronico"]
            ).strip()

            empleados_excel.add(correo)

        # ==========================
        # DETECTAR EMPLEADOS QUE YA NO ESTÁN
        # ==========================

        empleados_actuales = await self.employees_repository.obtener_todos()

        for empleado_actual in empleados_actuales:

            correo_actual = empleado_actual.get(
                "correo_electronico"
            )

            if not correo_actual:
                continue

            if correo_actual not in empleados_excel:

                empleado_antiguo = empleado_actual.copy()

                # Mongo creará un nuevo _id
                empleado_antiguo.pop("_id", None)

                # Evitar duplicados en empleados_antiguos
                existe = await self.old_employee_repository.existe(
                    correo_electronico=correo_actual
                )

                if not existe:

                    empleado_antiguo["fecha"] = fecha_actual

                    await self.old_employee_repository.guardar(
                        empleado_antiguo
                    )

                # Marcar empleado como inactivo
                await self.employees_repository.desactivar(
                    correo_electronico=correo_actual
                )

        # ==========================
        # GUARDAR HORARIOS ACTUALES
        # COMO UN ÚNICO HORARIO ANTIGUO
        # ==========================

        horarios_actuales = await self.schedule_repository.obtener_todos()

        if horarios_actuales:

            horarios_antiguos = []

            for horario in horarios_actuales:

                horario_antiguo = horario.copy()

                # Mongo creará un nuevo _id
                horario_antiguo.pop("_id", None)

                horarios_antiguos.append(
                    horario_antiguo
                )

            # La importación anterior está dentro
            # de los horarios actuales
            importacion_anterior = horarios_antiguos[0].get(
                "importacion_id"
            )

            await self.old_schedule_repository.guardar(
                importacion_id=importacion_anterior,
                fecha=fecha_actual,
                horarios=horarios_antiguos
            )

        # ==========================
        # ELIMINAR HORARIOS ACTUALES
        # ==========================

        await self.schedule_repository.eliminar_todos()

        # ==========================
        # CERRAR IMPORTACIÓN VIGENTE
        # ==========================

        await self.importacion_repository.cerrar_vigente(
            hasta=fecha_actual
        )

        # ==========================
        # CREAR NUEVA IMPORTACIÓN
        # ==========================

        importacion = await self.importacion_repository.crear(
            fecha_subida=fecha_actual,
            nombre_archivo=nombre_archivo,
            desde=fecha_actual
        )

        importacion_id = str(
            importacion["_id"]
        )

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
        # GUARDAR HORARIOS ACTUALES
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

                "importacion_id": importacion_id,

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
                importacion_id=importacion_id,
                usuario_id=usuario_id,
                horario=horario
            )

            horarios_procesados += 1

        # ==========================
        # RESPUESTA
        # ==========================

        return {
            "valido": True,
            "importacion_id": importacion_id,
            "fecha_subida": fecha_actual,
            "vigente": True,
            "empleados": len(employee_ids),
            "horarios": horarios_procesados
        }

    # ==========================
    # OBTENER HORARIO ACTUAL
    # ==========================

    async def get_current_schedule(self):

        horarios = await self.schedule_repository.obtener_todos()

        resultado = []

        for horario in horarios:

            usuario_id = horario.get(
                "usuario_id"
            )

            usuario = await self.employees_repository.collection.find_one(
                {
                    "_id": usuario_id
                }
            )

            if not usuario:
                continue

            resultado.append({

                "usuario_id": str(
                    usuario_id
                ),

                "nombre_completo": usuario.get(
                    "nombre_completo"
                ),

                "area": usuario.get(
                    "area"
                ),

                "cargo": usuario.get(
                    "cargo"
                ),

                "correo_electronico": usuario.get(
                    "correo_electronico"
                ),

                "lunes": horario.get(
                    "lunes"
                ),

                "martes": horario.get(
                    "martes"
                ),

                "miercoles": horario.get(
                    "miercoles"
                ),

                "jueves": horario.get(
                    "jueves"
                ),

                "viernes": horario.get(
                    "viernes"
                )
            })

        return {
            "vigente": True,
            "total": len(resultado),
            "horarios": resultado
        }
