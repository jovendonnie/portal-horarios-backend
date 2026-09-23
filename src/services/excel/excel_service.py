from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase


from src.repositories.importation_repository import ImportacionRepository

from src.services.excel.excel_reader import ExcelReader
from src.services.excel.excel_employees import ExcelEmployees
from src.services.excel.excel_schedules import ExcelSchedules

from src.services.excel.excel_validator import ExcelValidator


class ExcelService:

    def __init__(self, db: AsyncIOMotorDatabase):

        self.importacion_repository = ImportacionRepository(db)

        self.excel_reader = ExcelReader()

        self.excel_employees = ExcelEmployees(db)

        self.excel_schedules = ExcelSchedules(db)

    # ==========================
    # IMPORTAR EXCEL
    # ==========================

    async def import_excel(self, archivo):

        # ==========================
        # LEER Y VALIDAR ARCHIVO
        # ==========================

        resultado_archivo = await self.excel_reader.leer_archivo(
            archivo
        )

        if not resultado_archivo["valido"]:

            return resultado_archivo

        nombre_archivo = resultado_archivo["nombre_archivo"]

        excel = resultado_archivo["excel"]

        archivo_excel = resultado_archivo["archivo_excel"]

        # ==========================
        # VALIDAR HOJAS
        # ==========================

        resultado_hojas = self.excel_reader.validar_hojas(
            archivo_excel
        )

        if not resultado_hojas["valido"]:

            return resultado_hojas

        # ==========================
        # LEER EXCEL
        # ==========================

        resultado_lectura = self.excel_reader.leer_hojas(
            excel
        )

        if not resultado_lectura["valido"]:

            return resultado_lectura

        empleados = resultado_lectura["empleados"]

        horarios = resultado_lectura["horarios"]

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

        empleados_excel = self.excel_employees.obtener_empleados_excel(
            empleados
        )

        # ==========================
        # DETECTAR EMPLEADOS QUE YA NO ESTÁN
        # ==========================

        await self.excel_employees.detectar_empleados_que_ya_no_estan(
            empleados_excel=empleados_excel,
            fecha_actual=fecha_actual
        )

        # ==========================
        # GUARDAR HORARIOS ACTUALES
        # COMO UN ÚNICO HORARIO ANTIGUO
        # ==========================

        await self.excel_schedules.guardar_horarios_antiguos(
            fecha_actual=fecha_actual
        )

        # ==========================
        # ELIMINAR HORARIOS ACTUALES
        # ==========================

        await self.excel_schedules.eliminar_horarios_actuales()

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

        employee_ids = await self.excel_employees.guardar_empleados(
            empleados
        )

        # ==========================
        # GUARDAR HORARIOS ACTUALES
        # ==========================

        horarios_procesados = await self.excel_schedules.guardar_horarios(
            horarios=horarios,
            employee_ids=employee_ids,
            importacion_id=importacion_id
        )

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